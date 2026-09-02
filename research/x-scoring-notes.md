# X ranking snapshot
Repo: https://github.com/xai-org/x-algorithm  
Pinned tree: `7ba776848b12d8422eb0f291ee03ea5c17ab0188`  
`param.rs` header: last sync `2026-09-01T16:42:25Z`

This app copies **RankingScorer weighted mode** only:

`score = offset(sum(w_i * P(action_i)))`, then OON `* 0.75`.

It does **not** run Phoenix, Thunder, SimClusters, visibility filtering, author-diversity across a slate, or cold-start boosts.

Personas emit the Phoenix heads RankingScorer multiplies. Python owns the sum. Groq never emits `impact_score`.

BluePrint TFIDF heads (`training/artifacts/phoenix_heads.joblib`) blend into `like_probability` (favorite, 0.75) and `repost_probability` (retweet, 0.35). Reply / quote / follow / block stay Groq or heuristic.

## Weights (`home-mixer/params/param.rs`)

Weights multiply **predicted probabilities**, not counts.

| Head | Weight |
| --- | ---: |
| favorite | 0.5 |
| reply | 5.0 |
| retweet | 1.0 |
| photo_expand | 0.05 |
| video_open | 0.07 |
| click | 0.4 |
| open_link | 0.2 |
| profile_click | 0.0 |
| vqv | 0.0 |
| share | 2.0 |
| share_via_dm | 5.0 |
| share_via_copy_link | 20.0 |
| dwell | 0.05 |
| quote | 5.0 |
| quoted_click | 0.05 |
| quoted_vqv | 0.0 |
| follow_author | 4.0 |
| post_unexplored | 0.02 (in-network only) |
| cont_dwell_time | 0.004 (seconds; not in offset totals) |
| not_interested | -43.2 |
| block_author | -31.2 |
| mute_author | -58.8 |
| report | -234.0 |
| not_dwelled | -0.02 |

## Other public defaults used here

- `ValueModelMode` = `weighted` (not dwell-regret)
- `OonWeightFactor` = `0.75`
- `NEGATIVE_SCORES_OFFSET` = `0.001` (`home-mixer/params/config.rs`)
- `MultiplierPreOffset` = `false` so OON applies after offset
- `PostUnexploredWeightInNetworkOnly` = `true`

UI 0-100 is `clamp(raw / 6) * 100`, a display mapping, not an X production percentile.

