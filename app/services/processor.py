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
import json
import logging
import uuid
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

import pipeline.extract as pipeline_extract
from app.api.schemas import ALL_FIELDS
from app.config import get_settings
from app.db.models import Comparison, Extraction, Submission
from app.db.session import SessionLocal
from app.services.diff import warning_text_diff, word_diff
from pipeline.compare import compare as pipeline_compare

logger = logging.getLogger(__name__)

# Dedicated logger for the per-submission completion event. Emits one JSON
# line per item to stdout for cloud-log scraping (T083). The durable audit
# record lives on the `extractions` row; this is the observability sidecar.
_event_logger = logging.getLogger("ttb.processor.event")


def _emit_completion_event(payload: dict[str, Any]) -> None:
    """Log a single JSON line describing the outcome of one submission.

    The 5-second p95 latency target is not a hard cutoff for the prototype,
    but `latency_ms` is always logged so we can read it from stdout in
    addition to the persisted `extractions.latency_ms` column.
    """
    try:
        line = json.dumps(payload, default=str, sort_keys=True)
    except (TypeError, ValueError):  # pragma: no cover - defensive
        line = json.dumps({"event": "extraction.completed", "error": "serialize_failed"})
    _event_logger.info(line)


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


# Wall-clock cap on a single submission's processing. Generous given
# pipeline.extract's per-attempt timeout (30s) × up-to-4 attempts + backoff.
_PROCESS_TIMEOUT_SECONDS = 300.0


# --- Startup rescue --------------------------------------------------------


