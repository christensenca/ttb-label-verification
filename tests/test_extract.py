"""Unit tests for extraction response shaping.

These tests stay intentionally below the live model boundary. They verify
that one-shot structured responses can be adapted into the existing flat
label shape without sneaking comparison normalization into extraction.
"""

from __future__ import annotations

from pipeline.extract import (
    DEFAULT_MODEL,
    SYSTEM_PROMPT,
    FieldExtraction,
    OneShotExtractedLabel,
    unwrap_one_shot_label,
)


def _field(value: str | None, confidence: str = "hi") -> FieldExtraction:
    return FieldExtraction(value=value, extraction_confidence=confidence)


def test_unwrap_one_shot_label_flattens_values_and_preserves_confidence():
    one_shot = OneShotExtractedLabel(
        brand=_field("GRAY WHALE", "hi"),
        class_type=_field("GIN", "hi"),
        alcohol_content=_field("43% ALC./VOL.", "med"),
        net_contents=_field("750ML", "hi"),
        producer_name=_field("GOLDEN STATE DISTILLERY", "med"),
        producer_address=_field("PARLIER, CALIFORNIA", "med"),
        is_imported=False,
        country_of_origin=_field(None, "low"),
        government_warning_text=_field("GOVERNMENT WARNING: (1) READABLE", "med"),
        government_warning_bold=True,
        government_warning_body_bold=False,
    )

    label, confidence = unwrap_one_shot_label(one_shot)

    assert label.model_dump() == {
        "brand": "GRAY WHALE",
        "class_type": "GIN",
        "alcohol_content": "43% ALC./VOL.",
        "net_contents": "750ML",
        "producer_name": "GOLDEN STATE DISTILLERY",
        "producer_address": "PARLIER, CALIFORNIA",
        "is_imported": False,
        "country_of_origin": None,
        "government_warning_text": "GOVERNMENT WARNING: (1) READABLE",
        "government_warning_bold": True,
        "government_warning_body_bold": False,
    }
    assert confidence == {
        "brand": "hi",
        "class_type": "hi",
        "alcohol_content": "med",
        "net_contents": "hi",
        "producer_name": "med",
        "producer_address": "med",
        "country_of_origin": "low",
        "government_warning_text": "med",
    }


def test_unwrap_one_shot_label_does_not_normalize_or_parse_values():
    one_shot = OneShotExtractedLabel(
        brand=_field("  The Maker's Mark Distillery Inc.  ", "med"),
        class_type=_field("KENTUCKY\nSTRAIGHT BOURBON WHISKY", "hi"),
        alcohol_content=_field("ALC. 45% BY VOL.", "hi"),
        net_contents=_field("0.75 L", "hi"),
        producer_name=_field("WILLIAM GRANT & SONS, INC.", "hi"),
        producer_address=_field("NEW YORK, NY.", "hi"),
        is_imported=True,
        country_of_origin=_field("SCOTLAND", "hi"),
        government_warning_text=_field("Government Warning: mixed case", "low"),
        government_warning_bold=False,
        government_warning_body_bold=None,
    )

    label, _ = unwrap_one_shot_label(one_shot)

    assert label.brand == "  The Maker's Mark Distillery Inc.  "
    assert label.class_type == "KENTUCKY\nSTRAIGHT BOURBON WHISKY"
    assert label.alcohol_content == "ALC. 45% BY VOL."
    assert label.net_contents == "0.75 L"
    assert label.producer_name == "WILLIAM GRANT & SONS, INC."
    assert label.producer_address == "NEW YORK, NY."
    assert label.country_of_origin == "SCOTLAND"
    assert label.government_warning_text == "Government Warning: mixed case"
    assert label.government_warning_bold is False
    assert label.government_warning_body_bold is None


def test_prompt_forbids_known_brand_address_leakage():
    assert "Do not use known distillery" in SYSTEM_PROMPT
    assert "Do not return an address unless the city/state text is visible" in SYSTEM_PROMPT


def test_prompt_separates_warning_header_bold_from_body_bold():
    assert "Compare 'GOVERNMENT WARNING:'" in SYSTEM_PROMPT
    assert "warning text after the header" in SYSTEM_PROMPT


def test_default_model_is_gemini_pro_preview():
    assert DEFAULT_MODEL == "google/gemini-3.1-pro-preview"


def test_prompt_describes_warning_bold_concisely():
    assert "Compare 'GOVERNMENT WARNING:' to the warning text immediately after it" in SYSTEM_PROMPT
    assert "True if the header looks darker/heavier" in SYSTEM_PROMPT
    assert "All-caps is not bold" in SYSTEM_PROMPT
