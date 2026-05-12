"""Vision-LLM-based label field extraction.

Extracts structured field data (brand name, class/type, ABV, net contents,
producer name & address, country of origin, government warning statement)
from a label image via OpenAI's vision API. See decision #2 in
docs/architecture-decisions.md.
"""

from pathlib import Path


def extract(image_path: Path) -> dict:
    """Extract label fields from an image.

    Returns a dict shaped like the ExtractedLabel schema (TBD). Calls the
    configured vision model with a structured-output prompt.

    Implementation pending — first pass coming as part of the eval phase.
    """
    raise NotImplementedError
