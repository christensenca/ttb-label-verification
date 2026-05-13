"""End-to-end: upload → process (all pass) → override pass→fail → reject.

The "changing pass status (pass→fail)" deploy-readiness gate. The model said
the field passed; the reviewer overrides to fail (with comment), then rejects
the submission with the now-failing field as a structured reason. After
reload, all three writes — the override, the rejection decision, and the
selected reason — are intact, and the original model verdict is still
visible.
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


def _matching_expected() -> dict:
    """Matches mock_extract's Don Julio default so every field naturally passes."""
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
    from app.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "image_storage_dir", tmp_path)
    return tmp_path


@pytest.fixture()
def inline_processor(monkeypatch: pytest.MonkeyPatch, db_session):
    real_process = proc_module.process_submission

    def _inline(ids):
        for sid in ids:
            real_process(submission_id=sid, session_factory=lambda: db_session)

    monkeypatch.setattr(proc_module, "_schedule_processing", _inline)


def test_e2e_override_pass_to_fail_then_reject(
    client, db_session, mock_extract, isolated_image_dir, inline_processor
):
    # 1. Upload + process. All fields pass on first pass.
    upload = client.post(
        "/api/submissions",
        files={"image": ("label.jpg", io.BytesIO(_real_jpeg()), "image/jpeg")},
        data={"expected_values": json.dumps(_matching_expected())},
    )
    new_id = upload.json()["id"]
    client.post("/api/submissions/start")

    detail = client.get(f"/api/submissions/{new_id}").json()
    assert detail["status"] == "ready_for_review"
    all_fields = [f for g in detail["groups"] for f in g["fields"]]
    assert all(f["effective_verdict"] == "pass" for f in all_fields)

    # 2. Override a *passing* field to fail. Use producer_address — non-text
    #    constraints don't matter for the override write, only that the field
    #    name is a real comparison row on this submission.
    override = client.post(
        f"/api/submissions/{new_id}/overrides",
        json={
            "field": "producer_address",
            "override_verdict": "fail",
            "comment": "Reviewer audit: the printed address differs from the application.",
        },
    )
    assert override.status_code == 200, override.text

    # The row now reads as effectively-failing while the model verdict stays "pass".
    detail2 = client.get(f"/api/submissions/{new_id}").json()
    addr_row = next(
        f
        for g in detail2["groups"]
        for f in g["fields"]
        if f["field"] == "producer_address"
    )
    assert addr_row["model_verdict"] == "pass"
    assert addr_row["effective_verdict"] == "fail"
    assert addr_row["override"]["override_verdict"] == "fail"
    assert addr_row["override"]["original_verdict"] == "pass"

    # 3. Reject the submission, citing the overridden field as the reason.
    reject = client.post(
        f"/api/submissions/{new_id}/decision",
        json={
            "decision": "rejected",
            "comment": "Address mismatch flagged during audit.",
            "rejection_field_ids": [addr_row["id"]],
        },
    )
    assert reject.status_code == 200, reject.text
    body = reject.json()
    assert body["decision"] == "rejected"
    assert body["rejection_field_ids"] == [addr_row["id"]]

    # 4. Reload — override + rejection + reason all survive.
    final = client.get(f"/api/submissions/{new_id}").json()
    assert final["status"] == "rejected"
    assert final["review"]["decision"] == "rejected"
    assert final["review"]["comment"] == "Address mismatch flagged during audit."
    assert final["review"]["rejection_field_ids"] == [addr_row["id"]]
    addr_final = next(
        f
        for g in final["groups"]
        for f in g["fields"]
        if f["field"] == "producer_address"
    )
    assert addr_final["effective_verdict"] == "fail"
    assert addr_final["model_verdict"] == "pass"
    assert addr_final["override"]["override_verdict"] == "fail"


def test_e2e_reject_with_passing_field_id_is_allowed_without_override(
    client, db_session, mock_extract, isolated_image_dir, inline_processor
):
    """Locks in the actual contract: the reviewer can cite a field as a
    rejection reason even if the model passed it AND no override-to-fail
    exists. The reviewer's judgment is authoritative — see
    `app/api/decisions.py` docstring and `tests/api/test_decisions_reject_validation.py`.

    The override-to-fail path tested above is the *recommended* workflow when
    the reviewer disagrees with the model, but it isn't a hard precondition.
    """
    upload = client.post(
        "/api/submissions",
        files={"image": ("label.jpg", io.BytesIO(_real_jpeg()), "image/jpeg")},
        data={"expected_values": json.dumps(_matching_expected())},
    )
    new_id = upload.json()["id"]
    client.post("/api/submissions/start")

    detail = client.get(f"/api/submissions/{new_id}").json()
    a_passing_row = next(
        f for g in detail["groups"] for f in g["fields"] if f["effective_verdict"] == "pass"
    )
    response = client.post(
        f"/api/submissions/{new_id}/decision",
        json={
            "decision": "rejected",
            "comment": "reviewer override of the model's pass verdict",
            "rejection_field_ids": [a_passing_row["id"]],
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["rejection_field_ids"] == [a_passing_row["id"]]
