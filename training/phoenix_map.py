"""Map BluePrint next-actions onto RankingScorer Phoenix heads.

BluePrint labels booleans on the next message in a thread.
Heads with no BluePrint label stay heuristic/Groq (share, dwell, click, report, mute).
"""

from __future__ import annotations

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


def thread_example(thread: list, cluster_id: int) -> dict | None:
    if not thread or len(thread) < 2:
        return None
    context = thread[:-1]
    last = thread[-1]
    post_text = " ".join(str(m.get("text") or "") for m in context).strip()
    if len(post_text) < 12:
        return None
    return {
        "text": post_text[:4000],
        "cluster_id": int(cluster_id),
        "labels": actions_to_labels(last.get("actions") or {}),
        "n_context": len(context),
    }
