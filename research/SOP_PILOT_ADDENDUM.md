# SOP pilot addendum (locked 2026-09-18)

Short record of **accepted permanent deltas** versus `X_Impact_Simulator_Full_SOP.docx` (v1.0, 2 Sep 2026) and the **B → C** path. This does not reopen those decisions.

## Path

Durable **Gate B** pilot, then **Gate C evidence**. **Not** public beta (Gate D) yet.

This addendum’s companion PR covers only:

- Render paid plan + persistent disk config/docs for SQLite (`render.yaml`, `research/RENDER_OWNER_RUNBOOK.md`, README)
- Public-demo **loss banner** (and Save/History note) while storage is ephemeral
- Immutable **x-algorithm SHA pin** matching current in-repo weights
- This addendum

**After this PR (owner follow-up, not in this sprint):** Gate C backtests using the owner’s ≥20 historical posts. No claim that Gate C or D is complete.

## Accepted permanent deltas vs original SOP

| SOP wording | Permanent pilot decision |
| --- | --- |
| Normalized categorical action distribution summing to 1 (§9.2) | **Independent compatible action marginals** (dwell + click + like + repost may co-occur) |
| `/api/v1/...` resource layout (§13) | **Flat `/api/*`** (`/api/simulate`, `/api/compare`, `/api/simulations/...`) |
| Postgres/Supabase + job queue (§4, §13) | **SQLite single-node** on one Render instance; in-process `asyncio.to_thread` (no Celery) |
| Calibrated confidence on scores (§9.2, §1.4) | UI **stability ≠ calibrated confidence**; `confidence` stays 0.0 until empirical calibration exists |
| Public beta / keyed staging friction | **Anonymous public demo ON** + optional personal Groq key; no new pilot-key gate |

Sep 5 implementation semantics (owner isolation, proxy unification, upload caps, production env guards) remain in tree.

## Access (unchanged)

Anonymous demo sessions consume the server Groq quota within `SIM_PUBLIC_RUNS_PER_HOUR`. Visitors may supply a **personal Groq key** for their request only. Optional operator keys stay under Advanced access. This sprint does not add extra credentials.

## Non-claims

- **Not empirically calibrated.** Priors are research assumptions; Monte Carlo p10–p90 and “Run stability” measure simulator randomness only.
- **Not X production.** RankingScorer public defaults only — not Phoenix, Thunder, SimClusters retrieval, VMRanker, visibility filters, author diversity, or runtime experiments.
- **Not a virality guarantee** and not a live X feed.
- **Not Gate C complete** until the owner backtest exists. **Not Gate D.**

## Durable storage pointer

Owner upgrade, disk mount, `SQLITE_PATH=/var/data/runs.sqlite`, health checks (`storage.production_ready` / `storage.path`), and SQLite backup notes: **`research/RENDER_OWNER_RUNBOOK.md`**.
