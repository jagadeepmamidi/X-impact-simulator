# X Impact Simulator

Experimental X-inspired audience and distribution simulator. **Comparative, not predictive.** Not X production. No live X feed. No virality guarantee.

Repo: [github.com/jagadeepmamidi/X-impact-simulator](https://github.com/jagadeepmamidi/X-impact-simulator)

Fifteen niche archetypes emit Phoenix-style *affinities*. Python maps those onto assumed impression-level base rates, scores them with public RankingScorer weights from [xai-org/x-algorithm](https://github.com/xai-org/x-algorithm), then runs a Monte Carlo **full-cascade** spread. Groq never emits `impact_score`. p10–p90 describe the final-round score of the same graph simulation shown in the UI.

## What you can do

- Score a hook against **tech**, **fitness**, **finance**, or **comedy** packs (15 archetypes each, cloned to 40 / 100 / 320 simulated agents)
- Optional **Hook B** compare on the same media and seed
- Verdict with full-cascade p10–p90, Niche Index, audience fit, negative risk, **stability** (not statistical confidence), and rewrite suggestions
- Save every run and **replay by id**
- BluePrint heads blend **favorite (40%)** and **retweet (25%)** only
- LLM/heuristic 0–1 heads are **affinities**; Python maps them onto assumed impression-level priors before RankingScorer weights run

## Local run

Needs Python 3.11+, Node 20+, and a [Groq](https://console.groq.com) key for LLM + vision + Whisper. Without a key, heuristic scoring still runs.

```bash
cp .env.example .env   # set GROQ_API_KEY

cd backend
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt   # Windows
# source .venv/bin/activate && pip install -r requirements.txt   # macOS/Linux
.venv\Scripts\python -m uvicorn app.main:app --host 127.0.0.1 --port 8000

cd frontend
npm install
npm run dev
```

Open [http://localhost:3000](http://localhost:3000). API health: [http://127.0.0.1:8000/api/health](http://127.0.0.1:8000/api/health).

## Environment

| Variable | Where | Purpose |
| --- | --- | --- |
| `GROQ_API_KEY` | backend | Text, vision, Whisper |
| `CORS_ORIGINS` | backend | Comma-separated frontend origins |
| `NEXT_PUBLIC_API_URL` | frontend | FastAPI base URL |
| `NEXT_PUBLIC_SITE_URL` | frontend | Canonical site URL |

Copy `.env.example`. Never commit `.env`.

## Deploy

- **API** — Render web service, root `backend`, start `uvicorn app.main:app --host 0.0.0.0 --port $PORT`, health `/api/health`
- **UI** — Vercel project, root `frontend`, set `NEXT_PUBLIC_API_URL` to the Render URL

Free Render web services spin down after 15 minutes idle. The first request after that is slow.

## API

| Method | Path | Notes |
| --- | --- | --- |
| `GET` | `/api/health` | Liveness |
| `POST` | `/api/simulate` | Multipart: `niche`, `text`, optional media |
| `POST` | `/api/compare` | `text_a` + `text_b` |
| `GET` | `/api/simulations/{id}` | Replay a saved run |

## Disclaimer

Uncalibrated research prototype. Ranking weights follow a public snapshot of X's RankingScorer, not the production stack (no Thunder, SimClusters, visibility filtering, or live traffic). Treat ranges as comparative, not forecasts.
