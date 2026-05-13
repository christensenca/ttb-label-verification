"""Unit tests for benchmark report shaping."""

from __future__ import annotations

from pipeline.compare import CANONICAL_WARNING
from scripts import bench_models
from scripts.bench_models import to_canonical


def test_to_canonical_keeps_warning_bold_for_scoring():
    label = {
        "brand": "Tito's",
        "government_warning_text": "GOVERNMENT WARNING: ...",
        "government_warning_bold": False,
        "government_warning_body_bold": True,
        "field_confidence": {"brand": "hi"},
        "front_label_text": "debug transcript",
    }

    canonical = to_canonical(label)

    assert canonical["brand"] == "Tito's"
    assert canonical["government_warning_text"] == "GOVERNMENT WARNING: ..."
    assert canonical["government_warning_bold"] is False
    assert canonical["government_warning_body_bold"] is True
    assert "field_confidence" not in canonical
    assert "front_label_text" not in canonical


def test_report_splits_warning_text_from_style(monkeypatch, tmp_path):
    monkeypatch.setattr(bench_models, "BOTTLES", ["don_julio"])
    monkeypatch.setattr(bench_models, "MODELS", ["test/model"])
    report_path = tmp_path / "report.md"
    results = {
        "don_julio": {
            "test/model": {
                "label": {
                    "brand": "Don Julio",
                    "class_type": "Tequila Blanco",
                    "alcohol_content": "40% alc./vol.",
                    "net_contents": "750 mL",
                    "producer_name": "Diageo",
                    "producer_address": "New York, NY",
                    "is_imported": True,
                    "country_of_origin": "Product of Mexico",
                    "government_warning_text": CANONICAL_WARNING,
                    "government_warning_bold": False,
                    "government_warning_body_bold": False,
                },
                "field_confidence": {},
                "latency_ms": 1234,
                "in_tok": 10,
                "out_tok": 20,
                "error": None,
            }
        }
    }

    bench_models.write_report(results, report_path)

    report = report_path.read_text()
    assert "| model | accuracy | warn text | warn style |" in report
    assert "| warn text | warn style | score | confidence | latency |" in report
    assert "1/1 (100%)" in report
    assert "0/1 (0%)" in report
    assert "text matches but warning header is not bold" in report
