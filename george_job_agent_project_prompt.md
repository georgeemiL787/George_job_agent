# George's Local AI Job Search Agent — Full Project Specification

> **Intended reader:** An AI coding assistant (Claude Code, Cursor, etc.) that will implement this project from scratch.  
> Read every section before writing a single line of code. The spec is intentionally complete — follow it precisely.

---

## 1. Project Summary

Build a **local, CLI-first Python agent** that automates the AI/ML job search workflow for George Emil Sadek, a final-year Computer Engineering student in Cairo, Egypt. The agent:

- Searches Egyptian job boards (Wuzzuf, Indeed EG, Jooble EG) for AI/ML/CV/NLP/LLM roles,
- Scores and ranks each role against George's profile,
- Tailors his CV (LaTeX → PDF) to each target role,
- Writes a cover letter (PDF) for each strong match,
- Maintains an Excel tracker workbook,
- Persists state in three Markdown memory files,
- Can be run manually or on a schedule (every 4 hours, Africa/Cairo timezone).

The agent is **local-first**: it runs on George's machine, writes all outputs to `workspace/`, and uses the Anthropic Claude API for all LLM tasks. No cloud deployment is needed.

---

## 2. Technology Stack

| Layer | Choice | Notes |
|---|---|---|
| Language | Python 3.11+ | Type-annotated throughout |
| LLM | `anthropic` SDK — `claude-sonnet-4-20250514` | All prompts go through this |
| Web scraping | `httpx` + `BeautifulSoup4` + `playwright` | Playwright for JS-rendered pages |
| PDF generation | `subprocess` calling `pdflatex` | CV: compile LaTeX; Cover letter: Jinja2 LaTeX template |
| Excel tracker | `openpyxl` | Single workbook, multiple sheets |
| Scheduler | `APScheduler` | Background job, Africa/Cairo tz |
| CLI | `typer` | Commands: `run`, `status`, `tailor`, `schedule` |
| Config | `pydantic-settings` + `.env` | API key, paths |
| Logging | `loguru` | File + console |
| Testing | `pytest` + `pytest-httpx` | Unit + integration stubs |

All dependencies go in `requirements.txt`. Pin versions.

---

## 3. Repository Layout

```
george-job-agent/
├── README.md
├── .env.example
├── requirements.txt
├── pyproject.toml                  # optional, for packaging
│
├── agent/
│   ├── __init__.py
│   ├── main.py                     # Typer CLI entry point
│   ├── config.py                   # Pydantic Settings
│   ├── orchestrator.py             # Top-level run() loop
│   │
│   ├── search/
│   │   ├── __init__.py
│   │   ├── base.py                 # Abstract Scraper
│   │   ├── wuzzuf.py               # Wuzzuf scraper
│   │   ├── indeed_eg.py            # Indeed Egypt scraper
│   │   ├── jooble_eg.py            # Jooble Egypt scraper
│   │   └── deduplicator.py         # Cross-source dedup
│   │
│   ├── scoring/
│   │   ├── __init__.py
│   │   └── scorer.py               # LLM-based role scorer
│   │
│   ├── cv/
│   │   ├── __init__.py
│   │   ├── master_cv.py            # Load / reconcile master CV facts
│   │   ├── tailorer.py             # LLM-based CV tailoring → LaTeX
│   │   ├── renderer.py             # pdflatex compile
│   │   └── templates/
│   │       └── ats_base.tex        # ATS-safe single-column LaTeX template
│   │
│   ├── cover_letter/
│   │   ├── __init__.py
│   │   ├── writer.py               # LLM cover letter writer
│   │   └── templates/
│   │       └── letter_base.tex     # Cover letter LaTeX template
│   │
│   ├── tracker/
│   │   ├── __init__.py
│   │   └── workbook.py             # openpyxl tracker operations
│   │
│   ├── memory/
│   │   ├── __init__.py
│   │   └── store.py                # Read / write the three .md memory files
│   │
│   └── scheduler/
│       ├── __init__.py
│       └── job.py                  # APScheduler setup
│
├── workspace/
│   ├── memory/
│   │   ├── job-search-profile.md   # User profile (seed from section 9 below)
│   │   ├── applications-log.md     # Rolling log of found/applied roles
│   │   └── cv-notes.md             # Reusable CV facts and tailoring notes
│   ├── cv/
│   │   ├── master/
│   │   │   └── george_master.tex   # Reconciled master CV in LaTeX
│   │   └── tailored/               # Per-role tailored CVs: <slug>.tex + .pdf
│   ├── cover_letters/              # Per-role cover letters: <slug>.pdf
│   ├── tracker/
│   │   └── george_emil_job_tracker.xlsx
│   └── logs/
│       └── agent.log
│
└── tests/
    ├── test_scoring.py
    ├── test_dedup.py
    └── test_tracker.py
```

