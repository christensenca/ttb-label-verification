"""Contract tests for DELETE /api/submissions/{id}/overrides/{field} (T067, US4).

- success → 204 and subsequent GET shows effective_verdict reverted to model_verdict
- delete of a non-existent override → 404
"""

from __future__ import annotations

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


def _submission_with_failing(db_session) -> Submission:
    sub = Submission(
        image_key="sha256:test.jpg",
        expected_values=_expected(),
        status="ready_for_review",
        is_fixture=True,
    )
    db_session.add(sub)
    db_session.flush()
    fields = [
        ("brand", "fail"),
        ("class_type", "pass"),
        ("alcohol_content", "pass"),
        ("net_contents", "pass"),
        ("producer_name", "pass"),
        ("producer_address", "pass"),
        ("is_imported", "pass"),
        ("country_of_origin", "pass"),
        ("government_warning_text", "pass"),
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


def test_delete_override_returns_204_and_reverts_effective_verdict(
    client, db_session
):
    sub = _submission_with_failing(db_session)
    db_session.add(
        FieldOverride(
            submission_id=sub.id,
            field="brand",
            original_verdict="fail",
            override_verdict="pass",
            comment="reviewer override",
        )
    )
    db_session.flush()

    # Confirm override is in effect first
    before = client.get(f"/api/submissions/{sub.id}").json()
    brand_row_before = [
        row
        for g in before["groups"]
        for row in g["fields"]
        if row["field"] == "brand"
    ][0]
    assert brand_row_before["effective_verdict"] == "pass"
    assert brand_row_before["override"] is not None

    response = client.delete(f"/api/submissions/{sub.id}/overrides/brand")
    assert response.status_code == 204, response.text

    db_session.expire_all()
    assert (
        db_session.query(FieldOverride)
        .filter_by(submission_id=sub.id, field="brand")
        .count()
        == 0
    )

    after = client.get(f"/api/submissions/{sub.id}").json()
    brand_row_after = [
        row
        for g in after["groups"]
        for row in g["fields"]
        if row["field"] == "brand"
    ][0]
    assert brand_row_after["effective_verdict"] == "fail"
    assert brand_row_after["model_verdict"] == "fail"
    assert brand_row_after["override"] is None


def test_delete_nonexistent_override_returns_404(client, db_session):
    sub = _submission_with_failing(db_session)

    response = client.delete(f"/api/submissions/{sub.id}/overrides/brand")
    assert response.status_code == 404, response.text


def test_delete_override_on_unknown_submission_returns_404(client, db_session):
    import uuid as _uuid

    response = client.delete(
        f"/api/submissions/{_uuid.uuid4()}/overrides/brand"
    )
    assert response.status_code == 404, response.text


def test_delete_override_with_unknown_field_returns_404(client, db_session):
    sub = _submission_with_failing(db_session)

    response = client.delete(f"/api/submissions/{sub.id}/overrides/not_a_field")
    assert response.status_code == 404, response.text
