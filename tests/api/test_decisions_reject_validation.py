"""Contract tests for rejection-id validation on POST /api/submissions/{id}/decision (T060, US5).

Covers the contract from specs/001-verify-and-review/contracts/api.md:
- empty rejection_field_ids on reject → 400
- rejection id referencing a different submission → 400
- rejection ids referencing comparisons on this submission → 200 (any field
  may be cited as a rejection reason, including ones the model passed; the
  reviewer's judgment overrides the model's verdict).
"""

from __future__ import annotations

import uuid

from app.db.models import Comparison, FieldOverride, Submission


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


def _submission_with(
    db_session, *, failing_fields: list[str] | None = None
) -> Submission:
    failing_fields = failing_fields or []
    sub = Submission(
        image_key="sha256:test.jpg",
        expected_values=_expected(),
        status="ready_for_review",
        is_fixture=True,
    )
    db_session.add(sub)
    db_session.flush()
    all_fields = [
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
    ]
    for field in all_fields:
        db_session.add(
            Comparison(
                submission_id=sub.id,
                field=field,
                verdict="fail" if field in failing_fields else "pass",
                rule="ok",
                extracted_value="x",
                expected_value="x",
                reason="ok",
            )
        )
    db_session.flush()
    return sub


def test_reject_with_empty_rejection_field_ids_returns_400(client, db_session):
    sub = _submission_with(db_session, failing_fields=["brand"])

    response = client.post(
        f"/api/submissions/{sub.id}/decision",
        json={"decision": "rejected", "rejection_field_ids": []},
    )
    assert response.status_code in {400, 422}, response.text


def test_reject_with_missing_rejection_field_ids_returns_400(client, db_session):
    sub = _submission_with(db_session, failing_fields=["brand"])

    response = client.post(
        f"/api/submissions/{sub.id}/decision",
        json={"decision": "rejected"},
    )
    assert response.status_code in {400, 422}, response.text


def test_reject_with_id_from_other_submission_returns_400(client, db_session):
    sub_a = _submission_with(db_session, failing_fields=["brand"])
    sub_b = _submission_with(db_session, failing_fields=["brand"])

    # Pick a failing comparison on sub_b
    other = (
        db_session.query(Comparison)
        .filter_by(submission_id=sub_b.id, verdict="fail")
        .first()
    )
    assert other is not None

    response = client.post(
        f"/api/submissions/{sub_a.id}/decision",
        json={
            "decision": "rejected",
            "rejection_field_ids": [str(other.id)],
        },
    )
    assert response.status_code == 400, response.text
    detail = response.json()["detail"]
    assert "unknown" in detail.lower() or str(other.id) in detail


def test_reject_with_unknown_uuid_returns_400(client, db_session):
    sub = _submission_with(db_session, failing_fields=["brand"])
    bogus = uuid.uuid4()

    response = client.post(
        f"/api/submissions/{sub.id}/decision",
        json={
            "decision": "rejected",
            "rejection_field_ids": [str(bogus)],
        },
    )
    assert response.status_code == 400, response.text


def test_reject_with_passing_comparison_is_allowed(client, db_session):
    """Reviewer may cite any field — including ones the model marked `pass` —
    as a rejection reason. The reviewer's judgment is authoritative."""
    sub = _submission_with(db_session, failing_fields=["brand"])
    passing = (
        db_session.query(Comparison)
        .filter_by(submission_id=sub.id, verdict="pass")
        .first()
    )
    assert passing is not None

    response = client.post(
        f"/api/submissions/{sub.id}/decision",
        json={
            "decision": "rejected",
            "rejection_field_ids": [str(passing.id)],
        },
    )
    assert response.status_code == 200, response.text


def test_reject_with_override_to_pass_is_allowed(client, db_session):
    """A row whose effective verdict is `pass` via override can still be cited
    as a rejection reason — the reviewer may decide to flip their stance."""
    sub = _submission_with(db_session, failing_fields=["brand", "class_type"])

    failing = (
        db_session.query(Comparison)
        .filter_by(submission_id=sub.id, field="brand")
        .first()
    )
    assert failing is not None and failing.verdict == "fail"

    db_session.add(
        FieldOverride(
            submission_id=sub.id,
            field="brand",
            original_verdict="fail",
            override_verdict="pass",
            comment="reviewer says brand actually matches",
        )
    )
    db_session.flush()

    response = client.post(
        f"/api/submissions/{sub.id}/decision",
        json={
            "decision": "rejected",
            "rejection_field_ids": [str(failing.id)],
        },
    )
    assert response.status_code == 200, response.text


def test_reject_with_mixed_pass_and_fail_is_allowed(client, db_session):
    """Mixed pass + fail batch persists fine — both ids belong to the submission."""
    sub = _submission_with(db_session, failing_fields=["brand", "class_type"])

    failing = (
        db_session.query(Comparison)
        .filter_by(submission_id=sub.id, field="brand")
        .first()
    )
    passing = (
        db_session.query(Comparison)
        .filter_by(submission_id=sub.id, field="producer_name")
        .first()
    )
    assert failing is not None and passing is not None

    response = client.post(
        f"/api/submissions/{sub.id}/decision",
        json={
            "decision": "rejected",
            "rejection_field_ids": [str(failing.id), str(passing.id)],
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert sorted(body["rejection_field_ids"]) == sorted(
        [str(failing.id), str(passing.id)]
    )
