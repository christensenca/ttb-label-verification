"""Background processing for submissions.

Per research R12: `process_all_loaded()` flips every `loaded` row to
`processing` in one SQL statement, then schedules N independent background
tasks (one per submission), each gated by a module-level
`asyncio.Semaphore(EXTRACTION_CONCURRENCY)`.

Per research R13: an extraction failure still writes one `Extraction` row
(with `error` populated, data columns null) and one synthesized `Comparison`
row per known field so the override / rejection APIs see uniform data.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any

from sqlalchemy import func, update
from sqlalchemy.orm import Session

import pipeline.extract as pipeline_extract
from app.api.schemas import ALL_FIELDS
from app.config import get_settings
from app.db.models import Comparison, Extraction, Submission
from app.db.session import SessionLocal
from app.services.diff import word_diff
from pipeline.compare import compare as pipeline_compare

logger = logging.getLogger(__name__)


# Fields with `extraction_confidence` reported by the model — these are the
# only text fields we run a word-diff against on failure.
_TEXT_FIELDS = {
    "brand",
    "class_type",
    "alcohol_content",
    "net_contents",
    "producer_name",
    "producer_address",
    "country_of_origin",
    "government_warning_text",
}

# Human-readable rule label per field for display alongside the verdict.
_RULE_BY_FIELD: dict[str, str] = {
    "brand": "fuzzy match ≥85%",
    "class_type": "fuzzy match ≥85% after class normalize",
    "producer_name": "fuzzy match ≥85% after role normalize",
    "producer_address": "fuzzy match ≥85% after state/country normalize",
    "alcohol_content": "numeric tolerance ±0.1%",
    "net_contents": "unit-aware comparison",
    "is_imported": "boolean equality",
    "country_of_origin": "normalized exact match",
    "government_warning_text": "TTB canonical text match",
    "government_warning_style": "TTB header/body weight check",
}


# Module-level semaphore created lazily so the loop is the running loop.
_semaphore: asyncio.Semaphore | None = None


def _get_semaphore() -> asyncio.Semaphore:
    global _semaphore
    if _semaphore is None:
        _semaphore = asyncio.Semaphore(get_settings().extraction_concurrency)
    return _semaphore


# --- Startup rescue --------------------------------------------------------


def rescue_processing_on_startup() -> int:
    """Flip any rows stuck in `processing` to `extraction_failed`.

    Anything left in `processing` at boot is from a previous run that died
    mid-flight; mark them failed so the queue is never stuck.
    """
    with SessionLocal() as session:
        ids = list(
            session.execute(
                update(Submission)
                .where(Submission.status == "processing")
                .values(status="extraction_failed")
                .returning(Submission.id)
            )
            .scalars()
            .all()
        )
        session.commit()
    if ids:
        logger.warning(
            "rescue: marked %d processing submissions as extraction_failed: %s",
            len(ids),
            ids,
        )
    return len(ids)


# --- Per-submission processing ---------------------------------------------


def _stringify(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str):
        return value
    return str(value)


def _resolve_image_path(image_key: str) -> Path:
    """Map an ImageStore key back to a filesystem path.

    The prototype uses `FilesystemImageStore`, so the key concatenates onto
    `IMAGE_STORAGE_DIR`. When the storage backend changes, this helper is
    where the abstraction grows (e.g. download Azure Blob to a temp file).
    """
    return Path(get_settings().image_storage_dir) / image_key


def process_submission(
    submission_id: uuid.UUID,
    *,
    session_factory: Callable[[], Session] | None = None,
    image_path: str | Path | None = None,
    extractor: Callable[..., pipeline_extract.ExtractionResult] | None = None,
) -> None:
    """Run pipeline.extract + compare + diff for one submission, persist rows.

    All writes for a successful extraction land in one transaction. On any
    error, a separate transaction writes the failure-shaped `Extraction`
    plus synthesized `Comparison` rows so the read-model stays uniform.
    """
    factory = session_factory or SessionLocal
    extractor_fn = extractor or pipeline_extract.extract
    owns_session = session_factory is None
    session = factory()
    try:
        sub = session.get(Submission, submission_id)
        if sub is None:
            logger.warning("processor: submission %s not found", submission_id)
            return

        resolved_image_path = image_path or _resolve_image_path(sub.image_key)
        expected = dict(sub.expected_values)

        try:
            result = extractor_fn(resolved_image_path)
        except Exception as exc:  # noqa: BLE001 — we want a wide net here
            logger.exception(
                "processor: extraction failed for %s", submission_id
            )
            _write_failure(session, sub, expected, exc)
            return

        try:
            extracted_dict = result.label.model_dump()
            cmp_result = pipeline_compare(extracted_dict, expected)
            session.add(
                Extraction(
                    submission_id=sub.id,
                    extracted_label=extracted_dict,
                    field_confidence=dict(result.field_confidence),
                    latency_ms=int(result.latency_ms),
                    input_tokens=int(result.input_tokens),
                    output_tokens=int(result.output_tokens),
                    model=result.model,
                    error=None,
                )
            )
            for field in ALL_FIELDS:
                entry = cmp_result.get(field, {})
                matched = bool(entry.get("matched"))
                verdict = "pass" if matched else "fail"
                extracted_value = _stringify(entry.get("extracted"))
                expected_value = _stringify(entry.get("expected"))
                diff_extracted = diff_expected = None
                if verdict == "fail" and field in _TEXT_FIELDS:
                    diff_extracted, diff_expected = word_diff(
                        extracted_value or "", expected_value or ""
                    )
                session.add(
                    Comparison(
                        submission_id=sub.id,
                        field=field,
                        verdict=verdict,
                        rule=_RULE_BY_FIELD.get(field, "comparison"),
                        extracted_value=extracted_value,
                        expected_value=expected_value,
                        reason=entry.get("reason"),
                        diff_extracted=diff_extracted,
                        diff_expected=diff_expected,
                    )
                )
            sub.status = "ready_for_review"
            session.commit()
            logger.info(
                "processor: submission %s ready_for_review (model=%s latency_ms=%s in=%s out=%s)",
                sub.id,
                result.model,
                int(result.latency_ms),
                result.input_tokens,
                result.output_tokens,
            )
        except Exception as exc:  # noqa: BLE001 — defensive after extract
            logger.exception(
                "processor: post-extract failure for %s", submission_id
            )
            session.rollback()
            _write_failure(session, None, expected, exc, submission_id=submission_id)
    finally:
        if owns_session:
            session.close()


def _write_failure(
    session: Session,
    sub: Submission | None,
    expected: dict[str, Any],
    exc: BaseException,
    *,
    submission_id: uuid.UUID | None = None,
) -> None:
    """Persist the failure-shaped Extraction + synthesized Comparison rows."""
    if sub is None:
        if submission_id is None:
            raise ValueError("must pass either sub or submission_id")
        sub = session.get(Submission, submission_id)
        if sub is None:
            return
    is_imported = bool(expected.get("is_imported"))

    session.add(
        Extraction(
            submission_id=sub.id,
            extracted_label=None,
            field_confidence=None,
            latency_ms=None,
            input_tokens=None,
            output_tokens=None,
            model=get_settings().openrouter_model,
            error=str(exc),
        )
    )
    for field in ALL_FIELDS:
        # `country_of_origin` is the only field that is genuinely
        # not-applicable on this submission when the label is domestic.
        if field == "country_of_origin" and not is_imported:
            verdict = "not_applicable"
        else:
            verdict = "fail"
        expected_text = _stringify(expected.get(field)) if field in expected else None
        session.add(
            Comparison(
                submission_id=sub.id,
                field=field,
                verdict=verdict,
                rule="extraction failed",
                extracted_value=None,
                expected_value=expected_text,
                reason="no extraction available",
                diff_extracted=None,
                diff_expected=None,
            )
        )
    sub.status = "extraction_failed"
    session.commit()


# --- Start all loaded ------------------------------------------------------


def process_all_loaded(db: Session) -> list[uuid.UUID]:
    """Flip every `loaded` submission to `processing` and schedule extraction.

    The flip happens in one SQL `UPDATE ... RETURNING id` so callers never see
    a half-flipped queue. The handler returns immediately; each scheduled task
    acquires the semaphore independently before invoking the vision call.

    Takes the FastAPI-managed session so the flip is visible inside the same
    request transaction (and so tests using a SAVEPOINT session see it).
    """
    ids: list[uuid.UUID] = list(
        db.execute(
            update(Submission)
            .where(Submission.status == "loaded")
            .values(status="processing", updated_at=func.now())
            .returning(Submission.id)
        )
        .scalars()
        .all()
    )
    db.flush()

    if ids:
        _schedule_processing(ids)
    return ids


def _schedule_processing(ids: Iterable[uuid.UUID]) -> None:
    """Schedule one background task per submission.

    Each task runs `process_submission` (sync) inside a worker thread so the
    OpenAI client's blocking I/O does not stall the event loop. The
    semaphore caps the number of concurrent vision calls.
    """
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        # No running loop (e.g., invoked from a sync context outside FastAPI).
        # Fall back to running the tasks inline; acceptable for the prototype.
        for sid in ids:
            try:
                process_submission(submission_id=sid)
            except Exception:  # noqa: BLE001
                logger.exception("processor: inline-run failed for %s", sid)
        return

    sem = _get_semaphore()

    async def _run_one(sid: uuid.UUID) -> None:
        async with sem:
            await asyncio.to_thread(process_submission, sid)

    for sid in ids:
        loop.create_task(_run_one(sid))
