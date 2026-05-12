"""Vision-model benchmark for label extraction.

Runs each (model × bottle) combination through pipeline.extract, scores
against ground truth via pipeline.compare, and produces a JSON dump + a
markdown report under reports/.

Usage:
  python -m scripts.bench_models                              # live run
  python -m scripts.bench_models --from-cache reports/x.json  # re-score
                                                              # cached results
"""

from __future__ import annotations

import argparse
import json
import time
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

from pipeline.compare import SCORED_FIELDS, compare
from pipeline.extract import extract

load_dotenv()

MODELS = [
    "openai/gpt-4o",                  # full, not mini — testing capability ceiling
    "google/gemini-3.1-flash-lite",   # newer Gemini generation
    # Previous bench set — restore for comparison:
    # "openai/gpt-4o-mini",
    # "google/gemini-2.5-flash",
    # "openai/gpt-4.1-mini",
    # "google/gemini-2.5-pro",
]

BOTTLES = [
    "don_julio",
    "gray_whale",
    "hendricks",
    "makers_mark",
    "titos",
    "whistlepig",
    "woodfords",
]

REPO = Path(__file__).resolve().parent.parent
IMAGES = REPO / "test_data" / "images"
EXPECTED = REPO / "test_data" / "expected"
REPORTS = REPO / "reports"


def to_canonical(label: dict) -> dict:
    """Strip extractor-internal fields (transcription scaffold) and keep
    only what the comparator scores against ground truth."""
    keys = list(SCORED_FIELDS) + ["government_warning_text"]
    return {k: label.get(k) for k in keys}


def short(model: str) -> str:
    return model.split("/")[-1]


# -------- runner --------


def run_live() -> dict:
    """Hit the LLM for every (bottle × model) combination."""
    REPORTS.mkdir(exist_ok=True)
    total = len(BOTTLES) * len(MODELS)
    print(f"running {total} calls: {len(BOTTLES)} bottles × {len(MODELS)} models")

    results: dict = {}
    idx = 0
    for bottle in BOTTLES:
        results[bottle] = {}
        for model in MODELS:
            idx += 1
            t0 = time.perf_counter()
            print(f"  [{idx:>2}/{total}] {bottle:14} {model:38}", end="", flush=True)
            try:
                r = extract(IMAGES / f"{bottle}.jpg", model=model)
                results[bottle][model] = {
                    "label": r.label.model_dump(),
                    "latency_ms": r.latency_ms,
                    "in_tok": r.input_tokens,
                    "out_tok": r.output_tokens,
                    "error": None,
                }
                print(f"  {r.latency_ms / 1000:>5.1f}s", flush=True)
            except Exception as e:
                results[bottle][model] = {
                    "label": None,
                    "latency_ms": (time.perf_counter() - t0) * 1000,
                    "in_tok": 0,
                    "out_tok": 0,
                    "error": f"{type(e).__name__}: {e}",
                }
                print(f"  ERROR: {e}", flush=True)
    return results


def load_cached(path: Path) -> dict:
    """Load a previously-saved bench JSON.

    Tolerates the older v1/v2 method-nested shape produced by an earlier
    iteration of this script — picks v1 when present so the cache from
    `reports/bench-20260512-123643.json` re-scores cleanly without a
    schema migration.
    """
    raw = json.loads(path.read_text())
    if not raw:
        return raw
    sample = next(iter(raw.values()))
    if sample and all(isinstance(v, dict) and "label" not in v for v in sample.values()):
        # Method-nested shape: results[bottle][method][model]. Flatten via v1.
        flat: dict = {}
        for bottle, methods in raw.items():
            chosen = methods.get("v1") or next(iter(methods.values()))
            flat[bottle] = chosen
        return flat
    return raw


def run() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--from-cache",
        type=Path,
        metavar="PATH",
        help="Re-score a previously saved bench JSON (skips all LLM calls).",
    )
    args = parser.parse_args()

    REPORTS.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    results_path = REPORTS / f"bench-{stamp}.json"
    report_path = REPORTS / f"bench-{stamp}.md"

    if args.from_cache:
        print(f"loading cached results from {args.from_cache}")
        results = load_cached(args.from_cache)
        # Don't overwrite the source; just write a fresh re-scored copy.
        results_path.write_text(json.dumps(results, indent=2, default=str))
        print(f"results → {results_path}")
        print(f"report  → {report_path}\n", flush=True)
    else:
        print(f"results → {results_path}")
        print(f"report  → {report_path}\n", flush=True)
        start = time.perf_counter()
        results = run_live()
        elapsed = time.perf_counter() - start
        results_path.write_text(json.dumps(results, indent=2, default=str))
        print(f"\ndone in {elapsed / 60:.1f} min\n", flush=True)

    write_report(results, report_path)
    print(f"report written: {report_path}")


