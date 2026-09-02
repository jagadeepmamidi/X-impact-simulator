from __future__ import annotations

import argparse
import json
from pathlib import Path

import joblib
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, brier_score_loss
from sklearn.model_selection import train_test_split
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


def _metrics(y_true: np.ndarray, proba: np.ndarray) -> dict:
    ap: dict[str, float | None] = {}
    brier: dict[str, float | None] = {}
    for i, head in enumerate(PHOENIX_HEADS):
        yt = y_true[:, i]
        if yt.sum() == 0 or yt.sum() == len(yt):
            ap[head] = None
            brier[head] = None
            continue
        ap[head] = float(average_precision_score(yt, proba[:, i]))
        brier[head] = float(brier_score_loss(yt, proba[:, i]))
    return {"average_precision": ap, "brier": brier}


def majority_proba(y_train: np.ndarray, n_eval: int) -> np.ndarray:
    prev = y_train.mean(axis=0)
    return np.tile(prev, (n_eval, 1))


def train(
    jsonl: Path,
    out_dir: Path,
    max_features: int = 80000,
    min_df: int = 3,
    split: str = "shuffle",
    seed: int = 42,
) -> dict:
    texts, y = load_jsonl(jsonl)
    n = len(texts)
    if split == "sequential":
        cut = max(1, int(n * 0.9))
        train_x, eval_x = texts[:cut], texts[cut:]
        train_y, eval_y = y[:cut], y[cut:]
    else:
        train_x, eval_x, train_y, eval_y = train_test_split(
            texts, y, test_size=0.1, random_state=seed, shuffle=True
        )
        cut = len(train_x)
    pipe = Pipeline(
        [
            ("tfidf", TfidfVectorizer(max_features=max_features, ngram_range=(1, 2), min_df=min_df)),
            (
                "clf",
                OneVsRestClassifier(
                    LogisticRegression(max_iter=200, class_weight="balanced"),
                    n_jobs=-1,
                ),
            ),
        ]
    )
    pipe.fit(train_x, train_y)
    proba = pipe.predict_proba(eval_x)
    model_metrics = _metrics(eval_y, proba)
    base_metrics = _metrics(eval_y, majority_proba(train_y, len(eval_x)))
    beats = {}
    for head in PHOENIX_HEADS:
        m, b = model_metrics["average_precision"][head], base_metrics["average_precision"][head]
        beats[head] = None if m is None or b is None else bool(m > b)
    out_dir.mkdir(parents=True, exist_ok=True)
    model_path = out_dir / "phoenix_heads.joblib"
    joblib.dump({"pipeline": pipe, "heads": list(PHOENIX_HEADS), "split": split, "seed": seed}, model_path)
    card = {
        "intended_use": "Optional favorite/retweet blend. Not impression-level Phoenix.",
        "split": split,
        "seed": seed,
        "n": n,
        "train": cut,
        "eval": n - cut,
        "heads_used_in_app": ["favorite", "retweet"],
        "beats_majority_ap": beats,
    }
    report = {
        "n": n,
        "train": cut,
        "eval": n - cut,
        "split": split,
        "average_precision": model_metrics["average_precision"],
        "brier": model_metrics["brier"],
        "majority_average_precision": base_metrics["average_precision"],
        "beats_majority_ap": beats,
        "model": str(model_path),
    }
    (out_dir / "train_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    (out_dir / "model_card.json").write_text(json.dumps(card, indent=2), encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--jsonl", default="data/processed/blueprint_phoenix.jsonl")
    parser.add_argument("--out", default="training/artifacts")
    parser.add_argument("--split", choices=("shuffle", "sequential"), default="shuffle")
    args = parser.parse_args()
    print(json.dumps(train(Path(args.jsonl), Path(args.out), split=args.split), indent=2))


if __name__ == "__main__":
    main()
