"""Submissions API: list, start, create, detail, image (T034–T037, T057)."""

from __future__ import annotations

import csv
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
    BulkCreateOut,
    BulkErrorOut,
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
from app.services.reviews import compute_effective_verdict
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


def _detect_image_type(content: bytes) -> str | None:
    """Return the canonical content-type derived from the file's magic bytes.

    Trusting the bytes (not the client-declared content-type) is both more
    secure — an attacker can lie about the content-type to smuggle arbitrary
    bytes through — and more forgiving of real-world uploads where the file
    extension or browser-supplied MIME doesn't match the actual format
    (e.g., a PNG saved with a .jpg extension).
    """
    if content.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if content.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if content.startswith(b"RIFF") and content[8:12] == b"WEBP":
        return "image/webp"
    return None


def _check_image_content(content: bytes) -> tuple[str | None, str | None]:
    """Run every post-read image check.

    Returns ``(detected_content_type, error_message)``. On success the
    detected type is non-None and the error is None; on failure the detected
    type is None and the error explains why. Combines: empty-body, magic-byte
    detection, Pillow header decode (catches corrupt/truncated images), and
    a pixel-count cap that blocks decompression-bomb images claiming huge
    dimensions in a small file.
    """
    if not content:
        return None, "image file is empty"
    detected = _detect_image_type(content)
    if detected is None:
        return None, "file is not a recognized image (expected JPEG, PNG, or WebP)"
    try:
        with Image.open(io.BytesIO(content)) as img:
            img.verify()
        with Image.open(io.BytesIO(content)) as img:
            width, height = img.size
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        return None, f"invalid image: {exc}"
    if width * height > MAX_IMAGE_PIXELS:
        return None, (
            f"image dimensions {width}x{height} exceed pixel limit "
            f"({MAX_IMAGE_PIXELS:,} px)"
        )
    return detected, None


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

    content = await _read_capped(image, MAX_IMAGE_BYTES)
    detected, err = _check_image_content(content)
    if err is not None:
        # 415 if we can't recognize the bytes as any supported image format,
        # 400 if the format is recognized but the file is corrupt or oversize.
        status_code = 400 if _detect_image_type(content) is not None else 415
        raise HTTPException(status_code=status_code, detail=err)
    assert detected is not None  # narrow for type checker
    content_type = detected

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


# --- Bulk create -----------------------------------------------------------


_CSV_HEADER = [
    "filename",
    "brand",
    "class_type",
    "alcohol_content",
    "net_contents",
    "producer_name",
    "producer_address",
    "is_imported",
    "country_of_origin",
]
MAX_CSV_BYTES = 1 * 1024 * 1024  # 1 MB — generous for a manifest
MAX_BULK_IMAGES = 100  # cap files per bulk POST to bound server memory
MAX_BULK_TOTAL_BYTES = 200 * 1024 * 1024  # 200 MB cap on the combined upload


def _coerce_bool(raw: str, field: str) -> bool:
    v = raw.strip().lower()
    if v in {"true", "1", "yes"}:
        return True
    if v in {"false", "0", "no", ""}:
        return False
    raise ValueError(f"{field}: expected true/false, got {raw!r}")


def _coerce_float(raw: str, field: str) -> float:
    try:
        return float(raw.strip())
    except ValueError as exc:
        raise ValueError(f"{field}: expected number, got {raw!r}") from exc


def _row_to_expected_values(row: dict[str, str]) -> ExpectedValues:
    """Map one CSV DictReader row to a validated ExpectedValues."""
    country_raw = (row.get("country_of_origin") or "").strip()
    payload = {
        "brand": (row.get("brand") or "").strip(),
        "class_type": (row.get("class_type") or "").strip(),
        "alcohol_content": _coerce_float(
            row.get("alcohol_content") or "", "alcohol_content"
        ),
        "net_contents": (row.get("net_contents") or "").strip(),
        "producer_name": (row.get("producer_name") or "").strip(),
        "producer_address": (row.get("producer_address") or "").strip(),
        "is_imported": _coerce_bool(row.get("is_imported") or "", "is_imported"),
        "country_of_origin": country_raw or None,
    }
    return ExpectedValues.model_validate(payload)


