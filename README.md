# George's Local AI Job Search Agent

A local Python CLI agent that automates the AI/ML job search workflow for George Emil Sadek. Searches Egyptian job boards, scores roles against the candidate profile, tailors a unique ATS-optimized CV for every strong match, writes a professional cover letter, and tracks everything in Excel.

---

## Prerequisites

- Python 3.11 or later
- TeX Live or MiKTeX (for PDF compilation). Without this, CVs are saved as .tex only.
- Playwright Chromium (for Indeed Egypt scraper)

Check Python version:
```
python --version
```

Check pdflatex:
```
pdflatex --version
```

---

## Installation

1. Clone or copy this directory to your machine.

2. Install Python dependencies:
```
python -m pip install -r requirements.txt
```

3. Install Playwright Chromium browser:
```
python -m playwright install chromium
```

4. Copy the example env file and fill in your API key:
```
copy .env.example .env
```

---

## .env Setup

Edit `.env`:
```
OPENROUTER_API_KEY=sk-or-v1-your-key-here
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1
SCORING_MODEL=nvidia/nemotron-3-super-120b-a12b:free
CV_MODEL=nvidia/nemotron-3-super-120b-a12b:free
LETTER_MODEL=nvidia/nemotron-3-super-120b-a12b:free
FALLBACK_MODEL=openai/gpt-oss-120b:free
WORKSPACE_DIR=workspace
CV_VARIATIONS_DIR=cv_variations
LATEX_BIN=pdflatex
LOG_LEVEL=INFO
MIN_SCORE_TO_TAILOR=60
NOTIFY_ENABLED=false
```

Copy from `.env.example`. For production runs, prefer stable (often paid) models for `CV_MODEL` and `LETTER_MODEL` to reduce LaTeX/JSON failures.

The OpenRouter API key is free to obtain at https://openrouter.ai

---

## First Run

The workspace memory files are pre-seeded from your existing profile. Run a dry-run first to verify everything works:
```
python -m agent run --dry-run
```

This searches all sources and scores roles, but does not write any files or tailor CVs. Review the terminal output.

Then run the full cycle:
```
python -m agent run
```

---

## CLI Reference

| Command | Description |
|---|---|
| `python -m agent run` | Full search, score, tailor, track cycle |
| `python -m agent run --dry-run` | Score only, nothing written to disk |
| `python -m agent status` | Print top open roles from tracker |
| `python -m agent tailor <slug>` | Force-tailor CV for one role by its slug |
| `python -m agent add-role` | Add a role (interactive, file, or flags) |
| `python -m agent add-linkedin` | Same; defaults source to LinkedIn |
| `python -m agent review <slug>` | Review artifacts; optionally approve |
| `python -m agent approve <slug>` | Mark role Ready for apply |
| `python -m agent package <slug>` | Bundle CV/letter PDFs for one role |
| `python -m agent sync-master` | Regenerate `workspace/cv/master/george_master.tex` stub |
| `python -m agent mark-applied <slug>` | Mark a role as applied in tracker |
| `python -m agent schedule` | Start the 4-hour background scheduler |
| `python -m agent status --drafts` | Show Draft roles awaiting review |

---

## Adding a LinkedIn Role (recommended)

LinkedIn has no public job-search API and blocks automated scraping. Use **manual capture** — the agent scores, tailors, and tracks the role like any board listing.

### Option A — interactive

```
python -m agent add-linkedin
```

Paste title, company, location, LinkedIn job URL, and the full JD (blank line to finish).

### Option B — JSON or Markdown file

Copy a template, fill it in, then run:

```
copy agent\templates\linkedin_role.json workspace\roles\my_role.json
python -m agent add-linkedin --file workspace\roles\my_role.json
```

Templates: `agent/templates/linkedin_role.json` and `agent/templates/linkedin_role.md`.

### Option C — CLI flags

```
python -m agent add-linkedin --title "AI Engineer" --company "Acme" --location "Cairo" ^
  --url "https://www.linkedin.com/jobs/view/123" --description-file jd.txt
```

The tracker source is `linkedin` when the URL is on linkedin.com; otherwise `manual`. Roles are logged in `workspace/memory/applications-log.md`.

---

## Starting the Scheduler

The scheduler runs a full cycle every 4 hours in Africa/Cairo timezone:
```
python -m agent schedule
```

It runs once immediately on startup, then every 4 hours. Press Ctrl+C to stop.

---

## Tracker File

The Excel tracker is saved at:
```
workspace/tracker/george_emil_job_tracker.xlsx
```

Open it in Excel or LibreOffice. Three sheets:
- **Pipeline** - all open roles, ranked by score, yellow apply links
- **Applied** - archived after you confirm application
- **Log** - every agent action timestamped

---

## Output Files

| Path | Contents |
|---|---|
| `workspace/cv/tailored/<slug>.tex` | Tailored LaTeX CV for one role |
| `workspace/cv/tailored/<slug>.pdf` | Compiled PDF (if pdflatex installed) |
| `workspace/cover_letters/<slug>_letter.tex` | Cover letter LaTeX |
| `workspace/cover_letters/<slug>_letter.pdf` | Cover letter PDF |
| `workspace/tracker/george_emil_job_tracker.xlsx` | Excel tracker |
| `workspace/logs/agent.log` | Full agent log |
| `workspace/memory/cv-facts.md` | Core CV facts (sent to LLM) |
| `workspace/memory/cv-role-playbook.md` | Company/role tailoring notes |
| `workspace/memory/tracker-priorities.md` | Tracker ordering journal (not sent to LLM) |
| `workspace/memory/cv-variations.md` | PDF archive index |
| `workspace/logs/runs/*.json` | Structured per-run reports |
| `workspace/packages/<slug>/` | Apply bundles from `package` command |
| `cv_variations/*.pdf` | Historical tailored CV PDFs (reference archive) |

**Deprecated:** root-level `cv-notes.md` and `job-search-profile.md` — edit `workspace/memory/` only.

New tailored outputs start as **Draft** in the tracker until you run `review` or `approve`.

---

## Running Tests

```
python -m pytest tests/ -v
```

---

## Job Sources

| Source | Method | Notes |
|---|---|---|
| Wuzzuf | httpx + BeautifulSoup4 | Primary Egypt source |
| Bayt | httpx + BeautifulSoup4 | Strong Egypt/MENA coverage |
| Tanqeeb | httpx + BeautifulSoup4 | Egypt-focused board |
| Indeed Egypt | Playwright (headless) | Requires playwright install |
| LinkedIn | `add-linkedin` / `add-role --file` | Manual capture (no scraping) |

---

## CV Tailoring Strategy

A new CV is generated for every role that scores 60 or above. The LLM:

1. Extracts the top 8 keywords and requirements from the job description
2. Rewrites the Summary section for this exact role and company
3. Reorders sections based on role type (CV-first for vision roles, LLM tooling first for AI engineer roles)
4. Injects the JD keywords naturally into bullet points where truthfully supported
5. Includes all relevant quantifiable results from the master facts
6. Ensures single-column ATS-safe output with no icons or tables

The master CV at `workspace/cv/master/george_master.tex` is never submitted directly.

---

## Absolute Rules

- The agent never invents qualifications, employers, or metrics
- An application is only marked applied when you confirm it with `mark-applied`
- Existing applied/interviewed rows in the tracker are never overwritten
- Cover letters are always compiled to PDF