---

## 4. Configuration (`agent/config.py`)

```python
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    anthropic_api_key: str
    workspace_dir: str = "workspace"
    timezone: str = "Africa/Cairo"
    schedule_interval_hours: int = 4
    max_roles_per_run: int = 20
    min_score_to_tailor: int = 60          # 0-100 score threshold
    latex_bin: str = "pdflatex"             # path to pdflatex binary
    log_level: str = "INFO"

    class Config:
        env_file = ".env"
```

`.env.example`:
```
ANTHROPIC_API_KEY=sk-ant-...
WORKSPACE_DIR=workspace
LATEX_BIN=/usr/bin/pdflatex
```

---

## 5. User Profile (seed `workspace/memory/job-search-profile.md` exactly)

```markdown
# Job Search Profile

- Name: George Emil Sadek
- Base location: Cairo, Egypt
- Postal code: 11632
- Current stage: Final-year B.Sc. Computer Engineering student at Benha University, expected graduation June 2026
- Target role priorities:
  - Junior AI Engineer
  - Junior Machine Learning Engineer
  - Computer Vision Engineer
  - Applied AI / LLM Engineer
  - Data Scientist (entry-level only)
  - Relevant internships for AI/ML if strong
- Preferred geography:
  - Egypt first
  - Cairo / Giza / Maadi / New Cairo / 6th of October preferred
  - Remote acceptable when role is strongly relevant
- Strong profile signals:
  - Python, SQL, FastAPI, Flask, Docker, Linux, Git
  - PyTorch, TensorFlow, scikit-learn, OpenCV
  - LLM apps, RAG, prompt engineering, LangChain, LlamaIndex, CrewAI
  - Computer vision internship experience at Cellula Technologies
  - CV, NLP, backend API, and deployment-oriented projects
- Current search bias:
  - Entry-level and fresh-grad roles first
  - Final-year student friendly roles
  - AI/ML/CV/NLP/LLM roles over generic software roles
  - Prefer realistic fit over prestige or seniority stretch
- Document preferences:
  - Cover letters should always be delivered as PDF files
  - CVs should always use an ATS-friendly format
  - Tailored CVs should always be aligned to the target job description using truthful matching keywords
- Tracker preferences:
  - Maintain the reusable tracker workbook at workspace/tracker/george_emil_job_tracker.xlsx
  - Current automatic update cadence: every 4 hours in Africa/Cairo
  - Rank roles by realistic acceptance chance first, then relevance to AI/ML/CV/LLM goals
  - Keep the tracker easy and clean to scan on each refresh
  - Keep visible apply links highlighted in the tracker sheet
```

---

## 6. Master CV Facts (seed `workspace/memory/cv-notes.md`)

Use the following facts as the **ground truth** for all CV generation. Never invent facts beyond these.

### Identity
- **Full name:** George Emil Sadek  
- **Location:** Cairo, Egypt  
- **Email:** (leave placeholder `YOUR_EMAIL@example.com` — user will fill in)  
- **Phone:** (leave placeholder `+20-XXX-XXX-XXXX`)  
- **LinkedIn / GitHub:** (leave placeholders)

### Education
- B.Sc. Computer Engineering, Benha University — expected June 2026
- Strong academic standing (do not invent a GPA unless user provides one)

### Work Experience
**Cellula Technologies — Computer Vision Intern**  
- Worked on real AI/ML pipelines using TensorFlow and PyTorch  
- Projects included: teeth disease classification on medical data, flood mapping with optical data using image segmentation, shoplifting detection using computer vision and surveillance data  
- Demonstrated strong communication, collaboration, initiative, and problem-solving (documented in recommendation letter signed by Amjad Bakri, 2025-10-29)

**Elevvo — (ML/AI-related role; confirm exact title with user)**  
- Broad ML workflow coverage: preprocessing, feature engineering, scaling, documented model evaluation

