"""Text-normalization primitives for the comparator and (future) UI.

Two distinct concerns live here:

1. **Comparison normalization** — destructive (lowercase, drop punctuation,
   expand state abbreviations). Used only inside compare.py to decide
   whether two values are equivalent; the normalized form is never shown.

2. **Presentation cleaning** — non-destructive (case-aware title-casing of
   ALL-CAPS strings, whitespace collapse, trailing-period stripping).
   Reserved for the eventual API/UI serialization step, exposed here as
   `clean_for_display` so extract.py stays a faithful record of raw LLM
   output.

A small `apply_consistency_rules` helper sits between extraction and
comparison: it clears `country_of_origin` when the model couldn't decide
whether the bottle was imported (is_imported is None). It deliberately does
NOT clear country when is_imported is False — domestic bottles legitimately
print "USA" on the label (Maker's Mark, Tito's, Woodford Reserve).
"""

from __future__ import annotations

import re

from rapidfuzz import fuzz

# Two-way state map: abbreviations and full names both expand to a single
# canonical form (lowercased full name) so "TX" and "Texas" both collapse to
# "texas" inside norm_text.
_STATES: dict[str, str] = {
    "alabama": "alabama",
    "al": "alabama",
    "alaska": "alaska",
    "ak": "alaska",
    "arizona": "arizona",
    "az": "arizona",
    "arkansas": "arkansas",
    "ar": "arkansas",
    "california": "california",
    "ca": "california",
    "colorado": "colorado",
    "co": "colorado",
    "connecticut": "connecticut",
    "ct": "connecticut",
    "delaware": "delaware",
    "de": "delaware",
    "florida": "florida",
    "fl": "florida",
    "georgia": "georgia",
    "ga": "georgia",
    "hawaii": "hawaii",
    "hi": "hawaii",
    "idaho": "idaho",
    "id": "idaho",
    "illinois": "illinois",
    "il": "illinois",
    "indiana": "indiana",
    "in": "indiana",
    "iowa": "iowa",
    "ia": "iowa",
    "kansas": "kansas",
    "ks": "kansas",
    "kentucky": "kentucky",
    "ky": "kentucky",
    "louisiana": "louisiana",
    "la": "louisiana",
    "maine": "maine",
    "me": "maine",
    "maryland": "maryland",
    "md": "maryland",
    "massachusetts": "massachusetts",
    "ma": "massachusetts",
    "michigan": "michigan",
    "mi": "michigan",
    "minnesota": "minnesota",
    "mn": "minnesota",
    "mississippi": "mississippi",
    "ms": "mississippi",
    "missouri": "missouri",
    "mo": "missouri",
    "montana": "montana",
    "mt": "montana",
    "nebraska": "nebraska",
    "ne": "nebraska",
    "nevada": "nevada",
    "nv": "nevada",
    "new hampshire": "new hampshire",
    "nh": "new hampshire",
    "new jersey": "new jersey",
    "nj": "new jersey",
    "new mexico": "new mexico",
    "nm": "new mexico",
    "new york": "new york",
    "ny": "new york",
    "north carolina": "north carolina",
    "nc": "north carolina",
    "north dakota": "north dakota",
    "nd": "north dakota",
    "ohio": "ohio",
    "oh": "ohio",
    "oklahoma": "oklahoma",
    "ok": "oklahoma",
    "oregon": "oregon",
    "or": "oregon",
    "pennsylvania": "pennsylvania",
    "pa": "pennsylvania",
    "rhode island": "rhode island",
    "ri": "rhode island",
    "south carolina": "south carolina",
    "sc": "south carolina",
    "south dakota": "south dakota",
    "sd": "south dakota",
    "tennessee": "tennessee",
    "tn": "tennessee",
    "texas": "texas",
    "tx": "texas",
    "utah": "utah",
    "ut": "utah",
    "vermont": "vermont",
    "vt": "vermont",
    "virginia": "virginia",
    "va": "virginia",
    "washington": "washington",
    "wa": "washington",
    "west virginia": "west virginia",
    "wv": "west virginia",
    "wisconsin": "wisconsin",
    "wi": "wisconsin",
    "wyoming": "wyoming",
    "wy": "wyoming",
}

_COUNTRY_SUFFIXES = (
    "u.s.a.",
    "u.s.a",
    "usa",
    "united states of america",
    "united states",
    "u.k.",
    "uk",
    "united kingdom",
)

_CORP_SUFFIXES_KEEP_UPPER = {"LLC", "LLP", "LP", "PLC", "PBC", "USA", "UK"}
_CORP_SUFFIXES_TITLE = {"Inc", "Inc.", "Co", "Co.", "Ltd", "Ltd.", "Corp", "Corp."}


