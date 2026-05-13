"""End-to-end queue flow: list → start → poll → detail → approve (T029, US1)."""

from __future__ import annotations

from sqlalchemy import select

from app.db.models import Submission


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


def test_queue_flow_load_start_approve(client, db_session, mock_extract, monkeypatch):
    # Force the processor to run inline against the test session so we don't
    # depend on a background event loop within TestClient.
    from app.services import processor as proc_module

    real_process = proc_module.process_submission

    def _inline_schedule(submission_ids, *, session_factory=None, image_paths=None):
        for sid in submission_ids:
            real_process(
                submission_id=sid,
                session_factory=lambda: db_session,
                image_path="test_data/images/don_julio.jpg",
            )

    monkeypatch.setattr(proc_module, "_schedule_processing", _inline_schedule)

    # Seed two loaded items
    for i in range(2):
        sub = Submission(
            image_key="sha256:test.jpg",
            expected_values=_expected(f"Brand{i}"),
            status="loaded",
            is_fixture=True,
        )
        db_session.add(sub)
    db_session.flush()

    # List
    listing = client.get("/api/submissions").json()
    assert len(listing) == 2
    assert all(item["status"] == "loaded" for item in listing)

    # Start
    start = client.post("/api/submissions/start")
    assert start.status_code == 202

    # After inline processing, both should be ready_for_review
    rows = db_session.execute(select(Submission)).scalars().all()
    assert {r.status for r in rows} == {"ready_for_review"}

    sub_id = rows[0].id
    detail = client.get(f"/api/submissions/{sub_id}").json()
    assert detail["status"] == "ready_for_review"
    assert detail["extraction"] is not None

    approve = client.post(
        f"/api/submissions/{sub_id}/decision", json={"decision": "approved"}
    )
    assert approve.status_code == 200

    listing_after = client.get("/api/submissions").json()
    statuses = {item["id"]: item["status"] for item in listing_after}
    assert statuses[str(sub_id)] == "approved"
