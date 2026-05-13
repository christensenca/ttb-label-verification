"""Field-by-field tests for pipeline.compare.compare()."""

from __future__ import annotations

import pytest

from pipeline.compare import CANONICAL_WARNING, compare

TITLE_CASE_WARNING = (
    "Government Warning: (1) According to the Surgeon General, women should "
    "not drink alcoholic beverages during pregnancy because of the risk of "
    "birth defects. (2) Consumption of alcoholic beverages impairs your "
    "ability to drive a car or operate machinery, and may cause health "
    "problems."
)


def _base():
    """Minimal valid extracted/expected dicts so we can override one field."""
    return {
        "brand": "Don Julio",
        "class_type": "Tequila Blanco",
        "alcohol_content": 40.0,
        "net_contents": "750 mL",
        "producer_name": "Diageo",
        "producer_address": "New York, NY",
        "is_imported": True,
        "country_of_origin": "Mexico",
        "government_warning_text": CANONICAL_WARNING,
        "government_warning_bold": True,
    }


# ---------- brand / class_type / producer_name (fuzzy text) ----------


@pytest.mark.parametrize(
    "extracted, expected, matched",
    [
        ("Don Julio", "Don Julio", True),
        ("DIAGEO", "Diageo", True),
        ("STONE'S THROW", "Stone's Throw", True),
        ("WILLIAM GRANT & SONS, INC.", "William Grant and Sons Inc.", True),
        ("The Maker's Mark Distillery Inc.", "Maker's Mark Distillery Inc.", True),
        ("Hendrick's", "Hendrick's Gin", False),  # true partial extraction
        ("Tito's", "Tito's Handmade Vodka", False),  # true partial extraction
        ("GRAY WHALE", "Gray Whale Gin", False),  # true partial extraction
    ],
)
def test_brand_fuzzy(extracted, expected, matched):
    ext = _base() | {"brand": extracted}
    exp = _base() | {"brand": expected}
    assert compare(ext, exp)["brand"]["matched"] is matched


def test_class_type_partial_fails():
    ext = _base() | {"class_type": "Tequila"}
    exp = _base() | {"class_type": "Tequila Blanco"}
    assert compare(ext, exp)["class_type"]["matched"] is False


def test_class_type_caps_passes():
    ext = _base() | {"class_type": "TEQUILA BLANCO"}
    exp = _base() | {"class_type": "Tequila Blanco"}
    assert compare(ext, exp)["class_type"]["matched"] is True


# ---------- net_contents ----------


@pytest.mark.parametrize(
    "extracted, expected, matched",
    [
        ("750 mL", "750 mL", True),
        ("750ML", "750 mL", True),
        ("750 ml", "750 mL", True),
        ("0.75 L", "750 mL", True),
        ("0.75L", "750 mL", True),
        ("1 L", "1 L", True),
        ("375 mL", "750 mL", False),
        (None, "750 mL", False),
        ("750 mL", None, False),
    ],
)
def test_net_contents(extracted, expected, matched):
    ext = _base() | {"net_contents": extracted}
    exp = _base() | {"net_contents": expected}
    assert compare(ext, exp)["net_contents"]["matched"] is matched


# ---------- alcohol_content ----------


@pytest.mark.parametrize(
    "extracted, expected, matched",
    [
        (40.0, 40.0, True),
        (40.05, 40.0, True),
        (48.28, 48.28, True),
        ("40% Alc./Vol.", 40.0, True),
        ("ALC. 45% BY VOL.", 45.0, True),
        ("Alcohol 44% by volume", 44.0, True),
        ("80 proof", 40.0, False),
        (40.2, 40.0, False),
        (None, 40.0, False),
        (40.0, None, False),
        (None, None, True),
    ],
)
def test_alcohol_content(extracted, expected, matched):
    ext = _base() | {"alcohol_content": extracted}
    exp = _base() | {"alcohol_content": expected}
    assert compare(ext, exp)["alcohol_content"]["matched"] is matched


# ---------- producer_address ----------


@pytest.mark.parametrize(
    "extracted, expected, matched",
    [
        ("Austin, TX", "Austin, TX", True),
        ("AUSTIN, TX", "Austin, TX", True),
        ("AUSTIN TEXAS", "Austin, TX", True),
        ("Austin, Texas", "Austin, TX", True),
        ("Versailles, Kentucky USA", "Versailles, Kentucky", True),
        ("Star Hill Farm, Loretto, KY", "Star Hill Farm, Loretto, KY", True),
        ("Loretto, KY", "Star Hill Farm, Loretto, KY", False),  # true info loss
        # parris/parlier is a genuine OCR substitution, but token_sort
        # ratio of two short typo-distant strings lands ~90, above the
        # fuzzy threshold. Accepting this as the cost of fuzzy matching;
        # raising the threshold breaks legitimate corp-name variation.
        ("PARRIS, CALIFORNIA", "Parlier, California", True),
        ("Mineville, NY", "Mineville, NY", True),
    ],
)
def test_producer_address(extracted, expected, matched):
    ext = _base() | {"producer_address": extracted}
    exp = _base() | {"producer_address": expected}
    assert compare(ext, exp)["producer_address"]["matched"] is matched


# ---------- is_imported / country_of_origin pair ----------


def test_imported_with_country_match():
    # standard "Don Julio is imported from Mexico" case
    assert compare(_base(), _base())["country_of_origin"]["matched"] is True
    assert compare(_base(), _base())["is_imported"]["matched"] is True