# -------- reporting --------


def write_report(results: dict, path: Path) -> None:
    lines: list[str] = [
        "# Extraction benchmark\n",
        f"_{len(BOTTLES)} bottles × {len(MODELS)} models_\n",
    ]

    summary = {
        model: {
            "correct": 0, "total": 0,
            "warn_ok": 0, "warn_total": 0,
            "lat": [], "in": [], "out": [], "err": 0,
        }
        for model in MODELS
    }

    for bottle in BOTTLES:
        expected = json.loads((EXPECTED / f"{bottle}.json").read_text())["expected"]
        for model in MODELS:
            res = results.get(bottle, {}).get(model)
            if res is None:
                continue
            s = summary[model]
            if res.get("error") or res.get("label") is None:
                s["err"] += 1
                continue
            canonical = to_canonical(res["label"])
            cmp = compare(canonical, expected)
            for f in SCORED_FIELDS:
                s["total"] += 1
                if cmp[f]["matched"]:
                    s["correct"] += 1
            s["warn_total"] += 1
            if cmp["government_warning_text"]["matched"]:
                s["warn_ok"] += 1
            s["lat"].append(res["latency_ms"])
            s["in"].append(res["in_tok"])
            s["out"].append(res["out_tok"])

    lines.append("## Aggregate scores\n")
    lines.append("| model | accuracy | warn | avg latency | avg tokens (in/out) | errors |")
    lines.append("|---|---|---|---|---|---|")
    for model in MODELS:
        s = summary[model]
        if s["total"] == 0:
            lines.append(f"| {short(model)} | — | — | — | — | {s['err']} |")
            continue
        acc = s["correct"] / s["total"]
        warn_pct = s["warn_ok"] / s["warn_total"] if s["warn_total"] else 0
        avg_lat = sum(s["lat"]) / len(s["lat"]) if s["lat"] else 0
        avg_in = int(sum(s["in"]) / len(s["in"])) if s["in"] else 0
        avg_out = int(sum(s["out"]) / len(s["out"])) if s["out"] else 0
        lines.append(
            f"| {short(model)} | {s['correct']}/{s['total']} ({acc:.0%}) "
            f"| {s['warn_ok']}/{s['warn_total']} ({warn_pct:.0%}) "
            f"| {int(avg_lat)}ms | {avg_in}/{avg_out} | {s['err']} |"
        )
    lines.append("")

    for bottle in BOTTLES:
        expected = json.loads((EXPECTED / f"{bottle}.json").read_text())["expected"]
        lines.append(f"## {bottle}\n")
        lines.append("**Ground truth:**\n")
        lines.append("```json")
        lines.append(json.dumps(expected, indent=2))
        lines.append("```\n")

        header = "| model | " + " | ".join(SCORED_FIELDS) + " | warn | score | latency |"
        sep = "|" + "---|" * (len(SCORED_FIELDS) + 4)
        lines.append(header)
        lines.append(sep)

        # Per-row details with the reason on each cell as a tooltip.
        for model in MODELS:
            res = results.get(bottle, {}).get(model)
            if res is None or res.get("error") or res.get("label") is None:
                empty = " | ".join(["—"] * (len(SCORED_FIELDS) + 3))
                lines.append(f"| {short(model)} | {empty} |")
                continue
            canonical = to_canonical(res["label"])
            cmp = compare(canonical, expected)
            cells: list[str] = []
            ok_count = 0
            for f in SCORED_FIELDS:
                entry = cmp[f]
                if entry["matched"]:
                    ok_count += 1
                val = entry["extracted"]
                val_str = str(val)[:30] if val is not None else "null"
                glyph = "✓" if entry["matched"] else "✗"
                reason = entry["reason"].replace("|", "/")
                cells.append(f'{glyph} `{val_str}`<br><sub>{reason}</sub>')
            warn_entry = cmp["government_warning_text"]
            warn_glyph = "✓" if warn_entry["matched"] else "✗"
            warn_reason = warn_entry["reason"].replace("|", "/")
            cells.append(f"{warn_glyph}<br><sub>{warn_reason}</sub>")
            cells.append(f"{ok_count}/{len(SCORED_FIELDS)}")
            cells.append(f"{int(res['latency_ms'])}ms")
            lines.append(f"| {short(model)} | " + " | ".join(cells) + " |")
        lines.append("")
        lines.append("---\n")

    path.write_text("\n".join(lines))


if __name__ == "__main__":
    run()
