# DUSTER

Data quality and governance platform: a FastAPI backend running a PySpark DQ
engine, and a React frontend for two pipelines - **Profile Mapper** (profile
a source and generate/edit its DQ profile map) and **Validator** (run DQ
Rules against a source and review results) - behind a cookie-authenticated
dashboard with live notifications.

## Repo layout

```
duster/
├─ backend/     # FastAPI app + DQ engine (Python)
├─ frontend/    # React (Vite) SPA
├─ docs/        # design/flow docs
├─ requirements.txt   # backend deps (app + dev/test, one file)
└─ runtime/     # local runtime artifacts (uploads, job output, etc.)
```

## Backend

### Setup

```bash
python -m venv venv
venv\Scripts\activate        # Windows; use `source venv/bin/activate` on macOS/Linux
pip install -r requirements.txt
```

Copy `backend/.env.example` to `backend/.env` and fill in:

- `DATABASE_URL` - SQL Server connection string (via pyodbc) for the app's
  own database (users, sessions, saved connections, jobs, results).
- `CONNECTION_ENCRYPTION_KEY` - Fernet key encrypting saved connections'
  credentials at rest. Generate with:
  ```bash
  python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
  ```

Then apply migrations and create a login (from `backend/`):

```bash
cd backend
python scripts/run_migrations.py            # apply anything pending
python scripts/run_migrations.py --status   # show applied vs pending
python scripts/create_user.py <username>    # reset an existing user's password
```

**Windows + PySpark:** if a job fails to start with "The system cannot find
the path specified", set in `backend/.env`:

```
JAVA_HOME=C:\Program Files\Java\<the JDK folder that actually exists>
SPARK_HOME=<repo>\venv\Lib\site-packages\pyspark
PYSPARK_PYTHON=<repo>\venv\Scripts\python.exe
```

A Java 17 runtime is required wherever the backend runs - pip alone is not
enough (PySpark embeds a JVM).

### Run

```bash
python backend/app.py
```

Serves the API at **http://localhost:5050** (routes under `/api`), via
uvicorn. Session auth uses an httpOnly cookie with sliding expiry.

### Test

```bash
cd backend
pytest                    # all tests
pytest -m "not spark"     # skip tests needing a real local SparkSession
```

### Data quality rules

The Quality rules pages (`/quality-rules`, `/quality-rules/runs`) run a scoped,
template-based DQ engine (`backend/engine/quality/`). The design it follows: a rule is
a record (template + params + threshold + severity) kept separate from a
catalog/schema/table/column scope, and every rule × table is checked in one Spark
aggregate pass per table.

- **Catalog = saved connection.** A scope's catalog glob matches saved-connection
  names, so `*` means every connection. Schemas, tables and columns come from each
  source's own metadata, and columns are re-checked against the live Spark schema
  when a run starts.
- **Storage** is the app database. `dq_rules` holds the rules, `dq_runs` the runs, and
  `dq_results` is append-only, one row per rule × target with raw pass/total counts.
  Scores (row-weighted, table average, thresholds met) are rolled up from those counts
  when a run is read, never stored.
- **Templates** live in `engine/quality/templates.py`. Add one with `register(...)`, and
  mirror its metadata in `frontend/src/pages/QualityRules/ruleRegistry.js`.
- **API** is under `/api/quality-rules`: CRUD on rules, `POST /dry-run` (plans without
  scanning), `POST /runs` (async, returns 202), `GET /runs/{id|latest}` with rollups,
  `GET /runs/{id}/results` (paged, worst first) and `/results.csv`.

Apply `migrations/004_data_quality.sql` with `python scripts/run_migrations.py`. Tuning
knobs (`DQ_DEFAULT_PARALLEL_TABLES`, `DQ_MAX_EXPRS_PER_PASS`, `DQ_RUN_WORKERS`, …) are in
`core/config/data_quality_config.py`.

## Frontend

React 18 (JavaScript, no TypeScript) + Vite 5 + React Router v7 + Axios.
The current page lives in the URL (`BrowserRouter`), not in component state.

### Setup & run

```bash
cd frontend
npm install
npm run dev      # http://localhost:5173
npm run build    # production build → dist/ (also obfuscates the bundle, see build/obfuscate.js)
npm run preview  # preview the production build
```

