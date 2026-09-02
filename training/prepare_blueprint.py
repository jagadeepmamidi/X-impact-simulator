"""Stream a BluePrint subset into Phoenix-head JSONL. Run on Colab/GPU box, not this laptop."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from datasets import load_dataset

from phoenix_map import PHOENIX_HEADS, thread_example


def prepare(config: str, max_rows: int, out_path: Path, seed: int) -> dict:
    ds = load_dataset("ComplexDataLab/BluePrint", name=config, split="full", streaming=True)
    ds = ds.shuffle(seed=seed, buffer_size=10_000)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    kept = 0
    scanned = 0
    pos = {h: 0 for h in PHOENIX_HEADS}
    with out_path.open("w", encoding="utf-8") as handle:
        for row in ds:
            scanned += 1
            example = thread_example(row.get("thread") or [], int(row.get("cluster_id") or 0))
            if example is None:
                continue
            handle.write(json.dumps(example, ensure_ascii=False) + "\n")
            kept += 1
            for head, value in example["labels"].items():
                pos[head] += int(value)
            if kept >= max_rows:
                break
    summary = {"config": config, "scanned": scanned, "kept": kept, "positives": pos, "out": str(out_path)}
    (out_path.parent / "blueprint_prepare_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="25_clusters")
    parser.add_argument("--max-rows", type=int, default=80000)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--out", default="data/processed/blueprint_phoenix.jsonl")
    args = parser.parse_args()
    summary = prepare(args.config, args.max_rows, Path(args.out), args.seed)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
