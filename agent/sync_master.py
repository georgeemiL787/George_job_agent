"""Generate workspace/cv/master/george_master.tex stub from cv-facts."""
from __future__ import annotations

from agent.config import Settings
from agent.cv.master_cv import load_cv_facts


def sync_master_tex(settings: Settings) -> str:
    facts = load_cv_facts(settings)
    master_dir = settings.cv_master_path
    master_dir.mkdir(parents=True, exist_ok=True)
    out = master_dir / "george_master.tex"
    body = (
        "% Auto-generated stub from cv-facts.md — not submitted directly.\n"
        "% Tailored CVs are produced per role under workspace/cv/tailored/\n\n"
        f"% Facts excerpt (first 2000 chars):\n% {facts[:2000].replace(chr(10), ' ')}\n"
    )
    out.write_text(body, encoding="utf-8")
    return str(out)
