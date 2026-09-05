# X Impact Simulator — audit implementation report

Date: 2026-09-05

## Outcome

The locally implementable audit findings have been addressed. The application now has consistent probability semantics, synthetic feed competition, coherent persona populations, a leakage-resistant optional ML workflow, reproducible run metadata, safer persistence/API boundaries, and UI language that distinguishes simulator stability from evidence-backed confidence.

This remains an X-inspired scenario simulator. It is not a copy of X production, does not run the live Phoenix model or user graph, and is not empirically calibrated until real impression-denominator outcomes are collected and evaluated.

## Implemented changes

| Area | Resolution |
| --- | --- |
| Action semantics | Scoring and event sampling use the same prior-mapped per-impression probabilities. Compatible actions are independently sampled, so dwell, click, like, reply, repost, etc. can coexist. Noise is applied in log-odds space. |
| Feed competition | Algorithmic exposure now requires the target post to win a seeded synthetic candidate slate. Candidate rank, selection, and explicit synthetic in/out-of-network status are recorded per shown member; both public scoring branches are exercised. |
| Headline impact score | The score now blends 35% persona prior with 65% median sampled population/ranking outcome, so prevalence, candidate competition, network status, and cascade path affect the headline while retaining a lower-variance prior anchor. It remains a scenario score, not a forecast. |
| X scoring defaults | Public `param.rs` defaults were rechecked. `video_open`, `vqv`, and `dwell` defaults were corrected, and missing production components/runtime overrides are disclosed. |
| Monte Carlo display | The graph shown in the UI is the run nearest median exposure, score, and depth instead of always run zero. Score and exposure p10–p90 ranges remain visible. |
| Personas | Curated personas are validated behavior profiles. Nemotron-derived records are display variants only, mapped to a named behavior profile or rejected. Minor/sensitive/off-niche/malformed records are filtered and provenance is hashed. |
| Population sampling | Persona prevalence is weighted and deterministic by seed. Member behavior varies through correlated engagement/skepticism latents instead of independent arbitrary traits. |
| BluePrint ML | Training defaults to actor-grouped splits, records dataset/config/model hashes, uses a text-inferred cluster feature at runtime, and emits a validated `phoenix-heads-v2` artifact. |
| ML runtime safety | Missing, corrupt, incompatible, malformed, or failed artifacts fall back without taking down simulation. Favorite/retweet signals are log-odds lifts that preserve persona ordering. |
| LLM reliability | The Groq SDK is optional, calls have bounded timeout/retries, and partial/duplicate/unknown persona responses are rejected as a whole before deterministic fallback. |
| Calibration claims | The old “calibrated confidence” claim was removed. Reports say `prior-mapped-not-empirically-calibrated`; Monte Carlo stability is explicitly not model confidence. |
| Replay/provenance | Versioned manifests bind the complete report payload, input/content/reaction hashes, configuration, and persona/model/dataset/weight metadata. They are verified on load. Exact replay is blocked for incompatible or legacy-unverified snapshots; alternate seeds are labeled and hashed as variants. |
| Storage | Runs/outcomes use transactional SQLite with WAL, schema migration, foreign keys, owner isolation, verified snapshots, read-time retention enforcement, and validated legacy-outcome migration. Production fails closed unless SQLite risk is explicitly acknowledged. |
| API security | Production requires an administrator or per-owner key. Tenant keys can access only their own runs/outcomes. Request and per-file sizes are bounded while streaming; file signatures must match MIME types. Rate limits are scoped by authenticated owner plus safely resolved client address. |
| Frontend security | The same-origin Next.js proxy never injects the administrator key, forwards only a caller-entered key, and streams through its own byte cap before FastAPI. Production credentials are not bundled into browser JavaScript. |
| UI correctness | Hook A and B graphs render separately; ranges, provenance, fallbacks, calibration status, and data coverage are surfaced. Fabricated affinity/watch labels were replaced with accurately named proxies. |
| Media compare | Shared video frame extraction/transcription is prepared once for an A/B comparison rather than duplicated. |

## Verification

- Backend: `python -m pytest -q` — 75 passed; one third-party Starlette/httpx deprecation warning.
- Frontend: `npm.cmd run lint` — passed with zero warnings/errors.
- Frontend: `npm.cmd run build` — passed, including TypeScript and the dynamic same-origin API proxy route.
- Python syntax: `python -m compileall -q app ../training` — passed.
- Patch hygiene: `git diff --check` — passed; Git only reported expected Windows LF-to-CRLF notices.

## Required owner actions

1. Pin the exact BluePrint dataset commit, accept its access terms, run the preparation/training commands in the README, and ship the artifact only if held-out favorite/retweet AP and Brier scores beat the recorded baseline.
2. Generate Nemotron candidates, manually review them, and promote only approved files into `backend/data/overlays/{niche}.json`. Generated biographies and sensitive fields must remain display-ineligible.
3. Collect real post outcomes with impressions, observation windows, timestamps, and niche labels. Use a time-based holdout before replacing the assumed priors or claiming calibration.
4. For production, set `APP_ENV=production`, strong per-owner entries in backend-only `SIM_ACCESS_KEYS_JSON`, `BACKEND_API_URL`, matching backend/frontend `MAX_REQUEST_BYTES`, exact CORS origins, positive retention, and trusted proxy CIDRs where applicable. Keep the optional backend `SIM_API_KEY` as an administrator credential only.
5. Put SQLite on a persistent single-node disk and explicitly acknowledge that mode, or replace it with a managed durable database before horizontal scaling. SQLite is deliberately not presented as multi-instance production storage.
6. Keep `SIM_API_KEY`, `NEXT_PUBLIC_API_URL`, and `NEXT_PUBLIC_SIM_DEV_TOKEN` unset on the production frontend. Operators enter their per-owner key in the UI; rotate any key that may have been exposed.
7. Run a staging smoke test with text, image, video, A/B comparison, save/load, replay, outcome write/read, snapshot, rate limiting, and deletion before promoting the deployment.
8. Update the SOP after accepting these implementation semantics, especially the candidate-slate assumption, persona behavior/display split, probability meaning, replay contract, and calibration language.

## Irreducible limitations

- X runtime experiment values, live viewer history, Phoenix embeddings/checkpoints used in production, Thunder/SimClusters inventory, VMRanker, author diversity, visibility enforcement, and the live social graph are unavailable to this project.
- Candidate competitors and cascades are therefore synthetic scenario assumptions.
- No amount of local code can turn the score into a validated forecast without representative real outcomes and prospective evaluation.
