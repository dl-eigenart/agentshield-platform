"""
AgentShield Public Benchmark — Dataset Downloader

Fetches the four public prompt-injection benchmarks and normalises them to a
shared schema written as JSONL:

    {"text": str, "label": int, "source": str, "id": str}

where label = 1 means "malicious / injection", label = 0 means "benign".

Datasets:
  - Lakera PINT          (github.com/lakeraai/pint-benchmark, YAML)
  - deepset/prompt-injections        (HuggingFace)
  - Lakera/gandalf_ignore_instructions (HuggingFace — all positives)
  - qualifire/prompt-injections-benchmark (HuggingFace)
"""

from __future__ import annotations

import json
import os
import sys
import urllib.request
from pathlib import Path

OUT_DIR = Path(__file__).resolve().parents[1] / "datasets"
OUT_DIR.mkdir(parents=True, exist_ok=True)


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=True) + "\n")
    print(f"  wrote {len(rows):>5} rows -> {path.relative_to(OUT_DIR.parent)}")


# ---------------------------------------------------------------------------
# Lakera PINT benchmark — YAML file in the public repo
# ---------------------------------------------------------------------------

# The FULL Lakera PINT dataset (4,314 samples) is intentionally not published
# to prevent training-set contamination. Only the *example* subset is public:
# benchmark/data/example-dataset.yaml.  We use that as a PINT-style smoke test
# and are transparent about this limitation in the benchmark report.
PINT_URL = (
    "https://raw.githubusercontent.com/lakeraai/pint-benchmark/main/"
    "benchmark/data/example-dataset.yaml"
)


def download_pint() -> list[dict]:
    print("\n[1/6] Lakera PINT benchmark (public example subset) ...")
    try:
        import yaml  # type: ignore
    except ImportError:
        os.system(f"{sys.executable} -m pip install --break-system-packages -q pyyaml")
        import yaml  # type: ignore

    try:
        req = urllib.request.Request(
            PINT_URL, headers={"User-Agent": "AgentShield-Benchmark/1.0"}
        )
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw = resp.read().decode("utf-8")
    except Exception as exc:
        print(f"  ! could not fetch PINT ({exc}); skipping")
        return []

    data = yaml.safe_load(raw)
    rows: list[dict] = []
    for idx, item in enumerate(data):
        text = item.get("text") or ""
        cat = (item.get("category") or "").lower()
        # Lakera labels: "prompt_injection", "jailbreak", "hard_negatives",
        # "chats", "documents". Only first two are positive examples.
        if cat in {"prompt_injection", "jailbreak"}:
            label = 1
        elif cat in {"hard_negatives", "chats", "documents"}:
            label = 0
        else:
            # unknown category — skip to stay honest
            continue
        if not text.strip():
            continue
        rows.append(
            {
                "text": text,
                "label": label,
                "source": "pint",
                "id": f"pint-{idx}",
                "category": cat,
            }
        )
    write_jsonl(OUT_DIR / "pint.jsonl", rows)
    return rows


# ---------------------------------------------------------------------------
# Hugging Face datasets
# ---------------------------------------------------------------------------

def download_deepset() -> list[dict]:
    print("\n[2/6] deepset/prompt-injections ...")
    from datasets import load_dataset, get_dataset_config_names  # type: ignore

    rows: list[dict] = []
    try:
        ds = load_dataset("deepset/prompt-injections")
    except Exception as exc:
        print(f"  ! load_dataset failed ({exc}); skipping")
        return []

    for split in ds:
        for idx, row in enumerate(ds[split]):
            text = row.get("text") or ""
            label = int(row.get("label", 0))
            if not text.strip():
                continue
            rows.append(
                {
                    "text": text,
                    "label": label,
                    "source": "deepset",
                    "id": f"deepset-{split}-{idx}",
                    "split": split,
                }
            )
    write_jsonl(OUT_DIR / "deepset.jsonl", rows)
    return rows


