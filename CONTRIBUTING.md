# Contributing

## Setup

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m playwright install chromium
copy .env.example .env
```

## Checks before a PR

```powershell
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m pytest tests/ -q
.\.venv\Scripts\python.exe -m pip check
```

## Do not commit

- `.env` or API keys
- `build/`, `dist/`, `__pycache__/`, `.pytest_cache/`
- `workspace/logs/`, `workspace/tracker/*.db`, tailored CVs/letters from local runs
- Duplicate CV PDFs in `cv_variations/` (keep one canonical archive)

## Clean local artifacts

```powershell
.\scripts\clean_local.ps1
.\scripts\clean_local.ps1 -IncludeWorkspaceOutputs
```

## Desktop build

```powershell
.\scripts\build_desktop.ps1 -Clean
```