### Projects
- **Student Helper** — LLM application (relevant for AI/NLP/LLM roles)
- **Flood Rapid Mapping API** — FastAPI + image segmentation deployment
- **Shoplifting Detection System** — computer vision, video understanding, measurable experiments
- **Email Spam Detection** — classification, preprocessing, scikit-learn
- **Supermarket Sales Analysis** — data analytics, Pandas, NumPy
- **Rehab Helper** — AI-assisted tool (relevant for ML engineer / data science roles)

### Technical Skills
- **Languages:** Python, SQL, C++ (basic), Linux shell
- **ML/AI frameworks:** PyTorch, TensorFlow, scikit-learn, OpenCV
- **LLM/AI tooling:** LangChain, LlamaIndex, CrewAI, RAG pipelines, prompt engineering
- **Backend:** FastAPI, Flask, REST APIs
- **DevOps/Tools:** Docker, Git, Linux

### Soft Skills / Leadership
- IEEE student member (leadership and technical communication evidence)
- Able to explain technical work to non-technical audiences

### CV Tailoring Rules (always enforce)
1. **Never invent** degrees, employers, certifications, dates, or skills.
2. **Reorder, reword, and re-emphasize** based on role type (see role angles below).
3. Keep every version **ATS-safe**: single-column, standard headings, no tables, icons, or text boxes.
4. Do not claim multi-year full-time professional experience. Use "hands-on", "built", "developed", "applied".
5. Cover letters always export as PDF.

### Tailoring Angles by Role Type
- **Junior AI Engineer:** Lead with LLM apps, RAG, prompt engineering, FastAPI, Docker, LangChain, LlamaIndex.
- **ML Engineer:** Lead with PyTorch/TensorFlow, deployment APIs, Docker, model evaluation, preprocessing.
- **Computer Vision Engineer:** Lead with Cellula internship, OpenCV, segmentation, video classification, perception work.
- **Data Scientist:** Lead with Python, SQL, Pandas, NumPy, scikit-learn, model evaluation, experimentation.
- **AI Internship:** Emphasize final-year status, rapid learning, internships, practical projects, communication.

---

## 7. Job Search Module (`agent/search/`)

### 7.1 Abstract Scraper (`base.py`)

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional
import datetime

@dataclass
class JobListing:
    title: str
    company: str
    location: str
    source: str                        # "wuzzuf" | "indeed_eg" | "jooble_eg"
    apply_url: str
    description: str = ""
    posted_date: Optional[str] = None
    raw_html: str = ""
    slug: str = ""                     # auto-generated: company-title-source, lowercased, hyphened
    fetched_at: str = field(default_factory=lambda: datetime.datetime.utcnow().isoformat())

class BaseScraper(ABC):
    @abstractmethod
    def search(self, queries: list[str], max_results: int = 20) -> list[JobListing]:
        ...
```

### 7.2 Wuzzuf Scraper (`wuzzuf.py`)

- Target base URL: `https://wuzzuf.net/search/jobs/`
- Query parameters: `q={query}&a=hpb`
- Use `httpx` with realistic browser headers (User-Agent: Chrome 124).
- Parse with `BeautifulSoup4`.
- Extract: job title, company, location, "time ago" post date, apply link (`/jobs/{slug}`), short description snippet.
- For each listing, optionally fetch the detail page to get full description (rate-limit: 1 req/sec, randomise ±0.3s).
- Return a `list[JobListing]`.
- Handle pagination up to 3 pages per query.
- Implement exponential back-off (3 retries) on 429/5xx.

### 7.3 Indeed Egypt Scraper (`indeed_eg.py`)

- Target: `https://eg.indeed.com/jobs?q={query}&l=Cairo%2C+Egypt`
- Use `playwright` (headless Chromium) because Indeed renders via JS.
- After page load, wait for `.jobsearch-ResultsList` selector.
- Extract each job card: title, company, location, summary, apply href.
- Fetch the full job detail page for each listing to get complete description.
- Same rate-limit and retry rules as Wuzzuf.

### 7.4 Jooble Egypt Scraper (`jooble_eg.py`)

- Target: `https://jooble.org/jobs-{query-slug}/Egypt`
- `httpx` + `BeautifulSoup4`.
- Parse job cards for title, company, location, snippet, apply URL.
- Pagination: up to 2 pages per query.

### 7.5 Search Queries

Always run these queries across all three sources every refresh:

