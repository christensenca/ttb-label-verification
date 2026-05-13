"""Decision API: POST /api/submissions/{id}/decision (T038, US1).

Approve / reject an item. Decisions are final in v1.

Reject contract per `contracts/api.md`:
- non-empty `rejection_field_ids` required
- every id must reference a comparison row on this submission
- each referenced comparison's **effective verdict** must be `fail`
  (i.e., model verdict == "fail" AND no `field_overrides` row exists that
  flips it to "pass")
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.schemas import DecisionIn, DecisionOut
from app.db.models import Comparison, FieldOverride, Review, Submission
from app.db.session import get_db

router = APIRouter(prefix="/api", tags=["decisions"])


@router.post(
    "/submissions/{submission_id}/decision",
    response_model=DecisionOut,
)
def create_decision(
    submission_id: uuid.UUID,
    payload: DecisionIn,
    db: Session = Depends(get_db),
) -> DecisionOut:
    sub = db.get(Submission, submission_id)
    if sub is None:
        raise HTTPException(status_code=404, detail="submission not found")

    if sub.status not in {"ready_for_review", "extraction_failed"}:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"submission is in status '{sub.status}'; decision not allowed",
        )

    existing = (
        db.execute(select(Review).where(Review.submission_id == sub.id))
        .scalars()
        .first()
    )
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="decision already recorded for this submission",
        )

    if payload.decision == "rejected":
        ids = payload.rejection_field_ids or []
        # All ids must belong to comparisons on this submission and have
        # effective verdict = fail.
        comparisons = (
            db.execute(
                select(Comparison).where(
                    Comparison.submission_id == sub.id,
                    Comparison.id.in_(ids),
                )
            )
            .scalars()
            .all()
        )
        comparisons_by_id = {c.id: c for c in comparisons}
        missing = [str(i) for i in ids if i not in comparisons_by_id]
        if missing:
            raise HTTPException(
                status_code=400,
                detail=f"unknown rejection_field_ids: {missing}",
            )
        # Effective verdict check
        overrides = (
            db.execute(
                select(FieldOverride).where(FieldOverride.submission_id == sub.id)
            )
            .scalars()
            .all()
        )
        override_by_field = {o.field: o for o in overrides}
        for c in comparisons:
            ov = override_by_field.get(c.field)
            effective = ov.override_verdict if ov else c.verdict
            if effective != "fail":
                raise HTTPException(
                    status_code=400,
                    detail=(
                        f"comparison {c.id} (field={c.field}) has effective "
                        f"verdict '{effective}', cannot be used as rejection reason"
                    ),
                )

    review = Review(
        submission_id=sub.id,
        decision=payload.decision,
        comment=payload.comment,
        rejection_field_ids=(
            [str(i) for i in payload.rejection_field_ids]
            if payload.rejection_field_ids
            else None
        ),
    )
    sub.status = payload.decision
    db.add(review)
    db.flush()
    db.refresh(review)

    return DecisionOut(
        decision=review.decision,  # type: ignore[arg-type]
        comment=review.comment,
        rejection_field_ids=(
            [uuid.UUID(s) for s in review.rejection_field_ids]
            if review.rejection_field_ids
            else None
        ),
        created_at=review.created_at,
    )