def norm_text(s: str | None) -> str:
    """Aggressive normalization for comparison only — never display.

    Lowercases, collapses whitespace, normalizes ``&`` -> ``and``, strips a
    leading "the ", and drops commas plus trailing periods. The output is
    intended to be compared with == or fuzz.ratio, not shown to a human.
    """
    if s is None:
        return ""
    out = s.lower().strip()
    out = out.replace("&", " and ")
    out = out.replace(",", " ")
    out = re.sub(r"\s+", " ", out).strip()
    if out.startswith("the "):
        out = out[4:]
    out = out.rstrip(".")
    return out.strip()


def expand_state_abbrev(s: str) -> str:
    """Replace standalone state tokens (abbrev or full name) with the
    canonical lowercased full name. Input is expected to already be
    lowercased + comma-normalized via norm_text."""
    if not s:
        return s
    # Handle two-word states first so "new york" isn't tokenized into
    # standalone "new" / "york".
    multiword = sorted(
        (k for k in _STATES if " " in k),
        key=len,
        reverse=True,
    )
    for name in multiword:
        if name in s:
            s = s.replace(name, _STATES[name])

    tokens = s.split()
    expanded = []
    for tok in tokens:
        state_key = tok.replace(".", "")
        expanded.append(_STATES.get(state_key, _STATES.get(tok, tok)))
    return " ".join(expanded)


def norm_class_type(s: str | None) -> str:
    """Normalize class/type for comparison.

    Preserves meaningful class terms but drops leading content claims such as
    ``100%`` when the expected value is the regulatory class itself.
    """
    out = norm_text(s)
    out = re.sub(r"\b\d+(?:\.\d+)?\s*%\s*", " ", out)
    return re.sub(r"\s+", " ", out).strip()


_PRODUCER_ROLE_PREFIXES = (
    "distilled aged and bottled by ",
    "distilled and bottled by ",
    "distilled bottled by ",
    "aged and bottled by ",
    "imported by ",
    "bottled by ",
    "distilled by ",
    "produced by ",
    "processed by ",
    "blended by ",
    "made by ",
)


def norm_producer_name(s: str | None) -> str:
    """Normalize producer name for comparison.

    Label text often includes the mandatory role phrase ("Imported by",
    "Distilled & Bottled by"). The expected application value may store just
    the responsible party name, so strip only leading role phrases.
    """
    out = norm_text(s)
    for prefix in _PRODUCER_ROLE_PREFIXES:
        if out.startswith(prefix):
            out = out[len(prefix) :]
            break
    if out.startswith("the "):
        out = out[4:]
    return out.strip()


def strip_country_suffix(s: str) -> str:
    """Drop a trailing country marker from an already-normalized string.

    Used on producer_address so that "versailles kentucky usa" compares
    equal to "versailles kentucky". Country-of-origin info belongs in its
    own field.
    """
    if not s:
        return s
    out = s
    # Try longest match first so "united states of america" wins over "usa".
    for suffix in sorted(_COUNTRY_SUFFIXES, key=len, reverse=True):
        if out.endswith(" " + suffix):
            out = out[: -(len(suffix) + 1)]
            break
        if out == suffix:
            out = ""
            break
    return out.strip()


def normalize_country_origin(s: str | None) -> str:
    """Normalize country-of-origin phrases to a country value for comparison."""
    out = norm_text(s)
    prefixes = (
        "product of ",
        "produced in ",
        "made in ",
        "distilled in ",
        "bottled in ",
        "distilled and bottled in ",
    )
    for prefix in sorted(prefixes, key=len, reverse=True):
        if out.startswith(prefix):
            return out[len(prefix) :].strip()
    return out


def parse_net_contents(s: str | None) -> float | None:
    """Parse a net-contents string into milliliters.

    Accepts "750 mL", "750ML", "0.75 L", "1L", "1.75 L", "375mL", "50 cL".
    Returns the volume in mL as a float, or None if unparseable.
    """
    if s is None:
        return None
    m = re.search(r"(\d+(?:\.\d+)?)\s*(ml|l|cl)\b", s.strip(), re.IGNORECASE)
    if not m:
        return None
    value = float(m.group(1))
    unit = m.group(2).lower()
    if unit == "ml":
        return value
    if unit == "cl":
        return value * 10.0
    return value * 1000.0  # litres


def parse_alcohol_content(value) -> float | None:
    """Parse an alcohol-content extraction into ABV percentage points.

    Accepts numeric values from the older extractor and raw extracted strings
    such as "40% Alc./Vol.", "ALC. 45% BY VOL.", "Alcohol 44% by volume",
    and "48.28 ALC/VOL". Deliberately does not convert proof to ABV; proof-only
    strings return None so extraction/comparison can surface the missing ABV.
    """
    if value is None:
        return None
    if isinstance(value, int | float):
        return float(value)
    if not isinstance(value, str):
        return None

    s = value.strip()
    if not s:
        return None

    percent = r"(\d+(?:\.\d+)?)\s*%"
    alc_words = r"(?:alc\.?|alcohol)"
    vol_words = r"(?:vol\.?|volume)"
    patterns = (
        rf"{alc_words}\s*{percent}.*?(?:by\s*)?{vol_words}",
        rf"{percent}\s*{alc_words}.*?{vol_words}",
        rf"{percent}.*?(?:by\s*)?{vol_words}",
        rf"(\d+(?:\.\d+)?)\s*{alc_words}\s*/?\s*{vol_words}",
    )
    for pattern in patterns:
        m = re.search(pattern, s, re.IGNORECASE)
        if m:
            return float(m.group(1))
    return None


