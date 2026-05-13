"""Contract test for GET /api/submissions/{id} (T027, US1)."""

from __future__ import annotations

import uuid

from app.db.models import Comparison, Extraction, Submission


def _expected():
    return {
        "brand": "Don Julio",
        "class_type": "Tequila Blanco",
        "alcohol_content": 40.0,
        "net_contents": "750 mL",
        "producer_name": "Diageo",
        "producer_address": "New York, NY",
        "is_imported": True,
        "country_of_origin": "Mexico",
    }


ALL_FIELDS = [
    "brand",
    "class_type",
    "producer_name",
    "producer_address",
    "alcohol_content",
    "net_contents",
    "is_imported",
    "country_of_origin",
    "government_warning_text",
    "government_warning_style",
]


def test_get_loaded_submission_has_empty_groups_and_null_extraction(
    client, db_session
):
    sub = Submission(
        image_key="sha256:test.jpg",
        expected_values=_expected(),
        status="loaded",
        is_fixture=True,
    )
    db_session.add(sub)
    db_session.flush()

    response = client.get(f"/api/submissions/{sub.id}")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["id"] == str(sub.id)
    assert body["status"] == "loaded"
    assert body["groups"] == []
    assert body["extraction"] is None
    assert body["review"] is None
    assert body["image_url"] == f"/api/submissions/{sub.id}/image"


def test_get_ready_for_review_has_full_payload(client, db_session):
    sub = Submission(
        image_key="sha256:test.jpg",
        expected_values=_expected(),
        status="ready_for_review",
        is_fixture=True,
    )
    db_session.add(sub)
    db_session.flush()
    db_session.add(
        Extraction(
            submission_id=sub.id,
            extracted_label={"brand": "Don Julio"},
            field_confidence={"brand": "hi"},
            latency_ms=2500,
            input_tokens=100,
            output_tokens=50,
            model="test-model/mock",
            error=None,
        )
    )
    for field in ALL_FIELDS:
        db_session.add(
            Comparison(
                submission_id=sub.id,
                field=field,
                verdict="pass",
                rule="exact match after normalize",
                extracted_value="x",
                expected_value="x",
                reason="ok",
            )
        )
    db_session.flush()

    body = client.get(f"/api/submissions/{sub.id}").json()
    assert body["status"] == "ready_for_review"
    assert body["extraction"]["model"] == "test-model/mock"
    assert body["extraction"]["error"] is None
    assert body["extraction"]["latency_ms"] == 2500
    assert body["extraction"]["tokens"]["input"] == 100
    assert body["extraction"]["tokens"]["output"] == 50

    group_names = [g["name"] for g in body["groups"]]
    assert group_names == [
        "Identity",
        "Producer",
        "Quantitative",
        "Origin",
        "Government Warning",
    ]
    flat_fields = [f["field"] for g in body["groups"] for f in g["fields"]]
    assert set(flat_fields) == set(ALL_FIELDS)
    for g in body["groups"]:
        for f in g["fields"]:
            assert f["effective_verdict"] == "pass"
            assert f["model_verdict"] == "pass"


def test_get_extraction_failed_has_synthesized_groups_and_error(client, db_session):
    sub = Submission(
        image_key="sha256:test.jpg",
        expected_values=_expected(),
        status="extraction_failed",
        is_fixture=True,
    )
    db_session.add(sub)
    db_session.flush()
    db_session.add(
        Extraction(
            submission_id=sub.id,
            extracted_label=None,
            field_confidence=None,
            latency_ms=None,
            input_tokens=None,
            output_tokens=None,
            model="test-model/mock",
            error="model failed to read image",
        )
    )
    for field in ALL_FIELDS:
        db_session.add(
            Comparison(
                submission_id=sub.id,
                field=field,
                verdict="fail",
                rule="extraction failed",
                extracted_value=None,
                expected_value=None,
                reason="no extraction available",
            )
        )
    db_session.flush()

    body = client.get(f"/api/submissions/{sub.id}").json()
    assert body["status"] == "extraction_failed"
    assert body["extraction"]["error"] == "model failed to read image"
    flat_fields = [f for g in body["groups"] for f in g["fields"]]
    assert len(flat_fields) == 10
    for f in flat_fields:
        assert f["model_verdict"] in {"fail", "not_applicable"}
        assert f["rule"] == "extraction failed"


def test_get_unknown_submission_returns_404(client):
    body_resp = client.get(f"/api/submissions/{uuid.uuid4()}")
    assert body_resp.status_code == 404