def download_gandalf() -> list[dict]:
    print("\n[3/6] Lakera/gandalf_ignore_instructions ...")
    from datasets import load_dataset  # type: ignore

    rows: list[dict] = []
    try:
        ds = load_dataset("Lakera/gandalf_ignore_instructions")
    except Exception as exc:
        print(f"  ! load_dataset failed ({exc}); skipping")
        return []

    # All Gandalf samples are adversarial (trying to make the agent leak the password).
    for split in ds:
        for idx, row in enumerate(ds[split]):
            text = row.get("text") or row.get("prompt") or ""
            if not text.strip():
                continue
            rows.append(
                {
                    "text": text,
                    "label": 1,
                    "source": "gandalf",
                    "id": f"gandalf-{split}-{idx}",
                    "split": split,
                }
            )
    write_jsonl(OUT_DIR / "gandalf.jsonl", rows)
    return rows


def download_qualifire() -> list[dict]:
    """qualifire/prompt-injections-benchmark was renamed and is now gated
    on Hugging Face (rogue-security/prompt-injections-benchmark, license
    cc-by-nc-4.0, auto-gated). Without an HF_TOKEN we cannot fetch it.
    """
    print("\n[4/6] qualifire/prompt-injections-benchmark ...")
    from datasets import load_dataset  # type: ignore

    rows: list[dict] = []
    for name in ("qualifire/prompt-injections-benchmark", "rogue-security/prompt-injections-benchmark"):
        try:
            ds = load_dataset(name)
            break
        except Exception as exc:
            print(f"  ! {name} -> {type(exc).__name__}: {str(exc)[:120]}")
            ds = None
    if ds is None:
        print("  ! skipping (gated, requires HF_TOKEN)")
        return []

    for split in ds:
        for idx, row in enumerate(ds[split]):
            text = row.get("text") or row.get("prompt") or ""
            label_raw = row.get("label")
            if label_raw is None:
                continue
            if isinstance(label_raw, str):
                label = 1 if label_raw.lower() in {"jailbreak", "malicious", "injection", "1", "true"} else 0
            else:
                label = int(label_raw)
            if not text.strip():
                continue
            rows.append(
                {
                    "text": text,
                    "label": label,
                    "source": "qualifire",
                    "id": f"qualifire-{split}-{idx}",
                    "split": split,
                }
            )
    write_jsonl(OUT_DIR / "qualifire.jsonl", rows)
    return rows


def download_jackhhao() -> list[dict]:
    """Additional public benchmark — used to compensate for the two gated sets
    (full PINT, qualifire). Widely cited in prompt-injection research."""
    print("\n[5/6] jackhhao/jailbreak-classification ...")
    from datasets import load_dataset  # type: ignore

    rows: list[dict] = []
    try:
        ds = load_dataset("jackhhao/jailbreak-classification")
    except Exception as exc:
        print(f"  ! load_dataset failed ({exc}); skipping")
        return []

    for split in ds:
        for idx, row in enumerate(ds[split]):
            text = row.get("prompt") or row.get("text") or ""
            type_str = (row.get("type") or "").lower()
            if not text.strip():
                continue
            label = 1 if type_str in {"jailbreak", "malicious", "injection"} else 0
            rows.append(
                {
                    "text": text,
                    "label": label,
                    "source": "jackhhao",
                    "id": f"jackhhao-{split}-{idx}",
                    "split": split,
                }
            )
    write_jsonl(OUT_DIR / "jackhhao.jsonl", rows)
    return rows


def download_hackaprompt() -> list[dict]:
    """HackAPrompt 2023 competition — one of the largest adversarial prompt
    corpora (~600k rows). We sample only `correct=True` and shuffle to cap
    to keep the benchmark tractable."""
    print("\n[6/6] hackaprompt/hackaprompt-dataset (sampled) ...")
    from datasets import load_dataset  # type: ignore

    rows: list[dict] = []
    try:
        ds = load_dataset("hackaprompt/hackaprompt-dataset", split="train", streaming=True)
    except Exception as exc:
        print(f"  ! load_dataset failed ({exc}); skipping")
        return []

    seen = 0
    # All successful hackaprompt attempts are by definition adversarial.
    for row in ds:
        if row.get("correct") is not True:
            continue
        text = row.get("user_input") or row.get("prompt") or ""
        if not text.strip():
            continue
        rows.append(
            {
                "text": text,
                "label": 1,
                "source": "hackaprompt",
                "id": f"hackaprompt-{seen}",
                "level": row.get("level"),
                "model": row.get("model"),
            }
        )
        seen += 1
        if seen >= 1500:  # cap — the dataset is huge
            break
    write_jsonl(OUT_DIR / "hackaprompt.jsonl", rows)
    return rows


