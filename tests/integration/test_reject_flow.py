"""End-to-end reject flow with structured reasons (T061, US5).

Process an item → two fields fail → reject with both ids + a comment → fetch
detail → the review block round-trips through GET /api/submissions/{id}.
"""

from __future__ import annotations

from app.db.models import Comparison, Submission


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


def test_reject_with_two_reasons_persists_and_roundtrips(client, db_session):
    """Insert a ready_for_review submission with two failing fields and a
    review-able shape, then exercise the full POST decision → GET detail loop."""
    sub = Submission(
        image_key="sha256:test.jpg",
        expected_values=_expected("RejectMe"),
        status="ready_for_review",
        is_fixture=True,
    )
    db_session.add(sub)
    db_session.flush()

    fields = [
        ("brand", "fail"),
        ("class_type", "fail"),
        ("alcohol_content", "pass"),
        ("net_contents", "pass"),
        ("producer_name", "pass"),
        ("producer_address", "pass"),
        ("is_imported", "pass"),
        ("country_of_origin", "not_applicable"),
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

    failing = (
        db_session.query(Comparison)
        .filter_by(submission_id=sub.id, verdict="fail")
        .all()
    )
    assert len(failing) == 2
    failing_ids = sorted(str(c.id) for c in failing)

    response = client.post(
        f"/api/submissions/{sub.id}/decision",
        json={
            "decision": "rejected",
            "comment": "brand and class_type both wrong",
            "rejection_field_ids": failing_ids,
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["decision"] == "rejected"
    assert body["comment"] == "brand and class_type both wrong"
    assert sorted(body["rejection_field_ids"]) == failing_ids

    # Round-trip via GET detail
    detail = client.get(f"/api/submissions/{sub.id}").json()
    assert detail["status"] == "rejected"
    assert detail["review"] is not None
    assert detail["review"]["decision"] == "rejected"
    assert detail["review"]["comment"] == "brand and class_type both wrong"
    assert sorted(detail["review"]["rejection_field_ids"]) == failing_ids
