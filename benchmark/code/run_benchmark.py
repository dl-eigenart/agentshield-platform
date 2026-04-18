"""
AgentShield Public Benchmark — async evaluation runner.

Reads `datasets/all.jsonl` (produced by download_datasets.py), sends each
sample to the AgentShield `/v1/classify` endpoint, records the raw response,
then computes per-dataset and aggregate metrics (accuracy, precision, recall,
F1, confusion matrix) for a configurable decision threshold.

Usage:
    AGENTSHIELD_API_KEY=ask_...  python3 run_benchmark.py

Environment:
    AGENTSHIELD_API_KEY   required — key for the /v1/classify endpoint
    AGENTSHIELD_BASE      default https://api.agentshield.pro
    CONCURRENCY           default 16
    DECISION_THRESHOLD    default 0.5  (we use is_threat as ground-truth decision)
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from collections import defaultdict
from pathlib import Path

import aiohttp

ROOT = Path(__file__).resolve().parents[1]
DATASETS = ROOT / "datasets"
RESULTS = ROOT / "results"
RESULTS.mkdir(parents=True, exist_ok=True)

API_BASE = os.environ.get("AGENTSHIELD_BASE", "https://api.agentshield.pro").rstrip("/")
API_KEY = os.environ.get("AGENTSHIELD_API_KEY")
CONCURRENCY = int(os.environ.get("CONCURRENCY", "16"))
THRESHOLD = float(os.environ.get("DECISION_THRESHOLD", "0.5"))
MAX_TEXT_LEN = int(os.environ.get("MAX_TEXT_LEN", "8000"))  # guard against huge docs

if not API_KEY:
    print("ERROR: set AGENTSHIELD_API_KEY", file=sys.stderr)
    sys.exit(1)

CLASSIFY_URL = f"{API_BASE}/v1/classify"


def load_samples() -> list[dict]:
    path = DATASETS / "all.jsonl"
    with path.open() as fh:
        return [json.loads(line) for line in fh if line.strip()]


async def classify(session: aiohttp.ClientSession, sample: dict) -> dict:
    text = sample["text"][:MAX_TEXT_LEN]
    body = {"text": text}
    for attempt in range(4):
        try:
            async with session.post(
                CLASSIFY_URL,
                json=body,
                headers={
                    "Content-Type": "application/json",
                    "X-API-Key": API_KEY,
                },
                timeout=aiohttp.ClientTimeout(total=30),
            ) as resp:
                if resp.status == 429:
                    # Rate limit — exponential backoff
                    await asyncio.sleep(2 ** attempt)
                    continue
                resp.raise_for_status()
                data = await resp.json()
                result = data.get("result", {}) or {}
                return {
                    "id": sample["id"],
                    "source": sample["source"],
                    "label": int(sample["label"]),
                    "predicted": 1 if result.get("is_threat") else 0,
                    "confidence": float(result.get("confidence") or 0.0),
                    "intent": result.get("intent"),
                    "benign_similarity": result.get("benign_similarity"),
                    "classification_path": result.get("classification_path"),
                    "processing_time_ms": result.get("processing_time_ms"),
                    "top_category": (
                        result.get("threat_scores", [{}])[0].get("category")
                        if result.get("threat_scores") else None
                    ),
                    "http_status": resp.status,
                }
        except Exception as exc:  # noqa: BLE001
            if attempt == 3:
                return {
                    "id": sample["id"],
                    "source": sample["source"],
                    "label": int(sample["label"]),
                    "predicted": None,
                    "error": f"{type(exc).__name__}: {exc}",
                }
            await asyncio.sleep(1 + attempt)
    return {"id": sample["id"], "source": sample["source"], "label": int(sample["label"]), "predicted": None, "error": "retries_exhausted"}


async def bounded(sem: asyncio.Semaphore, fn, *args, **kwargs):
    async with sem:
        return await fn(*args, **kwargs)


async def run() -> list[dict]:
    samples = load_samples()
    print(f"loaded {len(samples)} samples")

    sem = asyncio.Semaphore(CONCURRENCY)
    connector = aiohttp.TCPConnector(limit=CONCURRENCY * 2)
    async with aiohttp.ClientSession(connector=connector) as session:
        tasks = [bounded(sem, classify, session, s) for s in samples]
        results: list[dict] = []
        t0 = time.time()
        for i, coro in enumerate(asyncio.as_completed(tasks), 1):
            r = await coro
            results.append(r)
            if i % 100 == 0 or i == len(tasks):
                elapsed = time.time() - t0
                rps = i / elapsed if elapsed else 0
                print(f"  [{i:>5}/{len(tasks)}]  elapsed={elapsed:6.1f}s  rate={rps:5.1f} req/s")
    return results


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------

def confusion(rows: list[dict]) -> dict:
    tp = fp = tn = fn = 0
    for r in rows:
        if r.get("predicted") is None:
            continue
        y, p = r["label"], r["predicted"]
        if y == 1 and p == 1: tp += 1
        elif y == 0 and p == 1: fp += 1
        elif y == 0 and p == 0: tn += 1
        elif y == 1 and p == 0: fn += 1
    return {"tp": tp, "fp": fp, "tn": tn, "fn": fn}


def metrics_from_confusion(cm: dict) -> dict:
    tp, fp, tn, fn = cm["tp"], cm["fp"], cm["tn"], cm["fn"]
    total = tp + fp + tn + fn
    acc = (tp + tn) / total if total else 0.0
    prec = tp / (tp + fp) if (tp + fp) else 0.0
    rec = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * prec * rec / (prec + rec) if (prec + rec) else 0.0
    fpr = fp / (fp + tn) if (fp + tn) else 0.0
    fnr = fn / (fn + tp) if (fn + tp) else 0.0
    return {
        "accuracy": acc,
        "precision": prec,
        "recall": rec,
        "f1": f1,
        "false_positive_rate": fpr,
        "false_negative_rate": fnr,
        "n": total,
    }


def summarize(results: list[dict]) -> dict:
    # per-source + overall
    buckets: dict[str, list[dict]] = defaultdict(list)
    for r in results:
        buckets[r["source"]].append(r)
    buckets["__all__"] = results

    out: dict[str, dict] = {}
    for src, rows in buckets.items():
        errors = sum(1 for r in rows if r.get("predicted") is None)
        cm = confusion(rows)
        m = metrics_from_confusion(cm)
        m["errors"] = errors
        m["has_both_classes"] = any(r["label"] == 1 for r in rows) and any(
            r["label"] == 0 for r in rows
        )
        # Latency stats from successful responses
        lats = [
            r["processing_time_ms"]
            for r in rows
            if r.get("processing_time_ms") is not None
        ]
        if lats:
            lats_sorted = sorted(lats)
            m["latency_p50_ms"] = lats_sorted[len(lats_sorted) // 2]
            m["latency_p95_ms"] = lats_sorted[int(len(lats_sorted) * 0.95)]
            m["latency_mean_ms"] = sum(lats) / len(lats)
        m["confusion"] = cm
        out[src] = m
    return out


def main() -> None:
    results = asyncio.run(run())

    # Persist raw predictions
    raw_path = RESULTS / "predictions.jsonl"
    with raw_path.open("w") as fh:
        for r in results:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"wrote raw predictions -> {raw_path}")

    summary = summarize(results)
    summary_path = RESULTS / "metrics.json"
    with summary_path.open("w") as fh:
        json.dump(summary, fh, indent=2)
    print(f"wrote metrics -> {summary_path}")

    # Pretty print
    print("\n" + "=" * 88)
    print(f"{'source':<14} {'n':>6} {'acc':>7} {'prec':>7} {'rec':>7} {'f1':>7} {'fpr':>7} {'fnr':>7} {'errs':>5}")
    print("-" * 88)
    order = sorted([k for k in summary if k != "__all__"]) + ["__all__"]
    for src in order:
        m = summary[src]
        note = "" if m.get("has_both_classes") else "  (single-class)"
        print(
            f"{src:<14} {m['n']:>6} "
            f"{m['accuracy']:>7.3f} {m['precision']:>7.3f} "
            f"{m['recall']:>7.3f} {m['f1']:>7.3f} "
            f"{m['false_positive_rate']:>7.3f} {m['false_negative_rate']:>7.3f} "
            f"{m['errors']:>5}{note}"
        )


if __name__ == "__main__":
    main()