```python
SEARCH_QUERIES = [
    "AI engineer Cairo",
    "machine learning engineer Cairo",
    "computer vision engineer Cairo",
    "NLP engineer Cairo",
    "LLM engineer Cairo",
    "data scientist junior Cairo",
    "AI intern Cairo",
    "ML intern Egypt",
    "junior AI developer Egypt",
    "applied AI engineer Cairo",
]
```

### 7.6 Deduplicator (`deduplicator.py`)

After collecting all listings from all sources:
- Normalize title + company: lowercase, strip punctuation.
- Mark duplicate if `(normalized_title, normalized_company)` pair already seen in this run **or** already exists in `applications-log.md`.
- Keep the listing from the most preferred source (Wuzzuf > Indeed > Jooble).
- Return only unique, fresh listings.

---

## 8. Scoring Module (`agent/scoring/scorer.py`)

Use the Claude API to score each deduplicated listing against George's profile.

### Input to LLM

```
System:
You are a job-fit evaluator. Given a job description and a candidate profile, return a JSON object with these fields:
- score: integer 0-100 (realistic acceptance probability from the candidate's perspective, not pure skill match)
- tier: "top" | "strong" | "medium" | "stretch" | "skip"
- fit_summary: 2-sentence plain English summary of why this role fits or doesn't
- key_matches: list of up to 5 specific matching skills/keywords from the JD
- gaps: list of up to 3 honest gaps or concerns
- role_family: "ai_engineer" | "ml_engineer" | "cv_engineer" | "data_scientist" | "ai_intern" | "adjacent" | "irrelevant"
Return ONLY valid JSON. No preamble or markdown fences.

User:
CANDIDATE PROFILE:
<paste full job-search-profile.md content here>

JOB TITLE: {title}
COMPANY: {company}
LOCATION: {location}
JOB DESCRIPTION:
{description}
```

### Scoring Rules (enforce in system prompt)

- Heavily reward: student-friendly / fresh-grad wording, 0–2 years experience requirements, Cairo/Giza location, direct AI/ML/CV/NLP/LLM stack overlap.
- Penalise: implicit or explicit 3+ year full-time requirements, vague "senior" language, non-AI-adjacent titles, roles outside Egypt without a clear remote arrangement.
- `skip` tier if: generic software role with no AI component, outside Egypt with no remote stated, clearly requires 5+ years.

### Post-scoring filter

- Drop all `skip` tier roles.
- Sort remaining by `score` descending.
- Cap at `max_roles_per_run` (default 20).

---

## 9. CV Tailoring Module (`agent/cv/`)

### 9.1 LaTeX Base Template (`templates/ats_base.tex`)

Implement a **single-column ATS-safe LaTeX CV template** with these sections in order:

1. `\section*{Summary}` — 2–3 sentence professional summary
2. `\section*{Skills}` — flat keyword list, no icons
3. `\section*{Experience}` — reverse chronological, company / title / dates / bullet points
4. `\section*{Projects}` — project name / short description / tech stack bullets
5. `\section*{Education}` — degree / university / expected graduation
6. `\section*{Highlights}` — optional: IEEE, certifications, recommendation letter note

Rules for the template:
- No `multicol`, no `tabularx` for layout, no `fontawesome`, no colored boxes.
- Use `\documentclass[11pt,a4paper]{article}` with `geometry`, `hyperref`, `enumitem`, `parskip`.
- Monochrome only (black text on white).
- Section headers: simple `\hrule` under `\section*{}`.
- Bullets: `\begin{itemize}[leftmargin=*, nosep]`.

### 9.2 Tailorer (`tailorer.py`)

For each role that scores `>= min_score_to_tailor`:

1. Load master CV facts from `workspace/memory/cv-notes.md`.
2. Load the target `JobListing`.
3. Call Claude API with this prompt:

```
System:
You are an expert CV writer. Your task is to produce a tailored LaTeX CV for the given role.
Rules:
- Use ONLY the facts listed in the MASTER FACTS section. Do not invent any new employers, degrees, certifications, dates, or skills.
- Reorder sections and rewrite bullet points to emphasize the most relevant experience for this specific role.
- Pull the most important truthful keywords from the JOB DESCRIPTION and use them naturally in bullets.
- Keep the CV ATS-safe: single column, standard section headings, no icons, no tables, no graphics.
- Output ONLY the complete compilable LaTeX source. No explanation, no markdown fences.
- The CV must fit on one page (use \vspace{} and font size adjustments if needed).
- Tailor the summary to address the specific role title and company.

User:
MASTER FACTS:
{full content of cv-notes.md}

TARGET ROLE:
Title: {title}
Company: {company}
Location: {location}
Role Family: {role_family from scorer}
Key JD Keywords: {key_matches from scorer}

JOB DESCRIPTION:
{description}

BASE LATEX TEMPLATE (adapt this structure):
{content of ats_base.tex}

Produce the tailored LaTeX CV now.
```