def rescue_processing_on_startup(
    *,
    session_factory: Callable[[], Session] | None = None,
) -> int:
    """Rescue any rows stuck in `processing` from a previous run.

    Anything left in `processing` at boot is from a previous run that died
    mid-flight. Each stuck row is converted to a full failure record (the
    same shape as a live extractor exception) so the review UI renders the
    error banner and the synthesized field rows — without those, the row
    looks broken to the reviewer.
    """
    factory = session_factory or SessionLocal
    owns_session = session_factory is None
    session = factory()
    rescued: list[uuid.UUID] = []
    try:
        stuck = (
            session.execute(
                select(Submission).where(Submission.status == "processing")
            )
            .scalars()
            .all()
        )
        for sub in stuck:
            expected = dict(sub.expected_values)
            exc = RuntimeError(
                "rescued: processing did not finish before restart"
            )
            _write_failure(session, sub, expected, exc)
            rescued.append(sub.id)
    finally:
        if owns_session:
            session.close()
    if rescued:
        logger.warning(
            "rescue: marked %d processing submissions as extraction_failed: %s",
            len(rescued),
            rescued,
        )
    return len(rescued)


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
            if _still_processing(session, sub):
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
                    differ = (
                        warning_text_diff
                        if field == "government_warning_text"
                        else word_diff
                    )
                    diff_extracted, diff_expected = differ(
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
            # Guard against a watchdog/rescue having already terminated this
            # row while the extractor was running. Without this, a slow
            # extraction that completes after a timeout would resurrect the
            # row to ready_for_review with a duplicate set of writes.
            if not _still_processing(session, sub):
                session.rollback()
                logger.info(
                    "processor: submission %s already terminal; abandoning success write",
                    submission_id,
                )
                return
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
            _emit_completion_event(
                {
                    "event": "extraction.completed",
                    "submission_id": str(sub.id),
                    "status": "ready_for_review",
                    "model": result.model,
                    "latency_ms": int(result.latency_ms),
                    "input_tokens": int(result.input_tokens),
                    "output_tokens": int(result.output_tokens),
                    "error": None,
                }
            )
        except Exception as exc:  # noqa: BLE001 — defensive after extract
            logger.exception(
                "processor: post-extract failure for %s", submission_id
            )
            session.rollback()
            if _still_processing(session, sub):
                _write_failure(session, None, expected, exc, submission_id=submission_id)
    finally:
        if owns_session:
            session.close()


def _still_processing(session: Session, sub: Submission) -> bool:
    """Refresh `sub` and return True iff its status is still `processing`.

    Used to avoid racing with a watchdog/rescue that may have already
    terminated the row while extraction was in flight.
    """
    try:
        session.refresh(sub)
    except Exception:  # noqa: BLE001 — refresh failure shouldn't crash the worker
        return True
    return sub.status == "processing"


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
        verdict = (
            "not_applicable"
            if field == "country_of_origin" and not is_imported
            else "fail"
        )
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
    _emit_completion_event(
        {
            "event": "extraction.completed",
            "submission_id": str(sub.id),
            "status": "extraction_failed",
            "model": get_settings().openrouter_model,
            "latency_ms": None,
            "input_tokens": None,
            "output_tokens": None,
            "error": str(exc),
        }
    )


def _write_timeout_failure(
    submission_id: uuid.UUID,
    timeout_seconds: float,
    *,
    session_factory: Callable[[], Session] | None = None,
) -> None:
    """Persist a timeout-shaped failure record from a fresh session.

    Called when the per-task wall-clock budget expires before
    `process_submission` returns. Uses a separate session because the
    extractor thread is still holding the original one.
    """
    factory = session_factory or SessionLocal
    owns_session = session_factory is None
    session = factory()
    try:
        sub = session.get(Submission, submission_id)
        if sub is None:
            return
        if sub.status != "processing":
            # The extractor thread already finished, or another rescue/
            # watchdog already terminated this row. Nothing to do.
            return
        expected = dict(sub.expected_values)
        exc = TimeoutError(f"processing exceeded {timeout_seconds:g}s")
        _write_failure(session, sub, expected, exc)
    finally:
        if owns_session:
            session.close()


# --- Start all loaded ------------------------------------------------------


def process_all_loaded(db: Session) -> list[uuid.UUID]:
    """Flip every `loaded` submission to `processing` and schedule extraction.

    We select IDs ordered by `created_at DESC` (matching the queue UI's
    display order) so scheduling is deterministic — the first items on
    screen are the first admitted to the concurrency semaphore. The
    subsequent UPDATE flips all of them in one statement so callers never
    see a half-flipped queue.

    Takes the FastAPI-managed session so the flip is visible inside the same
    request transaction (and so tests using a SAVEPOINT session see it).
    """
    ordered_ids: list[uuid.UUID] = list(
        db.execute(
            select(Submission.id)
            .where(Submission.status == "loaded")
            .order_by(Submission.created_at.desc(), Submission.id)
        )
        .scalars()
        .all()
    )
    if not ordered_ids:
        return []

    db.execute(
        update(Submission)
        .where(Submission.id.in_(ordered_ids))
        .values(status="processing", updated_at=func.now())
    )
    db.flush()

    _schedule_processing(ordered_ids)
    return ordered_ids


def _schedule_processing(ids: Iterable[uuid.UUID]) -> None:
    """Schedule one background task per submission.

    Each task runs `process_submission` (sync) inside a worker thread so the
    OpenAI client's blocking I/O does not stall the event loop. The
    semaphore caps the number of concurrent vision calls. Each task is
    wrapped with a per-submission wall-clock timeout so a hung extractor
    cannot wedge the row indefinitely.
    """
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        # No running loop (e.g., invoked from a sync context outside FastAPI).
        # Fall back to running the tasks inline; acceptable for the prototype.
        # The async wall-clock timeout doesn't apply here — the inline path
        # is only used by scripts/CLI, not the production request flow.
        for sid in ids:
            try:
                process_submission(submission_id=sid)
            except Exception:  # noqa: BLE001
                logger.exception("processor: inline-run failed for %s", sid)
        return

    sem = _get_semaphore()

    async def _run_one(sid: uuid.UUID) -> None:
        async with sem:
            await _run_with_timeout(sid)

    for sid in ids:
        loop.create_task(_run_one(sid))


async def _run_with_timeout(
    submission_id: uuid.UUID,
    *,
    session_factory: Callable[[], Session] | None = None,
    image_path: str | Path | None = None,
    extractor: Callable[..., pipeline_extract.ExtractionResult] | None = None,
) -> None:
    """Run `process_submission` with a wall-clock timeout.

    On timeout the extractor thread is left to drain (Python threads can't
    be cancelled), but the submission is marked failed via a fresh session
    so the queue advances. The status guard inside `process_submission`
    prevents the late-completing thread from overwriting the failure.
    """
    timeout = _PROCESS_TIMEOUT_SECONDS  # read at call time so tests can monkeypatch
    try:
        await asyncio.wait_for(
            asyncio.to_thread(
                process_submission,
                submission_id,
                session_factory=session_factory,
                image_path=image_path,
                extractor=extractor,
            ),
            timeout=timeout,
        )
    except asyncio.TimeoutError:
        logger.warning(
            "processor: submission %s exceeded %ss; writing timeout failure",
            submission_id,
            timeout,
        )
        await asyncio.to_thread(
            _write_timeout_failure,
            submission_id,
            timeout,
            session_factory=session_factory,
        )
