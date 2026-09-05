# X Impact Simulator review and minimal implementation plan

Reviewed 5 September 2026 against `X_Impact_Simulator_Full_SOP.docx` and commit `a73586b`. Three Luna subagents reviewed SOP coverage, backend checks, and frontend behavior; the coordinating agent verified findings and ran browser checks. The original review is preserved below. The user subsequently approved implementation; the implementation status at the end records what was fixed and what still needs external validation.

## Assessment

The app is a working experimental audience simulator with meaningful automated coverage. It is suitable for local comparative experiments. It is not yet ready to declare the SOP complete or to deploy publicly using the checked-in defaults.

Preserve the existing FastAPI/Next.js structure, statistical personas, deterministic fallback, Monte Carlo simulation, independent compatible actions, owner isolation, and stored-probability replay. The next work should fix concrete integration/data issues and validate usefulness. It does not need an architecture rewrite.

## Verification performed

| Check | Result |
| --- | --- |
| Existing backend suite in `backend/.venv` | 75 passed in 33.98 seconds; one third-party Starlette deprecation warning |
| Frontend ESLint | Passed |
| Frontend production build and TypeScript | Passed; also passed with the Vercel rewrite branch selected |
| Browser text run through the intended Next API proxy | Passed with deterministic fallback |
| Browser A/B comparison with 500 people per variant | Both reports and separate graphs rendered |
| Save outcome and load saved run | Passed; switching runs exposed the stale-form issue below |
| Stored-probability replay | Original and replay simulation payloads and impact scores matched exactly |
| Browser load of a 40-person run after a 500-person run | Report loaded, but current controls/footer incorrectly still said 500 |
| Event-loop diagnostic | A 50 ms timer resumed after 250 ms when the endpoint executed a 250 ms synchronous pipeline fixture |

Browser writes used synthetic inputs in a disposable SQLite database outside the repository, with Groq disabled. The test run was verified absent from the workspace database. These checks do not establish live Groq/vision/transcription reliability, hosted deployment behavior, the SOP's live-provider latency budget, or real-world predictive accuracy. Upload and model-contract unit tests passing is not a live media test.

## Confirmed findings

### 1. Outcome data can remain attached visually to the wrong run

`frontend/app/simulator.tsx:295` reuses `OutcomePanel` across load/replay, and its effect at line 720 does not reset fields or save status when `runId` changes. All fetch failures are swallowed at line 735.

Reproduction: save 1,000 impressions and 50 likes, then replay. The new run has no outcome (API returns 404), yet the form still contains 1,000/50 and says "Saved against this run id." Saving again can associate those numbers with the wrong simulation.

Small fix: reset/key the panel by run ID, reset status immediately, distinguish no saved outcome from network/auth errors, and prevent a stale response from updating a newer run. Validate numeric input rather than silently converting invalid text to null. Restore population and boost from the loaded report and derive report labels from its stored settings (`onLoad` line 125, `onReplay` line 146, footer line 301).

Acceptance: changing runs cannot carry over outcomes or success messages; loading a 40-person run consistently displays 40; invalid input produces a clear error.

### 2. The Render blueprint does not activate production safeguards

`render.yaml:1` selects the free plan and provides only Python, Groq and CORS settings. `backend/app/config.py:9` defaults to development; `main.py:125` allows unkeyed development access. Production validation runs only when production mode is explicitly selected. `store.py:19` stores runs in a fixed local SQLite path.

