"""Contract tests for POST /api/admin/reset (T077, US6).

Covers the contract from specs/001-verify-and-review/contracts/api.md:
- missing/false `confirm` → 400
- valid request deletes user submissions (and cascades)
- valid request resets fixture submissions to status='loaded' and clears
  their extractions/comparisons/overrides/reviews
- user image keys are deleted from storage; fixture image keys remain
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.config import get_settings
from app.db.models import (
    Comparison,
    Extraction,
    FieldOverride,
    Review,
    Submission,
)
from app.services.storage import FilesystemImageStore


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


def _make_submission(
    db_session,
    *,
    is_fixture: bool,
    status_value: str = "ready_for_review",
    image_key: str = "sha256:test.jpg",
) -> Submission:
    sub = Submission(
        image_key=image_key,
        expected_values=_expected(),
        status=status_value,
        is_fixture=is_fixture,
    )
    db_session.add(sub)
    db_session.flush()
    return sub


def _attach_extraction(db_session, sub: Submission) -> Extraction:
    ext = Extraction(
        submission_id=sub.id,
        extracted_label={"brand": "Don Julio"},
        field_confidence={"brand": "hi"},
        latency_ms=1000,
        input_tokens=100,
        output_tokens=20,
        model="test-model/mock",
    )
    db_session.add(ext)
    db_session.flush()
    return ext


def _attach_comparisons(db_session, sub: Submission) -> list[Comparison]:
    rows = []
    for field, verdict in [
        ("brand", "fail"),
        ("class_type", "pass"),
    ]:
        cmp = Comparison(
            submission_id=sub.id,
            field=field,
            verdict=verdict,
            rule="ok",
            extracted_value="x",
            expected_value="x",
            reason="ok",
        )
        db_session.add(cmp)
        rows.append(cmp)
    db_session.flush()
    return rows


def _attach_override(db_session, sub: Submission) -> FieldOverride:
    ov = FieldOverride(
        submission_id=sub.id,
        field="brand",
        original_verdict="fail",
        override_verdict="pass",
        comment="reviewer override",
    )
    db_session.add(ov)
    db_session.flush()
    return ov


def _attach_review(
    db_session, sub: Submission, *, decision: str = "approved"
) -> Review:
    rev = Review(
        submission_id=sub.id,
        decision=decision,
        comment="looks good",
        rejection_field_ids=None,
    )
    db_session.add(rev)
    db_session.flush()
    return rev


def test_reset_without_confirm_returns_400(client, db_session):
    response = client.post("/api/admin/reset", json={})
    assert response.status_code in (400, 422), response.text


def test_reset_with_confirm_false_returns_400(client, db_session):
    response = client.post("/api/admin/reset", json={"confirm": False})
    assert response.status_code in (400, 422), response.text


def test_reset_deletes_user_submissions_and_resets_fixtures(client, db_session):
    fixture = _make_submission(
        db_session,
        is_fixture=True,
        status_value="approved",
        image_key="sha256:fixture.jpg",
    )
    _attach_extraction(db_session, fixture)
    _attach_comparisons(db_session, fixture)
    _attach_override(db_session, fixture)
    _attach_review(db_session, fixture, decision="approved")

    user_sub = _make_submission(
        db_session,
        is_fixture=False,
        status_value="rejected",
        image_key="sha256:user.jpg",
    )
    _attach_extraction(db_session, user_sub)
    _attach_comparisons(db_session, user_sub)
    _attach_review(db_session, user_sub, decision="rejected")

    response = client.post("/api/admin/reset", json={"confirm": True})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["deleted_submissions"] == 1
    assert body["restored_fixtures"] == 1

    db_session.expire_all()
    # User submission gone, and its dependents are gone (FK cascade).
    assert db_session.get(Submission, user_sub.id) is None
    assert (
        db_session.query(Extraction).filter_by(submission_id=user_sub.id).count()
        == 0
    )
    assert (
        db_session.query(Comparison).filter_by(submission_id=user_sub.id).count()
        == 0
    )
    assert (
        db_session.query(Review).filter_by(submission_id=user_sub.id).count() == 0
    )

    # Fixture submission remains, but is reset to `loaded` and child rows are gone.
    fixture_after = db_session.get(Submission, fixture.id)
    assert fixture_after is not None
    assert fixture_after.status == "loaded"
    assert (
        db_session.query(Extraction).filter_by(submission_id=fixture.id).count()
        == 0
    )
    assert (
        db_session.query(Comparison).filter_by(submission_id=fixture.id).count()
        == 0
    )
    assert (
        db_session.query(FieldOverride).filter_by(submission_id=fixture.id).count()
        == 0
    )
    assert db_session.query(Review).filter_by(submission_id=fixture.id).count() == 0


def test_reset_deletes_user_image_keys_but_leaves_fixture_keys(
    client, db_session, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    # Point the FilesystemImageStore at an isolated dir for this test.
    settings = get_settings()
    monkeypatch.setattr(settings, "image_storage_dir", tmp_path, raising=False)

    store = FilesystemImageStore(tmp_path)
    fixture_key = store.put(b"\xff\xd8\xff fixture bytes", "image/jpeg")
    user_key = store.put(b"\xff\xd8\xff user bytes------", "image/jpeg")
    assert (tmp_path / fixture_key).exists()
    assert (tmp_path / user_key).exists()

    _make_submission(
        db_session, is_fixture=True, status_value="loaded", image_key=fixture_key
    )
    _make_submission(
        db_session,
        is_fixture=False,
        status_value="ready_for_review",
        image_key=user_key,
    )

    response = client.post("/api/admin/reset", json={"confirm": True})
    assert response.status_code == 200, response.text

    assert (tmp_path / fixture_key).exists(), "fixture image must remain"
    assert not (tmp_path / user_key).exists(), "user image must be deleted"


def test_reset_with_no_submissions_returns_zeros(client, db_session):
    response = client.post("/api/admin/reset", json={"confirm": True})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["deleted_submissions"] == 0
    assert body["restored_fixtures"] == 0
