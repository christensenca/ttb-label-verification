"""Background processing for submissions.

Phase 2 ships only the startup-rescue routine — the actual per-submission
processor is implemented in Phase 3 (T031–T033). The rescue is here so the
FastAPI lifespan (T015) can call it without a forward reference to Phase 3.
"""

from __future__ import annotations

import logging

from sqlalchemy import update

from app.db.models import Submission
from app.db.session import SessionLocal

logger = logging.getLogger(__name__)


def rescue_processing_on_startup() -> int:
    """Flip any rows stuck in `processing` to `extraction_failed`.

    Anything left in `processing` at boot is from a previous run that was
    killed mid-flight; mark them failed so the queue is never stuck.
    Returns the number of rows rescued.
    """
    with SessionLocal() as session:
        result = session.execute(
            update(Submission)
            .where(Submission.status == "processing")
            .values(status="extraction_failed")
            .returning(Submission.id)
        )
        ids = [row[0] for row in result.all()]
        session.commit()

    if ids:
        logger.warning(
            "rescue: marked %d processing submissions as extraction_failed: %s",
            len(ids),
            ids,
        )
    return len(ids)