def fuzzy_ratio(a: str, b: str) -> float:
    """Token-sort ratio over rapidfuzz, returning 0..100. Token-sort so
    "william grant and sons inc" matches "sons william grant inc"-style
    reordering as well as straight typos."""
    if not a and not b:
        return 100.0
    return float(fuzz.token_sort_ratio(a, b))


def apply_consistency_rules(extracted: dict) -> dict:
    """Defensive cleanup before comparison.

    Rule: if the model couldn't decide whether the bottle was imported
    (is_imported is None), we don't trust whatever country_of_origin it
    emitted — null it out so the comparator scores it against expected
    cleanly rather than penalizing a guess.

    We deliberately do NOT touch country when is_imported is False:
    Maker's Mark, Tito's, and Woodford Reserve all print "USA" on the
    label legitimately, and clearing it would create false mismatches.
    """
    out = dict(extracted)
    if out.get("is_imported") is None:
        out["country_of_origin"] = None
    return out


# ---------- presentation cleaning (UI-facing, non-destructive) ----------


def _is_all_caps(s: str) -> bool:
    letters = [c for c in s if c.isalpha()]
    return bool(letters) and all(c.isupper() for c in letters)


_SMALL_WORDS = {"of", "and", "the", "in", "by", "for", "to", "a", "an", "de", "la"}


def _smart_title(s: str) -> str:
    """Title-case while preserving small joining words (except first/last)
    and known corporate suffix conventions."""
    tokens = s.split()
    out: list[str] = []
    for i, tok in enumerate(tokens):
        bare = tok.rstrip(".,")
        trail = tok[len(bare) :]
        upper = bare.upper()
        if upper in _CORP_SUFFIXES_KEEP_UPPER:
            out.append(upper + trail)
            continue
        if upper.rstrip(".") in {x.upper().rstrip(".") for x in _CORP_SUFFIXES_TITLE}:
            out.append(bare.capitalize() + trail)
            continue
        # Pure US-state abbreviation? keep upper.
        if len(bare) == 2 and bare.lower() in _STATES and " " not in _STATES[bare.lower()]:
            # Two-letter state abbreviation like "NY" stays upper.
            out.append(bare.upper() + trail)
            continue
        if 0 < i < len(tokens) - 1 and bare.lower() in _SMALL_WORDS:
            out.append(bare.lower() + trail)
            continue
        out.append(bare.capitalize() + trail)
    return " ".join(out)


def normalize_warning_text(s: str) -> str:
    """Conservative cleanup used by the Government Warning comparator.

    The warning is checked for *near-exact* match against the canonical
    27 CFR text — we deliberately preserve commas, periods, and parens so
    real label deviations (missing punctuation, omitted clauses) still
    surface. What we *do* normalize is transport-level noise the model
    inevitably introduces:

      * Line endings: CRLF / CR -> LF
      * Non-breaking space (U+00A0) -> regular space
      * Smart quotes (curly ', ", `, ´) -> straight ASCII quotes
      * Markdown wrappers: ``**bold**`` / ``__bold__`` / ``_em_`` stripped
        (some models, notably Gemini chat, wrap the header in markdown)
      * Line-break hyphenation: ``pregn-\\nancy`` -> ``pregnancy``
      * Newlines -> spaces, then whitespace runs collapsed
    """
    if s is None:
        return ""
    out = s.replace("\r\n", "\n").replace("\r", "\n")
    out = out.replace(" ", " ")
    out = (
        out.replace("‘", "'")
        .replace("’", "'")
        .replace("“", '"')
        .replace("”", '"')
        .replace("`", "'")
        .replace("´", "'")
    )
    out = re.sub(r"\*\*(.+?)\*\*", r"\1", out, flags=re.DOTALL)
    out = re.sub(r"__(.+?)__", r"\1", out, flags=re.DOTALL)
    out = re.sub(r"(?<!_)_([^_\n]+)_(?!_)", r"\1", out)
    # Line-break hyphenation: a hyphen at end of line joined to next word.
    out = re.sub(r"(\w)-\n(\w)", r"\1\2", out)
    out = out.replace("\n", " ")
    out = re.sub(r"\s+", " ", out).strip()
    return out


def clean_for_display(value, field_name: str | None = None):
    """Best-effort presentation cleanup safe to surface to the UI.

    Non-destructive: never collapses information, only fixes formatting.
    Today's behavior is intentionally minimal — this exists as a hook the
    eventual API/UI layer can grow without circling back through compare.
    """
    if value is None or not isinstance(value, str):
        return value
    out = re.sub(r"\s+", " ", value).strip()
    out = out.rstrip(".")
    if _is_all_caps(out):
        out = _smart_title(out)
    return out
