"""Submissions API: list, start, detail, image (T034–T037, US1)."""

from __future__ import annotations

import mimetypes
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.schemas import (
    FIELD_GROUPS,
    ExpectedValues,
    ExtractionOut,
    ExtractionTokens,
    FieldGroupOut,
    FieldRowOut,
    OverrideOut,
    ReviewOut,
    StartOut,
    SubmissionDetailOut,
    SubmissionListItem,
)
from app.config import get_settings
from app.db.models import Comparison, Extraction, FieldOverride, Review, Submission
from app.db.session import get_db
from app.services import processor
from app.services.storage import FilesystemImageStore

router = APIRouter(prefix="/api", tags=["submissions"])


# --- List ------------------------------------------------------------------


@router.get("/submissions", response_model=list[SubmissionListItem])
def list_submissions(db: Session = Depends(get_db)) -> list[SubmissionListItem]:
    rows = (
        db.execute(select(Submission).order_by(Submission.created_at.desc()))
        .scalars()
        .all()
    )
    items: list[SubmissionListItem] = []
    for sub in rows:
        has_error = False
        if sub.status == "extraction_failed":
            has_error = True
        else:
            ext = (
                db.execute(
                    select(Extraction).where(Extraction.submission_id == sub.id)
                )
                .scalars()
                .first()
            )
            if ext is not None and ext.error is not None:
                has_error = True
        items.append(
            SubmissionListItem(
                id=sub.id,
                status=sub.status,  # type: ignore[arg-type]
                brand=str(sub.expected_values.get("brand", "")),
                is_fixture=sub.is_fixture,
                created_at=sub.created_at,
                thumbnail_url=f"/api/submissions/{sub.id}/image",
                has_extraction_error=has_error,
            )
        )
    return items


# --- Start -----------------------------------------------------------------


@router.post("/submissions/start", response_model=StartOut)
async def start(db: Session = Depends(get_db)):
    """Flip every loaded row to processing and schedule extraction.

    Defined `async` so `asyncio.create_task(...)` inside `_schedule_processing`
    targets the main event loop. With a sync handler in FastAPI's threadpool
    the scheduled tasks would race against the request's own row locks and
    deadlock. The handler returns immediately; the queued tasks run after
    the request's session commits and releases its locks.
    """
    from fastapi.responses import JSONResponse

    ids = processor.process_all_loaded(db)
    body = StartOut(scheduled=len(ids), submission_ids=ids)
    status_code = (
        status.HTTP_202_ACCEPTED if ids else status.HTTP_200_OK
    )
    return JSONResponse(content=body.model_dump(mode="json"), status_code=status_code)


# --- Detail ----------------------------------------------------------------


def _build_field_row(
    cmp: Comparison,
    override: FieldOverride | None,
    confidence: str | None,
) -> FieldRowOut:
    effective_verdict = override.override_verdict if override else cmp.verdict
    override_dto: OverrideOut | None = None
    if override is not None:
        override_dto = OverrideOut(
            field=override.field,
            original_verdict=override.original_verdict,  # type: ignore[arg-type]
            override_verdict=override.override_verdict,  # type: ignore[arg-type]
            comment=override.comment,
            created_at=override.created_at,
        )
    return FieldRowOut(
        id=cmp.id,
        field=cmp.field,
        extracted_value=cmp.extracted_value,
        expected_value=cmp.expected_value,
        model_verdict=cmp.verdict,  # type: ignore[arg-type]
        effective_verdict=effective_verdict,  # type: ignore[arg-type]
        rule=cmp.rule,
        reason=cmp.reason,
        confidence=confidence,  # type: ignore[arg-type]
        diff_extracted=cmp.diff_extracted,  # type: ignore[arg-type]
        diff_expected=cmp.diff_expected,  # type: ignore[arg-type]
        override=override_dto,
    )


@router.get("/submissions/{submission_id}", response_model=SubmissionDetailOut)
def get_submission(
    submission_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> SubmissionDetailOut:
    sub = db.get(Submission, submission_id)
    if sub is None:
        raise HTTPException(status_code=404, detail="submission not found")

    extraction_row = (
        db.execute(select(Extraction).where(Extraction.submission_id == sub.id))
        .scalars()
        .first()
    )
    comparisons = (
        db.execute(select(Comparison).where(Comparison.submission_id == sub.id))
        .scalars()
        .all()
    )
    overrides = (
        db.execute(
            select(FieldOverride).where(FieldOverride.submission_id == sub.id)
        )
        .scalars()
        .all()
    )
    review_row = (
        db.execute(select(Review).where(Review.submission_id == sub.id))
        .scalars()
        .first()
    )

    extraction_dto: ExtractionOut | None = None
    if extraction_row is not None:
        extraction_dto = ExtractionOut(
            model=extraction_row.model,
            latency_ms=extraction_row.latency_ms,
            tokens=ExtractionTokens(
                input=extraction_row.input_tokens,
                output=extraction_row.output_tokens,
            ),
            error=extraction_row.error,
        )

    groups: list[FieldGroupOut] = []
    if comparisons:
        confidence_map: dict[str, str | None] = (
            dict(extraction_row.field_confidence)  # type: ignore[arg-type]
            if extraction_row is not None and extraction_row.field_confidence
            else {}
        )
        cmp_by_field = {c.field: c for c in comparisons}
        override_by_field = {o.field: o for o in overrides}
        for group_name, fields in FIELD_GROUPS:
            rows = []
            for field in fields:
                cmp = cmp_by_field.get(field)
                if cmp is None:
                    continue
                conf = confidence_map.get(field)
                rows.append(_build_field_row(cmp, override_by_field.get(field), conf))
            groups.append(FieldGroupOut(name=group_name, fields=rows))  # type: ignore[arg-type]

    review_dto: ReviewOut | None = None
    if review_row is not None:
        review_dto = ReviewOut(
            decision=review_row.decision,  # type: ignore[arg-type]
            comment=review_row.comment,
            rejection_field_ids=(
                [uuid.UUID(s) for s in review_row.rejection_field_ids]
                if review_row.rejection_field_ids
                else None
            ),
            created_at=review_row.created_at,
        )

    return SubmissionDetailOut(
        id=sub.id,
        status=sub.status,  # type: ignore[arg-type]
        is_fixture=sub.is_fixture,
        created_at=sub.created_at,
        image_url=f"/api/submissions/{sub.id}/image",
        expected_values=ExpectedValues.model_validate(sub.expected_values),
        extraction=extraction_dto,
        groups=groups,
        review=review_dto,
    )


# --- Image -----------------------------------------------------------------


@router.get("/submissions/{submission_id}/image")
def get_image(submission_id: uuid.UUID, db: Session = Depends(get_db)) -> StreamingResponse:
    sub = db.get(Submission, submission_id)
    if sub is None:
        raise HTTPException(status_code=404, detail="submission not found")
    store = FilesystemImageStore(get_settings().image_storage_dir)
    try:
        fh = store.open(sub.image_key)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="image not found")

    # Best-effort content-type from the key suffix (e.g. "sha256:abc.jpg").
    suffix = sub.image_key.rsplit(".", 1)[-1].lower()
    content_type = mimetypes.types_map.get(f".{suffix}", "application/octet-stream")
    if suffix == "jpg":
        content_type = "image/jpeg"

    return StreamingResponse(fh, media_type=content_type)
