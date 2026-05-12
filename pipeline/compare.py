"""Per-field comparison between extracted and expected label values.

Strictness rules vary by field — see decision #6 in
docs/architecture-decisions.md:

  - Government Warning: strict (exact text, all-caps, bold)
  - Brand / producer / class-type: normalized fuzzy match
  - ABV: numeric tolerance (±0.1%)
  - Net contents: unit-aware comparison
  - Country of origin: normalized exact match
"""


def compare(extracted: dict, expected: dict) -> dict:
    """Compare extracted fields against expected values.

    Returns a per-field result dict with match/no-match plus evidence.
    Implementation pending.
    """
    raise NotImplementedError
