import json
import sys
from pathlib import Path

import joblib

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "training"))
from phoenix_map import PHOENIX_HEADS
from train_heads import train


def test_logistic_beats_majority_on_synthetic(tmp_path: Path) -> None:
    jsonl = tmp_path / "synthetic.jsonl"
    with jsonl.open("w", encoding="utf-8") as handle:
        for i in range(80):
            labels = {head: 1.0 if (i + idx) % 6 == 0 else 0.0 for idx, head in enumerate(PHOENIX_HEADS)}
            labels["favorite"] = 1.0
            labels["retweet"] = 1.0
            handle.write(json.dumps({"text": f"awesome shipping eval harness launch {i}", "labels": labels}) + "\n")
        for i in range(80):
            labels = {head: 1.0 if (i + idx) % 8 == 0 else 0.0 for idx, head in enumerate(PHOENIX_HEADS)}
            labels["favorite"] = 0.0
            labels["retweet"] = 0.0
            handle.write(json.dumps({"text": f"boring spam buy now discount click {i}", "labels": labels}) + "\n")
    report = train(jsonl, tmp_path / "out", max_features=2000, min_df=1, split="shuffle", seed=42)
    assert report["beats_majority_ap"]["favorite"] is True
    assert report["beats_majority_ap"]["retweet"] is True
    assert (tmp_path / "out" / "model_card.json").is_file()
    card = json.loads((tmp_path / "out" / "model_card.json").read_text(encoding="utf-8"))
    assert card["split"] == "shuffle"
    assert "intended_use" in card
    assert card["artifact_schema"] == "phoenix-heads-v2"
    assert card["model_sha256"]


def test_grouped_split_and_runtime_cluster_inference(tmp_path: Path, monkeypatch) -> None:
    jsonl = tmp_path / "grouped.jsonl"
    with jsonl.open("w", encoding="utf-8") as handle:
        for group in range(20):
            for row in range(4):
                labels = {
                    head: float((row + index) % 2 == 0)
                    for index, head in enumerate(PHOENIX_HEADS)
                }
                handle.write(
                    json.dumps(
                        {
                            "text": f"cluster topic {group % 2} group {group} sample {row}",
                            "cluster_id": group % 2,
                            "group_id": f"actor-{group}",
                            "labels": labels,
                            "dataset_revision": "fixture-v1",
                        }
                    )
                    + "\n"
                )

    report = train(
        jsonl,
        tmp_path / "out",
        max_features=2_000,
        min_df=1,
        split="grouped",
        seed=7,
        eval_fraction=0.2,
    )

    assert report["split_metadata"]["group_isolation_enforced"] is True
    assert report["split_metadata"]["group_overlap"] == 0
    artifact_path = tmp_path / "out" / "phoenix_heads.joblib"
    artifact = joblib.load(artifact_path)
    assert artifact["artifact_schema"] == "phoenix-heads-v2"
    assert artifact["feature_schema"]["cluster_id_used"] is True
    assert artifact["cluster_pipeline"] is not None

    import app.heads as heads

    monkeypatch.setattr(heads, "model_path", lambda: artifact_path)
    monkeypatch.setattr(heads, "_bundle", None)
    probabilities = heads.predict_text("cluster topic 1 with enough text for inference")
    assert probabilities is not None
    assert {"favorite", "retweet"}.issubset(probabilities)
