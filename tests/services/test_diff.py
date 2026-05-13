"""Unit tests for the word-diff helper (T022, US1).

Verifies the contract from research R3 / data-model § Word-diff format:
- whitespace tokens are preserved
- identical inputs produce all-`equal` tokens
- completely different inputs produce only `added`/`removed`
- mixed inputs tag matched runs as `equal` and divergent runs as `added`/`removed`
"""

from __future__ import annotations

import pytest

from app.services.diff import word_diff


def _kinds(tokens):
    return [t["kind"] for t in tokens]


def _texts(tokens):
    return [t["text"] for t in tokens]


def test_identical_input_all_equal():
    extracted, expected = word_diff("hello world", "hello world")
    assert _kinds(extracted) == ["equal"] * len(extracted)
    assert _kinds(expected) == ["equal"] * len(expected)
    assert "".join(_texts(extracted)) == "hello world"
    assert "".join(_texts(expected)) == "hello world"


def test_completely_different_input_only_add_and_remove_on_words():
    extracted, expected = word_diff("alpha beta", "gamma delta")
    # Non-whitespace tokens must all be `added` (extracted side) or `removed` (expected side).
    assert all(t["kind"] == "added" for t in extracted if t["text"].strip())
    assert all(t["kind"] == "removed" for t in expected if t["text"].strip())


def test_whitespace_preserved():
    extracted, expected = word_diff("a  b", "a  b")
    # Reconstructing the token text should yield the original strings
    assert "".join(_texts(extracted)) == "a  b"
    assert "".join(_texts(expected)) == "a  b"


def test_added_word_only_in_extracted():
    extracted, expected = word_diff("hello brave world", "hello world")
    # 'brave' should appear in extracted as `added`; never in expected
    added = [t for t in extracted if t["kind"] == "added"]
    assert any("brave" in t["text"] for t in added)
    assert all("brave" not in t["text"] for t in expected)


def test_removed_word_only_in_expected():
    extracted, expected = word_diff("hello world", "hello brave world")
    removed = [t for t in expected if t["kind"] == "removed"]
    assert any("brave" in t["text"] for t in removed)
    assert all("brave" not in t["text"] for t in extracted)


def test_empty_inputs():
    extracted, expected = word_diff("", "")
    assert extracted == []
    assert expected == []


@pytest.mark.parametrize(
    "a,b",
    [
        ("Government WARNING: According", "GOVERNMENT WARNING: According"),
        ("one two three", "one two three four"),
    ],
)
def test_diff_returns_lists_of_dicts(a, b):
    extracted, expected = word_diff(a, b)
    assert isinstance(extracted, list)
    assert isinstance(expected, list)
    for token in extracted + expected:
        assert set(token.keys()) == {"text", "kind"}
        assert token["kind"] in {"equal", "added", "removed"}
