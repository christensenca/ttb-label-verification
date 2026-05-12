"""Vision-LLM-based label field extraction.

Single structured-output call per label via OpenAI vision through OpenRouter.
See decision #2 in docs/architecture-decisions.md.

Anti-hallucination strategy: the schema requires the model to populate
verbatim transcriptions of both labels BEFORE extracting structured fields.
That grounds the structured output in text the model has explicitly committed
to seeing, rather than letting it pattern-complete from its training corpus.

The schema mirrors the expected-values JSON in test_data/expected/, plus
the two transcription fields and `government_warning_text` (always required
for alcohol, validated separately by the comparator against the canonical
TTB warning text).
"""

from __future__ import annotations

import base64
import io
import os
import time
from dataclasses import dataclass
from pathlib import Path

from openai import OpenAI
from PIL import Image
from pydantic import BaseModel, Field

DEFAULT_BASE_URL = "https://openrouter.ai/api/v1"
DEFAULT_MODEL = "openai/gpt-4o"
DEFAULT_IMAGE_LONG_SIDE = 1536  # Currently-checked-in composites are this size.


class ExtractedLabel(BaseModel):
    """Structured fields extracted from a TTB alcohol label.

    Field order matters: structured output is generated token-by-token, so
    putting the two transcription fields first forces the model to commit
    to a transcription before extracting fields from it.
    """

    # ----- Transcription (anti-hallucination "show your work") -----
    front_label_text: str = Field(
        description="Verbatim transcription of ALL visible text on the FRONT label, preserving case and line order as best you can. Include every word you can read. This is the source of truth for the structured fields below."
    )
    back_label_text: str = Field(
        description="Verbatim transcription of ALL visible text on the BACK label, preserving case and line order as best you can. Include every word you can read. This is the source of truth for the structured fields below."
    )

    # ----- Structured fields extracted from the transcription above -----
    brand: str | None = Field(
        description="Brand name as printed — the most prominent product-line identifier. Do not append the class/type unless it visibly appears as part of the brand logo."
    )
    class_type: str | None = Field(
        description="Class/type designation as printed (the kind of spirit: bourbon, gin, vodka, tequila, rye whiskey, etc.). Use wording from the transcription."
    )
    alcohol_content: float | None = Field(
        description="ABV as shown on the label, as a number between 0 and 100 (e.g., 40.0 for '40% Alc./Vol.'). Do NOT convert proof to ABV. If only proof is shown without an explicit ABV percentage, return null."
    )
    net_contents: str | None = Field(
        description="As shown on the label including the unit (e.g., '750 mL', '1 L'). Preserve label formatting."
    )
    producer_name: str | None = Field(
        description="Company responsible for the product, taken verbatim from the transcription. For imported products, this is the importer named on the 'Imported by ...' line — NOT the foreign bottler. For domestic, the distillery or bottler. Strip preposition words ('Distilled by', 'Imported by', etc.); keep corporate suffixes (Inc., Co., LLC)."
    )
    producer_address: str | None = Field(
        description="City and state/region of the producer, quoted verbatim from the transcription. For imported products, use the US address from the 'Imported by ...' line. Strip trailing country codes — those belong in country_of_origin if applicable."
    )
    is_imported: bool | None = Field(
        description="True ONLY when the transcription contains the words 'Imported by'. A foreign country mentioned in a production statement does NOT qualify if a US bottler/producer is also named."
    )
    country_of_origin: str | None = Field(
        description="Country as literally stated on the label (e.g., 'Product of <Country>', 'Distilled and bottled in <Country>'). Null if no country is stated. Required when is_imported is true."
    )
    government_warning_text: str | None = Field(
        description="Full literal text of the Government Warning statement on the back, preserving case and punctuation. It should begin with 'GOVERNMENT WARNING:'. Null if missing or unreadable."
    )


@dataclass
class ExtractionResult:
    """Output of a single extraction call — fields + observability metadata."""

    label: ExtractedLabel
    latency_ms: float
    input_tokens: int
    output_tokens: int
    model: str


SYSTEM_PROMPT = """\
You are extracting TTB-required label information from a photograph of an \
alcohol beverage bottle. The image shows the FRONT label (left half) and \
BACK label (right half) of the same bottle, concatenated side-by-side.

CRITICAL: Read ONLY what is visible and legible on the labels in this \
specific image. Do NOT infer, guess, or apply outside knowledge about any \
brand or product. Inventing or recalling information you have seen elsewhere \
is a critical failure. If a field is not clearly readable, return null.

Output sequence — the schema requires this order:

  1. First, populate `front_label_text` and `back_label_text` with verbatim \
transcriptions of all visible text on each label. This is your reading pass.

  2. Then populate every structured field using ONLY information that \
appears in your transcriptions above. If a value is not present in your \
transcription, it must be null (or false for is_imported).

Field rules:

- alcohol_content: ABV as a percent number between 0 and 100 (e.g., 40.0 \
for '40% Alc./Vol.'). DO NOT convert proof to ABV. If only proof is shown \
without an explicit ABV percentage, return null.

- producer_name and producer_address: Take these verbatim from the \
transcription. For imported products, the relevant entity is the US \
importer named on the line beginning with 'Imported by ...' — \
even if a foreign bottler is also listed prominently. Strip preposition \
words ('Distilled by', 'Imported by', etc.); keep corporate suffixes.

- is_imported: True only when 'Imported by' appears in the transcription. \
A foreign country in a production statement (e.g., 'Distilled in <Country>') \
alone is NOT sufficient if a US bottler/producer is also named — that is a \
domestic product with foreign sourcing.

- country_of_origin: Capture what the label literally states. Null if no \
country is stated.

- government_warning_text: Verbatim from your back-label transcription. \
Should begin with 'GOVERNMENT WARNING:'. Null if missing or unreadable.
"""


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
        response_format=ExtractedLabel,
        temperature=temperature,
        max_tokens=4096,
    )
    latency_ms = (time.perf_counter() - start) * 1000

    parsed = response.choices[0].message.parsed
    if parsed is None:
        raw = response.choices[0].message.content
        raise RuntimeError(f"Model returned no parsed output. Raw content: {raw!r}")

    usage = response.usage
    return ExtractionResult(
        label=parsed,
        latency_ms=latency_ms,
        input_tokens=usage.prompt_tokens if usage else 0,
        output_tokens=usage.completion_tokens if usage else 0,
        model=model,
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
