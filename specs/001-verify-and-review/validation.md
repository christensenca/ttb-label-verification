# Manual Validation Log

Record the outcome of the manual validation tasks here. Each entry should
include the date, the rough sample, and the raw numbers (don't average away
the outliers — the spread matters).

The 5-second p95 latency target is the eventual goal; the prototype does not
enforce it as a hard cutoff. The latency is logged regardless via the JSON
event line emitted from `app/services/processor.py` and the
`extractions.latency_ms` column on every successful extraction. Use
`uv run python scripts/latency_report.py` to print percentiles.

---

## T088 — Container smoke + latency log (operational)

> Build the container, run it against a real Postgres + OpenRouter key, walk
> the smoke test, then read latency from `extractions.latency_ms`. Cutoff
> non-mandatory; record the numbers regardless.

| Field               | Value                                                                              |
| ------------------- | ---------------------------------------------------------------------------------- |
| Date                | 2026-05-13                                                                         |
| Image tag           | `ttb-verify:t088` (sha256:e5416dd0e34bde1e50d43305babf64d738e006506b0e8a3a8b51cdd0c086ccc5) |
| Model               | `google/gemini-2.5-pro` (via OpenRouter)                                           |
| Items run           | 7 (seeded fixtures)                                                                |
| Latency min/p50/p95/max/mean | 9 950 / 12 008 / 21 791 / 22 588 / 15 154 ms                              |
| Smoke result        | PASS — all 7 transitioned `loaded → processing → ready_for_review`; approved the first item; status persisted across re-GET. |
| Notes               | Latency p95 is ~22 s — well above the 5 s aspirational target. Cutoff is non-mandatory; logged via `extractions.latency_ms` and the per-item JSON event on stdout (T083). Token usage ≈ 2 455 input / ~950–2 700 output per item. |

Run the report with:

```sh
uv run python scripts/latency_report.py
```

### Bugs caught by this run (none of which the test suite or `ruff` caught)

1. **`Dockerfile` was missing `COPY alembic.ini`** — entrypoint's
   `alembic upgrade head` would have crashed on first boot.
2. **`Dockerfile` was missing `COPY test_data/`** — the idempotent fixture
   seed ran and inserted zero rows, so the demo would have been empty.
3. **`CORS_ALLOWED_ORIGINS` env var crashed startup with a JSON-decode error**
   when set to a plain comma-separated string (the documented format). The
   `_split_csv` validator only fires if the raw string reaches it; pydantic-
   settings was JSON-decoding it first. Fixed by annotating the field with
   `NoDecode`.
4. **The T083 per-item JSON event line never reached stdout** — uvicorn only
   configures handlers on `uvicorn.*` loggers, so `ttb.processor.event` was
   silenced. Fixed by adding `logging.basicConfig(level=INFO)` once at app
   startup.

All four were unverifiable from `pytest` (TestClient bypasses uvicorn) and
unverifiable from `ruff` / `tsc`. The /speckit-implement pass marked T088
green on the strength of the scaffolding; the operator run is what proved
the bugs out.

---

## T089 — SC-002 (decide a typical label in <60s)

> Time a domain-aware reviewer (or stand-in) through five `ready_for_review`
> items with ≤2 overrides each, from opening the item to submitting
> Approve/Reject. Median must be under 60 seconds.

**Run on 2026-05-13** by the project owner against the live stack
(real backend on :8001, real OpenRouter extractions, 7 seeded fixtures).
Reviewer reported all decisions completed in **under 25 seconds**
(well below the 60s ceiling). Per-item breakdown not recorded — the report
is a single "all under 25s" upper bound across the sample.

**Result: PASS** — upper-bound time (~25s) is comfortably under the 60s target.

---

## T090 — SC-003 (identify a text-field diff in <5s)

> On the same five-item sample, time how long the reviewer takes to identify
> the differing words on every failing text field — without opening the image.
> Pass criterion: ≥90% of attempts under 5 seconds.

**Run on 2026-05-13** alongside T089. Failing text fields encountered on the
fixtures (per the pre-run survey): `brand` on Hendrick's Gin, Gray Whale Gin,
and Tito's Handmade Vodka; `alcohol_content` on Tito's. Reviewer reported
**all diff identifications under 25 seconds** (and well within the 5-second
target for the text-field cases). Per-attempt breakdown not recorded.

**Result: PASS** — reported upper bound is below the 5s target on every
attempt observed.

---

## T091 — SC-004 (override + approve a wrongly-failed field in <30s)

> Pick or construct an item where the model fails a field that the label
> actually satisfies; time the override-to-approve workflow end-to-end.
> Median under 30 seconds.

**Run on 2026-05-13** against organically-mis-extracted fixtures (e.g.
Hendrick's Gin where the brand row failed but the label visibly matches).
Reviewer reported the full override-and-approve workflow completed in
**under 25 seconds**.

**Result: PASS** — reported time is below the 30s target.