4. Save output to `workspace/cv/tailored/{slug}.tex`.
5. Compile to PDF (see renderer).

### 9.3 Renderer (`renderer.py`)

```python
import subprocess, shutil, pathlib

def compile_latex(tex_path: pathlib.Path, output_dir: pathlib.Path) -> pathlib.Path:
    """Run pdflatex twice (for cross-references), return path to compiled PDF."""
    for _ in range(2):
        result = subprocess.run(
            ["pdflatex", "-interaction=nonstopmode", "-output-directory", str(output_dir), str(tex_path)],
            capture_output=True, text=True, timeout=60
        )
        if result.returncode != 0:
            raise RuntimeError(f"pdflatex failed:\n{result.stdout}\n{result.stderr}")
    pdf_path = output_dir / tex_path.with_suffix(".pdf").name
    return pdf_path
```

If `pdflatex` is not installed, log a clear warning and skip PDF compilation (keep `.tex` file).

---

## 10. Cover Letter Module (`agent/cover_letter/`)

### 10.1 Template (`templates/letter_base.tex`)

Standard professional letter in LaTeX:
- Sender block (top right): name, email, phone, city, date
- Recipient block: Hiring Manager, Company, Location
- Subject line: `Re: {Job Title} — {Company}`
- Body: 3 paragraphs (intro + fit, experience highlights, closing ask)
- Closing: "Sincerely, George Emil Sadek"

### 10.2 Writer (`writer.py`)

For each role that is tier `top` or `strong`:

1. Call Claude API:

```
System:
You are a professional cover letter writer for job applications in the AI/ML field.
Rules:
- Write a 3-paragraph cover letter (under 320 words total).
- Paragraph 1: Express genuine interest in the specific role and company. Mention the role title explicitly.
- Paragraph 2: Draw on 2–3 specific truthful highlights from the candidate's background that directly address the JD requirements.
- Paragraph 3: Close with a confident but not arrogant ask for an interview.
- Use professional but natural tone. No clichés ("I am writing to apply...").
- Do NOT invent qualifications. Use only facts from MASTER FACTS.
- Output ONLY the complete LaTeX letter source using the provided template. No markdown.

User:
MASTER FACTS:
{cv-notes.md}

TARGET ROLE:
Title: {title}
Company: {company}
Location: {location}
Key JD Requirements: {key_matches}
Fit Summary: {fit_summary from scorer}

LETTER TEMPLATE:
{letter_base.tex}
```

2. Save to `workspace/cover_letters/{slug}_letter.tex`.
3. Compile with `pdflatex` → `workspace/cover_letters/{slug}_letter.pdf`.

---

## 11. Tracker Module (`agent/tracker/workbook.py`)

Maintain **one persistent workbook** at `workspace/tracker/george_emil_job_tracker.xlsx`.

### Sheet 1: `Pipeline` (main view)

Columns (in order):

| Col | Header | Notes |
|---|---|---|
| A | Rank | Integer, recalculated each refresh |
| B | Company | Text |
| C | Role Title | Text |
| D | Location | Text |
| E | Source | wuzzuf / indeed / jooble |
| F | Score | 0–100 integer |
| G | Tier | top / strong / medium / stretch |
| H | Role Family | ai_engineer etc. |
| I | Fit Summary | 2-sentence string |
| J | **Apply Link** | Hyperlink, highlighted yellow (`FFFF00`) if status is "Not Applied" |
| K | CV Ready | Yes / No |
| L | Cover Letter Ready | Yes / No |
| M | Status | Not Applied / Applied / Interview / Rejected / Offer |
| N | Applied Date | ISO date string or blank |
| O | Notes | Free text |
| P | First Seen | ISO datetime |
| Q | Last Updated | ISO datetime |

