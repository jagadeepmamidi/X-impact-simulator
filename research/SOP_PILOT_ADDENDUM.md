# SOP pilot addendum (locked 2026-09-18; storage decision updated 2026-09-18)

Short record of **accepted permanent deltas** versus `X_Impact_Simulator_Full_SOP.docx` (v1.0, 2 Sep 2026) and the **B → C** path. This does not reopen those decisions except the storage hosting choice below.

## Path

**Current accepted setup:** free Render + ephemeral `/tmp` SQLite. Durable **Gate B** storage (paid plan + persistent disk) is **deferred**. Then **Gate C evidence**. **Not** public beta (Gate D) yet.

This addendum’s original companion PR covered:

- Render config/docs for SQLite (`render.yaml`, `research/RENDER_OWNER_RUNBOOK.md`, README)
- Public-demo **loss banner** (and Save/History note) while storage is ephemeral
- Immutable **x-algorithm SHA pin** matching current in-repo weights
- This addendum

**Decision change:** the owner stays on **free Render only**. The checked-in blueprint is `plan: free` + `SQLITE_PATH=/tmp/runs.sqlite` (no `disk:` block). The loss banner stays until durable storage exists. The paid+disk checklist remains in the owner runbook as **optional later**. Durable Gate B is not claimed complete.

**Synthetic Gate C harness (this follow-up):** `research/GATE_C_SYNTHETIC.md` — ≥20 **authored** tech-niche posts run through the existing simulator offline. That is **harness/pipeline validation only**. It is **not** empirical calibration and **does not** complete Gate C.

**Still blocked (owner, real outcomes):** consented historical posts with a consistent observation window. Real impressions were not available, so they remain deferred. No claim that Gate C or D is complete.

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
- **Not Gate C complete.** A synthetic harness exists (`research/GATE_C_SYNTHETIC.md`); empirical Gate C is still blocked pending real observed outcomes. **Not Gate D.**
- **Not durable Gate B.** Live SQLite is free `/tmp` until an optional paid disk is attached.

## Storage pointer

Current live path: free + `/tmp/runs.sqlite` (ephemeral; banner stays). Optional later paid disk, health checks (`storage.production_ready` / `storage.path`), and SQLite backup notes: **`research/RENDER_OWNER_RUNBOOK.md`**.
