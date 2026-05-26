# George Job Agent Desktop

Native Windows desktop app and CLI for George Emil Sadek's AI/ML job search workflow.

The app searches Egyptian job boards, scores roles against George's profile, tailors ATS-friendly CVs and cover letters, tracks roles locally in SQLite, and exports Excel workbooks when needed. It is local-first: no website deployment and no public dashboard.

## Prerequisites

- Windows 10/11
- Python 3.11 or later for source runs
- Playwright Chromium for Bayt, GulfTalent, and Indeed (deep runs)
- TeX Live or MiKTeX is optional. Without `pdflatex`, the app saves `.tex` artifacts only.

## Install For Source Runs

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m playwright install chromium
copy .env.example .env
```

Start the desktop app:

```powershell
.\.venv\Scripts\python.exe -m agent desktop
```

## Run modes

| Mode | Sources | Indeed | Playwright scrapers |
|------|---------|--------|---------------------|
| **Fast** (default) | Wuzzuf, LinkedIn, enabled httpx sources | Off | Skipped when `SKIP_SLOW_SOURCES=true` |
| **Deep** | All enabled + Indeed | On | Bayt, GulfTalent, Indeed |

- **Fast run** / **Deep run** buttons on the Dashboard
- **Stop Run** cancels cooperatively between scrapers, scores, and artifacts
- Live progress: `Collected | Fresh | Scored | Tailored | Failed`
- Run reports: `workspace/logs/runs/latest.json` (updated each phase)

## Local Config

See [`.env.example`](.env.example) for all options. Key settings:

```env
ENABLED_SOURCES=wuzzuf,linkedin,bayt
SKIP_SLOW_SOURCES=true
ENABLE_INDEED=false
SCORING_MODEL_FAST=
MAX_SCORING_CANDIDATES=30
PERSIST_DRY_RUN_SCORES=true
```

`linkedin` in `ENABLED_SOURCES` maps to the `linkedin_jobs` scraper internally.

Source toggles in the desktop UI can be saved to `workspace/config/run_sources.json`.

## Repository layout

| Path | Purpose |
|------|---------|
| `agent/` | Application code (orchestrator, scrapers, desktop, tracker) |
| `agent/desktop/assets/` | App icon (`app.ico`, `app.png`) |
| `workspace/memory/` | Seeded profile/CV facts (bundled in EXE) |
| `workspace/tracker/` | SQLite DB + optional Excel seed workbook |
| `cv_variations/` | Canonical CV PDF archive for tailoring context |
| `tests/` | Pytest suite |
| `packaging/` | PyInstaller spec |
| `scripts/` | `build_desktop.ps1`, `clean_local.ps1` |

Runtime outputs (gitignored): `workspace/logs/`, `workspace/cv/tailored/`, `build/`, `dist/`.

## Desktop Screens

- **Dashboard**: Fast/Deep/Dry runs, source toggles, live progress, scraper health, scheduler
- **Roles**: Pipeline table with scoring/artifact status; retry failed scores
- **Role Detail**: Fit summary, failures, tailor/approve/package
- **Run**: Live phase stepper, activity feed, scraper status, and ETA while a run is active
- **Settings**: Workspace paths, resolved config, setup wizard

## CLI Reference

| Command | Description |
|---|---|
| `python -m agent desktop` | Start the desktop app |
| `python -m agent run` | Full cycle (fast by default) |
| `python -m agent run --deep` | Deep cycle (Indeed + slow scrapers) |
| `python -m agent run --dry-run` | Score only |
| `python -m agent status` | Top roles + active run progress if running |
| `python -m agent scrape-health` | Quick card collect per source |
| `python -m agent schedule` | CLI scheduler (terminal must stay open) |

## Build The Windows App

```powershell
.\scripts\build_desktop.ps1 -Clean
```

Output: `dist\GeorgeJobAgent\GeorgeJobAgent.exe`

## Tests

```powershell
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m pytest tests/ -q
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for cleanup and commit guidelines.

## Rules

- The app never invents qualifications, employers, or metrics.
- Applications are marked applied only when you confirm them.
- Existing applied/interviewed rows are not overwritten.
- Keep `.env` private; rotate any exposed OpenRouter key.
