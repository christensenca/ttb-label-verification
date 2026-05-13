"""Run the FastAPI app with a deterministic stub extractor.

This is a **test harness only** — used by the Playwright e2e suite so the
browser tests can drive the real backend without burning OpenRouter credits.
The stub returns a canned Don Julio extraction regardless of the input image,
which lets the test author control field-by-field pass/fail by varying the
expected_values JSON in each upload (matching fields pass, mismatching fields
fail).

Usage:
    uv run python scripts/serve_with_stub_extractor.py
        # listens on 0.0.0.0:8000 with stubbed extractor

Do not run this in production — it bypasses the vision model entirely.
"""

from __future__ import annotations

import os

import uvicorn

import pipeline.extract as pipeline_extract
from pipeline.extract import ExtractedLabel, ExtractionResult


def _stub_extract(_image_path, **_kwargs) -> ExtractionResult:
    """Deterministic Don Julio extraction; ignores the image entirely."""
    return ExtractionResult(
        label=ExtractedLabel(
            brand="Don Julio",
            class_type="Tequila Blanco",
            alcohol_content=40.0,
            net_contents="750 mL",
            producer_name="DIAGEO",
            producer_address="NEW YORK, NY",
            is_imported=True,
            country_of_origin="MEXICO",
            government_warning_text=(
                "GOVERNMENT WARNING: (1) ACCORDING TO THE SURGEON GENERAL, "
                "WOMEN SHOULD NOT DRINK ALCOHOLIC BEVERAGES DURING PREGNANCY "
                "BECAUSE OF THE RISK OF BIRTH DEFECTS. (2) CONSUMPTION OF "
                "ALCOHOLIC BEVERAGES IMPAIRS YOUR ABILITY TO DRIVE A CAR OR "
                "OPERATE MACHINERY, AND MAY CAUSE HEALTH PROBLEMS."
            ),
        ),
        latency_ms=42.0,
        input_tokens=100,
        output_tokens=50,
        model="stub/e2e",
        field_confidence={
            "brand": "hi",
            "class_type": "hi",
            "alcohol_content": "hi",
            "net_contents": "hi",
            "producer_name": "hi",
            "producer_address": "hi",
            "country_of_origin": "hi",
            "government_warning_text": "hi",
        },
    )


def main() -> int:
    pipeline_extract.extract = _stub_extract  # type: ignore[assignment]
    # Importing app.main after the patch ensures the processor's module-level
    # `pipeline_extract` reference resolves to the patched function.
    from app.main import app  # noqa: F401 — needed so uvicorn picks it up

    host = os.environ.get("E2E_HOST", "127.0.0.1")
    port = int(os.environ.get("E2E_PORT", "8000"))
    uvicorn.run("app.main:app", host=host, port=port, log_level="info")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
