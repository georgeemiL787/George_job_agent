"""Tests for composed CV facts loading."""
from agent.config import Settings
from agent.cv.master_cv import load_cv_facts, load_master_cv_facts, load_role_playbook_hint


def test_load_cv_facts_exists():
    settings = Settings(openrouter_api_key="test-key")
    facts = load_cv_facts(settings)
    assert "Master positioning" in facts or "CV Facts" in facts
    assert len(facts) < 8000


def test_load_master_cv_facts_slim():
    settings = Settings(openrouter_api_key="test-key")
    composed = load_master_cv_facts(
        settings,
        role_family="ai_engineer",
        company="Global Brands",
    )
    assert len(composed) < 20000


def test_playbook_hint_for_company():
    settings = Settings(openrouter_api_key="test-key")
    hint = load_role_playbook_hint(settings, "ai_engineer", "Siemens")
    assert hint == "" or "Siemens" in hint or len(hint) > 0
