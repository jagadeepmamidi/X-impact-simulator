# X ranking defaults used by the simulator
Repo: https://github.com/xai-org/x-algorithm
Source checked: public `main` on 2026-09-04
`param.rs` upstream mirror comment: last sync `2026-08-12`

This app copies **RankingScorer weighted mode** only:

`score = offset(sum(w_i * P(action_i)))`, then OON `* 0.75`.

It does **not** run the live Phoenix model/history, Thunder, SimClusters retrieval, visibility filtering, author diversity, VMRanker, runtime experiments, or cold-start boosts. Candidate-slate competition in this app is a documented synthetic scenario model.

Personas emit the Phoenix heads RankingScorer multiplies. Python owns the sum. Groq never emits `impact_score`.

Optional BluePrint TFIDF heads (`training/artifacts/phoenix_heads.joblib`) first infer the dataset content cluster, then apply persona-preserving log-odds lifts to `like_probability` (favorite, 40%) and `repost_probability` (retweet, 25%). Reply / quote / follow / block stay Groq or heuristic.

## Weights (`home-mixer/params/param.rs`)

Weights multiply **predicted probabilities**, not counts.

| Head | Weight |
| --- | ---: |
| favorite | 0.5 |
| reply | 5.0 |
| retweet | 1.0 |
| photo_expand | 0.05 |
| video_open | 0.05 |
| click | 0.4 |
| open_link | 0.2 |
| profile_click | 0.0 |
| vqv | 0.05 (not currently predicted by this simulator) |
| share | 2.0 |
| share_via_dm | 5.0 |
| share_via_copy_link | 20.0 |
| dwell | 0.0 |
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

UI 0-100 is a documented sigmoid of the prior-mapped raw ranking score (`affinity-prior-map-v2`), not `raw / 6` and not an X production percentile. Monte Carlo p10/p50/p90 are the **final-round scores of complete cascade runs**; the displayed graph is the run nearest the median exposure/score.

## Impression-prior mapping (`affinity-prior-map-v2`)

RankingScorer weights multiply **P(action | impression)**. LLM and heuristic heads in this app are 0-1 *affinities*. Before scoring, Python maps each affinity `a` onto an assumed base rate `p0`:

`P = sigmoid(logit(p0) + 2.2 * (2a - 1))`

`p0` values are research priors, **not X telemetry and not empirical calibration**. Both graph event sampling and scoring now use the same prior-mapped probability stream. Noise is applied in log-odds space so rare events are not overwhelmed by additive jitter. Compatible actions are sampled independently rather than forced into one categorical action.

Simulation knobs live in `SimulationConfig` (`sim-config-v4`): share fanout, candidate-pool size/top-k, synthetic competitor distributions, explicit author-network priors, network/stage adjustments, exposure budget, log-odds noise, and stopping rules. Every saved run records this configuration and a verified hash manifest binding the report, reactions, input, personas, weights, and model metadata used for compatibility-checked replay.

