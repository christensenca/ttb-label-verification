"""Vision-model benchmark for label extraction.

Runs each (model × bottle) combination through pipeline.extract, scores
against ground truth, and produces a JSON dump + markdown report under
reports/.

Usage: python -m scripts.bench_models
"""

from __future__ import annotations

import json
import time
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

from pipeline.extract import extract

load_dotenv()

MODELS = [
    # Top-2 after the dual-method bench:
    "openai/gpt-4o-mini",       # highest accuracy (79%), 0 errors
    "google/gemini-2.5-flash",  # Google-side balance pick
    # Others temporarily off — uncomment to re-add for a wider sweep:
    # "openai/gpt-4o",
    # "openai/gpt-4.1-mini",
    # "google/gemini-2.5-pro",
    # "google/gemini-3.1-flash-lite",
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

SCORED_FIELDS = [
    "brand",
    "class_type",
    "alcohol_content",
    "net_contents",
    "producer_name",
    "producer_address",
    "is_imported",
    "country_of_origin",
]


# -------- comparison helpers --------


def normalize(v):
    if v is None:
        return None
    if isinstance(v, str):
        return v.lower().strip().rstrip(".")
    return v


def field_match(extracted, expected) -> bool:
    return normalize(extracted) == normalize(expected)


def to_canonical(label: dict) -> dict:
    """Strip extractor-internal fields (transcription scaffold) and keep
    only what the comparator scores against ground truth."""
    keys = SCORED_FIELDS + ["government_warning_text"]
    return {k: label.get(k) for k in keys}


def short(model: str) -> str:
    return model.split("/")[-1]


# -------- runner --------


def run() -> None:
    REPORTS.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    results_path = REPORTS / f"bench-{stamp}.json"
    report_path = REPORTS / f"bench-{stamp}.md"

    total = len(BOTTLES) * len(MODELS)
    print(f"running {total} calls: {len(BOTTLES)} bottles × {len(MODELS)} models")
    print(f"results → {results_path}")
    print(f"report  → {report_path}\n", flush=True)

    start = time.perf_counter()
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

            # Save incrementally so partial failure / timeout leaves usable data.
            results_path.write_text(json.dumps(results, indent=2, default=str))

    elapsed = time.perf_counter() - start
    print(f"\ndone in {elapsed / 60:.1f} min\n", flush=True)

    write_report(results, report_path)
    print(f"report written: {report_path}")


def write_report(results: dict, path: Path) -> None:
    lines: list[str] = []
    lines.append(f"# Extraction benchmark\n")
    lines.append(f"_{len(BOTTLES)} bottles × {len(MODELS)} models_\n")

    # Per-model aggregate
    summary = {
        model: {"correct": 0, "total": 0, "warn_ok": 0, "warn_total": 0, "lat": [], "in": [], "out": [], "err": 0}
        for model in MODELS
    }

    for bottle in BOTTLES:
        expected = json.loads((EXPECTED / f"{bottle}.json").read_text())["expected"]
        for model in MODELS:
            res = results[bottle][model]
            s = summary[model]
            if res.get("error") or res.get("label") is None:
                s["err"] += 1
                continue
            canonical = to_canonical(res["label"])
            for f in SCORED_FIELDS:
                s["total"] += 1
                if field_match(canonical.get(f), expected.get(f)):
                    s["correct"] += 1
            warn = canonical.get("government_warning_text") or ""
            s["warn_total"] += 1
            if warn.upper().startswith("GOVERNMENT WARNING:"):
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

    # Per-bottle detail
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

        for model in MODELS:
            res = results[bottle][model]
            if res.get("error") or res.get("label") is None:
                lines.append(f"| {short(model)} | " + " | ".join(["—"] * (len(SCORED_FIELDS) + 3)) + " |")
                continue
            canonical = to_canonical(res["label"])
            cells: list[str] = []
            ok_count = 0
            for f in SCORED_FIELDS:
                val = canonical.get(f)
                ok = field_match(val, expected.get(f))
                if ok:
                    ok_count += 1
                val_str = str(val)[:30] if val is not None else "null"
                cells.append(f"{'✓' if ok else '✗'} `{val_str}`")
            warn = canonical.get("government_warning_text") or ""
            warn_ok = warn.upper().startswith("GOVERNMENT WARNING:")
            cells.append("✓" if warn_ok else "✗")
            cells.append(f"{ok_count}/{len(SCORED_FIELDS)}")
            cells.append(f"{int(res['latency_ms'])}ms")
            lines.append(f"| {short(model)} | " + " | ".join(cells) + " |")
        lines.append("")
        lines.append("---\n")

    path.write_text("\n".join(lines))


if __name__ == "__main__":
    run()
