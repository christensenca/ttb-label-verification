"""Word-level diff for failing text fields.

Pure UI helper — never used for comparison logic itself. Splits both sides on
whitespace, runs `difflib.SequenceMatcher` over the resulting token streams,
and emits two parallel token lists tagged with `equal` / `added` / `removed`
plus preserved whitespace tokens so the UI can render contiguous text.

Token shape mirrors `data-model.md § Word-diff format`:

    {"text": "<chunk>", "kind": "equal" | "added" | "removed"}

`added` tokens appear in the extracted column (present in extracted, not in
expected). `removed` tokens appear in the expected column.
"""

from __future__ import annotations

import re
from difflib import SequenceMatcher
from typing import Literal, TypedDict

_TOKEN_RE = re.compile(r"\S+|\s+")


class DiffToken(TypedDict):
    text: str
    kind: Literal["equal", "added", "removed"]


def _tokenize(text: str) -> list[str]:
    """Split into runs of whitespace and runs of non-whitespace, preserving everything."""
    return _TOKEN_RE.findall(text)


def word_diff(extracted: str, expected: str) -> tuple[list[DiffToken], list[DiffToken]]:
    """Return parallel tagged-token streams for the extracted and expected sides."""
    a_tokens = _tokenize(extracted)
    b_tokens = _tokenize(expected)

    extracted_out: list[DiffToken] = []
    expected_out: list[DiffToken] = []

    matcher = SequenceMatcher(a=a_tokens, b=b_tokens, autojunk=False)
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            for tok in a_tokens[i1:i2]:
                extracted_out.append({"text": tok, "kind": "equal"})
            for tok in b_tokens[j1:j2]:
                expected_out.append({"text": tok, "kind": "equal"})
        elif tag == "replace":
            for tok in a_tokens[i1:i2]:
                extracted_out.append({"text": tok, "kind": "added"})
            for tok in b_tokens[j1:j2]:
                expected_out.append({"text": tok, "kind": "removed"})
        elif tag == "insert":
            for tok in b_tokens[j1:j2]:
                expected_out.append({"text": tok, "kind": "removed"})
        elif tag == "delete":
            for tok in a_tokens[i1:i2]:
                extracted_out.append({"text": tok, "kind": "added"})

    return extracted_out, expected_out