Formatting rules:
- Row 1: header row, bold, dark blue fill (`1F3864`), white text.
- Freeze row 1 and column A (`openpyxl.worksheet.views.SheetView`).
- Alternating row fill: white / very light blue (`EAF0FB`).
- Column J (Apply Link): highlight cell in yellow if `Status == "Not Applied"`; use `openpyxl` `Hyperlink` for the URL.
- Auto-filter on all columns.
- Column widths: set sensible fixed widths (A:5, B:22, C:30, D:16, E:9, F:7, G:9, H:14, I:50, J:35, K:10, L:14, M:14, N:13, O:40, P:20, Q:20).

### Sheet 2: `Applied` (archive)

Same columns as Pipeline. Rows are **moved here** (deleted from Pipeline) when status changes to `Applied`, `Interview`, `Rejected`, or `Offer`.

### Sheet 3: `Log`

| Col | Header |
|---|---|
| A | Timestamp |
| B | Event |
| C | Detail |

Append a row for every agent action: new role found, role scored, CV tailored, cover letter generated, status change.

### Workbook Operations

```python
class TrackerWorkbook:
    def load_or_create(self) -> None: ...
    def upsert_role(self, listing: JobListing, score_result: dict) -> None: ...
    def mark_applied(self, slug: str, applied_date: str) -> None: ...
    def mark_cv_ready(self, slug: str) -> None: ...
    def mark_letter_ready(self, slug: str) -> None: ...
    def get_all_slugs(self) -> set[str]: ...          # used by deduplicator
    def append_log(self, event: str, detail: str) -> None: ...
    def save(self) -> None: ...
```

**Do not delete or overwrite existing rows when refreshing** — only add new ones and update `Last Updated`.

---

## 12. Memory Module (`agent/memory/store.py`)

The three Markdown files in `workspace/memory/` are the agent's persistent state. Read them at startup; append to `applications-log.md` after each run.

```python
class MemoryStore:
    def load_profile(self) -> str: ...               # returns raw text of job-search-profile.md
    def load_cv_notes(self) -> str: ...              # returns raw text of cv-notes.md
    def load_applications_log(self) -> str: ...      # returns raw text of applications-log.md

    def append_run_summary(self, summary: str) -> None:
        """Append a new dated section to applications-log.md."""
        ...

    def append_cv_note(self, note: str) -> None:
        """Append a note to cv-notes.md (tailoring patterns, etc.)."""
        ...
```

Format appended sections as:

```markdown
## {YYYY-MM-DD HH:MM} Africa/Cairo

{summary text}
```

---

## 13. Orchestrator (`agent/orchestrator.py`)

This is the main run loop. Called by the CLI and the scheduler.

```python
async def run(manual: bool = False) -> None:
    log.info("Agent run starting")
    settings = get_settings()
    memory = MemoryStore(settings)
    tracker = TrackerWorkbook(settings)

    # 1. Search all sources
    all_listings = await search_all_sources(SEARCH_QUERIES)

    # 2. Deduplicate (against tracker slugs + memory)
    known_slugs = tracker.get_all_slugs()
    fresh = deduplicate(all_listings, known_slugs)
    log.info(f"{len(fresh)} fresh listings after dedup")

    # 3. Score each listing
    scored = []
    for listing in fresh:
        result = await score_listing(listing, memory.load_profile())
        if result["tier"] != "skip":
            listing.slug = make_slug(listing)
            scored.append((listing, result))

    # 4. Sort by score descending, cap at max_roles_per_run
    scored.sort(key=lambda x: x[1]["score"], reverse=True)
    scored = scored[:settings.max_roles_per_run]

    # 5. Upsert all into tracker
    for listing, result in scored:
        tracker.upsert_role(listing, result)

    # 6. Tailor CV and cover letter for roles above threshold
    for listing, result in scored:
        if result["score"] >= settings.min_score_to_tailor:
            await tailor_cv(listing, result, memory.load_cv_notes())
            tracker.mark_cv_ready(listing.slug)

        if result["tier"] in ("top", "strong"):
            await write_cover_letter(listing, result, memory.load_cv_notes())
            tracker.mark_letter_ready(listing.slug)

    # 7. Save tracker
    tracker.save()

    # 8. Write run summary to memory
    summary = build_run_summary(scored)
    memory.append_run_summary(summary)

    log.info("Agent run complete")
```

`build_run_summary()` should produce a Markdown block listing: total found, top roles with one-line fit note, CVs tailored, cover letters written.

---

## 14. CLI (`agent/main.py`)

Use `typer`:

```
python -m agent run                   # one-shot run
python -m agent run --dry-run         # search + score, no files written
python -m agent status                # print latest tracker summary to terminal
python -m agent tailor <slug>         # force-tailor CV for one specific role slug
python -m agent schedule              # start APScheduler background loop
python -m agent add-role              # interactive prompt to manually add a role
```

