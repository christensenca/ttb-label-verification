"""Vision-LLM-based label field extraction.

Single structured-output call per label via OpenAI vision through OpenRouter.
See decision #2 in docs/architecture-decisions.md.

This experimental extractor asks the model for the target fields directly
instead of requiring full front/back transcriptions first. Each raw text field
comes back with a readability confidence, then a tiny adapter unwraps the
response into the existing flat label shape used by the comparator.

Extraction deliberately does not normalize, parse, fuzzy-match, or compare
values. Those concerns stay in ``pipeline.normalize`` and ``pipeline.compare``.
"""

from __future__ import annotations

import base64
import io
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from openai import OpenAI
from PIL import Image
from pydantic import BaseModel, Field

DEFAULT_BASE_URL = "https://openrouter.ai/api/v1"
DEFAULT_MODEL = "google/gemini-3.1-flash-lite"
DEFAULT_IMAGE_LONG_SIDE = 1536  # Currently-checked-in composites are this size.

ExtractionConfidence = Literal["low", "med", "hi"]


class FieldExtraction(BaseModel):
    """One directly-extracted raw text field plus source readability."""

    value: str | None = Field(
        description=(
            "Raw visible text for this field exactly as printed. Null when the "
            "field is not visible, unreadable, or absent."
        )
    )
    extraction_confidence: ExtractionConfidence = Field(
        description=(
            "Readability confidence only: low for blurry/partial/glare-obscured "
            "text, med for readable but stylized or low-contrast text, hi for "
            "clean and unambiguous print."
        )
    )


class OneShotExtractedLabel(BaseModel):
    """Direct model response for one-shot extraction.

    Text-like values are wrapped with readability confidence. Simple booleans
    stay simple so the adapter does not invent confidence for non-text fields.
    """

    brand: FieldExtraction = Field(description="Brand name as it appears on the label.")
    class_type: FieldExtraction = Field(
        description="Class/type designation as it appears on the label."
    )
    alcohol_content: FieldExtraction = Field(
        description=(
            "Full visible alcohol-content statement exactly as printed, including "
            "tokens such as 'ALC.', 'Alcohol', '%', 'BY VOL.', or 'by volume'. "
            "Do not return only the numeric percentage when more text is visible."
        )
    )
    net_contents: FieldExtraction = Field(
        description="Net contents as shown on the label, including units."
    )
    producer_name: FieldExtraction = Field(
        description=(
            "Regulatory responsible-party name as printed. For imported products, "
            "use the US importer named in the 'Imported by' statement, not the "
            "foreign producer or bottler."
        )
    )
    producer_address: FieldExtraction = Field(
        description=(
            "Regulatory responsible-party address as printed. For imported products, "
            "use the US importer city/state from the 'Imported by' statement."
        )
    )
    is_imported: bool | None = Field(
        description=(
            "True if the visible label says 'Imported by' or equivalent import "
            "language. False if visible text makes it domestic. Null if not visible "
            "or unclear."
        )
    )
    country_of_origin: FieldExtraction = Field(
        description=(
            "Country of origin text as printed, such as 'Product of Mexico' or "
            "'Scotland'. Null when no country-of-origin text is visible."
        )
    )
    government_warning_text: FieldExtraction = Field(
        description=(
            "Visible Government Warning text exactly as printed. Null if the "
            "warning is not visible or unreadable."
        )
    )
    government_warning_bold: bool | None = Field(
        description=(
            "True if the 'GOVERNMENT WARNING:' header appears bold, false if it "
            "appears regular weight, null if the image is not clear enough to tell."
        )
    )


