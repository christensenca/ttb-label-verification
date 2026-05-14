"""Unit tests for the word-diff helper (T022, US1).

Verifies the contract from research R3 / data-model § Word-diff format:
- whitespace tokens are preserved
- identical inputs produce all-`equal` tokens
- completely different inputs produce only `added`/`removed`
- mixed inputs tag matched runs as `equal` and divergent runs as `added`/`removed`
"""

from __future__ import annotations

import pytest

from app.services.diff import warning_text_diff, word_diff


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


def test_missing_word_renders_inline_on_extracted_side():
    # A token present only in expected ("brave") is rendered inline on BOTH
    # sides as `removed`, so a reviewer reading the extracted-only column
    # sees a marker where the missing text belongs.
    extracted, expected = word_diff("hello world", "hello brave world")
    extracted_removed = [t for t in extracted if t["kind"] == "removed"]
    expected_removed = [t for t in expected if t["kind"] == "removed"]
    assert any("brave" in t["text"] for t in extracted_removed)
    assert any("brave" in t["text"] for t in expected_removed)


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


def test_word_diff_case_insensitive_treats_case_only_diffs_as_equal():
    extracted, _ = word_diff("Hello World", "hello world", case_insensitive=True)
    assert all(t["kind"] == "equal" for t in extracted)
    # Original casing must be preserved in the emitted text.
    assert "".join(_texts(extracted)) == "Hello World"


def test_warning_text_diff_body_case_only_difference_is_all_equal():
    # Same wording, header in all caps on both sides; body is all-caps in
    # extracted, mixed-case in expected. Should produce no add/remove tokens.
    extracted_text = (
        "GOVERNMENT WARNING: (1) ACCORDING TO THE SURGEON GENERAL, "
        "WOMEN SHOULD NOT DRINK ALCOHOLIC BEVERAGES DURING PREGNANCY."
    )
    expected_text = (
        "GOVERNMENT WARNING: (1) According to the Surgeon General, "
        "women should not drink alcoholic beverages during pregnancy."
    )
    a, b = warning_text_diff(extracted_text, expected_text)
    assert all(t["kind"] == "equal" for t in a)
    assert all(t["kind"] == "equal" for t in b)
    # Original casing on each side is preserved.
    assert "".join(_texts(a)) == extracted_text
    assert "".join(_texts(b)) == expected_text


def test_warning_text_diff_real_word_difference_still_surfaces():
    # 'CAUSE' replaced with 'CREATE' — that's a real semantic deviation and
    # should be highlighted even though case-style is otherwise different.
    extracted_text = (
        "GOVERNMENT WARNING: CONSUMPTION OF ALCOHOLIC BEVERAGES MAY CREATE "
        "HEALTH PROBLEMS."
    )
    expected_text = (
        "GOVERNMENT WARNING: Consumption of alcoholic beverages may cause "
        "health problems."
    )
    a, b = warning_text_diff(extracted_text, expected_text)
    added = [t["text"] for t in a if t["kind"] == "added"]
    removed = [t["text"] for t in b if t["kind"] == "removed"]
    assert any("CREATE" in t for t in added)
    assert any("cause" in t for t in removed)


def test_warning_text_diff_missing_comma_highlights_only_the_comma():
    # The real WhistlePig failure case: extracted is missing the comma after
    # "Surgeon General". The diff must highlight just the comma — not the
    # surrounding word — so a reviewer can spot the actual deviation.
    extracted_text = (
        "GOVERNMENT WARNING: ACCORDING TO THE SURGEON GENERAL WOMEN SHOULD"
    )
    expected_text = (
        "GOVERNMENT WARNING: According to the Surgeon General, women should"
    )
    a, _ = warning_text_diff(extracted_text, expected_text)
    flagged = [t for t in a if t["kind"] != "equal"]
    # Exactly one non-equal token, and it's the missing comma.
    assert [(t["text"], t["kind"]) for t in flagged] == [(",", "removed")]


def test_warning_text_diff_header_case_mismatch_highlighted():
    # Mis-cased header on the extracted side must show as a diff, since
    # the comparator treats the header as case-sensitive.
    a, _ = warning_text_diff(
        "Government Warning: same body",
        "GOVERNMENT WARNING: same body",
    )
    header_added = [t["text"] for t in a if t["kind"] == "added"]
    # The mis-cased header word tokens land on the extracted side as 'added'.
    # ":" tokenizes separately and matches case-insensitively on both sides.
    assert "Government" in header_added
    assert "Warning" in header_added
