# George Job Agent Desktop

Native Windows desktop app and CLI for George Emil Sadek's AI/ML job search workflow.

The app searches Egyptian job boards, scores roles against George's profile, tailors ATS-friendly CVs and cover letters, tracks roles locally in SQLite, and exports Excel workbooks when needed. It is local-first: no website deployment, no Supabase requirement, and no public dashboard.

## Prerequisites

- Windows 10/11
- Python 3.11 or later for source runs
- Playwright Chromium for the Indeed scraper
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

The first-run setup wizard can write `.env`, initialize SQLite, verify Playwright, and check optional LaTeX support.

## Local Config

Default local settings:

```env
OPENROUTER_API_KEY=your-openrouter-api-key-here
WORKSPACE_DIR=workspace
DATABASE_URL=sqlite:///workspace/tracker/job_agent.db
CV_VARIATIONS_DIR=cv_variations
LATEX_BIN=pdflatex
SCHEDULE_INTERVAL_HOURS=4
MAX_ROLES_PER_RUN=20
MIN_SCORE_TO_TAILOR=60
```

The tracker database is local SQLite. The existing workbook at `workspace/tracker/george_emil_job_tracker.xlsx` is imported once when the database is empty, and Excel export remains available from the app and CLI.

## Desktop Screens

- Dashboard: run full/dry cycles, see scraper health, top roles, and schedule status.
- Roles: browse, filter, import/export Excel, and open role details.
- Role Detail: tailor CV, approve, package, mark applied, and open artifact folders.
- Add Role: paste a LinkedIn/manual role and process it through scoring/tailoring.
- Run Monitor: view local logs.
- Settings: run setup checks, open workspace, and sync the master CV stub.

The scheduler runs only while the desktop app is open. Use Off / 1h / 2h / 4h from the Dashboard.

## CLI Reference

| Command | Description |
|---|---|
| `python -m agent desktop` | Start the native Windows desktop app |
| `python -m agent run` | Full search, score, tailor, track cycle |
| `python -m agent run --dry-run` | Score only, nothing written to disk |
| `python -m agent status` | Print top open roles and latest scraper health |
| `python -m agent add-role` | Add a role interactively, from file, or flags |
| `python -m agent add-linkedin` | Same, defaulting source to LinkedIn |
| `python -m agent tailor <slug>` | Force-tailor CV for one tracked role |
| `python -m agent review <slug>` | Review artifacts and optionally approve |
| `python -m agent approve <slug>` | Mark role Ready |
| `python -m agent package <slug>` | Bundle role artifacts |
| `python -m agent mark-applied <slug>` | Mark role applied |
| `python -m agent import-tracker` | Import Excel tracker into SQLite |
| `python -m agent export-tracker` | Export SQLite tracker to Excel |
| `python -m agent schedule` | Start CLI scheduler while terminal is open |

## Build The Windows App

```powershell
.\scripts\build_desktop.ps1 -Clean
```

Build output:

```text
dist\GeorgeJobAgent\GeorgeJobAgent.exe
```

The PyInstaller build includes app code, templates, workspace memory files, tracker workbook, role templates, and CV variation PDFs.

## Output Files

| Path | Contents |
|---|---|
| `workspace/tracker/job_agent.db` | Local SQLite tracker database |
| `workspace/tracker/george_emil_job_tracker.xlsx` | Excel import/export workbook |
| `workspace/cv/tailored/<slug>.tex` | Tailored LaTeX CV |
| `workspace/cv/tailored/<slug>.pdf` | Optional compiled PDF |
| `workspace/cover_letters/<slug>_letter.tex` | Cover letter LaTeX |
| `workspace/cover_letters/<slug>_letter.pdf` | Optional compiled PDF |
| `workspace/logs/agent.log` | App/agent log |
| `workspace/logs/runs/*.json` | Structured run reports |
| `workspace/packages/<slug>/` | Application package folder |

## Tests

```powershell
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m pytest tests/ -v
.\.venv\Scripts\python.exe -m pip check
```

## Rules

- The app never invents qualifications, employers, or metrics.
- Applications are marked applied only when you confirm them.
- Existing applied/interviewed rows are not overwritten.
- `.tex` artifacts are valid output when `pdflatex` is unavailable.
- Keep `.env` private; rotate any previously exposed OpenRouter key.