Configure the API base URL in `frontend/.env` (see `.env.example`):

```
VITE_API_BASE_URL=http://localhost:5050/api
```

If the backend is unreachable, the app shows a dismissable banner rather
than failing silently (`ApiBanner` in `App.jsx`).

### Test

```bash
cd frontend
npm test          # vitest run (single pass)
npm run test:watch
```

### Structure

```
frontend/src/
├─ main.jsx                # mounts <App/>, imports global.css
├─ App.jsx                 # route table, auth gate, API health banner
├─ styles/                 # global.css + per-feature stylesheets
├─ api/
│  └─ api.js               # Axios instance + every backend endpoint call
├─ contexts/
│  ├─ AuthContext.jsx          # session status (checking/authenticated/anonymous)
│  ├─ NotificationsContext.jsx # bell state, backed by an SSE stream
│  └─ ToastContext.jsx         # app-wide toasts
├─ hooks/                  # useAuth, useCachedResource, useJobList, useCatalog, …
├─ components/             # Sidebar, Topbar, PageShell, tables, modals, charts, …
│  ├─ configure/           # Connections page pieces (wizard, source/table pickers)
│  ├─ notifications/       # bell + panel + item
│  ├─ profileMapper/       # Profile Mapper job UI (schema picker, rule modals, …)
│  └─ validator/           # Validator job UI (new-job modal, results tabs/grid)
├─ utils/                  # helpers, pageCache, jobProgress, humanizeLog, …
├─ constants/
│  ├─ appConfig.js         # API base URL, nav model, page copy, upload/job config
│  ├─ sourceTypes.js       # source type + database type options
│  ├─ dbFields.js          # per-DB dynamic field configs + required fields
│  ├─ jobStatus.js         # job status enum/labels
│  └─ dqRules.js           # DQ1–DQ11 rules + score thresholds
├─ pages/
│  ├─ Login.jsx            # only route reachable without a session
│  ├─ Home.jsx             # dashboard (GET /api/dashboard/summary)
│  ├─ Connections.jsx      # saved database connections manager
│  ├─ ProfileMapper.jsx / ProfileMapperJob.jsx
│  ├─ Validator.jsx / ValidatorJob.jsx
│  ├─ Rules.jsx            # DQ rule reference (search + dimension filter)
│  ├─ PagePlaceholder.jsx  # empty stand-in for undesigned routes
│  └─ NotFound.jsx         # catch-all 404
└─ test/                   # vitest setup + fakes (e.g. fakeEventSource.js)
```

### Routing & auth

`App.jsx` wraps everything in `AuthProvider` + `BrowserRouter`. `/login` is
the only route reachable without a session; every other route is nested
under `AuthenticatedLayout`, which redirects to `/login` whenever
`useAuth().status !== "authenticated"` - including immediately after
sign-out, since it re-evaluates on every render. Login always lands on
`DEFAULT_ROUTE` (`/home`); the originally requested path is not remembered.

`NotificationsProvider` is mounted only inside `AuthenticatedLayout`, so
nothing is fetched or streamed on the login screen, and it unmounts (dropping
all state) the moment a session ends.

A few sidebar destinations (Rule Catalog's Dimension/Rules tabs, Data
Catalog's Assets/Glossary) route to `PagePlaceholder` - the nav exists, the
page content doesn't yet. Swap in the real page in `App.jsx` when it's designed.

### API layer contract

Every `api.js` function returns `{ ok: true, data }` on success or
`{ ok: false, error }` on failure. Axios is configured with `withCredentials:
true` (session cookie) and a 401 response triggers an app-wide unauthorized
handler registered by `AuthProvider`, so an expired/invalidated session is
reflected everywhere at once, not just on whichever page made the failing call.

Uploads and downloads use a longer transfer timeout (large files); ordinary
JSON calls use a 30s default so a hung backend fails loudly instead of
leaving a page stuck on `loading: true` forever.

### Notifications

The top bar's bell is backed by `NotificationsContext`: history comes from
`GET /api/notifications` (keyset-paginated), and new items arrive live over a
Server-Sent Events stream, authenticated by the session cookie.
