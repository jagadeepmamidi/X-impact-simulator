from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

import joblib
import numpy as np
import sklearn
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, brier_score_loss
from sklearn.model_selection import GroupShuffleSplit, train_test_split
from sklearn.multiclass import OneVsRestClassifier
from sklearn.pipeline import Pipeline

from phoenix_map import PHOENIX_HEADS

ARTIFACT_SCHEMA = "phoenix-heads-v2"
TRAINING_CONFIG_REVISION = "phoenix-heads-logreg-v2"


@dataclass(frozen=True)
class TrainingData:
    raw_texts: list[str]
    texts: list[str]
    labels: np.ndarray
    groups: list[str]
    cluster_ids: list[int]
    group_source_counts: dict[str, int]
    dataset_id: str
    dataset_config: str
    dataset_revision: str
    preparation_revision: str


def _json_hash(value: object) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _one_metadata_value(values: set[str]) -> str:
    clean = sorted(value for value in values if value)
    if not clean:
        return "unknown"
    if len(clean) == 1:
        return clean[0]
    return "mixed:" + ",".join(clean)


def feature_text(text: str, cluster_id: int) -> str:
    """Keep the behavioral cluster available as an explicit sparse feature."""
    return f"__cluster_{int(cluster_id)}__ {(text or '').strip()}"


def load_training_data(path: Path) -> TrainingData:
    raw_texts: list[str] = []
    texts: list[str] = []
    rows: list[list[float]] = []
    groups: list[str] = []
    cluster_ids: list[int] = []
    group_source_counts: dict[str, int] = {}
    dataset_ids: set[str] = set()
    dataset_configs: set[str] = set()
    dataset_revisions: set[str] = set()
    preparation_revisions: set[str] = set()
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            row = json.loads(line)
            raw_text = str(row["text"])
            cluster_id = int(row.get("cluster_id") or 0)
            group_id = str(row.get("group_id") or "").strip()
            if group_id:
                group_source = "group_id"
            else:
                group_id = str(row.get("thread_id") or "").strip()
                if group_id:
                    group_source = "thread_id"
                else:
                    normalized = " ".join(raw_text.split()).casefold()
                    group_id = f"content:{hashlib.sha256(normalized.encode('utf-8')).hexdigest()}"
                    group_source = "content_sha256_fallback"
            group_source_counts[group_source] = group_source_counts.get(group_source, 0) + 1
            raw_texts.append(raw_text)
            texts.append(feature_text(raw_text, cluster_id))
            rows.append([float(row["labels"][head]) for head in PHOENIX_HEADS])
            groups.append(group_id)
            cluster_ids.append(cluster_id)
            dataset_ids.add(str(row.get("dataset_id") or ""))
            dataset_configs.add(str(row.get("dataset_config") or ""))
            dataset_revisions.add(str(row.get("dataset_revision") or ""))
            preparation_revisions.add(str(row.get("preparation_revision") or ""))
    labels = np.array(rows, dtype=float)
    if not rows:
        labels = np.empty((0, len(PHOENIX_HEADS)), dtype=float)
    return TrainingData(
        raw_texts=raw_texts,
        texts=texts,
        labels=labels,
        groups=groups,
        cluster_ids=cluster_ids,
        group_source_counts=group_source_counts,
        dataset_id=_one_metadata_value(dataset_ids),
        dataset_config=_one_metadata_value(dataset_configs),
        dataset_revision=_one_metadata_value(dataset_revisions),
        preparation_revision=_one_metadata_value(preparation_revisions),
    )


def load_jsonl(path: Path) -> tuple[list[str], np.ndarray]:
    """Backward-compatible loader returning cluster-enriched text and labels."""
    data = load_training_data(path)
    return data.texts, data.labels


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


