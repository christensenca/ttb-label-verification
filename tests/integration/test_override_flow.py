"""End-to-end override flow (T068, US4).

Process an item with a failing field → override to pass with comment → approve →
reload → assert both the override (with comment) and the approval persisted,
and the original model verdict is still visible in the payload.
"""

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


def _ready_with_one_failing(db_session) -> Submission:
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


def test_override_then_approve_roundtrips_with_original_visible(client, db_session):
    sub = _ready_with_one_failing(db_session)

    # 1. Override the failing brand field to pass with a comment.
    override_resp = client.post(
        f"/api/submissions/{sub.id}/overrides",
        json={
            "field": "brand",
            "override_verdict": "pass",
            "comment": "OCR dropped a glyph; label brand actually matches.",
        },
    )
    assert override_resp.status_code == 200, override_resp.text

    # 2. Approve the submission. With the override flipping the only failing
    # field to pass, approve goes through without confirmation.
    decision_resp = client.post(
        f"/api/submissions/{sub.id}/decision",
        json={"decision": "approved"},
    )
    assert decision_resp.status_code == 200, decision_resp.text

    # 3. Reload the detail payload and assert everything persisted.
    detail = client.get(f"/api/submissions/{sub.id}").json()
    assert detail["status"] == "approved"
    assert detail["review"] is not None
    assert detail["review"]["decision"] == "approved"

    brand_row = [
        row
        for g in detail["groups"]
        for row in g["fields"]
        if row["field"] == "brand"
    ][0]
    # Original model verdict still visible (FR-020).
    assert brand_row["model_verdict"] == "fail"
    # Effective verdict reflects the override.
    assert brand_row["effective_verdict"] == "pass"
    assert brand_row["override"] is not None
    assert brand_row["override"]["override_verdict"] == "pass"
    assert brand_row["override"]["original_verdict"] == "fail"
    assert "OCR dropped" in brand_row["override"]["comment"]
