"""Classical multi-label baseline for BluePrint Phoenix heads. CPU-ok; run after prepare_blueprint."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import joblib
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score
from sklearn.multiclass import OneVsRestClassifier
from sklearn.pipeline import Pipeline

from phoenix_map import PHOENIX_HEADS


def load_jsonl(path: Path) -> tuple[list[str], np.ndarray]:
    texts: list[str] = []
    rows: list[list[float]] = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            row = json.loads(line)
            texts.append(row["text"])
            rows.append([float(row["labels"][h]) for h in PHOENIX_HEADS])
    return texts, np.array(rows, dtype=float)


def train(jsonl: Path, out_dir: Path, max_features: int = 80000) -> dict:
    texts, y = load_jsonl(jsonl)
    n = len(texts)
    cut = max(1, int(n * 0.9))
    pipe = Pipeline(
        [
            ("tfidf", TfidfVectorizer(max_features=max_features, ngram_range=(1, 2), min_df=3)),
            (
                "clf",
                OneVsRestClassifier(
                    LogisticRegression(max_iter=200, class_weight="balanced", n_jobs=None),
                    n_jobs=-1,
                ),
            ),
        ]
    )
    pipe.fit(texts[:cut], y[:cut])
    proba = pipe.predict_proba(texts[cut:])
    ap = {}
    for i, head in enumerate(PHOENIX_HEADS):
        yt = y[cut:, i]
        ap[head] = None if yt.sum() == 0 or yt.sum() == len(yt) else float(average_precision_score(yt, proba[:, i]))
    out_dir.mkdir(parents=True, exist_ok=True)
    model_path = out_dir / "phoenix_heads.joblib"
    joblib.dump({"pipeline": pipe, "heads": PHOENIX_HEADS}, model_path)
    report = {"n": n, "train": cut, "eval": n - cut, "average_precision": ap, "model": str(model_path)}
    (out_dir / "train_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--jsonl", default="data/processed/blueprint_phoenix.jsonl")
    parser.add_argument("--out", default="training/artifacts")
    args = parser.parse_args()
    print(json.dumps(train(Path(args.jsonl), Path(args.out)), indent=2))


if __name__ == "__main__":
    main()