@router.post(
    "/submissions/bulk",
    response_model=BulkCreateOut,
    status_code=status.HTTP_200_OK,
)
async def create_submissions_bulk(
    csv_file: UploadFile | None = File(default=None, alias="csv"),
    images: list[UploadFile] | None = File(default=None),
    db: Session = Depends(get_db),
) -> BulkCreateOut:
    if csv_file is None or not csv_file.filename:
        raise HTTPException(status_code=400, detail="csv file is required")
    if not images:
        raise HTTPException(status_code=400, detail="at least one image is required")
    if len(images) > MAX_BULK_IMAGES:
        raise HTTPException(
            status_code=400,
            detail=(
                f"batch exceeds {MAX_BULK_IMAGES}-image limit "
                f"(got {len(images)})"
            ),
        )

    csv_bytes = await _read_capped(csv_file, MAX_CSV_BYTES)
    if not csv_bytes:
        raise HTTPException(status_code=400, detail="csv file is empty")

    try:
        text = csv_bytes.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise HTTPException(
            status_code=400, detail=f"csv must be UTF-8: {exc}"
        ) from exc

    reader = csv.DictReader(io.StringIO(text))
    if reader.fieldnames is None:
        raise HTTPException(status_code=400, detail="csv has no header row")
    missing = [c for c in _CSV_HEADER if c not in reader.fieldnames]
    if missing:
        raise HTTPException(
            status_code=400, detail=f"csv missing required columns: {missing}"
        )

    # Pre-read each image once, run the image-only validation, and key by
    # filename for matching. Skip the image bytes for any row that fails the
    # image check — that's reported as a row-level error.
    image_blobs: dict[str, tuple[bytes, str, str | None]] = {}
    errors: list[BulkErrorOut] = []
    total_bytes = 0
    for upload in images:
        name = upload.filename or ""
        if not name:
            errors.append(BulkErrorOut(filename=None, reason="upload without a filename"))
            continue
        if name in image_blobs:
            errors.append(
                BulkErrorOut(filename=name, reason="duplicate image filename in upload")
            )
            continue
        content = await _read_capped(upload, MAX_IMAGE_BYTES)
        total_bytes += len(content)
        if total_bytes > MAX_BULK_TOTAL_BYTES:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"batch exceeds {MAX_BULK_TOTAL_BYTES // (1024 * 1024)} MB "
                    "total upload limit"
                ),
            )
        detected, check = _check_image_content(content)
        image_blobs[name] = (content, detected or "", check)

    csv_filenames_seen: set[str] = set()
    used_filenames: set[str] = set()
    created: list[SubmissionCreateOut] = []
    store = FilesystemImageStore(get_settings().image_storage_dir)

    for idx, row in enumerate(reader, start=1):
        filename = (row.get("filename") or "").strip()
        if not filename:
            errors.append(BulkErrorOut(row=idx, reason="filename column is empty"))
            continue
        if filename in csv_filenames_seen:
            errors.append(
                BulkErrorOut(
                    row=idx, filename=filename, reason="duplicate filename in csv"
                )
            )
            continue
        csv_filenames_seen.add(filename)

        if filename not in image_blobs:
            errors.append(
                BulkErrorOut(
                    row=idx,
                    filename=filename,
                    reason="no uploaded image matches this filename",
                )
            )
            continue
        content, ct, image_err = image_blobs[filename]
        if image_err is not None:
            errors.append(
                BulkErrorOut(row=idx, filename=filename, reason=image_err)
            )
            used_filenames.add(filename)
            continue

        try:
            validated = _row_to_expected_values(row)
        except ValidationError as exc:
            first = exc.errors()[0]
            loc = ".".join(str(p) for p in first.get("loc", ()))
            msg = first.get("msg", "validation error")
            errors.append(
                BulkErrorOut(
                    row=idx,
                    filename=filename,
                    reason=f"{loc}: {msg}" if loc else msg,
                )
            )
            used_filenames.add(filename)
            continue
        except ValueError as exc:
            errors.append(BulkErrorOut(row=idx, filename=filename, reason=str(exc)))
            used_filenames.add(filename)
            continue

        image_key = store.put(content, ct)
        sub = Submission(
            image_key=image_key,
            expected_values=validated.model_dump(),
            status="loaded",
            is_fixture=False,
        )
        db.add(sub)
        db.flush()
        created.append(SubmissionCreateOut(id=sub.id, status=sub.status))  # type: ignore[arg-type]
        used_filenames.add(filename)

    for fname in image_blobs.keys() - used_filenames:
        errors.append(
            BulkErrorOut(filename=fname, reason="image not referenced in csv")
        )

    return BulkCreateOut(created=created, errors=errors)


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
    effective_verdict = compute_effective_verdict(cmp, override)
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
    except FileNotFoundError as err:
        raise HTTPException(status_code=404, detail="image not found") from err

    # Best-effort content-type from the key suffix (e.g. "sha256:abc.jpg").
    suffix = sub.image_key.rsplit(".", 1)[-1].lower()
    content_type = mimetypes.types_map.get(f".{suffix}", "application/octet-stream")
    if suffix == "jpg":
        content_type = "image/jpeg"

    return StreamingResponse(fh, media_type=content_type)
