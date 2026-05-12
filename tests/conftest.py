"""Shared pytest fixtures for the compare/normalize/bench-replay suites."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
FIXTURE = Path(__file__).parent / "fixtures" / "extractions.json"
EXPECTED_DIR = REPO / "test_data" / "expected"


@pytest.fixture(scope="session")
def extractions() -> dict:
    """Cached extraction outputs, shape::

    { bottle: { model: { "label": {...}, "latency_ms": ..., "error": ... } } }
    """
    return json.loads(FIXTURE.read_text())


@pytest.fixture(scope="session")
def expected_for():
    """Returns a callable: bottle -> expected-values dict (the inner
    "expected" object from test_data/expected/<bottle>.json)."""

    cache: dict[str, dict] = {}

    def _get(bottle: str) -> dict:
        if bottle not in cache:
            cache[bottle] = json.loads((EXPECTED_DIR / f"{bottle}.json").read_text())["expected"]
        return cache[bottle]

    return _get
