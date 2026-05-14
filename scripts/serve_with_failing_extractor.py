"""Run the FastAPI app with an always-failing extractor.

Demo harness for the extraction-failure UI flow. The stub raises a
RuntimeError on every call, exercising the same code path that production
hits when OpenRouter returns an unrecoverable error: the processor writes
the failure-shaped Extraction + 10 synthesized Comparison rows, the queue
shows a red "Extraction Failed" pill, and the review screen renders the
ExtractionFailedBanner with the reviewer's recovery controls.

Usage:
    uv run python scripts/serve_with_failing_extractor.py
        # listens on 0.0.0.0:8000 with a failing extractor

Do not run this in production — it bypasses the vision model entirely.
"""

from __future__ import annotations

import os

import uvicorn

import pipeline.extract as pipeline_extract


def _failing_extract(_image_path, **_kwargs):
    """Always raises — used to exercise the extraction-failure UI path."""
    raise RuntimeError("simulated extraction failure: model unavailable")


def main() -> int:
    pipeline_extract.extract = _failing_extract  # type: ignore[assignment]
    # Importing app.main after the patch ensures the processor's module-level
    # `pipeline_extract` reference resolves to the patched function.
    from app.main import app  # noqa: F401 — needed so uvicorn picks it up

    host = os.environ.get("E2E_HOST", "127.0.0.1")
    port = int(os.environ.get("E2E_PORT", "8000"))
    uvicorn.run("app.main:app", host=host, port=port, log_level="info")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
