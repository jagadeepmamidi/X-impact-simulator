import json
import sys
from pathlib import Path

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
