# George Job Agent — Next Implementation Plan

| Field | Value |
|-------|--------|
| **Document type** | Implementation specification (design only) |
| **Status** | Not implemented — build when you are ready |
| **Project** | `George_job_agent` |
| **Version** | 2.0 |
| **Last updated** | May 2026 |

---

## Table of contents

1. [Executive summary](#1-executive-summary)
2. [Decisions locked in](#2-decisions-locked-in)
3. [What exists today](#3-what-exists-today)
4. [Goals and non-goals](#4-goals-and-non-goals)
5. [Hosting](#5-hosting)
6. [Target architecture](#6-target-architecture)
7. [Supabase PostgreSQL](#7-supabase-postgresql)
8. [Tracker migration (Excel → Postgres)](#8-tracker-migration-excel--postgres)
9. [Web UI](#9-web-ui)
10. [Scheduler (web-controlled)](#10-scheduler-web-controlled)
11. [Long-running jobs](#11-long-running-jobs)
12. [REST API specification](#12-rest-api-specification)
13. [Security](#13-security)
14. [Environment variables](#14-environment-variables)
15. [Local usage (after build)](#15-local-usage-after-build)
16. [Deployment](#16-deployment)
17. [Data flows](#17-data-flows)
18. [Implementation checklist](#18-implementation-checklist)
19. [Success criteria](#19-success-criteria)
20. [Current workaround (until built)](#20-current-workaround-until-built)
21. [Document control](#21-document-control)

---

## 1. Executive summary

This plan adds **three capabilities** on top of the existing CLI agent (no rewrite of scoring, tailoring, or scrapers):

| # | Capability | Summary |
|---|------------|---------|
| 1 | **Supabase PostgreSQL** | Tracker source of truth (roles, events, optional run metadata) |
| 2 | **Simple web UI** | Plain HTML/CSS/JS; full CLI parity in the browser |
| 3 | **Web scheduler** | Off / 1h / 2h / 4h auto-run from the dashboard |

**Delivery model:** One implementation phase — database, web UI, and scheduler **together** (not database-only first).

**Recommended runtime:** A single local Python process — FastAPI serves the API and static pages; APScheduler runs in the background; the agent calls the same modules as today (`orchestrator`, `manual_role`, etc.).

**Excel:** Postgres only for live data. Optional `python -m agent export-tracker` generates `.xlsx` when you want a spreadsheet.

---

## 2. Decisions locked in

| Question | Decision |
|----------|----------|
| Tracker backend after migration | **Postgres only** (Supabase); no dual-write to Excel |
| Excel file | **On-demand export** via `export-tracker` |
| Web UI + scheduler | **Same phase** as database migration |
| UI style | Minimal HTML, no emoji, no React/npm build |
| Scheduler intervals | Off, 1 hour, 2 hours, 4 hours |

---

## 3. What exists today

### 3.1 Entry points

| Item | Location | Notes |
|------|----------|-------|
| CLI | `agent/main.py` | Typer, 12 commands |
| Module run | `python -m agent` | `agent/__main__.py` |
| Config | `agent/config.py` | `.env` via pydantic-settings |
| Core loop | `agent/orchestrator.py` | Search → dedupe → score → tracker → tailor → notify |

### 3.2 CLI commands (web must match 1:1)

| Command | Purpose |
|---------|---------|
| `run` | Full automated cycle |
| `run --dry-run` | Score only; no tracker/artifact writes |
| `status` | Last run health + top tracker rows |
| `status --drafts` | Only `Draft` rows |
| `schedule` | Blocking scheduler (4h default, `.env`) |
| `add-role` | Manual role (interactive, file, or flags) |
| `add-linkedin` | Same; default source `linkedin` |
| `tailor <slug>` | Force CV for one role |
| `review <slug>` | Role + artifacts; optional approve |
| `approve <slug>` | Status → `Ready` |
| `package <slug>` | Bundle PDFs under `workspace/packages/<slug>/` |
| `mark-applied <slug>` | Status → `Applied` + date |
| `sync-master` | Regenerate master LaTeX stub from `cv-facts.md` |

### 3.3 Scheduler (current)

- **File:** `agent/scheduler/job.py`
- **Engine:** APScheduler `BlockingScheduler`
- **Interval:** `SCHEDULE_INTERVAL_HOURS` in `.env` (default **4**)
- **Timezone:** `TIMEZONE` (default **Africa/Cairo**)
- **Start:** `python -m agent schedule` — runs once immediately, then blocks until Ctrl+C
- **Limitation:** Interval change requires `.env` edit and restart

### 3.4 Tracker (current: Excel)

| Item | Value |
|------|--------|
| File | `workspace/tracker/george_emil_job_tracker.xlsx` |
| Class | `agent/tracker/workbook.py` → `TrackerWorkbook` |
| Pipeline | All live writes |
| Applied sheet | Same headers; rarely used (applied stays on Pipeline) |
| Log sheet | Timestamped events |
| Slug | Stored in Notes as `slug:<slug>` |

**Pipeline columns:** Rank, Company, Role Title, Location, Source, Score, Tier, Role Family, Fit Summary, Apply Link, CV Ready, Cover Letter Ready, Status, Applied Date, Notes, First Seen, Last Updated.

### 3.5 Run reports

- Path: `workspace/logs/runs/YYYY-MM-DD_HH-MM.json`
- Contents: per-scraper counts/errors, raw/fresh counts, scored/tailored/letters, failures
- Used by CLI `status` for scraper health

### 3.6 Workspace layout

```
workspace/
  memory/              # profile, cv-facts, applications-log, etc.
  tracker/             # george_emil_job_tracker.xlsx (today)
  cv/tailored/         # <slug>.tex / .pdf
  cover_letters/       # <slug>_letter.tex / .pdf
  packages/            # apply bundles
  logs/
    agent.log
    runs/*.json
  config/              # (planned) schedule.json
```

### 3.7 Dependencies today

Present: `apscheduler`, `pytz`, `typer`, `openpyxl`, `httpx`, `playwright`, etc.

**Not yet present:** `fastapi`, `uvicorn`, `sqlalchemy`, `psycopg`

---

## 4. Goals and non-goals

### 4.1 Goals

| ID | Goal | Approach |
|----|------|----------|
| G1 | Simple website | Vanilla HTML/CSS/JS |
| G2 | Configurable schedule | 1h / 2h / 4h / Off in UI; `workspace/config/schedule.json` |
| G3 | Full CLI parity | REST API maps 1:1 to commands |
| G4 | Online tracker | Supabase Postgres |
| G5 | Local-first | `python -m agent web` on `127.0.0.0.1` |
| G6 | Hostable later | Single app on always-on PaaS/VPS |

### 4.2 Non-goals

- Multi-user accounts (beyond optional single `WEB_TOKEN`)
- GitHub Pages–only hosting
- Notification settings in the UI (stay in `.env`)
- Automated application submission to job boards
- Storing CV/letter PDF binaries inside Postgres (files stay on disk)

---

## 5. Hosting

| Option | Web + scheduler + scrapers? | Notes |
|--------|------------------------------|-------|
| Your PC (`localhost`) | Yes | Best for dev; Playwright + LaTeX local |
| Render / Railway / Fly.io | Yes | Needs `DATABASE_URL`, persistent `workspace/` |
| Google Cloud Run | Yes (caveats) | Timeouts; custom image for Playwright/LaTeX |
| Small VPS / home server | Yes | Full control |
| **GitHub Pages** | **No** | Static only — no Python/API |
| GitHub Actions cron | Partial | Can run CLI on schedule; not a live UI |

The “website” is a **web application** (Python server + browser), not a static site.

---

## 6. Target architecture

```mermaid
flowchart TB
  subgraph client [Browser]
    pages[HTML_pages]
  end
  subgraph server [Python_process]
    api[FastAPI]
    static[Static_files]
    jobs[Job_runner_lock]
    sched[BackgroundScheduler]
    svc[Service_layer]
  end
  subgraph data [Data]
    pg[(Supabase_Postgres)]
    files[workspace_files]
  end
  subgraph agent [Existing_modules]
    orch[orchestrator]
    manual[manual_role]
    pack[package_role]
  end
  pages --> api
  api --> static
  api --> jobs
  api --> sched
  jobs --> svc
  sched --> svc
  svc --> orch
  svc --> manual
  svc --> pack
  svc --> pg
  orch --> files
  cli[Typer_CLI] --> svc
```

### 6.1 Design principles

1. **Thin web layer** — routes call existing logic; no duplicate scoring/tailoring.
2. **One run at a time** — shared lock for manual run and scheduled run.
3. **Postgres for pipeline** — files remain under `workspace/`.
4. **CLI remains** — Typer for scripts and automation.

### 6.2 New package layout

```
agent/
  web/
    app.py
    routes.py
    schemas.py
    services.py
    jobs.py
    scheduler_manager.py
    static/
      index.html
      roles.html
      role.html
      add-role.html
      style.css
      app.js
  tracker/
    workbook.py          # keep for export + migration
    postgres.py          # (new) PostgresTracker
    models.py            # (new) RoleRecord
  roles.py               # (new, optional) shared slug/row helpers
supabase/
  migrations/
    001_initial.sql
```

### 6.3 New dependencies

```
fastapi>=0.110
uvicorn[standard]>=0.27
sqlalchemy>=2.0
psycopg[binary]>=3.1
```

### 6.4 New CLI commands

| Command | Description |
|---------|-------------|
| `python -m agent web` | Start API + static UI (+ embedded scheduler) |
| `python -m agent export-tracker` | Export Postgres pipeline to `.xlsx` |
| `python -m agent import-tracker` | (optional) One-time import from existing xlsx |

---

## 7. Supabase PostgreSQL

### 7.1 Project reference

| Item | Value |
|------|--------|
| Project URL | `https://[YOUR-PROJECT-REF].supabase.co` |
| Project ref | `[YOUR-PROJECT-REF]` |
| DB host | `db.[YOUR-PROJECT-REF].supabase.co` |
| Port | `5432` |
| Database | `postgres` |
| User | `postgres` |

Dashboard: [Supabase project](https://supabase.com/dashboard/project/[YOUR-PROJECT-REF])

### 7.2 Connection strings (use `.env` only)

**Direct Postgres (Python agent — primary):**

```env
DATABASE_URL=postgresql://postgres:[YOUR-PASSWORD]@db.[YOUR-PROJECT-REF].supabase.co:5432/postgres
```

**Supabase project URL (REST / storage later):**

```env
SUPABASE_URL=https://[YOUR-PROJECT-REF].supabase.co
```

**Publishable key (browser clients with RLS — optional, future):**

```env
SUPABASE_PUBLISHABLE_KEY=[from Supabase API settings]
```

Do **not** put real passwords or service-role keys in this file or in git. Set them only in local `.env`.

If a database password was ever shared in chat or committed by mistake, **rotate it** under Project Settings → Database before going live.

### 7.3 Supabase CLI setup

```bash
supabase login
supabase init
supabase link --project-ref [YOUR-PROJECT-REF]
```

Apply migrations:

```bash
supabase db push
# or: supabase migration up
```

### 7.4 SQL schema (initial migration)

**Table: `roles`** (replaces Pipeline sheet)

| Column | Type | Notes |
|--------|------|--------|
| `slug` | `text` PRIMARY KEY | Stable id, e.g. `acme-ml-engineer-wuzzuf` |
| `rank` | `integer` | Recalculated on `rerank()` |
| `company` | `text` | |
| `title` | `text` | |
| `location` | `text` | |
| `source` | `text` | wuzzuf, bayt, linkedin, manual, … |
| `score` | `integer` | 0–100 |
| `tier` | `text` | top, strong, medium, stretch, skip |
| `role_family` | `text` | |
| `fit_summary` | `text` | |
| `apply_url` | `text` | |
| `cv_ready` | `boolean` | default false |
| `letter_ready` | `boolean` | default false |
| `status` | `text` | Not Applied, Draft, Ready, Applied |
| `applied_date` | `date` | nullable |
| `first_seen` | `timestamptz` | |
| `last_updated` | `timestamptz` | |

Indexes: `(status)`, `(score DESC)`, `(last_updated DESC)`.

**Table: `events`** (replaces Log sheet)

| Column | Type |
|--------|------|
| `id` | `bigserial` PRIMARY KEY |
| `timestamp` | `timestamptz` |
| `event` | `text` |
| `detail` | `text` |
| `slug` | `text` REFERENCES `roles(slug)` ON DELETE SET NULL |

**Table: `runs`** (optional; mirrors JSON run reports)

| Column | Type |
|--------|------|
| `id` | `bigserial` PRIMARY KEY |
| `timestamp` | `timestamptz` |
| `manual` | `boolean` |
| `dry_run` | `boolean` |
| `report_json` | `jsonb` |

---

## 8. Tracker migration (Excel → Postgres)

### 8.1 `PostgresTracker` interface

Implement the same public surface as `TrackerWorkbook`:

| Method | Behavior |
|--------|----------|
| `load_or_create()` | Ensure connection / tables exist |
| `upsert_role(listing, score_result)` | Insert or update by `slug` |
| `get_row_by_slug(slug)` | Return `RoleRecord` (not raw tuple) |
| `get_all_slugs()` | Set of slugs for dedup |
| `list_pipeline_rows()` | All rows for API/UI |
| `set_status` / `mark_draft` / `mark_ready_for_apply` / `mark_applied` | Status updates |
| `mark_cv_ready` / `mark_letter_ready` | Flags + event log |
| `rerank()` | `ORDER BY score DESC`, rewrite `rank` |
| `append_log(event, detail)` | Insert into `events` |
| `save()` | Commit transaction (no-op or flush for SQLAlchemy session) |

### 8.2 Call sites to switch

| File | Usage |
|------|--------|
| `agent/orchestrator.py` | Main run loop |
| `agent/manual_role.py` | Add-role path |
| `agent/main.py` | status, tailor, review, approve, mark-applied |
| `agent/package_role.py` | Read company/title/url/fit by slug |

Replace tuple indices (`row[1]`, `row[9]`, …) with `RoleRecord` fields everywhere touched.

### 8.3 One-time import

1. Read `workspace/tracker/george_emil_job_tracker.xlsx`
2. Parse `slug:` from Notes column
3. Upsert into `roles`; import Log sheet into `events`
4. Verify counts vs Excel

### 8.4 Export

`export-tracker` uses `openpyxl` to write a new xlsx from Postgres (Pipeline + Log sheets) for Excel/LibreOffice viewing.

---

## 9. Web UI

### 9.1 Global layout

- Header: **George Job Agent**
- Nav: **Dashboard** | **Roles** | **Add role**
- Neutral styling, system fonts, no emoji, no icon fonts

### 9.2 Pages

| Page | File | Purpose |
|------|------|---------|
| Dashboard | `index.html` | Scheduler, last run, Run / Dry-run, job status |
| Roles | `roles.html` | Pipeline table, filters |
| Role detail | `role.html` | Actions + downloads |
| Add role | `add-role.html` | Manual / LinkedIn form |

### 9.3 Dashboard sections

| Section | Content |
|---------|---------|
| Scheduler | Dropdown: Off, 1h, 2h, 4h + Save |
| Last run | Scraper name, count, error from latest `runs/*.json` |
| Actions | Run full cycle, Run dry-run (disabled while busy) |
| Status | Idle / Running since … |
| Optional | Tail last N lines of `agent.log` |

### 9.4 Roles list

- Columns: Rank, Score, Tier, Status, Company, Role (link)
- Filter: All | Drafts only
- Default: hide `Applied` (match CLI `status`)
- Sort by score (default)

### 9.5 Role detail

- Fit summary, apply link (new tab)
- CV / letter ready flags; file exists/missing
- Actions: Tailor, Approve, Package, Mark applied (date)
- Download: CV PDF, letter PDF (when present)

### 9.6 Add role

- Fields: Title, Company, Location, URL, Description (textarea)
- Source: `manual` | `linkedin`
- Submit → `POST /api/roles` → show score / redirect to detail

### 9.7 Frontend stack

- Vanilla `fetch()` in `app.js`
- Single `style.css`
- Poll `GET /api/jobs/current` every 3–5s while a run is active

---

## 10. Scheduler (web-controlled)

### 10.1 Config file

**Path:** `workspace/config/schedule.json`

```json
{
  "enabled": false,
  "interval_hours": 4
}
```

| Field | Values | Meaning |
|-------|--------|---------|
| `enabled` | `true` / `false` | Master switch |
| `interval_hours` | `1`, `2`, `4` | APScheduler interval |

**Default on first install:** `enabled: false` (no surprise scraper/API usage).

When user enables scheduling, seed `interval_hours` from `.env` `SCHEDULE_INTERVAL_HOURS` if present.

### 10.2 Implementation

- `BackgroundScheduler` inside FastAPI lifespan (not blocking terminal scheduler)
- Job: `orchestrator.run(manual=False, dry_run=False)`
- Same **run lock** as `POST /api/run`
- Timezone: `settings.timezone`

### 10.3 Dashboard display

- Next scheduled run time
- Last completed run timestamp (from latest run report or `runs` table)
- Current job status if manual/scheduled run is active

### 10.4 CLI `schedule` (backward compatible)

Refactor `agent/scheduler/job.py` to share `scheduler_manager`:

- **Web:** background scheduler in app lifespan
- **CLI:** optional blocking mode for `python -m agent schedule` without starting the web server

---

## 11. Long-running jobs

`orchestrator.run()` may take **5–30+ minutes**.

### 11.1 Job states

| State | Meaning |
|-------|---------|
| `idle` | No run in progress |
| `running` | Background thread active |
| `error` | Last run failed; message stored |

### 11.2 Concurrency

- One global `threading.Lock`
- `POST /api/run` while busy → **HTTP 409 Conflict**
- Scheduled job skips or waits if lock held (prefer skip + log)

### 11.3 Polling response example

```json
{
  "status": "running",
  "started_at": "2026-05-25T19:41:00+03:00",
  "dry_run": false,
  "error": null
}
```

When finished, include scraper summary from the latest run report.

---

## 12. REST API specification

**Base URL (local):** `http://127.0.0.1:8080/api`

### 12.1 Status and runs

| Method | Path | CLI | Description |
|--------|------|-----|-------------|
| GET | `/status` | `status` | Latest run report + pipeline rows |
| GET | `/status?drafts_only=true` | `status --drafts` | Draft filter |
| GET | `/jobs/current` | — | Job runner state |
| POST | `/run` | `run` | Query/body: `dry_run` boolean |
| GET | `/schedule` | — | Read schedule config + next run |
| PUT | `/schedule` | — | Update `enabled`, `interval_hours` |
| GET | `/logs/tail?lines=200` | — | Optional agent.log tail |

### 12.2 Roles

| Method | Path | CLI |
|--------|------|-----|
| GET | `/roles` | `status` (full list) |
| GET | `/roles/{slug}` | `review` (read) |
| POST | `/roles` | `add-role` / `add-linkedin` |
| POST | `/roles/{slug}/tailor` | `tailor` |
| POST | `/roles/{slug}/approve` | `approve` |
| POST | `/roles/{slug}/package` | `package` |
| POST | `/roles/{slug}/mark-applied` | `mark-applied` |

**POST `/roles` body:**

```json
{
  "title": "ML Engineer",
  "company": "Acme",
  "location": "Cairo",
  "apply_url": "https://example.com/job",
  "description": "Full job description text.",
  "source": "linkedin"
}
```

### 12.3 Files

| Method | Path | Description |
|--------|------|-------------|
| GET | `/files/{slug}/cv.pdf` | Tailored CV PDF |
| GET | `/files/{slug}/letter.pdf` | Cover letter PDF |
| GET | `/files/{slug}/cv.tex` | Optional TeX download |

Resolve paths only under `workspace/cv/tailored` and `workspace/cover_letters`. Reject `..` and unknown slugs.

### 12.4 Other

| Method | Path | CLI |
|--------|------|-----|
| POST | `/sync-master` | `sync-master` |

### 12.5 Role JSON (API response)

```json
{
  "slug": "acme-ml-engineer-wuzzuf",
  "rank": 1,
  "company": "Acme",
  "title": "ML Engineer",
  "location": "Cairo",
  "source": "wuzzuf",
  "score": 78,
  "tier": "strong",
  "role_family": "ml_engineer",
  "fit_summary": "Strong Python and ML match.",
  "apply_url": "https://example.com/apply",
  "cv_ready": true,
  "letter_ready": false,
  "status": "Draft",
  "applied_date": null,
  "first_seen": "2026-05-20T10:00:00Z",
  "last_updated": "2026-05-25T19:41:00Z"
}
```

---

## 13. Security

### 13.1 Local default

| Setting | Value |
|---------|--------|
| `WEB_HOST` | `127.0.0.1` |
| `WEB_PORT` | `8080` |
| `WEB_TOKEN` | empty |

### 13.2 Public exposure

```env
WEB_TOKEN=your-long-random-secret
```

Require on mutating routes and file downloads:

```http
Authorization: Bearer your-long-random-secret
```

### 13.3 Secrets hygiene

| Secret | Where |
|--------|--------|
| `OPENROUTER_API_KEY` | `.env` only |
| `DATABASE_URL` | `.env` only |
| `SUPABASE_PUBLISHABLE_KEY` | `.env` if needed for client |
| Service role key | `.env` only; never in frontend |

OpenRouter and Postgres credentials must **never** be sent to the browser.

---

## 14. Environment variables

Add to `.env` (see `.env.example` when implemented):

```env
# Supabase
DATABASE_URL=postgresql://postgres:[YOUR-PASSWORD]@db.[YOUR-PROJECT-REF].supabase.co:5432/postgres
SUPABASE_URL=https://[YOUR-PROJECT-REF].supabase.co
SUPABASE_PUBLISHABLE_KEY=

# Web
WEB_HOST=127.0.0.1
WEB_PORT=8080
WEB_TOKEN=
```

Existing variables unchanged: `OPENROUTER_*`, `WORKSPACE_DIR`, `TIMEZONE`, `SCHEDULE_INTERVAL_HOURS`, `MIN_SCORE_TO_TAILOR`, `NOTIFY_*`, etc.

---

## 15. Local usage (after build)

### 15.1 Prerequisites

- Python 3.11+
- `pip install -r requirements.txt`
- `python -m playwright install chromium`
- `pdflatex` (optional, for PDFs)
- `.env` with OpenRouter + `DATABASE_URL`

### 15.2 Start

```bash
python -m agent web
```

Open: **http://127.0.0.1:8080**

### 15.3 Typical browser workflow

1. Dashboard → **Dry-run** once (verify scrapers).
2. **Run full cycle** or enable **2h** schedule.
3. **Roles** → open top matches.
4. **Approve** → **Package** → download PDFs.
5. Apply on employer site manually → **Mark applied**.

### 15.4 CLI still works

```bash
python -m agent run --dry-run
python -m agent status --drafts
python -m agent add-linkedin -f workspace/roles/my_role.json
python -m agent export-tracker
```

---

## 16. Deployment

### 16.1 Checklist

- [ ] Always-on process (not ephemeral serverless unless timeouts are acceptable)
- [ ] Persistent disk for `workspace/` (CVs, logs) or object storage later
- [ ] `DATABASE_URL` and `OPENROUTER_API_KEY` on host
- [ ] Playwright + Chromium in container image (Indeed scraper)
- [ ] LaTeX in image or accept `.tex`-only output
- [ ] HTTPS reverse proxy + `WEB_TOKEN` if public

### 16.2 Platform notes

| Platform | Pros | Cons |
|----------|------|------|
| Render | Simple git deploy | Free tier may sleep |
| Railway | Volumes + env | Credit limits |
| Cloud Run | Google ecosystem | Cold start, timeouts |
| Home PC | Full control | You manage security |

### 16.3 Do not

- Deploy as GitHub Pages only
- Commit `.env` or database passwords
- Expose the API without `WEB_TOKEN` on the public internet

---

## 17. Data flows

### 17.1 Automated run

```
Scrapers (Wuzzuf, Bayt, Tanqeeb, Indeed EG)
  → deduplicate (Postgres slugs + applications log)
  → score_listing (OpenRouter)
  → PostgresTracker.upsert_role
  → if score >= MIN_SCORE_TO_TAILOR: CV (+ letter for top/strong)
  → rerank → commit
  → write run report JSON (+ optional runs row)
  → notify (if enabled)
```

### 17.2 Manual add role

```
POST /api/roles → RoleDraft → JobListing
  → score_listing → upsert → tailor if threshold met
  → event log
(no scrapers, no notify)
```

---

## 18. Implementation checklist

| Step | Task | Verify |
|------|------|--------|
| 1 | `supabase/migrations/001_initial.sql` + link project | Tables exist in dashboard |
| 2 | `DATABASE_URL` in `agent/config.py` | Connect from local Python |
| 3 | `PostgresTracker` + `RoleRecord` | `pytest` tracker tests pass |
| 4 | Switch orchestrator, manual_role, main, package_role | Full `run` writes to Postgres |
| 5 | `import-tracker` + `export-tracker` | Round-trip xlsx |
| 6 | `scheduler_manager` + `schedule.json` | UI changes interval without restart |
| 7 | `jobs.py` run lock | Second `POST /run` → 409 |
| 8 | FastAPI routes + file guards | No path traversal |
| 9 | Static HTML/CSS/JS | Full workflow in browser |
| 10 | `python -m agent web` | Dashboard + scheduler work |
| 11 | `tests/test_web.py` + mocked DB | CI green without live Supabase |
| 12 | Update root `README.md` | Link here; mark features as shipped |

**Estimated scope:** ~1,500–2,500 lines (Python + static UI + migrations + tests).

---

## 19. Success criteria

When this plan is fully implemented:

- [ ] Tracker lives in Supabase; CLI and web use Postgres
- [ ] `export-tracker` produces a readable `.xlsx` on demand
- [ ] One command starts web UI; all CLI actions work in the browser
- [ ] Scheduler: Off / 1h / 2h / 4h without editing `.env`
- [ ] Only one agent run at a time (manual + scheduled)
- [ ] Dry-run and full run show live status in the UI
- [ ] Existing CLI commands still work
- [ ] No secrets in the repository
- [ ] Local use works without cloud hosting (DB is remote Supabase; app is local)

---

## 20. Current workaround (until built)

| Need | Command |
|------|---------|
| Auto-run every 4h | `python -m agent schedule` |
| Change interval | Edit `SCHEDULE_INTERVAL_HOURS` in `.env`, restart |
| View tracker | `python -m agent status` |
| Full run | `python -m agent run` |
| Add LinkedIn role | `python -m agent add-linkedin -f workspace/roles/my_role.json` |

Templates: `agent/templates/linkedin_role.json`, `agent/templates/linkedin_role.md`

---

## 21. Document control

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | May 2026 | Initial web UI + scheduler spec |
| 2.0 | May 2026 | Added Supabase Postgres, locked decisions, full package format |

**To implement:** Switch to Agent mode and say *implement NEXT_PLAN.md*.

**Related docs:** [README.md](README.md) (current CLI usage), [george_job_agent_project_prompt.md](george_job_agent_project_prompt.md) (original project prompt).

---

*This document is specification only. No code in this plan has been built unless explicitly noted elsewhere in the repo.*
