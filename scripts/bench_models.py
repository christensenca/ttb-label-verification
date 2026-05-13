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

# Model selection: span the cost/capability range for each provider, mixing
# thinking and non-thinking variants so the latency-vs-accuracy plot reveals
# an efficient frontier rather than clustering at one tier.
MODELS = [
    # --- OpenAI: 4o → 5, non-thinking + thinking ---
    "openai/gpt-4o-mini",       # 4o gen, mini, non-thinking — cheap baseline
    "openai/gpt-4o",            # 4o gen, flagship non-thinking, vision-strong
    "openai/gpt-4.1-mini",      # 4.1 gen, mid non-thinking
    "openai/o4-mini",           # reasoning/thinking model in the o-series
    "openai/gpt-5",             # newest gen top-tier
    # --- Google: Gemini 2.5 flash + neighbors, non-thinking + thinking ---
    "google/gemini-2.5-flash-lite",   # cheapest 2.5 variant
    "google/gemini-2.5-flash",        # mid 2.5 (dynamic thinking)
    "google/gemini-2.5-pro",          # thinking 2.5 top
    "google/gemini-3.1-flash-lite",   # newer fast tier
    "google/gemini-3.1-pro-preview",  # current best baseline
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
    """Strip extractor-internal/debug fields before comparator scoring."""
    keys = list(SCORED_FIELDS) + [
        "government_warning_text",
        "government_warning_bold",
        "government_warning_body_bold",
    ]
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
                    "field_confidence": r.field_confidence,
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


def _confidence_summary(confidence: dict | None) -> str:
    if not confidence:
        return "—"
    counts = {level: 0 for level in ("hi", "med", "low")}
    for level in confidence.values():
        if level in counts:
            counts[level] += 1
    return f"hi {counts['hi']} / med {counts['med']} / low {counts['low']}"


def _provider(model: str) -> str:
    return model.split("/", 1)[0]


def _pareto_frontier(points: list[tuple[float, float, str]]) -> list[tuple[float, float, str]]:
    """Pareto-best points minimizing x and maximizing y.

    points: list of (latency, accuracy, label). Returns the subset on the
    frontier, sorted by latency ascending — ready to draw a step line.
    """
    if not points:
        return []
    sorted_pts = sorted(points, key=lambda p: (p[0], -p[1]))
    frontier: list[tuple[float, float, str]] = []
    best_y = float("-inf")
    for x, y, label in sorted_pts:
        if y > best_y:
            frontier.append((x, y, label))
            best_y = y
    return frontier


def _plot_frontier(
    points: list[tuple[float, float, str]],
    *,
    title: str,
    ylabel: str,
    out_path: Path,
) -> None:
    """Scatter latency vs accuracy with provider colors and a Pareto line."""
    import matplotlib.pyplot as plt

    if not points:
        return

    provider_colors = {"openai": "#10a37f", "google": "#4285f4"}
    fig, ax = plt.subplots(figsize=(9, 6))

    for x, y, label in points:
        prov = _provider(label)
        ax.scatter(
            x, y,
            color=provider_colors.get(prov, "#888"),
            s=80, edgecolors="black", linewidths=0.5, zorder=3,
            label=prov,
        )
        ax.annotate(
            short(label),
            (x, y),
            textcoords="offset points", xytext=(6, 4),
            fontsize=8, zorder=4,
        )

    frontier = _pareto_frontier(points)
    if len(frontier) >= 2:
        ax.plot(
            [p[0] for p in frontier],
            [p[1] for p in frontier],
            color="#888", linestyle="--", linewidth=1.2, zorder=2,
            label="Pareto frontier",
        )

    ax.set_xlabel("avg latency (ms)")
    ax.set_ylabel(ylabel)
    ax.set_title(title)
    ax.grid(True, alpha=0.3)

    # De-dupe legend (one entry per provider).
    handles, labels = ax.get_legend_handles_labels()
    seen: dict[str, object] = {}
    for h, lab in zip(handles, labels, strict=False):
        seen.setdefault(lab, h)
    ax.legend(seen.values(), seen.keys(), loc="lower right", fontsize=9)

    fig.tight_layout()
    fig.savefig(out_path, dpi=130)
    plt.close(fig)


def write_report(results: dict, path: Path) -> None:
    lines: list[str] = [
        "# Extraction benchmark\n",
        f"_{len(BOTTLES)} bottles × {len(MODELS)} models_\n",
    ]

    summary = {
        model: {
            "correct": 0,
            "total": 0,
            "warn_ok": 0,
            "warn_total": 0,
            "warn_style_ok": 0,
            "warn_style_total": 0,
            "conf": {"hi": 0, "med": 0, "low": 0},
            "lat": [],
            "in": [],
            "out": [],
            "err": 0,
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
            s["warn_style_total"] += 1
            if cmp["government_warning_style"]["matched"]:
                s["warn_style_ok"] += 1
            for level in res.get("field_confidence", {}).values():
                if level in s["conf"]:
                    s["conf"][level] += 1
            s["lat"].append(res["latency_ms"])
            s["in"].append(res["in_tok"])
            s["out"].append(res["out_tok"])

    # --- plots: latency vs accuracy & latency vs warning-text accuracy ---
    overall_points: list[tuple[float, float, str]] = []
    warn_points: list[tuple[float, float, str]] = []
    for model in MODELS:
        s = summary[model]
        if not s["lat"]:
            continue
        avg_lat = sum(s["lat"]) / len(s["lat"])
        if s["total"]:
            overall_points.append((avg_lat, s["correct"] / s["total"], model))
        if s["warn_total"]:
            warn_points.append((avg_lat, s["warn_ok"] / s["warn_total"], model))

    stem = path.stem  # e.g. bench-20260513-103045
    overall_plot = path.with_name(f"{stem}-latency-vs-accuracy.png")
    warn_plot = path.with_name(f"{stem}-latency-vs-warning.png")
    try:
        _plot_frontier(
            overall_points,
            title="Latency vs accuracy (all scored fields)",
            ylabel="accuracy (fraction of fields matched)",
            out_path=overall_plot,
        )
        _plot_frontier(
            warn_points,
            title="Latency vs warning-text accuracy",
            ylabel="warning text match rate",
            out_path=warn_plot,
        )
        lines.append("## Latency vs accuracy\n")
        lines.append(f"![latency vs accuracy]({overall_plot.name})\n")
        lines.append(f"![latency vs warning-text accuracy]({warn_plot.name})\n")
    except ImportError:
        lines.append("_(matplotlib not installed — skipping plots)_\n")

    lines.append("## Aggregate scores\n")
    lines.append(
        "| model | accuracy | warn text | warn style | avg latency | "
        "avg tokens (in/out) | confidence | errors |"
    )
    lines.append("|---|---|---|---|---|---|---|---|")
    for model in MODELS:
        s = summary[model]
        if s["total"] == 0:
            lines.append(f"| {short(model)} | — | — | — | — | — | — | {s['err']} |")
            continue
        acc = s["correct"] / s["total"]
        warn_pct = s["warn_ok"] / s["warn_total"] if s["warn_total"] else 0
        warn_style_pct = (
            s["warn_style_ok"] / s["warn_style_total"] if s["warn_style_total"] else 0
        )
        avg_lat = sum(s["lat"]) / len(s["lat"]) if s["lat"] else 0
        avg_in = int(sum(s["in"]) / len(s["in"])) if s["in"] else 0
        avg_out = int(sum(s["out"]) / len(s["out"])) if s["out"] else 0
        conf = s["conf"]
        lines.append(
            f"| {short(model)} | {s['correct']}/{s['total']} ({acc:.0%}) "
            f"| {s['warn_ok']}/{s['warn_total']} ({warn_pct:.0%}) "
            f"| {s['warn_style_ok']}/{s['warn_style_total']} ({warn_style_pct:.0%}) "
            f"| {int(avg_lat)}ms | {avg_in}/{avg_out} "
            f"| hi {conf['hi']} / med {conf['med']} / low {conf['low']} | {s['err']} |"
        )
    lines.append("")

    for bottle in BOTTLES:
        expected = json.loads((EXPECTED / f"{bottle}.json").read_text())["expected"]
        lines.append(f"## {bottle}\n")
        lines.append("**Ground truth:**\n")
        lines.append("```json")
        lines.append(json.dumps(expected, indent=2))
        lines.append("```\n")

        header = (
            "| model | "
            + " | ".join(SCORED_FIELDS)
            + " | warn text | warn style | score | confidence | latency |"
        )
        sep = "|" + "---|" * (len(SCORED_FIELDS) + 6)
        lines.append(header)
        lines.append(sep)

        # Per-row details with the reason on each cell as a tooltip.
        for model in MODELS:
            res = results.get(bottle, {}).get(model)
            if res is None or res.get("error") or res.get("label") is None:
                empty = " | ".join(["—"] * (len(SCORED_FIELDS) + 5))
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
                cells.append(f"{glyph} `{val_str}`<br><sub>{reason}</sub>")
            warn_entry = cmp["government_warning_text"]
            warn_glyph = "✓" if warn_entry["matched"] else "✗"
            warn_reason = warn_entry["reason"].replace("|", "/")
            cells.append(f"{warn_glyph}<br><sub>{warn_reason}</sub>")
            style_entry = cmp["government_warning_style"]
            style_glyph = "✓" if style_entry["matched"] else "✗"
            style_reason = style_entry["reason"].replace("|", "/")
            cells.append(f"{style_glyph}<br><sub>{style_reason}</sub>")
            cells.append(f"{ok_count}/{len(SCORED_FIELDS)}")
            cells.append(_confidence_summary(res.get("field_confidence")))
            cells.append(f"{int(res['latency_ms'])}ms")
            lines.append(f"| {short(model)} | " + " | ".join(cells) + " |")
        lines.append("")
        lines.append("---\n")

    path.write_text("\n".join(lines))


if __name__ == "__main__":
    run()
