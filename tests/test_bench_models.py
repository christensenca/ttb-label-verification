"""Unit tests for benchmark report shaping."""

from __future__ import annotations

from scripts.bench_models import to_canonical


def test_to_canonical_keeps_warning_bold_for_scoring():
    label = {
        "brand": "Tito's",
        "government_warning_text": "GOVERNMENT WARNING: ...",
        "government_warning_bold": False,
        "field_confidence": {"brand": "hi"},
        "front_label_text": "debug transcript",
    }

    canonical = to_canonical(label)

    assert canonical["brand"] == "Tito's"
    assert canonical["government_warning_text"] == "GOVERNMENT WARNING: ..."
    assert canonical["government_warning_bold"] is False
    assert "field_confidence" not in canonical
    assert "front_label_text" not in canonical
