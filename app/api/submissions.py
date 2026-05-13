"""Submissions API: list, start, create, detail, image (T034–T037, T057)."""

from __future__ import annotations

import io
import json
import mimetypes
import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import StreamingResponse
from PIL import Image, UnidentifiedImageError
from pydantic import ValidationError
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
    SubmissionCreateOut,
    SubmissionDetailOut,
    SubmissionListItem,
)
from app.config import get_settings
from app.db.models import Comparison, Extraction, FieldOverride, Review, Submission
from app.db.session import get_db
from app.services import processor
from app.services.storage import FilesystemImageStore

router = APIRouter(prefix="/api", tags=["submissions"])

MAX_IMAGE_BYTES = 10 * 1024 * 1024  # 10 MB per contracts/api.md
MAX_IMAGE_PIXELS = 40_000_000  # 40 MP — far above any realistic label photo
_UPLOAD_CHUNK = 64 * 1024


async def _read_capped(upload: UploadFile, max_bytes: int) -> bytes:
    """Read an UploadFile in chunks, aborting as soon as `max_bytes` is exceeded.

    Prevents an attacker from forcing the server to buffer multi-GB requests
    just to learn we'd reject them after the fact.
    """
    buf = bytearray()
    while True:
        chunk = await upload.read(_UPLOAD_CHUNK)
        if not chunk:
            break
        buf.extend(chunk)
        if len(buf) > max_bytes:
            raise HTTPException(
                status_code=400,
                detail=f"image exceeds {max_bytes // (1024 * 1024)} MB limit",
            )
    return bytes(buf)


def _matches_magic(content: bytes, content_type: str) -> bool:
    """Verify the byte signature matches the client-declared content type.

    Defense against an attacker uploading arbitrary bytes (e.g., an
    executable) under a permitted image content-type.
    """
    if content_type in {"image/jpeg", "image/jpg"}:
        return content.startswith(b"\xff\xd8\xff")
    if content_type == "image/png":
        return content.startswith(b"\x89PNG\r\n\x1a\n")
    if content_type == "image/webp":
        return content.startswith(b"RIFF") and content[8:12] == b"WEBP"
    return False


def _validate_image_bytes(content: bytes) -> None:
    """Decode the image headers via Pillow and enforce a pixel-count cap.

    `Image.verify()` parses headers and catches corrupt/truncated payloads
    without decoding the pixel data. The pixel-count cap blocks
    decompression-bomb images that claim huge dimensions in a small file.
    """
    try:
        with Image.open(io.BytesIO(content)) as img:
            img.verify()
        with Image.open(io.BytesIO(content)) as img:
            width, height = img.size
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise HTTPException(
            status_code=400, detail=f"invalid image: {exc}"
        ) from exc
    if width * height > MAX_IMAGE_PIXELS:
        raise HTTPException(
            status_code=400,
            detail=(
                f"image dimensions {width}x{height} exceed pixel limit "
                f"({MAX_IMAGE_PIXELS:,} px)"
            ),
        )


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


# --- Create ----------------------------------------------------------------


_ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/jpg", "image/png", "image/webp"}


@router.post(
    "/submissions",
    response_model=SubmissionCreateOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_submission(
    image: UploadFile | None = File(default=None),
    expected_values: str | None = Form(default=None),
    db: Session = Depends(get_db),
) -> SubmissionCreateOut:
    if image is None or not image.filename:
        raise HTTPException(status_code=400, detail="image file is required")
    if expected_values is None:
        raise HTTPException(status_code=400, detail="expected_values is required")

    content_type = (image.content_type or "").lower()
    if content_type not in _ALLOWED_IMAGE_TYPES:
        raise HTTPException(
            status_code=415,
            detail=f"unsupported image content type: {content_type or 'unknown'}",
        )

    content = await _read_capped(image, MAX_IMAGE_BYTES)
    if not content:
        raise HTTPException(status_code=400, detail="image file is empty")

    if not _matches_magic(content, content_type):
        raise HTTPException(
            status_code=400,
            detail=f"file bytes do not match declared content type {content_type}",
        )

    _validate_image_bytes(content)

    try:
        parsed = json.loads(expected_values)
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=400, detail=f"expected_values is not valid JSON: {exc.msg}"
        ) from exc

    try:
        validated = ExpectedValues.model_validate(parsed)
    except ValidationError as exc:
        first = exc.errors()[0]
        loc = ".".join(str(p) for p in first.get("loc", ()))
        msg = first.get("msg", "validation error")
        detail = f"{loc}: {msg}" if loc else msg
        raise HTTPException(status_code=400, detail=detail) from exc

    store = FilesystemImageStore(get_settings().image_storage_dir)
    image_key = store.put(content, content_type)

    sub = Submission(
        image_key=image_key,
        expected_values=validated.model_dump(),
        status="loaded",
        is_fixture=False,
    )
    db.add(sub)
    db.flush()
    db.refresh(sub)
    return SubmissionCreateOut(id=sub.id, status=sub.status)  # type: ignore[arg-type]


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