def train_cluster_predictor(
    data: TrainingData,
    train_idx: np.ndarray,
    eval_idx: np.ndarray,
    *,
    max_features: int,
    min_df: int,
    seed: int,
) -> tuple[Pipeline | None, int, list[int], dict]:
    """Learn the BluePrint cluster from text so runtime can supply the same feature."""

    train_labels = np.asarray([data.cluster_ids[int(index)] for index in train_idx])
    cluster_ids = sorted({int(value) for value in train_labels})
    default_cluster = int(np.bincount(train_labels - train_labels.min()).argmax() + train_labels.min())
    if len(cluster_ids) == 1:
        predicted = np.full(len(eval_idx), default_cluster)
        predictor = None
    else:
        predictor = Pipeline(
            [
                (
                    "tfidf",
                    TfidfVectorizer(
                        max_features=max(2_000, max_features // 2),
                        ngram_range=(1, 2),
                        min_df=min_df,
                    ),
                ),
                (
                    "clf",
                    LogisticRegression(
                        max_iter=300,
                        class_weight="balanced",
                        random_state=seed,
                    ),
                ),
            ]
        )
        predictor.fit([data.raw_texts[int(index)] for index in train_idx], train_labels)
        predicted = predictor.predict([data.raw_texts[int(index)] for index in eval_idx])
    actual = np.asarray([data.cluster_ids[int(index)] for index in eval_idx])
    accuracy = float(np.mean(predicted == actual)) if len(actual) else None
    return predictor, default_cluster, cluster_ids, {
        "cluster_ids": cluster_ids,
        "default_cluster": default_cluster,
        "eval_accuracy": accuracy,
        "runtime_strategy": "text-classifier" if predictor is not None else "single-cluster-constant",
    }


def split_indices(
    data: TrainingData,
    split: str = "grouped",
    seed: int = 42,
    eval_fraction: float = 0.1,
) -> tuple[np.ndarray, np.ndarray, dict]:
    n = len(data.texts)
    if n < 2:
        raise ValueError("Training requires at least two examples.")
    if not 0 < eval_fraction < 1:
        raise ValueError("eval_fraction must be between 0 and 1.")
    indices = np.arange(n)
    if split == "grouped":
        unique_groups = set(data.groups)
        if len(unique_groups) < 2:
            raise ValueError(
                "Grouped split requires at least two stable groups. Regenerate with preparation v2 "
                "or explicitly choose a legacy row-level split."
            )
        splitter = GroupShuffleSplit(n_splits=1, test_size=eval_fraction, random_state=seed)
        train_idx, eval_idx = next(splitter.split(indices, groups=np.asarray(data.groups)))
    elif split == "sequential":
        cut = max(1, min(n - 1, int(n * (1 - eval_fraction))))
        train_idx, eval_idx = indices[:cut], indices[cut:]
    elif split == "shuffle":
        train_idx, eval_idx = train_test_split(
            indices,
            test_size=eval_fraction,
            random_state=seed,
            shuffle=True,
        )
    else:
        raise ValueError(f"Unknown split strategy: {split}")

    train_groups = {data.groups[int(index)] for index in train_idx}
    eval_groups = {data.groups[int(index)] for index in eval_idx}
    overlap = train_groups & eval_groups
    warnings: list[str] = []
    if data.group_source_counts.get("content_sha256_fallback", 0):
        warnings.append(
            "Some rows lacked group_id/thread_id; exact normalized content hashes were used as a safe "
            "duplicate boundary, but actor-level isolation cannot be proven for those rows."
        )
    if split != "grouped":
        warnings.append("Explicit legacy row-level split selected; group isolation is not enforced.")
    metadata = {
        "requested": split,
        "strategy": split,
        "eval_fraction": eval_fraction,
        "group_isolation_enforced": split == "grouped",
        "leakage_safe": split == "grouped" and not overlap,
        "group_source_counts": data.group_source_counts,
        "groups_total": len(set(data.groups)),
        "groups_train": len(train_groups),
        "groups_eval": len(eval_groups),
        "group_overlap": len(overlap),
        "train_indices_sha256": _json_hash([int(index) for index in sorted(train_idx)]),
        "eval_indices_sha256": _json_hash([int(index) for index in sorted(eval_idx)]),
        "warnings": warnings,
    }
    return np.asarray(train_idx), np.asarray(eval_idx), metadata


def train(
    jsonl: Path,
    out_dir: Path,
    max_features: int = 80000,
    min_df: int = 3,
    split: str = "grouped",
    seed: int = 42,
    eval_fraction: float = 0.1,
    dataset_revision: str | None = None,
    dataset_config: str | None = None,
) -> dict:
    data = load_training_data(jsonl)
    n = len(data.texts)
    train_idx, eval_idx, split_metadata = split_indices(data, split, seed, eval_fraction)
    cluster_pipeline, cluster_default, cluster_ids, cluster_metadata = train_cluster_predictor(
        data,
        train_idx,
        eval_idx,
        max_features=max_features,
        min_df=min_df,
        seed=seed,
    )
    train_x = [data.texts[int(index)] for index in train_idx]
    if cluster_pipeline is None:
        predicted_clusters = [cluster_default for _ in eval_idx]
    else:
        predicted_clusters = [
            int(value)
            for value in cluster_pipeline.predict(
                [data.raw_texts[int(index)] for index in eval_idx]
            )
        ]
    eval_x = [
        feature_text(data.raw_texts[int(index)], cluster_id)
        for index, cluster_id in zip(eval_idx, predicted_clusters, strict=True)
    ]
    train_y = data.labels[train_idx]
    eval_y = data.labels[eval_idx]
    cut = len(train_x)
    training_config = {
        "class_weight": "balanced",
        "eval_fraction": eval_fraction,
        "heads": list(PHOENIX_HEADS),
        "max_features": max_features,
        "max_iter": 200,
        "min_df": min_df,
        "ngram_range": [1, 2],
        "revision": TRAINING_CONFIG_REVISION,
        "seed": seed,
        "split": split,
    }
    training_config_sha256 = _json_hash(training_config)
    pipe = Pipeline(
        [
            ("tfidf", TfidfVectorizer(max_features=max_features, ngram_range=(1, 2), min_df=min_df)),
            (
                "clf",
                OneVsRestClassifier(
                    LogisticRegression(max_iter=200, class_weight="balanced", random_state=seed),
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

    dataset_sha256 = _file_hash(jsonl)
    dataset_metadata = {
        "id": data.dataset_id,
        "config": dataset_config or data.dataset_config,
        "revision": dataset_revision or data.dataset_revision,
        "sha256": dataset_sha256,
        "preparation_revision": data.preparation_revision,
    }
    metrics_metadata = {
        "average_precision": model_metrics["average_precision"],
        "brier": model_metrics["brier"],
        "majority_average_precision": base_metrics["average_precision"],
        "majority_brier": base_metrics["brier"],
        "beats_majority_ap": beats,
    }
    training_metadata = {
        "dataset": dataset_metadata,
        "config": {
            "revision": TRAINING_CONFIG_REVISION,
            "sha256": training_config_sha256,
            "values": training_config,
        },
        "sklearn_version": sklearn.__version__,
        "split": split_metadata,
        "seed": seed,
        "metrics": metrics_metadata,
        "cluster_inference": cluster_metadata,
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    model_path = out_dir / "phoenix_heads.joblib"
    joblib.dump(
        {
            "artifact_schema": ARTIFACT_SCHEMA,
            "pipeline": pipe,
            "cluster_pipeline": cluster_pipeline,
            "cluster_default": cluster_default,
            "cluster_ids": cluster_ids,
            "heads": list(PHOENIX_HEADS),
            "feature_schema": {
                "text": "UTF-8 post context, capped upstream at 4,000 characters",
                "cluster_token": "__cluster_<integer>__ prefix",
                "cluster_id_used": True,
                "runtime_cluster_source": cluster_metadata["runtime_strategy"],
            },
            "split": split,
            "seed": seed,
            "training": training_metadata,
        },
        model_path,
    )
    model_sha256 = _file_hash(model_path)
    card = {
        "artifact_schema": ARTIFACT_SCHEMA,
        "intended_use": "Optional favorite/retweet blend. Not impression-level Phoenix.",
        "split": split,
        "split_metadata": split_metadata,
        "seed": seed,
        "n": n,
        "train": cut,
        "eval": len(eval_x),
        "heads_used_in_app": ["favorite", "retweet"],
        "beats_majority_ap": beats,
        "dataset": dataset_metadata,
        "training_config": training_metadata["config"],
        "sklearn_version": sklearn.__version__,
        "metrics": metrics_metadata,
        "cluster_inference": cluster_metadata,
        "model_sha256": model_sha256,
        "model_size_bytes": model_path.stat().st_size,
        "limitations": [
            "BluePrint contains observed action sequences, not impression denominators.",
            "The runtime app currently uses only favorite and retweet as optional content-level signals.",
            "Content-hash fallback groups protect exact duplicates only; prepare-v2 actor groups are preferred.",
        ],
    }
    report = {
        "artifact_schema": ARTIFACT_SCHEMA,
        "n": n,
        "train": cut,
        "eval": len(eval_x),
        "split": split,
        "split_metadata": split_metadata,
        "seed": seed,
        "average_precision": model_metrics["average_precision"],
        "brier": model_metrics["brier"],
        "majority_average_precision": base_metrics["average_precision"],
        "majority_brier": base_metrics["brier"],
        "beats_majority_ap": beats,
        "model": str(model_path),
        "dataset": dataset_metadata,
        "training_config_revision": TRAINING_CONFIG_REVISION,
        "training_config_sha256": training_config_sha256,
        "sklearn_version": sklearn.__version__,
        "model_sha256": model_sha256,
        "cluster_inference": cluster_metadata,
    }
    (out_dir / "train_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    (out_dir / "model_card.json").write_text(json.dumps(card, indent=2), encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--jsonl", default="data/processed/blueprint_phoenix.jsonl")
    parser.add_argument("--out", default="training/artifacts")
    parser.add_argument("--split", choices=("grouped", "shuffle", "sequential"), default="grouped")
    parser.add_argument("--eval-fraction", type=float, default=0.1)
    parser.add_argument("--dataset-revision", default=None)
    parser.add_argument("--dataset-config", default=None)
    args = parser.parse_args()
    print(
        json.dumps(
            train(
                Path(args.jsonl),
                Path(args.out),
                split=args.split,
                eval_fraction=args.eval_fraction,
                dataset_revision=args.dataset_revision,
                dataset_config=args.dataset_config,
            ),
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
