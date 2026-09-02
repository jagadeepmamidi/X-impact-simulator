# ComplexDataLab/BluePrint

- Retrieved: 2026-09-02
- Gated: yes (access works for this HF account)
- Config for V1: `25_clusters` / split `full` (~6.8M threads, 1.8 GB parquet)
- Schema: `thread[]` with `text`, `user_id`, `relative_integer_time`, bool `actions`; plus `cluster_id`
- Actions present: like, reply, repost, quote, follow, block (+ undo/post housekeeping we ignore)
- Map: `training/phoenix_map.py` → favorite, reply, retweet, quote, follow_author, block_author
- Missing vs RankingScorer: share*, dwell, click, photo_expand, video_open, open_link, mute, report, not_interested — keep heuristic/Groq
- Use: stream, do not download the full 6.8M locally first. Sample ~80k next-action rows on Colab.
- Environment: research / Colab. Not a live X For You feed.