class ExtractedLabel(BaseModel):
    """Flat extracted fields consumed by comparison and benchmarks."""

    brand: str | None = Field(description="Brand name as printed.")
    class_type: str | None = Field(description="Class/type designation as printed.")
    alcohol_content: str | float | None = Field(description="Alcohol-content statement as printed.")
    net_contents: str | None = Field(description="Net contents as printed.")
    producer_name: str | None = Field(description="Regulatory responsible-party name as printed.")
    producer_address: str | None = Field(
        description="Regulatory responsible-party address as printed."
    )
    is_imported: bool | None = Field(
        description="Whether the visible label identifies an importer."
    )
    country_of_origin: str | None = Field(description="Country-of-origin text as printed.")
    government_warning_text: str | None = Field(description="Government Warning text as printed.")
    government_warning_bold: bool | None = Field(
        description="Whether the Government Warning header appears bold."
    )


@dataclass
class ExtractionResult:
    """Output of a single extraction call — fields + observability metadata."""

    label: ExtractedLabel
    latency_ms: float
    input_tokens: int
    output_tokens: int
    model: str
    field_confidence: dict[str, ExtractionConfidence]


SYSTEM_PROMPT = """\
You are extracting TTB-required label information from a photograph of an \
alcohol beverage bottle. The image may show the front panel, the back panel, \
or a side-by-side/stacked composite of multiple panels.

CRITICAL: Read ONLY what is visible and legible on the labels in this \
specific image. Do NOT infer, guess, or apply outside knowledge about any \
brand or product. Inventing or recalling information you have seen elsewhere \
is a critical failure. If a field is not visible or not clearly readable, \
return null for that field's value.

Field rules:

- For wrapped text fields, return the raw visible text exactly as printed. \
Preserve tokens, punctuation, case, and line-order as well as the image allows. \
Do not normalize, title-case, expand abbreviations, parse units, or compare \
values to expected regulatory text.

- extraction_confidence: This is source readability only. Use "low" for \
blurry, partial, glare-obscured, or hard-to-read text; "med" for readable \
but stylized or low-contrast text; "hi" for clean print that is unambiguous.

- alcohol_content: Return the full visible alcohol-content statement. If the \
label says "ALC. 40% BY VOL.", "40% Alc./Vol.", or "Alcohol 40% by volume", \
return the whole visible phrase, not just "40" or "40%". Do NOT convert proof \
to ABV.

- producer_name and producer_address: Extract the mandatory regulatory \
name/address statement for the product. For imported spirits, prefer the US \
"Imported by" name and city/state over any foreign "Bottled by", "Distilled \
by", or producer statement. For domestic products, use the visible bottler, \
distiller, or processor name/address statement. Keep wording as printed; do \
not strip or rewrite prepositions.

- is_imported: True only when visible label text says "Imported by" or \
equivalent import language. False when visible text clearly identifies a \
domestic producer/bottler without import language. Null if unclear.

- country_of_origin: Return the visible country-of-origin wording as printed. \
Null if no country-of-origin text is visible.

- government_warning_text: Return only the visible Government Warning text \
exactly as printed. If the back panel or warning block is not visible, this \
field must be null. Do not fill in the standard warning from memory.

- government_warning_bold: True if the 'GOVERNMENT WARNING:' header is \
printed in bold typeface on the label. False if regular weight. Null if \
you cannot tell from the image.
"""


WRAPPED_FIELDS = (
    "brand",
    "class_type",
    "alcohol_content",
    "net_contents",
    "producer_name",
    "producer_address",
    "country_of_origin",
    "government_warning_text",
)


def unwrap_one_shot_label(
    one_shot: OneShotExtractedLabel,
) -> tuple[ExtractedLabel, dict[str, ExtractionConfidence]]:
    """Adapt one-shot field wrappers into the existing flat label shape."""
    flat = {name: getattr(one_shot, name).value for name in WRAPPED_FIELDS}
    confidence = {name: getattr(one_shot, name).extraction_confidence for name in WRAPPED_FIELDS}
    label = ExtractedLabel(
        **flat,
        is_imported=one_shot.is_imported,
        government_warning_bold=one_shot.government_warning_bold,
    )
    return label, confidence


