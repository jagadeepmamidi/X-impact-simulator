"""Map BluePrint next-actions onto RankingScorer Phoenix heads.

BluePrint labels booleans on the next message in a thread.
Heads with no BluePrint label stay heuristic/Groq (share, dwell, click, report, mute).
"""

from __future__ import annotations

import hashlib
import json

BLUEPRINT_DATASET_ID = "ComplexDataLab/BluePrint"
PREPARATION_SCHEMA = "blueprint-phoenix-v2"

PHOENIX_HEADS = (
    "favorite",
    "reply",
    "retweet",
    "quote",
    "follow_author",
    "block_author",
)

BLUEPRINT_TO_PHOENIX = {
    "like": "favorite",
    "reply": "reply",
    "repost": "retweet",
    "quote": "quote",
    "follow": "follow_author",
    "block": "block_author",
}

def empty_labels() -> dict[str, float]:
    return {head: 0.0 for head in PHOENIX_HEADS}


def actions_to_labels(actions: dict | None) -> dict[str, float]:
    labels = empty_labels()
    if not actions:
        return labels
    for src, dest in BLUEPRINT_TO_PHOENIX.items():
        if bool(actions.get(src)):
            labels[dest] = 1.0
    return labels


def _stable_hash(value: object) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def stable_thread_id(thread: list) -> str:
    """Hash stable message identity/content fields while excluding outcome labels."""
    identity = [
        {
            "relative_integer_time": message.get("relative_integer_time"),
            "text": str(message.get("text") or ""),
            "user_id": str(message.get("user_id") or ""),
        }
        for message in thread
    ]
    return f"thread:{_stable_hash(identity)}"


def stable_group_id(thread: list, thread_id: str | None = None) -> str:
    """Group on the actor whose next action supplies the training label."""
    if thread:
        actor_id = str(thread[-1].get("user_id") or "").strip()
        if actor_id:
            return f"actor:{_stable_hash(actor_id)}"
    return thread_id or stable_thread_id(thread)


def thread_example(thread: list, cluster_id: int) -> dict | None:
    if not thread or len(thread) < 2:
        return None
    context = thread[:-1]
    last = thread[-1]
    post_text = " ".join(str(m.get("text") or "") for m in context).strip()
    if len(post_text) < 12:
        return None
    thread_id = stable_thread_id(thread)
    return {
        "text": post_text[:4000],
        "cluster_id": int(cluster_id),
        "thread_id": thread_id,
        "group_id": stable_group_id(thread, thread_id),
        "labels": actions_to_labels(last.get("actions") or {}),
        "n_context": len(context),
    }
