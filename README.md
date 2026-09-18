# X Impact Simulator

Experimental X-inspired audience and distribution simulator. **Comparative, not predictive.** Not X production. No live X feed. No virality guarantee.

Repo: [github.com/jagadeepmamidi/X-impact-simulator](https://github.com/jagadeepmamidi/X-impact-simulator)

Fifteen curated behavior archetypes emit Phoenix-style *affinities*. A seeded, weighted population layer maps sanitized display personas onto those explicit behavior profiles. Python maps affinities onto assumed impression-level priors, scores them with public RankingScorer defaults from [xai-org/x-algorithm](https://github.com/xai-org/x-algorithm), and runs a Monte Carlo **full-cascade** spread with synthetic candidate-slate competition. Groq never emits `impact_score`; the headline score blends 35% persona prior with 65% sampled population/ranking outcome. The shown graph is the run nearest median exposure/score; p10–p90 describe variation across all runs.

## What you can do

- Score a hook against **tech**, **fitness**, **finance**, or **comedy** packs (15 curated behavior profiles each), sampled into 40 / 100 / 320 / 500 coherent audience members
- Optional **Hook B** compare on the same media and seed
- Verdict with full-cascade p10–p90, Niche Index, audience fit, negative risk, **stability** (not statistical confidence), and rewrite suggestions
- Save every run with verified hashes/config provenance and **replay from stored probabilities by id**; per-owner keys isolate saved runs
- Browse recent runs, restore their population/boost settings, and record observed counts with observation time and window
- Optional BluePrint heads infer the content cluster and apply content-level log-odds lifts to **favorite (40%)** and **retweet (25%)**, preserving persona differences
- Compatible actions are sampled independently (for example dwell + click + like + repost), rather than forced into one category
- LLM/heuristic 0–1 heads are **affinities**; Python maps them onto assumed impression-level priors before RankingScorer weights run

## Local run

Needs Python 3.11+, Node 22+, and a [Groq](https://console.groq.com) key for LLM + vision + Whisper. Without a key, heuristic scoring still runs.

```bash
cp .env.example .env   # backend settings; set GROQ_API_KEY if wanted
cp .env.example frontend/.env.local   # Next.js settings (server-only names stay private)

cd backend
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt   # Windows
# source .venv/bin/activate && pip install -r requirements.txt   # macOS/Linux
.venv\Scripts\python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

In a second terminal, start from the repository root:

```bash
cd frontend
npm install
npm run dev
```

Open [http://localhost:3000](http://localhost:3000). API health: [http://127.0.0.1:8000/api/health](http://127.0.0.1:8000/api/health).

Local and hosted frontend requests use the same `/api/*` handler. Set `BACKEND_API_URL` in `frontend/.env.local`; leave `NEXT_PUBLIC_API_URL` empty. The obsolete `INTERNAL_API_URL`/`BACKEND_PORT` rewrite is removed. Public demo mode requires no operator key. The optional personal Groq key uses the visitor's provider quota; private deployments still accept an operator key under advanced access settings. Selecting a recent run fills its ID; **Load** opens it, **Re-run snapshot** creates a new run from stored probabilities, and **Replay animation** only plays the graph.

Selected pictures now show local previews and individual remove controls. Image-only runs require successful vision extraction; provider failures return an actionable error rather than a fabricated text-only result. When a caption is available, a failed image analysis is explicitly labeled as caption-only. Qwen vision responses are capped at 512 tokens; four or five images/frames are combined into a numbered contact sheet to fit the provider's three-image limit, with reduced detail noted in the report. Very short text such as `hey` is marked as insufficient context; its simulated reach reflects scenario assumptions.

Graph playback supports pause/resume, replay, round scrubbing, and speed selection. Reduced-motion preferences disable autoplay. Detailed model diagnostics and observed outcomes remain available in expandable sections.

The pilot accepts at most 3.5 MB of combined media and a 4 MB complete request. Larger videos need a separate upload path and are deferred. **Stop waiting** stops the browser request; synchronous server work may still finish and appear after **Refresh runs**. The proxy stops waiting after 90 seconds by default.

## Optional data preparation and training

Run these from the repository root in a separate environment (Colab is fine for the larger download):

```bash
pip install -r training/requirements.txt
python training/prepare_nemotron.py --per-niche 24
python training/prepare_blueprint.py --revision <PINNED_DATASET_COMMIT_SHA>
python training/train_heads.py --split grouped --dataset-revision <PINNED_DATASET_COMMIT_SHA>
```

Review the generated Nemotron files before promoting them into `backend/data/overlays/{niche}.json`; runtime validation will still reject minor, sensitive, malformed, and off-niche records. The BluePrint artifact is written to `training/artifacts/phoenix_heads.joblib`; the app only loads the new validated artifact schema. Do not claim empirical calibration until you have collected a sufficiently large set of real impression-denominator outcomes through the outcome endpoint and evaluated calibration on a held-out time period.

## Environment

| Variable | Where | Purpose |
| --- | --- | --- |
| `APP_ENV` | backend | `development`, `test`, or fail-closed `production` validation |
| `GROQ_API_KEY` | backend | Optional text, vision, Whisper; deterministic fallback works without it |
| `CORS_ORIGINS` | backend | Comma-separated frontend origins |
| `SIM_PUBLIC_DEMO` | backend | Opt-in public runs using the server Groq quota; defaults to false. Visitors receive separate browser-session ownership and remain rate limited. |
| `SIM_API_KEY` | backend | Optional administrator key with access to every owner; never configure it on the frontend server |
| `SIM_ACCESS_KEYS_JSON` | backend | JSON map of owner IDs to strong keys; production UI users enter their own key and can access only their runs |
| `TRUSTED_PROXY_CIDRS` | backend | Proxy ranges allowed to supply forwarding headers for rate limiting |
| `RUN_RETENTION_DAYS` | backend | Required and positive in production |
| `ALLOW_SQLITE_IN_PRODUCTION` | backend | Explicit acknowledgement for single-node SQLite. Hosted free Render uses ephemeral `/tmp`. Paid disk is optional later. |
| `SQLITE_PATH` | backend | Database file; absolute path or relative to repository root. Local default `backend/data/runs.sqlite`. Hosted free Render: `/tmp/runs.sqlite`. |
| `SIM_MAX_CONCURRENT_RUNS` | backend | Maximum active analyses per process, default 2; excess requests receive 503 with `Retry-After` |
| `NEXT_PUBLIC_API_URL` | frontend | Optional direct API override; leave empty to use the same-origin proxy |
| `NEXT_PUBLIC_SITE_URL` | frontend | Canonical site URL |
| `BACKEND_API_URL` | frontend server | Private upstream URL used by the bounded, streaming same-origin `/api/*` proxy |
| `MAX_REQUEST_BYTES` | backend + frontend server | Matching request limit enforced while streaming at both boundaries |
| `API_PROXY_TIMEOUT_SECONDS` | frontend server | Time to wait for backend headers, default 90 seconds (1–300) |
| `NEXT_PUBLIC_SIM_DEV_TOKEN` | frontend | Optional browser-visible local gate only; never use as a production secret |

Copy `.env.example`. Never commit `.env`.

## Deploy

- **API** — Render web service, root `backend`, start `uvicorn app.main:app --host 0.0.0.0 --port $PORT`, health `/api/health`. Production startup requires `APP_ENV=production`, `SIM_PUBLIC_DEMO=true` and/or a strong credential in `SIM_ACCESS_KEYS_JSON` or `SIM_API_KEY`, positive retention, and an explicit single-node SQLite acknowledgement. Public demo visitors use the server Groq key; reserve `SIM_API_KEY` for administration.
- **UI** — Vercel project, root `frontend`; set server-only `BACKEND_API_URL` and the same `MAX_REQUEST_BYTES` as FastAPI. Do **not** set `SIM_API_KEY` or `GROQ_API_KEY` on Vercel. Leave `NEXT_PUBLIC_API_URL` and `NEXT_PUBLIC_SIM_DEV_TOKEN` unset; public demo visitors need no operator key when `SIM_PUBLIC_DEMO` is enabled on the backend. Private operator keys stay under Advanced access and are forwarded only to the backend.

The checked-in Render blueprint is the **free ephemeral demo**: `plan: free`, `SQLITE_PATH=/tmp/runs.sqlite`, no persistent disk, production mode, 30-day retention, public demo on, credential `sync: false`. Free instances cannot attach a disk and spin down after inactivity; `/tmp` is wiped on restart, redeploy, and spin-down. `GET /api/health` reports `storage.production_ready: false` on this path, so the UI loss banner stays. Details: [`research/RENDER_OWNER_RUNBOOK.md`](research/RENDER_OWNER_RUNBOOK.md).

**Optional later (not the default):** paid Starter (or higher) + disk at `/var/data` + `SQLITE_PATH=/var/data/runs.sqlite`. Disks are single-instance and skip zero-downtime deploys. Existing `/tmp` data is not migrated automatically. Keep that path out of `render.yaml` while staying on free — Blueprint sync would push Starter/disk.

For Vercel, keep the 4 MB request limit; the proxy route requests a 120-second function duration to cover its default 90-second upstream timeout. Use a plan/settings that support that duration (or lower `API_PROXY_TIMEOUT_SECONDS` if Fluid Compute is disabled). Provider timeout/retry settings bound individual calls; stopping a browser request does not cancel those calls. Real provider latency, budgets, live media, backup/restore and hosted smoke checks remain deployment acceptance work.

SOP deltas and Gate B→C scope: [`research/SOP_PILOT_ADDENDUM.md`](research/SOP_PILOT_ADDENDUM.md). Ranking weight pin: [`research/x-scoring-notes.md`](research/x-scoring-notes.md).

## API

With public demo mode enabled, the browser sends a random tab-scoped `X-Demo-Session` identifier so visitors can access only their own saved runs. The default analysis uses the server's Groq key. Visitors can optionally provide a personal Groq key through `X-Groq-API-Key`; it is used only for their request and is never stored in a report. Closing the tab clears the browser's session credentials.

Private operators can still send their key as `X-API-Key`. A key from `SIM_ACCESS_KEYS_JSON` owns every run it creates and receives `404` for another owner's run IDs; the optional `SIM_API_KEY` is an administrator override. Public mode is disabled unless explicitly enabled on the backend. Enabling it allows visitors to consume the configured server Groq quota; request and concurrency limits still apply. The shared server-key budget is 20 public runs per hour by default (`SIM_PUBLIC_RUNS_PER_HOUR`), counted across visitors; personal Groq keys bypass only that shared budget. Limits are in memory on this single-process demo and reset when it restarts.

| Method | Path | Notes |
| --- | --- | --- |
| `GET` | `/api/health` | Liveness; includes `storage.production_ready`, `storage.ephemeral`, `storage.path` |
| `POST` | `/api/simulate` | Multipart: `niche`, `text`, optional media |
| `POST` | `/api/compare` | `text_a` + `text_b` |
| `GET` | `/api/simulations?limit=20` | Recent owner-visible run summaries; limit 1–100 |
| `GET` | `/api/simulations/{id}` | Load a saved run owned by the authenticated key |
| `POST` | `/api/simulations/{id}/replay` | Replay stored probabilities/config with compatibility checks |
| `GET/POST` | `/api/simulations/{id}/outcome` | Read or record observed outcomes for future calibration |
| `GET` | `/api/simulations/{id}/snapshot` | Read the immutable provenance/config manifest |
| `DELETE` | `/api/simulations/{id}` | Delete a run and its outcome |

## Checks

From `backend`, run `python -m pytest -q`. From `frontend`, run `npm run lint`, `npm run build`, then `npm run test:proxy`. The proxy test starts only local fixture servers and checks the actual built handler, caller credentials, request size, timeouts and unavailable-backend errors. GitHub Actions runs these same checks. Browser regression steps and accepted SOP scope are recorded in `SOP_REVIEW_PLAN.md` and `research/SOP_PILOT_ADDENDUM.md`.

## Disclaimer

Prior-mapped research prototype, not empirically calibrated. Ranking weights follow public X defaults, not runtime experiments or the full production stack (no live Phoenix model/user history, Thunder, SimClusters retrieval, VMRanker, visibility filtering, or live traffic). Monte Carlo bands measure simulator randomness only; treat results as comparative scenarios, not forecasts.
