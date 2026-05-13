"""Decision API: POST /api/submissions/{id}/decision (T038, US1).

Approve / reject an item. Decisions are final in v1.

Reject contract per `contracts/api.md`:
- non-empty `rejection_field_ids` required
- every id must reference a comparison row on this submission

Reviewers can cite any field as a rejection reason — including fields the model
marked as `pass`. This lets a reviewer flag a problem the model missed.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.schemas import DecisionIn, DecisionOut
from app.db.models import Comparison, Review, Submission
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
        # Every id must reference a comparison row on this submission. The
        # reviewer may cite any field — including ones the model passed —
        # so we don't filter on verdict here.
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
        found_ids = {c.id for c in comparisons}
        missing = [str(i) for i in ids if i not in found_ids]
        if missing:
            raise HTTPException(
                status_code=400,
                detail=f"unknown rejection_field_ids: {missing}",
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
