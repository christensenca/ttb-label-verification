"""Processor success-path unit test (T023, US1).

Stubs the extractor; verifies the persistence side-effects per data-model:
  - exactly one `Extraction` row with latency/tokens/model/extracted_label/field_confidence
  - exactly 10 `Comparison` rows (one per field across all 5 groups)
  - submission status flips to `ready_for_review`
  - all writes happen in one transaction (single commit)
"""

from __future__ import annotations

import uuid

from sqlalchemy import select

from app.api.schemas import ALL_FIELDS
from app.db.models import Comparison, Extraction, Submission


def test_processor_success_writes_extraction_comparisons_and_flips_status(
    db_session, mock_extract
):
    # Insert a loaded submission whose expected_values matches the don_julio fixture.
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

    from app.services import processor

    # Inject the test session factory so the processor commits onto our SAVEPOINT.
    processor.process_submission(
        submission_id=submission_id,
        session_factory=lambda: db_session,
        image_path="test_data/images/don_julio.jpg",
    )

    refreshed = db_session.get(Submission, submission_id)
    assert refreshed.status == "ready_for_review"

    extractions = db_session.execute(
        select(Extraction).where(Extraction.submission_id == submission_id)
    ).scalars().all()
    assert len(extractions) == 1
    e = extractions[0]
    assert e.error is None
    assert e.model == "test-model/mock"
    assert e.latency_ms is not None
    assert e.input_tokens is not None and e.input_tokens > 0
    assert e.output_tokens is not None and e.output_tokens > 0
    assert isinstance(e.extracted_label, dict) and e.extracted_label.get("brand") == "Don Julio"
    assert isinstance(e.field_confidence, dict) and e.field_confidence.get("brand") == "hi"

    comparisons = db_session.execute(
        select(Comparison).where(Comparison.submission_id == submission_id)
    ).scalars().all()
    assert len(comparisons) == len(ALL_FIELDS) == 10
    fields_present = {c.field for c in comparisons}
    assert fields_present == set(ALL_FIELDS)
    for c in comparisons:
        assert c.verdict in {"pass", "fail", "not_applicable"}
        assert c.rule  # human-readable rule label
