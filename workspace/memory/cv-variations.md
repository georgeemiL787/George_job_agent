# CV Variations Archive

Historical ATS-friendly CV PDFs used for past applications and as reference when tailoring new roles. The agent reads this index alongside `cv-notes.md`; files live under `cv_variations/` at the repository root.

**Use when tailoring:** pick the closest existing variant by role family, mirror its emphasis (summary lead, project order, skill block), then generate fresh LaTeX from master facts — do not copy PDF text verbatim.

## Variants

| File | Path | Size | Role focus | When to use |
|------|------|------|------------|-------------|
| `george_emil_aiml_engineer_cv.pdf` | [cv_variations/george_emil_aiml_engineer_cv.pdf](../../cv_variations/george_emil_aiml_engineer_cv.pdf) | ~120 KB | Applied AI / LLM engineer | Nawy-like roles: RAG, LangChain, FastAPI, prompt engineering, agentic workflows |
| `george_emil_cv.pdf` | [cv_variations/george_emil_cv.pdf](../../cv_variations/george_emil_cv.pdf) | ~99 KB | General ATS one-pager | Default balanced AI/ML internship or junior engineer |
| `george_emil_cv-1.pdf` … `george_emil_cv-7.pdf` | [cv_variations/](../../cv_variations/) | ~99 KB each | Role-specific iterations | Match by company/role notes in `cv-notes.md` (e.g. Siemens, Global Brands, Geopro); `-1` … `-7` are successive tailoring passes |
| `George_Emil_Sadek_cv.pdf` | [cv_variations/George_Emil_Sadek_cv.pdf](../../cv_variations/George_Emil_Sadek_cv.pdf) | ~616 KB | Full formal CV | Longer layout; use for roles allowing 2 pages or when more project depth is needed |
| `George Emil cv.pdf` | [cv_variations/George Emil cv.pdf](../../cv_variations/George%20Emil%20cv.pdf) | ~735 KB | Extended portfolio-style | Richest project detail; reference for bullet wording, not default ATS length |

Duplicate: `george_emil_aiml_engineer_cv (1).pdf` is identical to `george_emil_aiml_engineer_cv.pdf` (backup copy).

## Role family → preferred variant

| `role_family` (scorer) | Start from |
|------------------------|------------|
| `ai_engineer` | `george_emil_aiml_engineer_cv.pdf` |
| `ml_engineer` | `george_emil_cv.pdf` or latest `george_emil_cv-N.pdf` |
| `cv_engineer` | `george_emil_cv.pdf` with Cellula-led bullets (see Geopro/Synapse notes in cv-notes) |
| `data_scientist` | `george_emil_cv.pdf` — Python, SQL, Pandas, scikit-learn near top (Banque Misr / LSEG notes) |
| `ai_intern` | `george_emil_cv.pdf` — final-year student line first |
| `adjacent` | `george_emil_cv.pdf` — de-emphasize pure GenAI, stress APIs/Python/Docker |

## Absolute paths (Windows)

For scripts and local tools:

- `d:\George_job_agent\cv_variations\george_emil_aiml_engineer_cv.pdf`
- `d:\George_job_agent\cv_variations\george_emil_cv.pdf`
- `d:\George_job_agent\cv_variations\george_emil_cv-1.pdf` through `george_emil_cv-7.pdf`
- `d:\George_job_agent\cv_variations\George_Emil_Sadek_cv.pdf`
- `d:\George_job_agent\cv_variations\George Emil cv.pdf`

## Agent-generated CVs (runtime)

New tailored CVs are written to `workspace/cv/tailored/<slug>.tex` and `<slug>.pdf` — separate from this archive. After a strong tailor run, consider saving a copy into `cv_variations/` with a descriptive name for future reference.
