"""End-to-end: upload → process (one field fails) → override fail→pass → approve.

This is the "changing pass status (fail→pass)" deploy-readiness gate. The
extractor's verdict on `brand` is wrong; the reviewer flips it to pass with a
comment, then approves. After reload, the override and the approval both
persist, and the original model verdict is still visible alongside the
effective verdict.
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


def _expected_with_wrong_brand() -> dict:
    """Force a brand mismatch against mock_extract's Don Julio default."""
    return {
        "brand": "WRONG BRAND",
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


def test_e2e_override_fail_to_pass_then_approve(
    client, db_session, mock_extract, isolated_image_dir, inline_processor
):
    # 1. Upload with an intentionally-wrong `brand` so the comparison fails.
    upload = client.post(
        "/api/submissions",
        files={"image": ("label.jpg", io.BytesIO(_real_jpeg()), "image/jpeg")},
        data={"expected_values": json.dumps(_expected_with_wrong_brand())},
    )
    assert upload.status_code == 201, upload.text
    new_id = upload.json()["id"]

    # 2. Process it.
    start = client.post("/api/submissions/start")
    assert start.status_code == 202, start.text
    assert new_id in start.json()["submission_ids"]

    # 3. Confirm brand failed and the diff helper populated the highlight tokens.
    detail = client.get(f"/api/submissions/{new_id}").json()
    assert detail["status"] == "ready_for_review"
    brand_row = next(
        f for g in detail["groups"] for f in g["fields"] if f["field"] == "brand"
    )
    assert brand_row["effective_verdict"] == "fail"
    assert brand_row["model_verdict"] == "fail"
    assert brand_row["override"] is None
    # word-diff tokens are returned only on failing text fields per the contract.
    assert brand_row["diff_extracted"] is not None
    assert brand_row["diff_expected"] is not None

    # 4. Override `brand` to pass with a comment.
    override = client.post(
        f"/api/submissions/{new_id}/overrides",
        json={
            "field": "brand",
            "override_verdict": "pass",
            "comment": "Brand on the label actually matches; extractor read it wrong.",
        },
    )
    assert override.status_code == 200, override.text

    # Effective verdict flips to pass while the model verdict stays "fail".
    detail2 = client.get(f"/api/submissions/{new_id}").json()
    brand_row2 = next(
        f for g in detail2["groups"] for f in g["fields"] if f["field"] == "brand"
    )
    assert brand_row2["effective_verdict"] == "pass"
    assert brand_row2["model_verdict"] == "fail"
    assert brand_row2["override"] is not None
    assert brand_row2["override"]["override_verdict"] == "pass"
    assert brand_row2["override"]["original_verdict"] == "fail"
    assert "extractor read it wrong" in brand_row2["override"]["comment"]

    # 5. With the only failing field now overridden, approve goes through cleanly.
    approve = client.post(
        f"/api/submissions/{new_id}/decision",
        json={"decision": "approved", "comment": "reviewed and verified by hand"},
    )
    assert approve.status_code == 200, approve.text

    # 6. Reload — every part of the audit trail is preserved.
    final = client.get(f"/api/submissions/{new_id}").json()
    assert final["status"] == "approved"
    assert final["review"]["decision"] == "approved"
    assert final["review"]["comment"] == "reviewed and verified by hand"
    brand_row3 = next(
        f for g in final["groups"] for f in g["fields"] if f["field"] == "brand"
    )
    assert brand_row3["effective_verdict"] == "pass"
    assert brand_row3["model_verdict"] == "fail"
    assert brand_row3["override"]["override_verdict"] == "pass"


def test_e2e_override_then_remove_reverts_effective_verdict(
    client, db_session, mock_extract, isolated_image_dir, inline_processor
):
    """The 'Remove override' affordance: DELETE flips the effective verdict
    back to the model's verdict and the comparison row's `override` clears."""
    upload = client.post(
        "/api/submissions",
        files={"image": ("label.jpg", io.BytesIO(_real_jpeg()), "image/jpeg")},
        data={"expected_values": json.dumps(_expected_with_wrong_brand())},
    )
    new_id = upload.json()["id"]
    client.post("/api/submissions/start")

    client.post(
        f"/api/submissions/{new_id}/overrides",
        json={"field": "brand", "override_verdict": "pass", "comment": "see above"},
    )
    assert (
        client.get(f"/api/submissions/{new_id}")
        .json()["groups"][0]["fields"][0]["effective_verdict"]
    ) is not None

    # Remove the override.
    deleted = client.delete(f"/api/submissions/{new_id}/overrides/brand")
    assert deleted.status_code == 204, deleted.text

    detail = client.get(f"/api/submissions/{new_id}").json()
    brand_row = next(
        f for g in detail["groups"] for f in g["fields"] if f["field"] == "brand"
    )
    assert brand_row["override"] is None
    assert brand_row["effective_verdict"] == "fail"  # reverted to model's verdict