def extract(
    image_path: str | Path,
    *,
    client: OpenAI | None = None,
    model: str | None = None,
    image_long_side: int = DEFAULT_IMAGE_LONG_SIDE,
    temperature: float = 0.0,
) -> ExtractionResult:
    """Extract structured label fields from a bottle photo.

    Args:
        image_path: Path to a JPEG/PNG. For our corpus, the front+back composite.
        client: Optional OpenAI client. Defaults to OpenRouter via env vars.
        model: Optional model slug. Defaults to OPENROUTER_MODEL env var or gpt-4o.
        image_long_side: Resize the image so the long side is this many pixels
            before encoding. Smaller = fewer image tokens, faster, but may
            lose fine-print legibility. Set to 0 to skip resize.
        temperature: Sampling temperature. Defaults to 0 (deterministic).

    Returns:
        ExtractionResult with parsed label fields and timing/token metadata.
    """
    path = Path(image_path)
    client = client or _default_client()
    model = model or os.environ.get("OPENROUTER_MODEL", DEFAULT_MODEL)

    image_data_url = _image_to_data_url(path, long_side=image_long_side)

    start = time.perf_counter()
    response = client.beta.chat.completions.parse(
        model=model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {"url": image_data_url, "detail": "high"},
                    },
                ],
            },
        ],
        response_format=OneShotExtractedLabel,
        temperature=temperature,
        max_tokens=8192,
    )
    latency_ms = (time.perf_counter() - start) * 1000

    parsed_one_shot = response.choices[0].message.parsed
    if parsed_one_shot is None:
        raw = response.choices[0].message.content
        raise RuntimeError(f"Model returned no parsed output. Raw content: {raw!r}")
    parsed, field_confidence = unwrap_one_shot_label(parsed_one_shot)

    usage = response.usage
    return ExtractionResult(
        label=parsed,
        latency_ms=latency_ms,
        input_tokens=usage.prompt_tokens if usage else 0,
        output_tokens=usage.completion_tokens if usage else 0,
        model=model,
        field_confidence=field_confidence,
    )


def _default_client() -> OpenAI:
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        raise RuntimeError(
            "OPENROUTER_API_KEY not set. Copy .env.example to .env and add a key, "
            "or pass a configured OpenAI client to extract()."
        )
    return OpenAI(base_url=DEFAULT_BASE_URL, api_key=api_key)


def _image_to_data_url(path: Path, *, long_side: int = 0) -> str:
    """Read the image; optionally resize so the long side is `long_side` px."""
    if not long_side:
        data = path.read_bytes()
        mime = _mime_for_suffix(path.suffix)
    else:
        with Image.open(path) as img:
            img = img.convert("RGB")
            w, h = img.size
            if max(w, h) > long_side:
                if w >= h:
                    new_size = (long_side, round(h * long_side / w))
                else:
                    new_size = (round(w * long_side / h), long_side)
                img = img.resize(new_size, Image.LANCZOS)
            buf = io.BytesIO()
            img.save(buf, "JPEG", quality=85, optimize=True)
            data = buf.getvalue()
            mime = "image/jpeg"

    b64 = base64.b64encode(data).decode("ascii")
    return f"data:{mime};base64,{b64}"


def _mime_for_suffix(suffix: str) -> str:
    s = suffix.lower().lstrip(".")
    return "image/jpeg" if s in {"jpg", "jpeg"} else f"image/{s}"


if __name__ == "__main__":
    # Smoke test: `python -m pipeline.extract test_data/images/don_julio.jpg`
    import json
    import sys

    from dotenv import load_dotenv

    load_dotenv()

    if len(sys.argv) != 2:
        print("Usage: python -m pipeline.extract <image_path>", file=sys.stderr)
        sys.exit(2)

    result = extract(sys.argv[1])
    print(f"model:       {result.model}")
    print(f"latency:     {result.latency_ms:.0f}ms")
    print(f"tokens:      {result.input_tokens} in / {result.output_tokens} out")
    print()
    print(json.dumps(result.label.model_dump(), indent=2))
    print()
    print(json.dumps({"field_confidence": result.field_confidence}, indent=2))