`add-role` workflow:
1. Prompt: paste job title, company, location, apply URL, and job description.
2. Score it with the LLM.
3. Tailor CV + cover letter if score >= threshold.
4. Add to tracker.

---

## 15. Scheduler (`agent/scheduler/job.py`)

```python
from apscheduler.schedulers.blocking import BlockingScheduler
import pytz

def start_scheduler():
    scheduler = BlockingScheduler(timezone=pytz.timezone("Africa/Cairo"))
    scheduler.add_job(
        func=run_sync,                        # sync wrapper around orchestrator.run()
        trigger="interval",
        hours=4,
        id="job_search_refresh",
        replace_existing=True,
    )
    scheduler.start()
```

Log a message at each scheduled run start and end.

---

## 16. Slug Generation

```python
import re

def make_slug(listing: JobListing) -> str:
    raw = f"{listing.company}-{listing.title}-{listing.source}"
    slug = raw.lower()
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    slug = slug.strip("-")[:80]
    return slug
```

Slugs are used as filenames for tailored CVs, cover letters, and tracker row identifiers.

---

## 17. Error Handling & Resilience

- Every scraper must handle `httpx.TimeoutException`, `httpx.HTTPStatusError`, and empty result pages gracefully — log warning and continue.
- Every LLM call must be wrapped in `try/except` with a fallback that logs the error and skips that listing (never crash the whole run).
- `pdflatex` failures must be caught; keep the `.tex` file even if PDF fails; log clearly.
- All LLM JSON responses must be parsed with `try/except json.JSONDecodeError`; if parse fails, retry once with a stricter prompt.
- Network errors during scraping must not prevent the tracker from being saved.

---

## 18. Logging

Use `loguru`. Configure on startup:

```python
from loguru import logger
logger.add("workspace/logs/agent.log", rotation="10 MB", retention="30 days", level=settings.log_level)
```

Log level `INFO` for normal operations, `DEBUG` for LLM prompt/response details, `WARNING` for recoverable failures, `ERROR` for unrecoverable ones.

---

## 19. Tests

Write at minimum:

- `test_scoring.py`: mock Claude API response, assert `score` and `tier` are parsed correctly.
- `test_dedup.py`: provide a list of listings with duplicates across sources, assert only unique ones remain.
- `test_tracker.py`: create a fresh workbook, upsert 3 roles, assert rows and formatting are correct, assert slug lookup works.

Use `pytest-httpx` to mock external HTTP calls in scraper tests.

---

## 20. README

Write a clear `README.md` covering:

1. Prerequisites (Python 3.11+, pdflatex / TeX Live, Playwright Chromium)
2. Installation steps (`pip install -r requirements.txt`, `playwright install chromium`)
3. `.env` setup
4. First run (seed the `workspace/memory/` files from this spec)
5. CLI command reference
6. How to add a role manually
7. How to start the scheduler
8. Tracker file location and how to open it

---

## 21. Implementation Order

Build in this order to stay unblocked:

1. `config.py` + `memory/store.py` — foundation
2. Seed all three `workspace/memory/*.md` files from this spec
3. `tracker/workbook.py` — so the run loop has somewhere to write
4. `search/wuzzuf.py` — primary source, test manually
5. `search/indeed_eg.py` + `search/jooble_eg.py`
6. `search/deduplicator.py`
7. `scoring/scorer.py`
8. `orchestrator.py` (stub CV/letter steps first, just score + track)
9. `cv/tailorer.py` + `cv/renderer.py` + LaTeX template
10. `cover_letter/writer.py` + letter template
11. `main.py` CLI
12. `scheduler/job.py`
13. Tests
14. README

---

## 22. Absolute Constraints (never violate)

- **Never fabricate** CV facts, application status, or qualifications.
- **Never claim an application was submitted** unless `mark_applied()` is called by the user via CLI.
- **Never overwrite** rows in the tracker that have `Status != "Not Applied"` — archive them instead.
- **Never delete** `workspace/memory/*.md` files or the tracker workbook.
- **ATS-safe only** — no decorative LaTeX in CVs.
- **Cover letters as PDF** — always compile to PDF, never deliver only `.tex`.
- **Truthful tailoring only** — keywords used in the CV must be backed by real experience in `cv-notes.md`.
```
