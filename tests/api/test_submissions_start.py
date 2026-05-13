"""Contract test for POST /api/submissions/start (T026, US1)."""

from __future__ import annotations

from sqlalchemy import select

from app.db.models import Submission


def _insert(db_session, status: str = "loaded") -> Submission:
    sub = Submission(
        image_key="sha256:test.jpg",
        expected_values={
            "brand": "Brand",
            "class_type": "Whisky",
            "alcohol_content": 40.0,
            "net_contents": "750 mL",
            "producer_name": "X",
            "producer_address": "Y",
            "is_imported": False,
        },
        status=status,
        is_fixture=True,
    )
    db_session.add(sub)
    db_session.flush()
    return sub


def test_start_with_zero_loaded_returns_200_zero(client, db_session):
    # No loaded items
    response = client.post("/api/submissions/start")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["scheduled"] == 0
    assert body["submission_ids"] == []


def test_start_with_loaded_items_flips_all_to_processing_synchronously(
    client, db_session, monkeypatch
):
    # Prevent the processor from actually running its async tasks; we only care
    # about the synchronous status flip here.
    from app.services import processor as proc_module

    monkeypatch.setattr(proc_module, "_schedule_processing", lambda *_a, **_kw: None)

    n = 3
    ids = [_insert(db_session).id for _ in range(n)]
    db_session.flush()

    response = client.post("/api/submissions/start")
    assert response.status_code == 202, response.text
    body = response.json()
    assert body["scheduled"] == n
    assert set(body["submission_ids"]) == {str(i) for i in ids}

    # Verify ALL flipped to processing inside the request, before returning.
    rows = db_session.execute(
        select(Submission).where(Submission.id.in_(ids))
    ).scalars().all()
    assert {r.status for r in rows} == {"processing"}
