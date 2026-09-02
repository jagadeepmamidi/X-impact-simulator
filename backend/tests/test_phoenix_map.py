import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "training"))
from phoenix_map import actions_to_labels, thread_example


def test_like_maps_to_favorite() -> None:
    labels = actions_to_labels({"like": True, "reply": False, "repost": True, "quote": False, "follow": False, "block": False})
    assert labels["favorite"] == 1.0
    assert labels["retweet"] == 1.0
    assert labels["reply"] == 0.0
    assert labels["block_author"] == 0.0


def test_short_thread_skipped() -> None:
    assert thread_example([{"text": "hi", "actions": {"like": True}}], 0) is None


def test_context_plus_last_action() -> None:
    thread = [
        {"text": "Shipping an open-source eval harness today.", "actions": {"post": True}},
        {"text": "nice", "actions": {"like": True, "reply": True, "repost": False, "quote": False, "follow": False, "block": False}},
    ]
    example = thread_example(thread, 3)
    assert example is not None
    assert "eval harness" in example["text"]
    assert example["cluster_id"] == 3
    assert example["labels"]["favorite"] == 1.0
    assert example["labels"]["reply"] == 1.0
