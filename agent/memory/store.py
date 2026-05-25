"""Memory store — read/write persistent markdown files."""
from __future__ import annotations

import datetime

import pytz

from agent.config import Settings
from agent.search.base import JobListing


class MemoryStore:
    def __init__(self, settings: Settings) -> None:
        self.memory_dir = settings.memory_path
        self.tz = pytz.timezone(settings.timezone)

        self._profile_file = self.memory_dir / "job-search-profile.md"
        self._log_file = self.memory_dir / "applications-log.md"
        self._cv_facts_file = self.memory_dir / "cv-facts.md"
        self._cv_notes_file = self.memory_dir / "cv-notes.md"
        self._playbook_file = self.memory_dir / "cv-role-playbook.md"
        self._priorities_file = self.memory_dir / "tracker-priorities.md"

    def load_profile(self) -> str:
        return self._profile_file.read_text(encoding="utf-8")

    def load_cv_notes(self) -> str:
        """Legacy alias — returns cv-facts.md."""
        if self._cv_facts_file.exists():
            return self._cv_facts_file.read_text(encoding="utf-8")
        return self._cv_notes_file.read_text(encoding="utf-8")

    def load_applications_log(self) -> str:
        if not self._log_file.exists():
            self._log_file.parent.mkdir(parents=True, exist_ok=True)
            self._log_file.write_text("", encoding="utf-8")
            return ""
        return self._log_file.read_text(encoding="utf-8")

    def append_run_summary(self, summary: str) -> None:
        """Append a new dated section to applications-log.md."""
        now = datetime.datetime.now(tz=self.tz)
        timestamp = now.strftime("%Y-%m-%d %H:%M")
        section = f"\n## {timestamp} Africa/Cairo\n\n{summary}\n"
        with self._log_file.open("a", encoding="utf-8") as f:
            f.write(section)

    def append_role_found(self, listing: JobListing, result: dict) -> None:
        """Log a manually added role (e.g. LinkedIn) in applications-log.md."""
        now = datetime.datetime.now(tz=self.tz)
        timestamp = now.strftime("%Y-%m-%d %H:%M")
        block = (
            f"\n## Manual add {timestamp} Africa/Cairo\n\n"
            f"- **{listing.company}** — {listing.title}\n"
            f"  - Source: {listing.source}\n"
            f"  - Score: {result['score']}/100 [{result['tier']}]\n"
            f"  - Location: {listing.location or 'n/a'}\n"
            f"  - Apply: {listing.apply_url}\n"
            f"  - Slug: `{listing.slug}`\n"
        )
        with self._log_file.open("a", encoding="utf-8") as f:
            f.write(block)

    def append_cv_note(self, note: str) -> None:
        """Append tailoring note to cv-role-playbook.md."""
        now = datetime.datetime.now(tz=self.tz)
        timestamp = now.strftime("%Y-%m-%d %H:%M")
        section = f"\n## Note added {timestamp} Africa/Cairo\n\n{note}\n"
        target = self._playbook_file if self._playbook_file.exists() else self._cv_notes_file
        with target.open("a", encoding="utf-8") as f:
            f.write(section)

    def append_tracker_priority(self, note: str) -> None:
        """Append ordering note to tracker-priorities.md (not sent to LLM)."""
        now = datetime.datetime.now(tz=self.tz)
        timestamp = now.strftime("%Y-%m-%d %H:%M")
        section = f"\n## {timestamp} Africa/Cairo\n\n{note}\n"
        self._priorities_file.parent.mkdir(parents=True, exist_ok=True)
        with self._priorities_file.open("a", encoding="utf-8") as f:
            f.write(section)
