"""Per-field comparison between extracted and expected label values.

Strictness rules vary by field — see decision #6 in
docs/architecture-decisions.md:

  - Government Warning: strict (exact text, all-caps, bold)
  - Brand / producer / class-type: normalized fuzzy match
  - ABV: numeric tolerance (±0.1%)
  - Net contents: unit-aware comparison
  - Country of origin: normalized exact match

`reason` strings are deliberately human-readable. They surface in the
bench report and will eventually surface in the agent-facing UI so a
reviewer can confirm the AI's decision in a couple of seconds
(per interview-highlights.md — Dave's "don't make my life harder" bar).
"""

from __future__ import annotations

from pipeline.normalize import (
    apply_consistency_rules,
    expand_state_abbrev,
    fuzzy_ratio,
    norm_text,
    normalize_warning_text,
    parse_net_contents,
    strip_country_suffix,
)

FUZZY_THRESHOLD = 85.0
ABV_TOLERANCE = 0.1
NET_CONTENTS_ML_TOLERANCE = 0.5

SCORED_FIELDS = (
    "brand",
    "class_type",
    "alcohol_content",
    "net_contents",
    "producer_name",
    "producer_address",
    "is_imported",
    "country_of_origin",
)

# Canonical TTB Government Warning text (27 CFR 16.21). Stored verbatim;
# the comparator collapses internal whitespace on both sides before equality
# check but requires the literal "GOVERNMENT WARNING:" prefix.
CANONICAL_WARNING = (
    "GOVERNMENT WARNING: (1) According to the Surgeon General, women should "
    "not drink alcoholic beverages during pregnancy because of the risk of "
    "birth defects. (2) Consumption of alcoholic beverages impairs your "
    "ability to drive a car or operate machinery, and may cause health "
    "problems."
)


def compare(extracted: dict, expected: dict) -> dict:
    """Compare extracted fields against expected values.

    Returns a per-field dict of the form::

        {
          "<field>": {
            "matched": bool,
            "extracted": <value>,
            "expected": <value>,
            "reason": "<short human-readable explanation>",
          },
          ...
          "government_warning_text": {...},
        }

    Includes all 8 scored fields plus `government_warning_text`.
    """
    extracted = apply_consistency_rules(extracted)

    out: dict[str, dict] = {}
    out["brand"] = _fuzzy_text_field(extracted.get("brand"), expected.get("brand"))
    out["class_type"] = _fuzzy_text_field(
        extracted.get("class_type"), expected.get("class_type")
    )
    out["alcohol_content"] = _abv_field(
        extracted.get("alcohol_content"), expected.get("alcohol_content")
    )
    out["net_contents"] = _net_contents_field(
        extracted.get("net_contents"), expected.get("net_contents")
    )
    out["producer_name"] = _fuzzy_text_field(
        extracted.get("producer_name"), expected.get("producer_name")
    )
    out["producer_address"] = _address_field(
        extracted.get("producer_address"), expected.get("producer_address")
    )
    out["is_imported"], out["country_of_origin"] = _import_pair(
        extracted.get("is_imported"),
        extracted.get("country_of_origin"),
        expected.get("is_imported"),
        expected.get("country_of_origin"),
    )
    out["government_warning_text"] = _warning_field(
        extracted.get("government_warning_text"),
        extracted.get("government_warning_bold"),
    )
    return out


# ---------- field rules ----------


def _fuzzy_text_field(extracted, expected) -> dict:
    if extracted is None and expected is None:
        return _entry(True, extracted, expected, "both null")
    if extracted is None or expected is None:
        return _entry(False, extracted, expected, "missing value on one side")
    a, b = norm_text(extracted), norm_text(expected)
    if a == b:
        return _entry(True, extracted, expected, "exact match after normalize")
    score = fuzzy_ratio(a, b)
    matched = score >= FUZZY_THRESHOLD
    reason = (
        f"fuzzy match ({score:.1f})"
        if matched
        else f"below fuzzy threshold ({score:.1f} < {FUZZY_THRESHOLD})"
    )
    return _entry(matched, extracted, expected, reason)


def _address_field(extracted, expected) -> dict:
    if extracted is None and expected is None:
        return _entry(True, extracted, expected, "both null")
    if extracted is None or expected is None:
        return _entry(False, extracted, expected, "missing value on one side")
    a = strip_country_suffix(expand_state_abbrev(norm_text(extracted)))
    b = strip_country_suffix(expand_state_abbrev(norm_text(expected)))
    if a == b:
        return _entry(True, extracted, expected, "exact match after state/country normalize")
    score = fuzzy_ratio(a, b)
    matched = score >= FUZZY_THRESHOLD
    reason = (
        f"fuzzy match ({score:.1f}) after state/country normalize"
        if matched
        else f"below fuzzy threshold ({score:.1f} < {FUZZY_THRESHOLD})"
    )
    return _entry(matched, extracted, expected, reason)


