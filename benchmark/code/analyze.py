"""
Error analysis + chart generation for the AgentShield public benchmark.

Reads results/predictions.jsonl, writes a handful of publication-quality PNGs
and a `report/summary.md` with the headline table + failure-mode commentary.
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results"
CHARTS = ROOT / "report" / "charts"
REPORT = ROOT / "report"
CHARTS.mkdir(parents=True, exist_ok=True)
REPORT.mkdir(parents=True, exist_ok=True)


def load_predictions() -> list[dict]:
    with (RESULTS / "predictions.jsonl").open() as fh:
        return [json.loads(line) for line in fh if line.strip()]


def load_metrics() -> dict:
    with (RESULTS / "metrics.json").open() as fh:
        return json.load(fh)


# ---------------------------------------------------------------------------
# Visualisations
# ---------------------------------------------------------------------------

BRAND = "#C1FF3D"   # AgentShield accent
INK   = "#0B1220"   # text / dark bar
WARN  = "#FF7A59"   # false-positive / warning
SAGE  = "#5FB6A4"   # true-negative / safe

plt.rcParams.update({
    "font.family": "DejaVu Sans",
    "axes.edgecolor": "#d0d5dd",
    "axes.grid": True,
    "grid.color": "#eef0f3",
    "grid.linewidth": 0.8,
})


def chart_f1_by_dataset(metrics: dict) -> None:
    order = ["gandalf", "safeguard", "deepset", "spml", "jackhhao", "pint"]
    order = [k for k in order if k in metrics]
    f1 = [metrics[k]["f1"] for k in order]
    acc = [metrics[k]["accuracy"] for k in order]

    x = np.arange(len(order))
    w = 0.38
    fig, ax = plt.subplots(figsize=(9, 4.5))
    ax.bar(x - w / 2, f1, w, label="F1", color=INK)
    ax.bar(x + w / 2, acc, w, label="Accuracy", color=BRAND, edgecolor=INK, linewidth=0.8)
    for i, (f, a) in enumerate(zip(f1, acc)):
        ax.text(x[i] - w/2, f + 0.01, f"{f:.2f}", ha="center", fontsize=9, color=INK)
        ax.text(x[i] + w/2, a + 0.01, f"{a:.2f}", ha="center", fontsize=9, color=INK)
    ax.set_xticks(x, [k.upper() for k in order])
    ax.set_ylim(0, 1.08)
    ax.set_ylabel("score")
    ax.set_title("AgentShield — F1 & Accuracy by dataset")
    ax.legend(loc="lower right", frameon=False)
    fig.tight_layout()
    fig.savefig(CHARTS / "f1_by_dataset.png", dpi=160, bbox_inches="tight")
    plt.close(fig)


def chart_confusion_grid(metrics: dict) -> None:
    sets = ["gandalf", "safeguard", "deepset", "spml", "jackhhao"]
    sets = [s for s in sets if s in metrics]
    cols = 3
    rows = (len(sets) + cols - 1) // cols
    fig, axes = plt.subplots(rows, cols, figsize=(cols * 3.4, rows * 3.0))
    axes = np.array(axes).reshape(-1)
    for i, src in enumerate(sets):
        cm = metrics[src]["confusion"]
        mat = np.array([[cm["tn"], cm["fp"]], [cm["fn"], cm["tp"]]])
        ax = axes[i]
        im = ax.imshow(mat, cmap="BuGn")
        ax.set_title(f"{src.upper()}  n={metrics[src]['n']}", fontsize=10)
        ax.set_xticks([0, 1], ["pred: benign", "pred: injection"], fontsize=8)
        ax.set_yticks([0, 1], ["true: benign", "true: injection"], fontsize=8)
        total = mat.sum()
        for (r, c), v in np.ndenumerate(mat):
            pct = v / total if total else 0
            color = "white" if v > mat.max() / 2 else INK
            ax.text(c, r, f"{int(v)}\n{pct:.1%}", ha="center", va="center",
                    fontsize=9, color=color)
    for j in range(i + 1, len(axes)):
        axes[j].axis("off")
    fig.suptitle("Confusion matrices per dataset", fontsize=12)
    fig.tight_layout()
    fig.savefig(CHARTS / "confusion_matrices.png", dpi=160, bbox_inches="tight")
    plt.close(fig)


def chart_confidence_distributions(preds: list[dict]) -> None:
    fig, ax = plt.subplots(figsize=(9, 4.2))
    buckets = defaultdict(list)
    for p in preds:
        if p.get("confidence") is None:
            continue
        key = "injection (true)" if p["label"] == 1 else "benign (true)"
        buckets[key].append(p["confidence"])
    bins = np.linspace(0, 1, 25)
    ax.hist(buckets["benign (true)"], bins=bins, alpha=0.8, label="true benign",
            color=SAGE)
    ax.hist(buckets["injection (true)"], bins=bins, alpha=0.8, label="true injection",
            color=INK)
    ax.set_xlabel("classifier confidence")
    ax.set_ylabel("count")
    ax.set_title("Confidence distribution by ground truth")
    ax.legend(frameon=False)
    fig.tight_layout()
    fig.savefig(CHARTS / "confidence_distributions.png", dpi=160, bbox_inches="tight")
    plt.close(fig)


def chart_latency(preds: list[dict]) -> None:
    lats = [p["processing_time_ms"] for p in preds if p.get("processing_time_ms") is not None]
    fig, ax = plt.subplots(figsize=(9, 3.6))
    ax.hist(lats, bins=40, color=BRAND, edgecolor=INK)
    ax.axvline(np.median(lats), color=INK, linestyle="--", linewidth=1)
    ax.text(np.median(lats), ax.get_ylim()[1] * 0.85, f"  p50 = {np.median(lats):.2f} ms",
            color=INK, fontsize=10)
    p95 = np.percentile(lats, 95)
    ax.axvline(p95, color=WARN, linestyle="--", linewidth=1)
    ax.text(p95, ax.get_ylim()[1] * 0.7, f"  p95 = {p95:.2f} ms", color=WARN, fontsize=10)
    ax.set_xlabel("processing_time_ms (classifier-side)")
    ax.set_ylabel("count")
    ax.set_title("End-to-end classifier latency")
    fig.tight_layout()
    fig.savefig(CHARTS / "latency.png", dpi=160, bbox_inches="tight")
    plt.close(fig)


def chart_fp_category_breakdown(preds: list[dict]) -> None:
    """What category does AgentShield think benign prompts belong to when it
    falsely flags them?"""
    fp_cats = Counter()
    fn_cats = Counter()
    for p in preds:
        if p["label"] == 0 and p.get("predicted") == 1 and p.get("top_category"):
            fp_cats[p["top_category"]] += 1
        if p["label"] == 1 and p.get("predicted") == 0 and p.get("top_category"):
            fn_cats[p["top_category"]] += 1

    fig, (a1, a2) = plt.subplots(1, 2, figsize=(11, 4))
    for ax, data, title, color in (
        (a1, fp_cats, "False-positive top category (flagged benign as injection)", WARN),
        (a2, fn_cats, "False-negative top category (missed injections)", INK),
    ):
        items = data.most_common(6)
        labels = [k for k, _ in items]
        vals = [v for _, v in items]
        ax.barh(labels[::-1], vals[::-1], color=color)
        ax.set_title(title, fontsize=10)
    fig.tight_layout()
    fig.savefig(CHARTS / "failure_categories.png", dpi=160, bbox_inches="tight")
    plt.close(fig)


# ---------------------------------------------------------------------------
# Markdown summary
# ---------------------------------------------------------------------------

def write_summary(metrics: dict, preds: list[dict]) -> None:
    all_ = metrics["__all__"]

    # Top failure examples
    fps = sorted([p for p in preds if p["label"] == 0 and p.get("predicted") == 1],
                 key=lambda p: -(p.get("confidence") or 0))[:8]
    fns = sorted([p for p in preds if p["label"] == 1 and p.get("predicted") == 0],
                 key=lambda p: (p.get("confidence") or 1))[:8]

    lines = []
    lines.append("# AgentShield — Public Benchmark Summary")
    lines.append("")
    lines.append(f"Samples evaluated: **{all_['n']:,}**  |  "
                 f"F1 **{all_['f1']:.3f}**  |  "
                 f"Accuracy **{all_['accuracy']:.3f}**  |  "
                 f"Latency p50 **{all_['latency_p50_ms']:.2f} ms**, "
                 f"p95 **{all_['latency_p95_ms']:.2f} ms**")
    lines.append("")
    lines.append("## Headline numbers")
    lines.append("")
    lines.append("| Dataset | N | Accuracy | Precision | Recall | F1 | FPR | FNR |")
    lines.append("|---|---:|---:|---:|---:|---:|---:|---:|")
    order = ["gandalf", "safeguard", "deepset", "spml", "jackhhao", "pint"]
    for src in order + ["__all__"]:
        if src not in metrics:
            continue
        m = metrics[src]
        name = "**TOTAL**" if src == "__all__" else src
        note = ""
        if not m.get("has_both_classes"):
            note = " †"
        lines.append(
            f"| {name}{note} | {m['n']:,} | {m['accuracy']:.3f} | "
            f"{m['precision']:.3f} | {m['recall']:.3f} | {m['f1']:.3f} | "
            f"{m['false_positive_rate']:.3f} | {m['false_negative_rate']:.3f} |"
        )
    lines.append("")
    lines.append("† Single-class split (no negatives available in source dataset) — "
                 "precision is trivially 1.0 when recall is high.")
    lines.append("")
    lines.append("## Top false positives (benign flagged as injection)")
    lines.append("")
    for p in fps:
        # Find original text
        txt = next((s for s in _samples_cache if s["id"] == p["id"]), {}).get("text", "")[:240]
        lines.append(f"- `[{p['source']}]` conf={p.get('confidence'):.3f} — "
                     f"{txt.strip().replace(chr(10),' ')}")
    lines.append("")
    lines.append("## Top false negatives (missed injections)")
    lines.append("")
    for p in fns:
        txt = next((s for s in _samples_cache if s["id"] == p["id"]), {}).get("text", "")[:240]
        lines.append(f"- `[{p['source']}]` conf={p.get('confidence'):.3f} — "
                     f"{txt.strip().replace(chr(10),' ')}")
    lines.append("")
    (REPORT / "summary.md").write_text("\n".join(lines), encoding="utf-8")


_samples_cache: list[dict] = []


def main() -> None:
    global _samples_cache
    metrics = load_metrics()
    preds = load_predictions()
    with (ROOT / "datasets" / "all.jsonl").open() as fh:
        _samples_cache = [json.loads(l) for l in fh if l.strip()]

    chart_f1_by_dataset(metrics)
    chart_confusion_grid(metrics)
    chart_confidence_distributions(preds)
    chart_latency(preds)
    chart_fp_category_breakdown(preds)
    write_summary(metrics, preds)
    print("wrote charts ->", CHARTS)
    print("wrote summary ->", REPORT / "summary.md")


if __name__ == "__main__":
    main()
