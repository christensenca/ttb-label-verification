"""Contract tests for POST /api/submissions/{id}/overrides (T066, US4).

Covers the contract from specs/001-verify-and-review/contracts/api.md:
- valid {field, override_verdict, comment} → 200 with original_verdict snapshotted
- empty comment → 400
- unknown field → 400
- second POST on the same field replaces (UPSERT) the existing row
- submission status outside ready_for_review / extraction_failed → 409
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


def _submission_with_failing(
    db_session, *, status_value: str = "ready_for_review"
) -> Submission:
    sub = Submission(
        image_key="sha256:test.jpg",
        expected_values=_expected(),
        status=status_value,
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


def test_create_override_returns_200_and_snapshots_original(client, db_session):
    sub = _submission_with_failing(db_session)

    response = client.post(
        f"/api/submissions/{sub.id}/overrides",
        json={
            "field": "brand",
            "override_verdict": "pass",
            "comment": "Label brand actually matches; OCR dropped an apostrophe.",
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["field"] == "brand"
    assert body["override_verdict"] == "pass"
    assert body["original_verdict"] == "fail"
    assert body["comment"].startswith("Label brand")
    assert body["created_at"]

    db_session.expire_all()
    overrides = (
        db_session.query(FieldOverride)
        .filter_by(submission_id=sub.id, field="brand")
        .all()
    )
    assert len(overrides) == 1
    assert overrides[0].override_verdict == "pass"
    assert overrides[0].original_verdict == "fail"


def test_create_override_empty_comment_is_allowed(client, db_session):
    """Comments are optional — reviewers can override silently."""
    sub = _submission_with_failing(db_session)

    response = client.post(
        f"/api/submissions/{sub.id}/overrides",
        json={"field": "brand", "override_verdict": "pass", "comment": ""},
    )
    assert response.status_code == 200, response.text
    assert response.json()["comment"] == ""


def test_create_override_omitted_comment_is_allowed(client, db_session):
    sub = _submission_with_failing(db_session)

    response = client.post(
        f"/api/submissions/{sub.id}/overrides",
        json={"field": "brand", "override_verdict": "pass"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["comment"] == ""


def test_create_override_unknown_field_returns_400(client, db_session):
    sub = _submission_with_failing(db_session)

    response = client.post(
        f"/api/submissions/{sub.id}/overrides",
        json={
            "field": "not_a_real_field",
            "override_verdict": "pass",
            "comment": "should fail",
        },
    )
    assert response.status_code == 400, response.text


def test_create_override_upserts_on_second_call(client, db_session):
    sub = _submission_with_failing(db_session)

    first = client.post(
        f"/api/submissions/{sub.id}/overrides",
        json={
            "field": "brand",
            "override_verdict": "pass",
            "comment": "first override",
        },
    )
    assert first.status_code == 200, first.text

    second = client.post(
        f"/api/submissions/{sub.id}/overrides",
        json={
            "field": "brand",
            "override_verdict": "fail",
            "comment": "actually still wrong",
        },
    )
    assert second.status_code == 200, second.text
    body = second.json()
    assert body["override_verdict"] == "fail"
    assert body["comment"] == "actually still wrong"

    db_session.expire_all()
    rows = (
        db_session.query(FieldOverride)
        .filter_by(submission_id=sub.id, field="brand")
        .all()
    )
    # Exactly one row remains — second call replaced the first.
    assert len(rows) == 1
    assert rows[0].override_verdict == "fail"
    assert rows[0].comment == "actually still wrong"


def test_create_override_on_approved_submission_returns_409(client, db_session):
    sub = _submission_with_failing(db_session, status_value="approved")

    response = client.post(
        f"/api/submissions/{sub.id}/overrides",
        json={
            "field": "brand",
            "override_verdict": "pass",
            "comment": "too late",
        },
    )
    assert response.status_code == 409, response.text


def test_create_override_on_extraction_failed_submission_is_allowed(
    client, db_session
):
    sub = _submission_with_failing(db_session, status_value="extraction_failed")

    response = client.post(
        f"/api/submissions/{sub.id}/overrides",
        json={
            "field": "brand",
            "override_verdict": "pass",
            "comment": "reviewer verified by eye",
        },
    )
    assert response.status_code == 200, response.text


def test_create_override_on_unknown_submission_returns_404(client, db_session):
    import uuid as _uuid

    response = client.post(
        f"/api/submissions/{_uuid.uuid4()}/overrides",
        json={
            "field": "brand",
            "override_verdict": "pass",
            "comment": "x",
        },
    )
    assert response.status_code == 404, response.text


def test_detail_payload_reflects_override(client, db_session):
    """The override should round-trip through GET /api/submissions/{id}: the
    field row's `override` block is populated, `effective_verdict` flips."""
    sub = _submission_with_failing(db_session)

    response = client.post(
        f"/api/submissions/{sub.id}/overrides",
        json={
            "field": "brand",
            "override_verdict": "pass",
            "comment": "reviewer override",
        },
    )
    assert response.status_code == 200, response.text

    detail = client.get(f"/api/submissions/{sub.id}").json()
    rows = [
        row for g in detail["groups"] for row in g["fields"] if row["field"] == "brand"
    ]
    assert len(rows) == 1
    row = rows[0]
    assert row["model_verdict"] == "fail"
    assert row["effective_verdict"] == "pass"
    assert row["override"] is not None
    assert row["override"]["override_verdict"] == "pass"
    assert row["override"]["original_verdict"] == "fail"
    assert row["override"]["comment"] == "reviewer override"
