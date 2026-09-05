"""Stream a BluePrint subset into Phoenix-head JSONL. Run on Colab/GPU box, not this laptop."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from datasets import load_dataset

from phoenix_map import BLUEPRINT_DATASET_ID, PHOENIX_HEADS, PREPARATION_SCHEMA, thread_example

PREPARATION_REVISION = "blueprint-prepare-v2"
SHUFFLE_BUFFER_SIZE = 10_000


def _json_hash(value: object) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def prepare(config: str, max_rows: int, out_path: Path, seed: int, revision: str = "main") -> dict:
    preparation_config = {
        "dataset_id": BLUEPRINT_DATASET_ID,
        "dataset_config": config,
        "dataset_revision": revision,
        "max_rows": max_rows,
        "preparation_revision": PREPARATION_REVISION,
        "preparation_schema": PREPARATION_SCHEMA,
        "seed": seed,
        "shuffle_buffer_size": SHUFFLE_BUFFER_SIZE,
    }
    ds = load_dataset(
        BLUEPRINT_DATASET_ID,
        name=config,
        revision=revision,
        split="full",
        streaming=True,
    )
    ds = ds.shuffle(seed=seed, buffer_size=SHUFFLE_BUFFER_SIZE)
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
            example.update(
                {
                    "dataset_id": BLUEPRINT_DATASET_ID,
                    "dataset_config": config,
                    "dataset_revision": revision,
                    "preparation_revision": PREPARATION_REVISION,
                    "preparation_schema": PREPARATION_SCHEMA,
                }
            )
            handle.write(json.dumps(example, ensure_ascii=False) + "\n")
            kept += 1
            for head, value in example["labels"].items():
                pos[head] += int(value)
            if kept >= max_rows:
                break
    summary = {
        **preparation_config,
        "preparation_config_sha256": _json_hash(preparation_config),
        "scanned": scanned,
        "kept": kept,
        "positives": pos,
        "out": str(out_path),
        "output_sha256": _file_hash(out_path),
    }
    (out_path.parent / "blueprint_prepare_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="25_clusters")
    parser.add_argument("--max-rows", type=int, default=80000)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--revision", default="main", help="Dataset revision; prefer a pinned commit SHA.")
    parser.add_argument("--out", default="data/processed/blueprint_phoenix.jsonl")
    args = parser.parse_args()
    summary = prepare(args.config, args.max_rows, Path(args.out), args.seed, revision=args.revision)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
