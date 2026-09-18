# Synthetic Gate C harness — not empirical calibration

**Status: `synthetic-harness-only`.** Real X impressions are **deferred**. This package validates that the simulator pipeline can score a ≥20-post tech-niche corpus, compare rankings to simple baselines, and emit a report. It is **not** Gate C complete, **not** a calibration, and **not** a public-beta unlock.

> SYNTHETIC validation of the harness/pipeline. NOT empirical calibration. Gate C is NOT complete. These posts and outcomes were authored for offline testing; they are not observed X impressions.

## What exists

| Path | Role |
| --- | --- |
| `research/gate_c_synthetic/synthetic_posts.json` | 24 authored tech-niche posts + invented 24h outcomes |
| `backend/app/gate_c_synthetic.py` | Offline backtest: `run_pipeline` + baselines + metrics |
| `backend/tests/test_gate_c_synthetic.py` | CI: corpus checks + full synthetic backtest, no secrets |
| `research/gate_c_synthetic/backtest_report.json` | Machine-readable report from the checked-in offline run |
| `research/gate_c_synthetic/backtest_report.csv` | Per-post table |
| `research/gate_c_synthetic/backtest_summary.md` | Short generated metrics summary |

## How to run

From `backend/` (heuristic path; **no Groq key required**):

```bash
python -m app.gate_c_synthetic
python -m pytest tests/test_gate_c_synthetic.py -q
```

Defaults: seed `42`, population `40`, boost `6`, Monte Carlo `8`, `persist` off, Groq disabled even if `GROQ_API_KEY` is set. Optional `--use-groq` allows the live provider; CI must not depend on it. Optional `--persist` writes runs to SQLite with `data_source=synthetic`.

## What is compared

Each synthetic post is scored with the existing `run_pipeline` (content features → persona affinities → prior map → RankingScorer cascade → scorecard). Rankings of `impact_score` / `profile_impact` are compared to:

- **Length** — token count
- **Keyword / promo** — tech-token reward minus promo-token penalty (independent of the simulator)
- **Random** — seeded hash, not a product baseline
- **Bland-post baseline** — the product's pack-level bland score; it is a **level**, not a ranking. `profile_impact` is the simulator score relative to that bland post

Targets are the **synthetic** impression count, like-rate, and (likes+replies+reposts)/impressions. Metrics: Spearman ρ, Kendall τ, tertile band hit rate. Monte Carlo `score_p10`–`score_p90` stay on the 0–100 UI scale (simulator randomness only) and are **not** impression intervals.

## Non-claims (read this twice)

- **Not empirically calibrated.** Assumed priors were not fitted to these rows or to any real X export.
- **Not Gate C complete.** SOP Gate C still needs consented historical posts, a consistent real observation window, and a usefulness check. Those are blocked until the owner can obtain real outcomes.
- **Not a forecast and not X production.** Comparative scenario scores only.
- **Not Gate D / public beta evidence.**
- Beating or losing a length/promo/random baseline **on this invented corpus** does not change product copy, priors, or confidence (`confidence` remains `0.0`).

## Empirical Gate C (still blocked)

Owner follow-up, when real analytics exist:

1. Replace this corpus with ≥20 consented historical posts (same niche, documented observation window).
2. Keep the same harness, baselines, and holdout rule (time-based, not a random shuffle of the same week).
3. Only then discuss whether priors should move. Twenty real posts is still an initial backtest, not a calibration claim.

Until that happens, treat every number in `backtest_summary.md` as a **pipeline self-check**.

On the checked-in synthetic corpus, simple length and keyword/promo heuristics can outrank `impact_score` on Spearman vs invented impressions. That is expected for authored labels and is **not** a reason to change priors or product copy.

