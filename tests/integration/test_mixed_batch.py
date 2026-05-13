"""Integration test for FR-010 / SC-006 (T029a, US1).

Verifies items that finish early are individually reviewable while siblings
are still processing — the streaming nature of `process_all_loaded`.
"""

from __future__ import annotations

from app.db.models import Comparison, Extraction, Submission


def _expected(brand: str):
    return {
        "brand": brand,
        "class_type": "Whisky",
        "alcohol_content": 40.0,
        "net_contents": "750 mL",
        "producer_name": "X",
        "producer_address": "Y",
        "is_imported": False,
    }


def test_completed_items_reviewable_while_others_still_processing(
    client, db_session, mock_extract
):
    """One submission's worth of rows is ready_for_review; siblings are processing.

    Approximates the in-flight state by inserting rows directly so the test is
    deterministic and doesn't depend on real async scheduling.
    """
    ready = Submission(
        image_key="sha256:test.jpg",
        expected_values=_expected("Ready"),
        status="ready_for_review",
        is_fixture=True,
    )
    processing_a = Submission(
        image_key="sha256:test.jpg",
        expected_values=_expected("ProcA"),
        status="processing",
        is_fixture=True,
    )
    processing_b = Submission(
        image_key="sha256:test.jpg",
        expected_values=_expected("ProcB"),
        status="processing",
        is_fixture=True,
    )
    db_session.add_all([ready, processing_a, processing_b])
    db_session.flush()

    # Hydrate the ready item with extraction + comparisons
    db_session.add(
        Extraction(
            submission_id=ready.id,
            extracted_label={"brand": "Ready"},
            field_confidence={"brand": "hi"},
            latency_ms=2000,
            input_tokens=100,
            output_tokens=50,
            model="test-model/mock",
        )
    )
    for field in (
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
    ):
        db_session.add(
            Comparison(
                submission_id=ready.id,
                field=field,
                verdict="pass",
                rule="ok",
                extracted_value="x",
                expected_value="x",
                reason="ok",
            )
        )
    db_session.flush()

    ready_payload = client.get(f"/api/submissions/{ready.id}").json()
    assert ready_payload["status"] == "ready_for_review"
    assert len(ready_payload["groups"]) == 5

    for proc_id in (processing_a.id, processing_b.id):
        body = client.get(f"/api/submissions/{proc_id}").json()
        assert body["status"] == "processing"
        assert body["groups"] == []
        assert body["extraction"] is None
