"""Print latency percentiles from successful extractions.

Reads `extractions.latency_ms` (which T031 persists for every successful
extraction) and prints count, min, p50, p95, max in milliseconds. Used by the
operator to validate a Start run — the constitution's 5-second p95 ceiling is
the eventual goal, but the prototype does not enforce it as a hard cutoff. We
log the times nonetheless so we can track drift.

Usage:
    uv run python scripts/latency_report.py
"""

from __future__ import annotations

import statistics
from typing import Sequence

from sqlalchemy import select

from app.db.models import Extraction
from app.db.session import SessionLocal


def _percentile(values: Sequence[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    # Linear interpolation between the two nearest ranks.
    k = (len(ordered) - 1) * pct
    lo, hi = int(k), min(int(k) + 1, len(ordered) - 1)
    return ordered[lo] + (ordered[hi] - ordered[lo]) * (k - lo)


def main() -> int:
    with SessionLocal() as session:
        rows = list(
            session.execute(
                select(Extraction.latency_ms).where(Extraction.latency_ms.is_not(None))
            ).scalars()
        )
    if not rows:
        print("no successful extractions on file")
        return 0
    latencies = [float(r) for r in rows]
    print(f"count : {len(latencies)}")
    print(f"min   : {min(latencies):.0f} ms")
    print(f"p50   : {statistics.median(latencies):.0f} ms")
    print(f"p95   : {_percentile(latencies, 0.95):.0f} ms")
    print(f"max   : {max(latencies):.0f} ms")
    print(f"mean  : {statistics.fmean(latencies):.0f} ms")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
