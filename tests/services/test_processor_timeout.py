"""Per-task wall-clock timeout for `process_submission`.

`_run_with_timeout` wraps the worker-thread call with `asyncio.wait_for`.
On timeout, a fresh-session helper writes the failure-shaped record so the
queue advances and the review UI shows a clear error banner.
"""

from __future__ import annotations

import asyncio
import time

from sqlalchemy import select

from app.api.schemas import ALL_FIELDS
from app.db.models import Comparison, Extraction, Submission
from app.services import processor


def _insert_processing_submission(db_session) -> Submission:
    sub = Submission(
        image_key="sha256:test.jpg",
        expected_values={
            "brand": "Don Julio",
            "class_type": "Tequila Blanco",
            "alcohol_content": 40.0,
            "net_contents": "750 mL",
            "producer_name": "Diageo",
            "producer_address": "New York, NY",
            "is_imported": True,
            "country_of_origin": "Mexico",
        },
        status="processing",
        is_fixture=True,
    )
    db_session.add(sub)
    db_session.flush()
    return sub


def test_run_with_timeout_writes_failure_when_processing_hangs(
    db_session, monkeypatch
):
    sub = _insert_processing_submission(db_session)
    submission_id = sub.id

    monkeypatch.setattr(processor, "_PROCESS_TIMEOUT_SECONDS", 0.05)

    # Replace process_submission with a stub that just blocks; the slow
    # call is what we want the wall-clock timeout to catch.
    def _hang(_sid, **_kwargs):
        time.sleep(0.5)

    monkeypatch.setattr(processor, "process_submission", _hang)

    asyncio.run(
        processor._run_with_timeout(
            submission_id,
            session_factory=lambda: db_session,
        )
    )

    refreshed = db_session.get(Submission, submission_id)
    assert refreshed.status == "extraction_failed"

    extractions = (
        db_session.execute(
            select(Extraction).where(Extraction.submission_id == submission_id)
        )
        .scalars()
        .all()
    )
    assert len(extractions) == 1
    assert extractions[0].error and "processing exceeded" in extractions[0].error

    comparisons = (
        db_session.execute(
            select(Comparison).where(Comparison.submission_id == submission_id)
        )
        .scalars()
        .all()
    )
    assert {c.field for c in comparisons} == set(ALL_FIELDS)
    for c in comparisons:
        assert c.rule == "extraction failed"


def test_run_with_timeout_does_not_double_write_when_processing_finishes_in_time(
    db_session, monkeypatch
):
    sub = _insert_processing_submission(db_session)
    submission_id = sub.id

    monkeypatch.setattr(processor, "_PROCESS_TIMEOUT_SECONDS", 1.0)

    # Stand-in for a fast extractor: flip status to a terminal state and
    # write nothing else. We're testing that the timeout wrapper does not
    # fire and does not call _write_timeout_failure.
    write_calls: list = []
    real_writer = processor._write_timeout_failure

    def _spy_writer(*args, **kwargs):
        write_calls.append((args, kwargs))
        real_writer(*args, **kwargs)

    monkeypatch.setattr(processor, "_write_timeout_failure", _spy_writer)

    def _fast(_sid, **_kwargs):
        # Simulate a successful extraction by flipping status here.
        sub_in_thread = db_session.get(Submission, _sid)
        sub_in_thread.status = "ready_for_review"
        db_session.commit()

    monkeypatch.setattr(processor, "process_submission", _fast)

    asyncio.run(
        processor._run_with_timeout(
            submission_id,
            session_factory=lambda: db_session,
        )
    )

    refreshed = db_session.get(Submission, submission_id)
    assert refreshed.status == "ready_for_review"
    assert write_calls == []


def test_write_timeout_failure_skips_when_already_terminal(db_session):
    sub = _insert_processing_submission(db_session)
    sub.status = "ready_for_review"
    db_session.flush()

    processor._write_timeout_failure(
        sub.id, 1.0, session_factory=lambda: db_session
    )

    # Status preserved; no failure record written over the success state.
    refreshed = db_session.get(Submission, sub.id)
    assert refreshed.status == "ready_for_review"
    extractions = (
        db_session.execute(
            select(Extraction).where(Extraction.submission_id == sub.id)
        )
        .scalars()
        .all()
    )
    assert extractions == []