def test_imported_country_origin_phrase_matches_country_value():
    ext = _base() | {"country_of_origin": "PRODUCT OF MEXICO"}
    out = compare(ext, _base())
    assert out["country_of_origin"]["matched"] is True


def test_imported_missing_country_extracted():
    ext = _base() | {"country_of_origin": None}
    exp = _base()
    out = compare(ext, exp)
    assert out["country_of_origin"]["matched"] is False
    assert "required" in out["country_of_origin"]["reason"]


def test_domestic_both_null():
    ext = {**_base(), "is_imported": False, "country_of_origin": None}
    exp = {**_base(), "is_imported": False, "country_of_origin": None}
    out = compare(ext, exp)
    assert out["is_imported"]["matched"] is True
    assert out["country_of_origin"]["matched"] is True


def test_domestic_label_prints_usa_is_tolerated():
    # Maker's Mark / Tito's / Woodford pattern.
    ext = {**_base(), "is_imported": False, "country_of_origin": "USA"}
    exp = {**_base(), "is_imported": False, "country_of_origin": None}
    out = compare(ext, exp)
    assert out["country_of_origin"]["matched"] is True


def test_is_imported_null_clears_country_via_consistency():
    # extracted with is_imported=None should have country wiped before compare.
    ext = {**_base(), "is_imported": None, "country_of_origin": "Mexico"}
    exp = {**_base(), "is_imported": True, "country_of_origin": "Mexico"}
    out = compare(ext, exp)
    assert out["is_imported"]["matched"] is False
    # Country now compared as None vs "Mexico" with imported=True on expected side.
    assert out["country_of_origin"]["matched"] is False


def test_imported_mismatch():
    ext = {**_base(), "is_imported": False}
    exp = {**_base(), "is_imported": True}
    out = compare(ext, exp)
    assert out["is_imported"]["matched"] is False


# ---------- government_warning_text ----------


def test_warning_canonical_passes():
    ext = _base()
    out = compare(ext, _base())
    assert out["government_warning_text"]["matched"] is True


def test_warning_title_case_fails():
    # Jenny's bright line: she rejected a submission for title-case warning.
    ext = _base() | {"government_warning_text": TITLE_CASE_WARNING}
    out = compare(ext, _base())
    assert out["government_warning_text"]["matched"] is False
    assert "all caps" in out["government_warning_text"]["reason"].lower()


def test_warning_truncated_fails():
    truncated = "GOVERNMENT WARNING: (1) According to the Surgeon General"
    ext = _base() | {"government_warning_text": truncated}
    out = compare(ext, _base())
    assert out["government_warning_text"]["matched"] is False


def test_warning_missing_fails():
    ext = _base() | {"government_warning_text": None}
    out = compare(ext, _base())
    assert out["government_warning_text"]["matched"] is False


def test_warning_bold_true_passes_text_and_style():
    ext = _base() | {"government_warning_bold": True}
    out = compare(ext, _base())
    assert out["government_warning_text"]["matched"] is True
    assert out["government_warning_style"]["matched"] is True
    assert "bold confirmed" in out["government_warning_style"]["reason"]


def test_warning_bold_false_is_style_issue_not_text_failure():
    ext = _base() | {"government_warning_bold": False}
    out = compare(ext, _base())
    assert out["government_warning_text"]["matched"] is True
    assert out["government_warning_style"]["matched"] is False
    assert "not bold" in out["government_warning_style"]["reason"]


def test_warning_all_caps_body_passes_when_only_header_is_bold():
    ext = _base() | {
        "government_warning_text": CANONICAL_WARNING.upper(),
        "government_warning_bold": True,
        "government_warning_body_bold": False,
    }
    out = compare(ext, _base())
    assert out["government_warning_text"]["matched"] is True


def test_warning_body_bold_is_style_issue_not_text_failure():
    ext = _base() | {
        "government_warning_text": CANONICAL_WARNING.upper(),
        "government_warning_bold": True,
        "government_warning_body_bold": True,
    }
    out = compare(ext, _base())
    assert out["government_warning_text"]["matched"] is True
    assert out["government_warning_style"]["matched"] is False
    assert "remainder" in out["government_warning_style"]["reason"]


def test_warning_bold_unknown_does_not_fail():
    # Older cached extractions predate the bold field — comparator should
    # not penalize them just for missing the signal.
    ext = _base() | {"government_warning_bold": None}
    out = compare(ext, _base())
    assert out["government_warning_text"]["matched"] is True
    assert out["government_warning_style"]["matched"] is True
    assert "bold unverified" in out["government_warning_style"]["reason"]


def test_warning_whitespace_collapses():
    # Newlines and multi-space inside the warning shouldn't matter.
    spaced = CANONICAL_WARNING.replace(" ", "  ").replace("(1)", "(1)\n")
    ext = _base() | {"government_warning_text": spaced}
    out = compare(ext, _base())
    assert out["government_warning_text"]["matched"] is True


# ---------- shape sanity ----------


def test_returns_all_fields():
    out = compare(_base(), _base())
    expected_keys = {
        "brand",
        "class_type",
        "alcohol_content",
        "net_contents",
        "producer_name",
        "producer_address",
        "is_imported",
        "country_of_origin",
        "government_warning_text",
        "government_warning_style",
    }
    assert set(out.keys()) == expected_keys


def test_entry_shape():
    out = compare(_base(), _base())
    for entry in out.values():
        assert set(entry.keys()) == {"matched", "extracted", "expected", "reason"}
        assert isinstance(entry["matched"], bool)
        assert isinstance(entry["reason"], str)
