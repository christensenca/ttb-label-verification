"""Field-level override API (T069, T070, US4).

Per contracts/api.md:
- POST /api/submissions/{id}/overrides — UPSERT one override row per field.
- DELETE /api/submissions/{id}/overrides/{field} — remove an override.

Override is only writable while the submission is in `ready_for_review` or
`extraction_failed`. Once a decision is recorded (`approved` / `rejected`)
the override surface freezes alongside the row.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.schemas import ALL_FIELDS, OverrideIn, OverrideOut
from app.db.models import Comparison, FieldOverride, Submission
from app.db.session import get_db

router = APIRouter(prefix="/api", tags=["overrides"])

_KNOWN_FIELDS = set(ALL_FIELDS)
_WRITEABLE_STATUSES = {"ready_for_review", "extraction_failed"}


@router.post(
    "/submissions/{submission_id}/overrides",
    response_model=OverrideOut,
)
def create_override(
    submission_id: uuid.UUID,
    payload: OverrideIn,
    db: Session = Depends(get_db),
) -> OverrideOut:
    sub = db.get(Submission, submission_id)
    if sub is None:
        raise HTTPException(status_code=404, detail="submission not found")

    if sub.status not in _WRITEABLE_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"submission is in status '{sub.status}'; "
                "overrides are only writable while status is "
                "ready_for_review or extraction_failed"
            ),
        )

    if payload.field not in _KNOWN_FIELDS:
        raise HTTPException(
            status_code=400, detail=f"unknown field: {payload.field!r}"
        )

    cmp = (
        db.execute(
            select(Comparison).where(
                Comparison.submission_id == sub.id,
                Comparison.field == payload.field,
            )
        )
        .scalars()
        .first()
    )
    if cmp is None:
        # The submission has comparisons but none for this field — treat as
        # bad input rather than a 404 (the field name is known to the
        # system, just not present on this submission).
        raise HTTPException(
            status_code=400,
            detail=f"no comparison row for field {payload.field!r} on this submission",
        )

    # UPSERT: delete the old row (if any) and insert a new one, in one tx.
    existing = (
        db.execute(
            select(FieldOverride).where(
                FieldOverride.submission_id == sub.id,
                FieldOverride.field == payload.field,
            )
        )
        .scalars()
        .first()
    )
    if existing is not None:
        db.delete(existing)
        db.flush()

    override = FieldOverride(
        submission_id=sub.id,
        field=payload.field,
        original_verdict=cmp.verdict,
        override_verdict=payload.override_verdict,
        comment=payload.comment,
    )
    db.add(override)
    db.flush()
    db.refresh(override)

    return OverrideOut(
        field=override.field,
        original_verdict=override.original_verdict,  # type: ignore[arg-type]
        override_verdict=override.override_verdict,  # type: ignore[arg-type]
        comment=override.comment,
        created_at=override.created_at,
    )


@router.delete(
    "/submissions/{submission_id}/overrides/{field}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_override(
    submission_id: uuid.UUID,
    field: str,
    db: Session = Depends(get_db),
) -> Response:
    sub = db.get(Submission, submission_id)
    if sub is None:
        raise HTTPException(status_code=404, detail="submission not found")

    existing = (
        db.execute(
            select(FieldOverride).where(
                FieldOverride.submission_id == sub.id,
                FieldOverride.field == field,
            )
        )
        .scalars()
        .first()
    )
    if existing is None:
        raise HTTPException(
            status_code=404,
            detail=f"no override found for field {field!r} on this submission",
        )
    db.delete(existing)
    db.flush()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
