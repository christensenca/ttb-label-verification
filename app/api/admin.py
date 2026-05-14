"""Admin API: destructive reset of the shared demo state (T078, US6).

Per contracts/api.md § Admin:
- POST /api/admin/reset wipes user submissions, resets fixtures to `loaded`,
  and clears all dependent rows (extractions, comparisons, overrides, reviews).
- Requires `{"confirm": true}` in the body; any other shape is rejected.

The endpoint runs the whole reset inside a single DB transaction. Filesystem
image deletion happens after the transaction body but inside the same request;
fixture image keys are deliberately left in place so the next `Start` can read
them without re-seeding.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends
from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from app.api.schemas import AdminResetIn, AdminResetOut
from app.config import get_settings
from app.db.models import Comparison, Extraction, FieldOverride, Review, Submission
from app.db.session import get_db
from app.services.storage import FilesystemImageStore

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.post("/reset", response_model=AdminResetOut)
def reset_demo(
    payload: AdminResetIn,
    db: Session = Depends(get_db),
) -> AdminResetOut:
    # Collect the image keys we need to clean up from disk BEFORE we delete
    # the rows. Fixture keys stay on disk so subsequent Start runs find them.
    user_keys: list[str] = list(
        db.execute(
            select(Submission.image_key).where(Submission.is_fixture.is_(False))
        )
        .scalars()
        .all()
    )

    fixture_ids: list = list(
        db.execute(select(Submission.id).where(Submission.is_fixture.is_(True)))
        .scalars()
        .all()
    )

    # Delete user submissions; FK cascades clean dependents.
    deleted_user = db.execute(
        delete(Submission).where(Submission.is_fixture.is_(False))
    ).rowcount or 0

    # Clear dependent rows for fixtures and reset their status.
    if fixture_ids:
        db.execute(
            delete(Extraction).where(Extraction.submission_id.in_(fixture_ids))
        )
        db.execute(
            delete(Comparison).where(Comparison.submission_id.in_(fixture_ids))
        )
        db.execute(
            delete(FieldOverride).where(
                FieldOverride.submission_id.in_(fixture_ids)
            )
        )
        db.execute(delete(Review).where(Review.submission_id.in_(fixture_ids)))
        db.execute(
            update(Submission)
            .where(Submission.is_fixture.is_(True))
            .values(status="loaded")
        )

    db.flush()

    # Best-effort filesystem cleanup for user images. Errors here are logged
    # but do not roll back the DB reset — the next Start has nothing to read
    # for the deleted rows anyway.
    #
    # Storage is content-addressed (sha256), so a user-uploaded byte-identical
    # copy of a fixture image shares the fixture's image_key. Only delete keys
    # that no remaining submission references, or we'd unlink the fixture's
    # backing file too.
    still_referenced = set(
        db.execute(
            select(Submission.image_key).where(Submission.image_key.in_(user_keys))
        )
        .scalars()
        .all()
    )
    store = FilesystemImageStore(get_settings().image_storage_dir)
    for key in user_keys:
        if key in still_referenced:
            continue
        try:
            store.delete(key)
        except Exception:
            logger.exception("admin reset: failed to delete image key %s", key)

    return AdminResetOut(
        deleted_submissions=int(deleted_user),
        restored_fixtures=len(fixture_ids),
    )
