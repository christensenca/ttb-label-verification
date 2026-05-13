"""Processor extraction-failure unit test (T024, US1, per research R13).

When the extractor raises:
  - one `Extraction` row exists with `error` set, all data columns null
  - 10 synthesized `Comparison` rows exist with `rule='extraction failed'`
    and `verdict='fail'` (or `'not_applicable'` where appropriate)
  - submission status flips to `extraction_failed`
"""

from __future__ import annotations

from sqlalchemy import select

from app.api.schemas import ALL_FIELDS
from app.db.models import Comparison, Extraction, Submission


def test_processor_failure_writes_synthesized_rows_and_flips_status(
    db_session, mock_extract
):
    sub = Submission(
        image_key="sha256:test.jpg",
        expected_values={
            "brand": "Don Julio",
            "class_type": "Tequila Blanco",
            "alcohol_content": 40.0,
            "net_contents": "750 mL",
            "producer_name": "Diageo",
            "producer_address": "New York, NY",
            "is_imported": True,
            "country_of_origin": "Mexico",
        },
        status="processing",
        is_fixture=True,
    )
    db_session.add(sub)
    db_session.flush()
    submission_id = sub.id

    def _boom(_path, **_kw):
        raise RuntimeError("simulated extraction failure")

    mock_extract.set(_boom)

    from app.services import processor

    processor.process_submission(
        submission_id=submission_id,
        session_factory=lambda: db_session,
        image_path="test_data/images/don_julio.jpg",
    )

    refreshed = db_session.get(Submission, submission_id)
    assert refreshed.status == "extraction_failed"

    extractions = db_session.execute(
        select(Extraction).where(Extraction.submission_id == submission_id)
    ).scalars().all()
    assert len(extractions) == 1
    e = extractions[0]
    assert e.error and "simulated extraction failure" in e.error
    assert e.extracted_label is None
    assert e.field_confidence is None
    assert e.latency_ms is None
    assert e.input_tokens is None
    assert e.output_tokens is None

    comparisons = db_session.execute(
        select(Comparison).where(Comparison.submission_id == submission_id)
    ).scalars().all()
    assert {c.field for c in comparisons} == set(ALL_FIELDS)
    for c in comparisons:
        assert c.verdict in {"fail", "not_applicable"}
        assert c.rule == "extraction failed"
        assert c.extracted_value is None
        assert c.diff_extracted is None
        assert c.diff_expected is None
