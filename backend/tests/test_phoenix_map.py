import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "training"))
from phoenix_map import actions_to_labels, stable_group_id, stable_thread_id, thread_example


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
        {
            "relative_integer_time": 1,
            "text": "Shipping an open-source eval harness today.",
            "user_id": "author-a",
            "actions": {"post": True},
        },
        {
            "relative_integer_time": 2,
            "text": "nice",
            "user_id": "actor-b",
            "actions": {"like": True, "reply": True, "repost": False, "quote": False, "follow": False, "block": False},
        },
    ]
    example = thread_example(thread, 3)
    assert example is not None
    assert "eval harness" in example["text"]
    assert example["cluster_id"] == 3
    assert example["thread_id"].startswith("thread:")
    assert example["group_id"].startswith("actor:")
    assert example["labels"]["favorite"] == 1.0
    assert example["labels"]["reply"] == 1.0


def test_stable_ids_exclude_action_labels_and_group_on_target_actor() -> None:
    thread = [
        {"relative_integer_time": 10, "text": "A sufficiently long context post.", "user_id": "author"},
        {"relative_integer_time": 11, "text": "response", "user_id": "target", "actions": {"like": True}},
    ]
    changed_actions = [dict(message) for message in thread]
    changed_actions[-1] = {**changed_actions[-1], "actions": {"like": False, "reply": True}}

    assert stable_thread_id(thread) == stable_thread_id(changed_actions)
    assert stable_group_id(thread) == stable_group_id(changed_actions)

    other_actor = [dict(message) for message in thread]
    other_actor[-1] = {**other_actor[-1], "user_id": "someone-else"}
    assert stable_group_id(thread) != stable_group_id(other_actor)
