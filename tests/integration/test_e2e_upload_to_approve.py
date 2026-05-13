"""End-to-end: upload a new submission, run processing, approve, verify.

Walks the entire workflow through real HTTP via TestClient:

    POST /api/submissions          (multipart upload)
    GET  /api/submissions          (verify it's there in `loaded`)
    POST /api/submissions/start    (schedule; processor runs inline)
    GET  /api/submissions/{id}     (ready_for_review with full read-model)
    POST /api/submissions/{id}/decision  (approve)
    GET  /api/submissions/{id}     (status persists, review block present)

This is the "from upload, processing, approval" half of the deploy-readiness
gate. The companion suites test the override path (changing pass status).
"""

from __future__ import annotations

import io
import json
from pathlib import Path

import pytest
from PIL import Image

from app.services import processor as proc_module


def _real_jpeg() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (32, 32), color=(120, 80, 40)).save(buf, format="JPEG")
    return buf.getvalue()


def _don_julio_expected() -> dict:
    """Expected values that line up with the default mock_extract result so
    every comparison passes on a fresh extraction."""
    return {
        "brand": "Don Julio",
        "class_type": "Tequila Blanco",
        "alcohol_content": 40.0,
        "net_contents": "750 mL",
        "producer_name": "DIAGEO",
        "producer_address": "NEW YORK, NY",
        "is_imported": True,
        "country_of_origin": "MEXICO",
    }


@pytest.fixture()
def isolated_image_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point IMAGE_STORAGE_DIR at a fresh temp dir for this test only."""
    from app.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "image_storage_dir", tmp_path)
    return tmp_path


@pytest.fixture()
def inline_processor(monkeypatch: pytest.MonkeyPatch, db_session):
    """Replace the async scheduler with a sync inline loop that shares the test
    session, so SAVEPOINT-isolated writes are visible to subsequent requests."""

    real_process = proc_module.process_submission

    def _inline(ids):
        for sid in ids:
            real_process(submission_id=sid, session_factory=lambda: db_session)

    monkeypatch.setattr(proc_module, "_schedule_processing", _inline)


def test_e2e_upload_process_approve_all_pass(
    client, db_session, mock_extract, isolated_image_dir, inline_processor
):
    # 1. Upload a brand-new (non-fixture) submission.
    upload = client.post(
        "/api/submissions",
        files={"image": ("label.jpg", io.BytesIO(_real_jpeg()), "image/jpeg")},
        data={"expected_values": json.dumps(_don_julio_expected())},
    )
    assert upload.status_code == 201, upload.text
    new_id = upload.json()["id"]
    assert upload.json()["status"] == "loaded"

    # The uploaded bytes were persisted to IMAGE_STORAGE_DIR.
    written = list(isolated_image_dir.iterdir())
    assert len(written) == 1
    assert written[0].name.startswith("sha256:")

    # 2. The queue listing shows the new row as `loaded` and `is_fixture=False`.
    listing = client.get("/api/submissions").json()
    assert any(
        r["id"] == new_id and r["status"] == "loaded" and r["is_fixture"] is False
        for r in listing
    )

    # 3. Start. Inline processor turns it into `ready_for_review` synchronously.
    start = client.post("/api/submissions/start")
    assert start.status_code == 202, start.text
    assert start.json()["scheduled"] >= 1
    assert new_id in start.json()["submission_ids"]

    # 4. Detail payload: ready_for_review, 10 comparisons, every effective_verdict pass.
    detail = client.get(f"/api/submissions/{new_id}").json()
    assert detail["status"] == "ready_for_review"
    assert detail["extraction"] is not None
    assert detail["extraction"]["error"] is None
    assert detail["extraction"]["model"] == "test-model/mock"
    all_fields = [f for g in detail["groups"] for f in g["fields"]]
    assert len(all_fields) == 10
    assert all(f["effective_verdict"] == "pass" for f in all_fields), [
        (f["field"], f["effective_verdict"]) for f in all_fields
    ]

    # 5. Approve. No rejection ids on the happy path.
    approve = client.post(
        f"/api/submissions/{new_id}/decision",
        json={"decision": "approved", "comment": "all fields match"},
    )
    assert approve.status_code == 200, approve.text
    body = approve.json()
    assert body["decision"] == "approved"
    assert body["comment"] == "all fields match"

    # 6. Reload — status persists, review block is populated, decision controls
    #    are locked from the API's perspective (duplicate decision → 409).
    after = client.get(f"/api/submissions/{new_id}").json()
    assert after["status"] == "approved"
    assert after["review"] is not None
    assert after["review"]["decision"] == "approved"
    assert after["review"]["comment"] == "all fields match"

    dup = client.post(
        f"/api/submissions/{new_id}/decision",
        json={"decision": "approved"},
    )
    assert dup.status_code == 409