def download_spml() -> list[dict]:
    """reshabhs/SPML — 16k system+user prompt pairs with injection labels.
    We use only the User Prompt column (what the classifier actually sees)
    and cap the split to keep the benchmark tractable."""
    print("\n[7/8] reshabhs/SPML_Chatbot_Prompt_Injection (capped @ 1500) ...")
    from datasets import load_dataset  # type: ignore
    import random

    rows: list[dict] = []
    try:
        ds = load_dataset("reshabhs/SPML_Chatbot_Prompt_Injection", split="train")
    except Exception as exc:
        print(f"  ! load_dataset failed ({exc}); skipping")
        return []

    # Stratified subsample: 750 pos + 750 neg
    pos, neg = [], []
    for idx, row in enumerate(ds):
        text = (row.get("User Prompt") or "").strip()
        if not text:
            continue
        label = int(row.get("Prompt injection") or 0)
        (pos if label == 1 else neg).append((idx, text))

    rng = random.Random(42)
    rng.shuffle(pos)
    rng.shuffle(neg)
    for bucket, label in ((pos[:750], 1), (neg[:750], 0)):
        for idx, text in bucket:
            rows.append(
                {
                    "text": text,
                    "label": label,
                    "source": "spml",
                    "id": f"spml-{idx}",
                }
            )
    write_jsonl(OUT_DIR / "spml.jsonl", rows)
    return rows


def download_safeguard() -> list[dict]:
    """xTRam1/safe-guard-prompt-injection — 8k rows, simple text+label schema."""
    print("\n[8/8] xTRam1/safe-guard-prompt-injection (capped @ 1500) ...")
    from datasets import load_dataset  # type: ignore
    import random

    rows: list[dict] = []
    try:
        ds = load_dataset("xTRam1/safe-guard-prompt-injection", split="train")
    except Exception as exc:
        print(f"  ! load_dataset failed ({exc}); skipping")
        return []

    pos, neg = [], []
    for idx, row in enumerate(ds):
        text = (row.get("text") or "").strip()
        if not text:
            continue
        label = int(row.get("label") or 0)
        (pos if label == 1 else neg).append((idx, text))

    rng = random.Random(42)
    rng.shuffle(pos)
    rng.shuffle(neg)
    for bucket, label in ((pos[:750], 1), (neg[:750], 0)):
        for idx, text in bucket:
            rows.append(
                {
                    "text": text,
                    "label": label,
                    "source": "safeguard",
                    "id": f"safeguard-{idx}",
                }
            )
    write_jsonl(OUT_DIR / "safeguard.jsonl", rows)
    return rows


def main() -> None:
    combined: list[dict] = []
    for fn in (
        download_pint,
        download_deepset,
        download_gandalf,
        download_qualifire,
        download_jackhhao,
        download_hackaprompt,
        download_spml,
        download_safeguard,
    ):
        try:
            combined.extend(fn())
        except Exception as exc:  # noqa: BLE001
            print(f"  ! {fn.__name__} failed: {exc}")

    write_jsonl(OUT_DIR / "all.jsonl", combined)

    print("\nSummary:")
    counts: dict[str, dict[str, int]] = {}
    for row in combined:
        src = row["source"]
        counts.setdefault(src, {"pos": 0, "neg": 0})
        counts[src]["pos" if row["label"] == 1 else "neg"] += 1
    total_pos = total_neg = 0
    for src, c in counts.items():
        print(f"  {src:10s}  positives={c['pos']:>5}  negatives={c['neg']:>5}  total={c['pos']+c['neg']:>5}")
        total_pos += c["pos"]
        total_neg += c["neg"]
    print(f"  {'TOTAL':10s}  positives={total_pos:>5}  negatives={total_neg:>5}  total={total_pos+total_neg:>5}")


if __name__ == "__main__":
    main()
