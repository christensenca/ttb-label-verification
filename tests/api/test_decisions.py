"""Contract test for POST /api/submissions/{id}/decision (T028, US1)."""

from __future__ import annotations

from app.db.models import Comparison, Submission


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


def _ready_submission(db_session, *, with_fail_field: bool = False) -> Submission:
    sub = Submission(
        image_key="sha256:test.jpg",
        expected_values=_expected(),
        status="ready_for_review",
        is_fixture=True,
    )
    db_session.add(sub)
    db_session.flush()
    fields = [
        ("brand", "pass"),
        ("class_type", "pass"),
        ("alcohol_content", "pass"),
        ("net_contents", "pass"),
        ("producer_name", "pass"),
        ("producer_address", "pass"),
        ("is_imported", "pass"),
        ("country_of_origin", "pass"),
        ("government_warning_text", "fail" if with_fail_field else "pass"),
        ("government_warning_style", "pass"),
    ]
    for field, verdict in fields:
        db_session.add(
            Comparison(
                submission_id=sub.id,
                field=field,
                verdict=verdict,
                rule="ok",
                extracted_value="x",
                expected_value="x",
                reason="ok",
            )
        )
    db_session.flush()
    return sub


def test_approve_persists_and_flips_status(client, db_session):
    sub = _ready_submission(db_session)

    response = client.post(
        f"/api/submissions/{sub.id}/decision",
        json={"decision": "approved"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["decision"] == "approved"

    refreshed = db_session.get(Submission, sub.id)
    assert refreshed.status == "approved"


def test_duplicate_decision_returns_409(client, db_session):
    sub = _ready_submission(db_session)

    first = client.post(
        f"/api/submissions/{sub.id}/decision", json={"decision": "approved"}
    )
    assert first.status_code == 200

    second = client.post(
        f"/api/submissions/{sub.id}/decision", json={"decision": "approved"}
    )
    assert second.status_code == 409


def test_approve_with_rejection_field_ids_returns_400(client, db_session):
    sub = _ready_submission(db_session, with_fail_field=True)

    # Find the failing comparison id
    failing = (
        db_session.query(Comparison)
        .filter_by(submission_id=sub.id, verdict="fail")
        .first()
    )
    assert failing is not None

    response = client.post(
        f"/api/submissions/{sub.id}/decision",
        json={
            "decision": "approved",
            "rejection_field_ids": [str(failing.id)],
        },
    )
    assert response.status_code in {400, 422}


def test_reject_persists(client, db_session):
    sub = _ready_submission(db_session, with_fail_field=True)
    failing = (
        db_session.query(Comparison)
        .filter_by(submission_id=sub.id, verdict="fail")
        .first()
    )
    response = client.post(
        f"/api/submissions/{sub.id}/decision",
        json={
            "decision": "rejected",
            "comment": "warning text mismatch",
            "rejection_field_ids": [str(failing.id)],
        },
    )
    assert response.status_code == 200, response.text
    refreshed = db_session.get(Submission, sub.id)
    assert refreshed.status == "rejected"
