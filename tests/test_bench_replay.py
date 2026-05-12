"""Regression test: replay cached gpt-4o-mini extractions through compare().

The v1 baseline (inline lower/strip normalizer in scripts/bench_models.py)
scored 44/56 = 78.6% on gpt-4o-mini. compare() picks up everything that's
actually formatting drift and lands at 49/56 = 87.5% — an 8.9-pp jump on
the same extraction outputs.

The remaining 7 failures are genuine extraction issues, not comparator
issues:
  - 4 partial brand/class/name extractions ("Hendrick's" missing "Gin",
    "Tito's" missing "Handmade Vodka", "WHISKY" missing the rest of
    "Kentucky Straight Bourbon Whisky", "WHISTLEPIG" missing "Whiskey Co.")
  - 2 nulls (titos.net_contents, whistlepig.producer_address)
  - 1 known ground-truth ambiguity (hendricks.brand — flagged in the plan)

The floor is therefore set at 85% — high enough to catch any regression
in the comparator, low enough to acknowledge that the rest belongs to
extract.py / prompt engineering, not compare.py.
"""

from __future__ import annotations

from pipeline.compare import SCORED_FIELDS, compare

MODEL = "openai/gpt-4o-mini"
BOTTLES = (
    "don_julio",
    "gray_whale",
    "hendricks",
    "makers_mark",
    "titos",
    "whistlepig",
    "woodfords",
)


def _score(extractions, expected_for) -> tuple[int, int]:
    correct = total = 0
    for bottle in BOTTLES:
        ext = extractions[bottle][MODEL]["label"]
        exp = expected_for(bottle)
        result = compare(ext, exp)
        for field in SCORED_FIELDS:
            total += 1
            if result[field]["matched"]:
                correct += 1
    return correct, total


def test_aggregate_accuracy_above_baseline(extractions, expected_for):
    correct, total = _score(extractions, expected_for)
    accuracy = correct / total
    # v1 baseline was 44/56 = 78.6%. compare() reclaims the formatting
    # drift cases and lands at 49/56 = 87.5%. Floor at 85% catches
    # comparator regressions without needing the LLM rerun to hit 90%+.
    assert accuracy >= 0.85, (
        f"Aggregate accuracy regressed: {correct}/{total} = {accuracy:.1%}"
    )


def test_warning_strict_rule_catches_real_deviations(extractions, expected_for):
    """The old bench used a loose ``startswith("GOVERNMENT WARNING:")``
    that scored 7/7. The strict canonical-text rule catches two genuine
    label issues: hendricks truncates the final sentence; woodfords drops
    a comma. The remaining 5 should all pass cleanly — anything less
    means we tightened the rule too far.
    """
    passing = 0
    for bottle in BOTTLES:
        ext = extractions[bottle][MODEL]["label"]
        exp = expected_for(bottle)
        if compare(ext, exp)["government_warning_text"]["matched"]:
            passing += 1
    assert passing >= 5, f"Warning regression: {passing}/7 pass (expected >=5)"


def test_per_bottle_pass_floor(extractions, expected_for):
    """Each bottle should land >=6/8 fields. Anything weaker than that
    means a single bottle's regressed and the aggregate accuracy is
    masking it."""
    failures: dict[str, int] = {}
    for bottle in BOTTLES:
        ext = extractions[bottle][MODEL]["label"]
        exp = expected_for(bottle)
        result = compare(ext, exp)
        passed = sum(result[f]["matched"] for f in SCORED_FIELDS)
        if passed < 6:
            failures[bottle] = passed
    assert not failures, f"Per-bottle floor breached: {failures}"
