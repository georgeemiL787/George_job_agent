"""Guard against committing OpenRouter key literals."""

from pathlib import Path


def test_openrouter_smoke_scripts_do_not_embed_key_literals():
    repo = Path(__file__).resolve().parents[1]
    key_prefix = "sk-or-v1" + "-"
    checked_files = [
        repo / ".env.example",
        repo / "README.md",
        repo / "test_openrouter.py",
        repo / "test_openrouter.mjs",
    ]

    for path in checked_files:
        if not path.exists():
            continue
        assert key_prefix not in path.read_text(encoding="utf-8")