def _abv_field(extracted, expected) -> dict:
    if extracted is None and expected is None:
        return _entry(True, extracted, expected, "both null")
    if extracted is None or expected is None:
        return _entry(False, extracted, expected, "missing value on one side")
    try:
        a, b = float(extracted), float(expected)
    except (TypeError, ValueError):
        return _entry(False, extracted, expected, "non-numeric value")
    diff = abs(a - b)
    matched = diff <= ABV_TOLERANCE
    reason = (
        f"within ±{ABV_TOLERANCE}% tolerance (Δ {diff:.2f})"
        if matched
        else f"outside ±{ABV_TOLERANCE}% tolerance (Δ {diff:.2f})"
    )
    return _entry(matched, extracted, expected, reason)


def _net_contents_field(extracted, expected) -> dict:
    if extracted is None and expected is None:
        return _entry(True, extracted, expected, "both null")
    if extracted is None or expected is None:
        return _entry(False, extracted, expected, "missing value on one side")
    a_ml = parse_net_contents(extracted)
    b_ml = parse_net_contents(expected)
    if a_ml is not None and b_ml is not None:
        diff = abs(a_ml - b_ml)
        matched = diff <= NET_CONTENTS_ML_TOLERANCE
        reason = (
            f"equal after unit conversion ({a_ml:g} mL vs {b_ml:g} mL)"
            if matched
            else f"volume mismatch ({a_ml:g} mL vs {b_ml:g} mL)"
        )
        return _entry(matched, extracted, expected, reason)
    # Fallback: one side unparseable — try fuzzy on normalized text.
    score = fuzzy_ratio(norm_text(extracted), norm_text(expected))
    matched = score >= FUZZY_THRESHOLD
    reason = (
        f"unparseable units; fuzzy match ({score:.1f})"
        if matched
        else f"unparseable units; below threshold ({score:.1f})"
    )
    return _entry(matched, extracted, expected, reason)


def _import_pair(ext_imp, ext_country, exp_imp, exp_country) -> tuple[dict, dict]:
    if ext_imp == exp_imp:
        imp_entry = _entry(True, ext_imp, exp_imp, "exact match")
    else:
        imp_entry = _entry(False, ext_imp, exp_imp, "boolean mismatch")

    # Country rule: required only when imported on either side.
    imported_anywhere = bool(ext_imp) or bool(exp_imp)
    if not imported_anywhere:
        # Domestic on both sides — country may or may not be present.
        # Accept any combination as long as nothing actively disagrees.
        if ext_country is None and exp_country is None:
            country_entry = _entry(True, ext_country, exp_country, "both null (domestic)")
        elif exp_country is None:
            # Expected says no country, extracted printed one (e.g., "USA").
            # Per the project spec this is acceptable: domestic bottles
            # legitimately print "USA". Treat as a soft pass.
            country_entry = _entry(
                True, ext_country, exp_country,
                "extracted country tolerated on domestic bottle",
            )
        else:
            country_entry = _country_match(ext_country, exp_country)
    else:
        if ext_country is None or exp_country is None:
            country_entry = _entry(
                False, ext_country, exp_country,
                "country_of_origin required when is_imported is true",
            )
        else:
            country_entry = _country_match(ext_country, exp_country)
    return imp_entry, country_entry


def _country_match(extracted, expected) -> dict:
    a, b = norm_text(extracted), norm_text(expected)
    matched = a == b
    return _entry(
        matched, extracted, expected,
        "exact match after normalize" if matched else "country mismatch",
    )


def _warning_field(extracted, bold) -> dict:
    """Near-exact comparison against the canonical TTB Government Warning.

    Three sub-checks per 27 CFR 16.21 and Jenny's interview:
      1. Prefix "GOVERNMENT WARNING:" appears verbatim, case-sensitive
         (she rejected a submission for title-casing it).
      2. Body text matches the canonical wording (case-insensitive,
         since the regulation fixes the *text* — labels print it in caps
         but our canonical string is the regulatory string).
      3. Header is printed in bold. ``bold=True`` passes; ``False`` fails;
         ``None`` is treated as "unknown" and does not fail the check
         (older cached extractions predate the bold field).

    Commas, periods, parens, and clause ordering are preserved by
    `normalize_warning_text` so real label deviations still surface.
    """
    if extracted is None:
        return _entry(False, None, CANONICAL_WARNING, "warning text missing")
    norm = normalize_warning_text(extracted)
    if not norm.startswith("GOVERNMENT WARNING:"):
        return _entry(
            False, extracted, CANONICAL_WARNING,
            "must begin with 'GOVERNMENT WARNING:' in all caps",
        )
    canonical = normalize_warning_text(CANONICAL_WARNING)
    text_ok = norm.casefold() == canonical.casefold()
    if not text_ok:
        return _entry(
            False, extracted, CANONICAL_WARNING,
            "text differs from TTB canonical warning",
        )
    if bold is False:
        return _entry(
            False, extracted, CANONICAL_WARNING,
            "text matches but warning header is not bold",
        )
    bold_note = "bold confirmed" if bold is True else "bold unverified"
    return _entry(
        True, extracted, CANONICAL_WARNING,
        f"exact match to TTB canonical ({bold_note})",
    )


# ---------- helpers ----------


def _entry(matched: bool, extracted, expected, reason: str) -> dict:
    return {
        "matched": matched,
        "extracted": extracted,
        "expected": expected,
        "reason": reason,
    }
