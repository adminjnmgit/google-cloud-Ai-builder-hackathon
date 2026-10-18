# Jagran Orbit

Strategy intelligence for SMB owners across 15 sectors: Automotive, Energy, Banking, Pharma, Technology, FMCG & Food,
Agriculture, Real Estate, Cement & Infra, Metals & Mining, Aviation & Travel, Telecom & Media, Retail & E-commerce,
Consumer Durables and Gems & Jewellery.
A Flask backend serves the frontend, turns the newsroom's business reports into events, and stores everything
in one MySQL database.

```
jagran_biz (MySQL)  -->  pipeline  -->  orbit_events (MySQL)  -->  /api/data  -->  owner / analyst pages
or a CSV export          translate,                                                      |
                         classify,                        orbit_workspaces/profiles/tasks  <-- /api/workspace
                         cluster, brief                   Gemini chat / brief / search     <-- /api/agents/*
```

The rule-based pipeline does the heavy lifting. Gemini agents sit around it (translate the odd Hindi row, catch
the stories the lexicon misses, merge split episodes, write a short brief per event, answer questions) and are
switched off unless configured, so the product runs without any Google Cloud AI access at all. See
[AI agents](#ai-agents) and `docs/diagrams/architecture-final.png`.

## Quick start (Windows, XAMPP)

Start MySQL in XAMPP, then:

```powershell
cd backend
python -m venv .venv
.venv\Scripts\pip install -r requirements-dev.txt
copy .env.example .env                       # the defaults match XAMPP (root, no password)

$env:FLASK_APP = "wsgi"
.venv\Scripts\flask orbit init-db            # creates the database if needed and applies the migrations
.venv\Scripts\flask orbit pipeline run       # builds the feed from jagran_biz (or: flask orbit seed)
.venv\Scripts\python run.py                  # http://127.0.0.1:5000/
```

Open `/` (owner), `/analyst/` or `/compare/`. `run.py` refuses to start, with a clear message, if MySQL is down or
the schema is behind the code.

Creating the app never touches the database: tables come from migrations, data from explicit commands.

## Layout

| Path | What it is |
| --- | --- |
| `backend/orbit/` | The Flask package (see below) |
| `backend/migrations/` | Alembic migrations (the only thing that changes the schema) |
| `backend/tests/` | pytest suite, run against a throwaway MySQL schema |
| `frontend/owner/` | The product (owner page) |
| `frontend/analyst/`, `frontend/compare/` | Analyst dashboard and pair-compare view |
| `frontend/shared/orbit-api.js` | Browser client: loads the feed, syncs the owner's workspace |
| `frontend/tests/` | Engine acceptance tests: `node orbit-quant.test.js` |
| `tests/e2e.mjs` | Headless Chrome end-to-end test against a running server |
| `Dockerfile` | Cloud Run image (gunicorn + frontend + backend) |

### Inside `backend/orbit/`

| Module | Responsibility |
| --- | --- |
| `app.py` | Application factory: wires components, no side effects |
| `config.py` | `Settings`: every environment variable, parsed and validated once. MySQL only |
| `extensions.py`, `models.py`, `enums.py` | SQLAlchemy 2.0 typed models, naming convention, string enums |
| `database.py` | Create the database, check the schema is at the latest migration |
| `runs.py` | Run the pipeline on a source and publish the result (MySQL advisory lock, atomic switch) |
| `store.py`, `serialize.py`, `feed_cache.py` | Persist events, render the frontend's JSON, cache it per run (gzip + ETag) |
| `queries.py`, `workspaces.py` | Read-side queries; the owner's workspace rules and validation |
| `api/` | Thin Flask blueprints: HTTP in, HTTP out |
| `web.py` | Frontend pages, JSON error handlers, headers |
| `errors.py` | Domain exceptions; `web.py` maps them to status codes |
| `pipeline/` | The pure engine: reports in, events out, no database |
| `agents/` | The Gemini agents and the one client they share; `agents/pipeline.py` is the engine with the agents slotted in |

## The pipeline

`backend/orbit/pipeline/` turns reports into events in two steps:

1. **classify** (`classify.py`): each report is matched against the detectors in `lexicon.py` (headline subject,
   text context, exclusions). A match gives a variable, direction, magnitude, level and industries. Stock-market
   chatter and the Personal Finance, Mutual Funds and Insurance sections are dropped.
2. **cluster** (`cluster.py`): hits on the same variable, sub-topic and direction with no gap over 4 days become one event.

All vocabulary lives in `lexicon.py`; change detectors, exclusions, caps and the episode gap there.

Sources (`pipeline/sources.py`): the `jagran_biz` table (rows with English text), a server-side CSV, or an uploaded
CSV (the Jagran export, or `Sl No, Type, Date, Headline, Summary`).

Each run is recorded in `orbit_pipeline_runs`. The new events are written first and only then made active in one
transaction, so readers never see a half-built feed. A run that finds no events fails and keeps the current feed.
Only one run can be in progress at a time, even across processes (a MySQL `GET_LOCK`). The newest 3 runs are kept
(`ORBIT_KEEP_RUNS`).

```powershell
flask orbit pipeline run --source jagran_biz [--machine]
flask orbit pipeline run --source csv --csv "C:\path\Jagran Biz - Sheet1.csv"
flask orbit pipeline runs
flask orbit seed                  # publish the bundled snapshot (frontend/owner/data/events.json)
flask orbit export-seed           # rebuild that snapshot (events.json + events.js) from the pipeline, DB untouched
```

To refresh on a schedule, run the first command from Windows Task Scheduler.

## AI agents

Six agents, all optional. The pipeline and every page behave exactly as before when they are off or when a
model call fails; an agent that cannot answer simply skips its step.

| Agent | Where it runs | Model | What it does |
| --- | --- | --- | --- |
| Translate | pipeline, before classify | Cloud Translation, else `gemini-3.5-flash-lite` | English for rows that still carry Devanagari; flagged `mt: true` like the offline translations |
| Classify | pipeline, after the lexicon | `gemini-3.8-flash` | Looks only at reports the lexicon did not match and may add hits, forced back into the lexicon's variables, sectors and categories. Never touches a lexicon hit |
| Cluster | pipeline, after cluster | `gemini-3.5-flash-lite` | Suggests merging same-variable episodes the 4-day gap split; applied only at confidence ≥ 0.75 and only ever merges |
| Brief | pipeline (newest events) and on demand | `gemini-3.8-flash` | `what` / `soWhat` / `watchNext` and a 1–5 `impact`, stored on the run and served inline in `/api/data` as `event.brief` |
| Chat | request time | `gemini-3.8-flash` | Answers from the published events only and cites the ids it used |
| Search | request time | Vertex AI Search, else local keywords | Semantic search when a Discovery Engine data store is configured |

Turn them on with `ORBIT_AI_ENABLED=1` and one way of reaching Gemini:

- **Vertex AI** — `GCP_PROJECT=<project>`. This is what Cloud Run uses: the service's runtime service account needs
  *Vertex AI User* and the Vertex AI API enabled. No key is stored anywhere. The newest Gemini models are served from
  the `global` Vertex endpoint, which is the default (`ORBIT_VERTEX_LOCATION` overrides it).
- **Gemini Developer API** — `GEMINI_API_KEY=<key>` from [AI Studio](https://aistudio.google.com/apikey). Meant for a
  laptop that has no IAM role on the project. When both are set the key wins.

`GET /api/agents` shows which backend is active and the key masked (`AIza…1234`); the key itself never leaves the
process, is excluded from dataclass reprs and is scrubbed from error messages. Per-agent switches
(`ORBIT_AI_TRANSLATE`, `_CLASSIFY`, `_CLUSTER`, `_BRIEF`), the model names and the budgets (`ORBIT_AI_CLASSIFY_MAX`,
`ORBIT_AI_BRIEF_MAX`) are listed in `backend/.env.example`. Cloud Translation and Vertex AI Search need a billed
project; without them the translate agent uses Gemini and search uses the local keyword fallback.

## Sectors

The sector list lives in `backend/orbit/pipeline/lexicon.py` (`INDUSTRIES`); the API, the workspace validation and the
stats all read it, so there is one backend list. A sector name is stored in `String(20)` columns, so keep it to 20
characters or fewer, and keep new sectors at the end of the list (stored workspaces refer to them by name).

A sector is wired in three places:

1. **Which articles belong to it**: a word list in `IND_PATTERNS`, plus the sectors named in each detector's `inds`.
   A detector marked `exclusive=True` uses only its own `inds`, which stops "edible oil" from becoming an Energy event.
2. **What moves it**: detectors in `DETECTORS` (e.g. `gold`, `monsoon`, `housing_demand`, `telecom_tariff`) and their
   entries in `CAPS` (largest believable move).
3. **How an owner's numbers respond**: `SECTORS` in `frontend/owner/js/owner.js` (preset profile, labels and the
   `lines` that connect profile inputs to variables) and `VARS` in `orbit-mvp-data.js` (and the analyst page's copy).

Company records in the analyst "Companies" view still cover the first five sectors only; the other ten are modelled
through the owner's own profile. After changing any of this, run `flask orbit export-seed` (refreshes the bundled
snapshot and the offline fallback), update `SEEDED_EVENTS` in `tests/conftest.py`, then reprocess with
`flask orbit pipeline run --source jagran_biz --machine`.

## Database and migrations

One MySQL/MariaDB database (`MYSQL_DATABASE`, default `jagran_orbit`). All application tables are prefixed `orbit_`
and sit beside the newsroom tables, which the migrations never touch.

```powershell
flask db migrate -m "describe the change"    # after editing models.py; review the generated file
flask db upgrade                             # apply
flask db check                               # fails if models.py and the migrations disagree
```

`tests/test_migrations.py` runs that same check in the test suite, so a model change without a migration fails CI.

## API

| Endpoint | |
| --- | --- |
| `GET /api/health` | Database engine and active feed |
| `GET /api/data` | Whole feed in the shape the frontend uses (`{meta, events}`), gzip + ETag |
| `GET /api/events` | Filter by `industry`, `category`, `var`, `direction`, `since`, `until`, `min_reports`, `q`; `limit`, `offset`, `include=reports` |
| `GET /api/events/<id>` | One event with its reports |
| `GET /api/stats` | Counts by category, industry and variable, and a weekly timeline |
| `GET /api/workspace` | The owner's sector, profiles and tasks (sets the workspace cookie on first use) |
| `PUT /api/workspace/sector`, `/profile/<sector>`, `/tasks/<sector>` | Save state (JSON only) |
| `DELETE /api/workspace/<sector>?part=profile\|tasks\|all` | Reset |
| `GET /api/admin/pipeline/runs`, `POST /api/admin/pipeline/run` | Run history; start a run (`{"source": "jagran_biz"}` or a CSV upload in field `file`) |
| `GET /api/agents` | The agent catalog and the active AI configuration (key masked) |
| `POST /api/agents/chat` | `{"question": ..., "sector": ...}` → `{answer, citations, model}`; `error` carries a masked reason when the model could not answer |
| `POST /api/agents/brief/<id>` | Write (or return the stored) brief for one event |
| `GET /api/agents/search?q=` | Vertex AI Search or keyword fallback over recent events; `limit` up to 50 |

Errors are JSON `{"error": ..., "message": ...}`. Admin endpoints need `X-Admin-Token` (or `Authorization: Bearer`)
matching `ORBIT_ADMIN_TOKEN`. With no token set they only accept requests from the same machine.

## How the frontend uses it

`owner/index.html` loads `shared/orbit-api.js`, which fetches `/api/data`, restores the owner's workspace, then starts `owner.js`.
Profile, tasks and the chosen sector are written to localStorage immediately and to the database in the background. If the
server is unreachable the page keeps working from localStorage (and the bundled snapshot for the feed) and catches up later. An existing
browser's local data is adopted into the database on its first visit. Opened from disk (`file://`) it behaves as before, local only.

The workspace is identified by a random token in an HttpOnly cookie. There are no logins yet, so anyone using the same
browser profile shares a workspace; add authentication before exposing this beyond trusted users.

## Development

```powershell
cd backend
.venv\Scripts\python -m pytest               # needs MySQL running; uses schema jagran_orbit_test
.venv\Scripts\ruff check . ; .venv\Scripts\ruff format .
cd ..\frontend\tests; node orbit-quant.test.js    # quant engine
cd ..\..; node tests\e2e.mjs                       # with the server running; needs Chrome
```

The suite rebuilds `jagran_orbit_test` from the migrations at the start of every run and refuses to run against any
schema whose name does not end in `_test`, so it cannot touch real data.

## Tables

`orbit_pipeline_runs`, `orbit_events`, `orbit_event_reports`, `orbit_event_tags` (pipeline output);
`orbit_workspaces`, `orbit_business_profiles`, `orbit_tasks` (owner state);
`orbit_translations` (machine translations, below).

## Machine-translated reports

`orbit_translations` holds offline English for Hindi-only articles. The pipeline uses them when
`ORBIT_USE_MACHINE_TRANSLATIONS=1` (or `--machine`). A human English headline always wins. Those reports carry
`mt: true` in the API and are never chosen as an event's face when a human-translated report exists.

## Deploy on Cloud Run

The image is the repo root `Dockerfile`. It serves the Flask app and the frontend with gunicorn. Put secrets in
Secret Manager or Cloud Run env vars — never in the image.

```powershell
gcloud run deploy jagran-orbit --source . --region asia-south1 --allow-unauthenticated `
  --add-cloudsql-instances PROJECT:REGION:INSTANCE `
  --set-env-vars "MYSQL_USER=app-user,MYSQL_DATABASE=example-prod-db,CLOUD_SQL_CONNECTION_NAME=PROJECT:REGION:INSTANCE,ORBIT_COOKIE_SECURE=1,ORBIT_MIGRATE_ON_START=1,ORBIT_ADMIN_TOKEN=change-me" `
  --set-secrets MYSQL_PASSWORD=orbit-db-password:latest
```

`/api/health` is the readiness check. The service starts even if no feed is published yet (`feed` is null until
`flask orbit seed` or `flask orbit pipeline run` has been applied to Cloud SQL). After the first deploy, load the
schema and events into Cloud SQL, then the owner page at `/` works.

To enable the agents on Cloud Run add `ORBIT_AI_ENABLED=1,GCP_PROJECT=<project>` to `--set-env-vars`, enable the
Vertex AI API in that project and grant the service's runtime service account `roles/aiplatform.user`. Leave
`GEMINI_API_KEY` unset there.

Secrets never go in the image or the repo: `backend/.env` is git-ignored and excluded by `.dockerignore` /
`.gcloudignore`, and a gitleaks workflow scans every push and pull request.
