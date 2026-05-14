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

_TOKEN_RE = re.compile(r"\w+|[^\s\w]|\s+")
_WARNING_HEADER = "GOVERNMENT WARNING:"


class DiffToken(TypedDict):
    text: str
    kind: Literal["equal", "added", "removed"]


def _tokenize(text: str) -> list[str]:
    """Split into runs of whitespace and runs of non-whitespace, preserving everything."""
    return _TOKEN_RE.findall(text)


def word_diff(
    extracted: str,
    expected: str,
    *,
    case_insensitive: bool = False,
) -> tuple[list[DiffToken], list[DiffToken]]:
    """Return parallel tagged-token streams for the extracted and expected sides.

    With ``case_insensitive=True``, tokens are compared after `casefold()` but
    emitted with their original casing — useful for fields where labels may
    legitimately render text in different cases.
    """
    a_tokens = _tokenize(extracted)
    b_tokens = _tokenize(expected)

    if case_insensitive:
        a_keys: list[str] = [t.casefold() for t in a_tokens]
        b_keys: list[str] = [t.casefold() for t in b_tokens]
    else:
        a_keys = a_tokens
        b_keys = b_tokens

    extracted_out: list[DiffToken] = []
    expected_out: list[DiffToken] = []

    matcher = SequenceMatcher(a=a_keys, b=b_keys, autojunk=False)
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
            # Tokens present only in expected. Render the same marker on the
            # extracted side so a reviewer scanning the extracted column can
            # see where text is missing (e.g., a dropped comma).
            for tok in b_tokens[j1:j2]:
                expected_out.append({"text": tok, "kind": "removed"})
                extracted_out.append({"text": tok, "kind": "removed"})
        elif tag == "delete":
            for tok in a_tokens[i1:i2]:
                extracted_out.append({"text": tok, "kind": "added"})

    return extracted_out, expected_out


def warning_text_diff(
    extracted: str, expected: str
) -> tuple[list[DiffToken], list[DiffToken]]:
    """Diff for Government Warning text — mirrors the comparator's case rule.

    Per `pipeline.compare._warning_text_field`, the literal 'GOVERNMENT
    WARNING:' prefix must match case-sensitively, but the body text is
    case-insensitive (labels routinely print the body in ALL CAPS while the
    regulation's canonical wording is mixed case).

    We split each side at the header marker, run the case-sensitive diff on
    the header, and the case-insensitive diff on the body. This stops the
    body's case style from flooding the diff with false-positive highlights
    while still surfacing a wrong-case header.
    """
    a_head, a_body = _split_at_warning_header(extracted)
    b_head, b_body = _split_at_warning_header(expected)
    head_a, head_b = word_diff(a_head, b_head)
    body_a, body_b = word_diff(a_body, b_body, case_insensitive=True)
    return head_a + body_a, head_b + body_b


def _split_at_warning_header(text: str) -> tuple[str, str]:
    """Split at the case-insensitive 'GOVERNMENT WARNING:' marker.

    Returns ``(header_part, rest)``. The header_part preserves original casing
    so a mis-cased header is still visible to the case-sensitive diff. If the
    marker is absent, returns ``("", text)``.
    """
    idx = text.upper().find(_WARNING_HEADER)
    if idx == -1:
        return "", text
    end = idx + len(_WARNING_HEADER)
    return text[:end], text[end:]