An otherwise unconfigured deployment from this blueprint would run without authentication and with non-durable local storage. Render documents that free services cannot attach persistent disks and that local files are lost on restarts/redeploys. [Render storage documentation](https://render.com/docs/disks), [free-service restrictions](https://render.com/docs/free).

Small fix before public access: set production mode, per-owner credentials, positive retention, and an intentional durable storage setup. Keep SQLite for a small single-instance pilot if it has a persistent disk and backups. Add a configurable database path so mounting storage and isolated testing are straightforward. Do not migrate to a larger database merely to match a suggested SOP stack.

Acceptance: missing production credentials fail startup; another owner's run is inaccessible; a saved run survives a service restart; backup/restore is demonstrated. Dashboard settings were not inspected, so this finding concerns the checked-in template, not a claim about an existing deployment.

### 3. Two frontend proxy paths disagree

`frontend/next.config.ts:5` installs a non-Vercel rewrite using `INTERNAL_API_URL` or port 8000. It runs before the dynamic handler in `frontend/app/api/[...path]/route.ts:15`, which uses the documented `BACKEND_API_URL` and implements bounded streaming and friendly failures.

Browser reproduction: with `BACKEND_API_URL=http://127.0.0.1:8765`, the ordinary build still tried port 8000 and returned a generic 500. Building with the existing Vercel condition enabled exercised the intended handler successfully.

Small fix: use the same handler/configuration in local and hosted runs; remove the obsolete conflicting rewrite. Add one smoke check with a nondefault backend port and one unavailable-backend check.

### 4. Synchronous work blocks async API endpoints

`backend/app/main.py:328` and line 358 call synchronous `run_pipeline`/`compare_hooks` directly. Those functions include synchronous provider calls and simulation work (`pipeline.py:214`). The timer diagnostic confirms event-loop starvation; this is not a load benchmark.

Small fix: move the existing synchronous pipeline off the async event loop, with bounded concurrency and request/provider time budgets. Verify health and a second request stay responsive during a slow analysis. A distributed queue is unnecessary for the current pilot; reconsider only if measured job duration or demand requires it.

### 5. Hosted upload limits differ from application limits

`backend/app/config.py:31` onward permits 8 MiB images, 32 MiB video, and 40 MiB combined uploads; the Next proxy defaults to 44 MiB. Vercel's documented function request limit is 4.5 MB, so the larger allowance cannot make those requests work through the documented Vercel path. [Vercel payload limit](https://vercel.com/docs/errors/function_payload_too_large).

Small fix for the text-first pilot: cap the entire multipart request below the hosting limit, show the limit before submission, and keep larger video uploads out of the pilot. Add a dedicated upload path only when larger media becomes a real requirement. Verify an over-limit request fails with a useful explanation.

## SOP alignment without adding unnecessary scope

| SOP area | Assessment and smallest next step |
| --- | --- |
| Scoring, personas, staged spread, uncertainty, replay | Substantially implemented and tested. Preserve these mechanisms. |
| Probability semantics, sections 9.2 and 11.2 | SOP 9.2 asks for a normalized distribution, while 11.2 permits compatible actions. Document independent action marginals explicitly; do not force likes, clicks and reposts to sum to one. |
| Confidence | UI already correctly says run stability and discloses missing calibration. Keep that distinction. |
| Creator context and profile impact | Follower count, explicit audience selection, and creator baseline are missing. Current profile impact is against a synthetic bland-post baseline. Record that as current scope; implement creator-relative metrics only when meaningful creator data is available. |
| Population | UI defaults to 40, API to 100, and 500 is supported and browser-tested. Keep smaller modes for quick checks; use 500 for the SOP acceptance demo. |
| Processing and history | Replace the timed "creating simulated population" display with an honest indeterminate state. Explain cancel behavior accurately. Add a modest per-owner recent-runs list when inviting pilot users; no elaborate job dashboard is needed now. |
| Text-first usability | The page is media-led and captions are small single-line fields. Give text a proper labelled textarea and describe niches as niches, not demographics. This can be a small layout change. |
| Provenance | Local weight/config hashes exist, but `research/x-scoring-notes.md:3` references a dated public main branch, not an exact upstream SHA. Record the immutable source revision. |
| Calibration and evaluation | Outcome collection exists; measured usefulness, time-held-out validation, and baseline improvement have not been established. UI also needs observation time/window fields already supported by the outcome schema. |
| CI and release gates | No checked-in GitHub Actions workflow was found. Add the existing backend tests, frontend lint and build to one simple workflow. Local checks are not evidence that branch protection or deployment monitoring is configured. |

The simulation-prototype gate is broadly supported by the current checks. Staging/public-beta gates remain incomplete: actual hosted smoke testing, historical backtesting, user feedback, durable operation and monitoring still need evidence.

## Implementation order for the next code pass

1. **Correctness patch:** outcome reset/error handling, loaded-run settings, unified proxy, and focused regression checks for the reproduced bugs.
2. **Pilot readiness patch:** production deployment defaults and storage path, nonblocking pipeline execution with bounded concurrency, practical upload limits, simple CI. Verify a slow run does not freeze health checks and persisted data survives restart.
3. **Small text-pilot patch:** text-first input, honest loading feedback, recent-run access, observation time/window capture. Update the SOP's accepted scope and event semantics alongside this work.
4. **Evidence before expansion:** run staging checks with the actual provider enabled, measure text latency and cost, collect at least the SOP's 20 historical posts using consistent observation windows, and ask 10 target users whether the advice is useful. Twenty posts is an initial backtest exercise, not sufficient evidence to claim calibration. Use a held-out time period and compare against simple baselines before changing priors or making predictive claims.

Defer QLoRA, additional model heads, more niche packs, advanced video, microservices, Redis/Celery, and a broad database redesign. Optional BluePrint training and Nemotron expansion are not prerequisites for the next useful pilot.

## What the owner needs to do

- Use current results as comparative scenarios; do not interpret 98/100 stability as 98% prediction accuracy.
- Before public deployment, confirm production environment, owner keys, durable storage, retention, provider limits and a rollback path.
- Supply consented historical outcomes and a consistent observation window; code alone cannot establish prediction quality.
- Choose a small technology-creator pilot and prioritize evidence that the recommendations help over expanding features.

## Implementation follow-up

Implemented locally after approval on 5 September 2026, using the three Luna agents and parent integration. No deployment, purchase, commit or push was performed. The DOCX remains the original roadmap; this follow-up records the accepted pilot scope.

| Review item | Implemented resolution |
| --- | --- |
| Stale outcomes and incorrect loaded controls | Outcome panels remount per run, ignore stale loads, distinguish no outcome from errors, reject invalid counts, and preserve observation time/window. Load/replay restores population and boost; footer and graphs use stored population. |
| Conflicting proxy | Removed the non-Vercel rewrite; local and hosted runs use `BACKEND_API_URL`. Added a 90-second configurable proxy timeout with an explicit message that work may finish in the background. |
| Blocking API | Analysis runs off the event loop with two worker slots by default. Full capacity returns 503/Retry-After. Cancellation does not free capacity until its worker actually finishes. |
| Deployment/storage | Free Render pilot blueprint, per-owner credential configuration, 30-day retention, and explicit ephemeral SQLite at `/tmp/runs.sqlite`. `SQLITE_PATH` still supports switching to a mounted database on a paid plan; SQLite sidecars are ignored by Git. |
| Upload mismatch | 3.5 MB combined media and 4 MB complete-request defaults, frontend preflight validation, and visible size/type limits. Large media remains deferred. |
| Pilot usability | Text-first labelled textareas, honest waiting feedback, stop-waiting control, distinct replay labels, owner-scoped recent runs with refresh and saved-outcome flags. |
| CI | Existing backend tests, frontend lint/build, and an actual built-server proxy integration suite run in one GitHub Actions workflow. |

Validation: the full backend suite passed 81 tests. The six new runtime/storage checks were rerun after strengthening recent-run API authorization coverage and passed. Frontend lint/build passed. The built-server proxy suite passed all five behavioral subtests (six test entries including the parent), covering nondefault routing, no administrator-key injection, upload limit, timeout and unavailable backend.

Browser regressions passed against a disposable database with Groq disabled: loading 40 after selecting 500 restores 40; replay clears 1,000/50 observations and the previous saved message; invalid text in a numeric field is rejected; valid counts and observation window save and refresh history; 500-person A/B reports render separately. The same temporary database successfully reopened across server restarts. Desktop and narrow mobile form layouts were inspected.

Accepted pilot semantics: compatible actions remain independent marginals, the current profile baseline remains synthetic, stability remains distinct from model confidence, and 500 is the demo population while smaller preview modes remain available. Creator-specific prediction, fine-tuning, large video and infrastructure expansion remain deferred.

External release work remains: supply production keys and origins, treat the free Render blueprint as disposable demo storage (or migrate to a paid disk before retaining user runs), verify a real backup/restore and hosted restart, configure provider budgets and function duration, run live Groq/media smoke tests, and gather consented outcomes and user feedback. The upstream weight source still needs an immutable revision recorded; local weight/config hashes already protect saved-run replay. No empirical-calibration or public-beta completion claim is made.
