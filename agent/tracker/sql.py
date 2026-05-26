"""SQLAlchemy-backed tracker for local SQLite."""
from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import Any

import sqlalchemy as sa
from loguru import logger
from sqlalchemy import MetaData, Table
from sqlalchemy.engine import Engine

from agent.config import Settings
from agent.search.base import JobListing
from agent.search.deduplicator import dedup_key
from agent.tracker.models import EventRecord, RoleRecord

metadata = MetaData()

roles_table = Table(
    "roles",
    metadata,
    sa.Column("slug", sa.Text, primary_key=True),
    sa.Column("rank", sa.Integer, nullable=False, server_default="0"),
    sa.Column("company", sa.Text, nullable=False, server_default=""),
    sa.Column("title", sa.Text, nullable=False, server_default=""),
    sa.Column("location", sa.Text, nullable=False, server_default=""),
    sa.Column("source", sa.Text, nullable=False, server_default=""),
    sa.Column("score", sa.Integer, nullable=False, server_default="0"),
    sa.Column("tier", sa.Text, nullable=False, server_default=""),
    sa.Column("role_family", sa.Text, nullable=False, server_default=""),
    sa.Column("fit_summary", sa.Text, nullable=False, server_default=""),
    sa.Column("apply_url", sa.Text, nullable=False, server_default=""),
    sa.Column("cv_ready", sa.Boolean, nullable=False, server_default=sa.false()),
    sa.Column("letter_ready", sa.Boolean, nullable=False, server_default=sa.false()),
    sa.Column("status", sa.Text, nullable=False, server_default="Not Applied"),
    sa.Column("applied_date", sa.Date, nullable=True),
    sa.Column("first_seen", sa.DateTime(timezone=True), nullable=True),
    sa.Column("last_updated", sa.DateTime(timezone=True), nullable=True),
    # ats_keywords: comma-separated ATS terms extracted from the JD
    sa.Column("ats_keywords", sa.Text, nullable=False, server_default=""),
    sa.Column("run_id", sa.Integer, nullable=True),
    sa.Column("scoring_status", sa.Text, nullable=False, server_default=""),
    sa.Column("artifact_status", sa.Text, nullable=False, server_default="none"),
    sa.Column("failure_reason", sa.Text, nullable=False, server_default=""),
    sa.Column("source_payload", sa.Text, nullable=False, server_default=""),
    sa.Column("score_payload", sa.Text, nullable=False, server_default=""),
)

events_table = Table(
    "events",
    metadata,
    sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
    sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
    sa.Column("event", sa.Text, nullable=False),
    sa.Column("detail", sa.Text, nullable=False),
    sa.Column("slug", sa.Text, sa.ForeignKey("roles.slug", ondelete="SET NULL"), nullable=True),
)

runs_table = Table(
    "runs",
    metadata,
    sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
    sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
    sa.Column("manual", sa.Boolean, nullable=False),
    sa.Column("dry_run", sa.Boolean, nullable=False),
    sa.Column("status", sa.Text, nullable=False, server_default="running"),
    sa.Column("phase", sa.Text, nullable=False, server_default=""),
    sa.Column("progress_json", sa.JSON, nullable=True),
    sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    sa.Column("failure_reason", sa.Text, nullable=False, server_default=""),
    sa.Column("report_json", sa.JSON, nullable=False),
)

sa.Index("ix_roles_status", roles_table.c.status)
sa.Index("ix_roles_score", roles_table.c.score.desc())
sa.Index("ix_roles_last_updated", roles_table.c.last_updated.desc())


def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _parse_datetime(value: str | dt.datetime | None) -> dt.datetime | None:
    if value in (None, ""):
        return None
    if isinstance(value, dt.datetime):
        return value
    text = str(value).replace("Z", "+00:00")
    try:
        parsed = dt.datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed


def _parse_date(value: str | dt.date | None) -> dt.date | None:
    if value in (None, ""):
        return None
    if isinstance(value, dt.datetime):
        return value.date()
    if isinstance(value, dt.date):
        return value
    return dt.date.fromisoformat(str(value))


def _normalize_database_url(url: str) -> str:
    return url


def _ensure_sqlite_parent(url: str) -> None:
    if not url.startswith("sqlite:///"):
        return
    raw = url.removeprefix("sqlite:///")
    if raw and raw != ":memory:":
        Path(raw).expanduser().parent.mkdir(parents=True, exist_ok=True)


def _migrate_add_columns(engine: Engine) -> None:
    """Safely add any new columns to existing databases (SQLite-compatible)."""
    new_columns = [
        ("ats_keywords", "TEXT NOT NULL DEFAULT ''"),
        ("run_id", "INTEGER"),
        ("scoring_status", "TEXT NOT NULL DEFAULT ''"),
        ("artifact_status", "TEXT NOT NULL DEFAULT 'none'"),
        ("failure_reason", "TEXT NOT NULL DEFAULT ''"),
        ("source_payload", "TEXT NOT NULL DEFAULT ''"),
        ("score_payload", "TEXT NOT NULL DEFAULT ''"),
    ]
    runs_columns = [
        ("status", "TEXT NOT NULL DEFAULT 'running'"),
        ("phase", "TEXT NOT NULL DEFAULT ''"),
        ("progress_json", "TEXT"),
        ("updated_at", "DATETIME"),
        ("failure_reason", "TEXT NOT NULL DEFAULT ''"),
    ]
    with engine.begin() as conn:
        # Get existing column names
        result = conn.execute(sa.text("PRAGMA table_info(roles)"))
        existing = {row[1] for row in result}
        result_runs = conn.execute(sa.text("PRAGMA table_info(runs)"))
        existing_runs = {row[1] for row in result_runs}
        for col_name, col_def in runs_columns:
            if col_name not in existing_runs:
                try:
                    conn.execute(sa.text(f"ALTER TABLE runs ADD COLUMN {col_name} {col_def}"))
                    logger.info(f"Migration: added runs.{col_name}")
                except Exception as e:
                    logger.warning(f"Migration runs.{col_name} failed: {e}")

        for col_name, col_def in new_columns:
            if col_name not in existing:
                try:
                    conn.execute(sa.text(f"ALTER TABLE roles ADD COLUMN {col_name} {col_def}"))
                    logger.info(f"Migrated: added column '{col_name}' to roles table")
                except Exception as e:
                    logger.warning(f"Migration skipped column '{col_name}': {e}")


class SqlTracker:
    """Tracker implementation backed by local SQLite-compatible SQLAlchemy tables."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.engine: Engine | None = None

    def load_or_create(self) -> None:
        if not self.settings.database_url:
            raise RuntimeError(
                "DATABASE_URL is required for the local SQL tracker. "
                "Use sqlite:///workspace/tracker/job_agent.db for the desktop app."
            )
        url = _normalize_database_url(self.settings.database_url)
        _ensure_sqlite_parent(url)
        self.engine = sa.create_engine(url, future=True)
        metadata.create_all(self.engine)
        _migrate_add_columns(self.engine)
        logger.info("Local SQL tracker ready")

    def _require_engine(self) -> Engine:
        if self.engine is None:
            self.load_or_create()
        assert self.engine is not None
        return self.engine

    def upsert_role(
        self,
        listing: JobListing,
        score_result: dict,
        *,
        run_id: int | None = None,
        scoring_status: str = "",
        artifact_status: str = "",
        failure_reason: str = "",
        source_payload: str = "",
        score_payload: str = "",
    ) -> None:
        now = _now()
        first_seen = _parse_datetime(listing.fetched_at) or now
        ats_raw = score_result.get("ats_keywords", [])
        ats_text = ", ".join(str(k) for k in ats_raw) if ats_raw else ""
        if listing.description:
            import json as _json

            payload: dict = {}
            if source_payload:
                try:
                    parsed = _json.loads(source_payload)
                    if isinstance(parsed, dict):
                        payload = parsed
                except _json.JSONDecodeError:
                    payload = {"prefilter": source_payload}
            payload["description"] = listing.description[:8000]
            source_payload = _json.dumps(payload)
        values = {
            "slug": listing.slug,
            "company": listing.company,
            "title": listing.title,
            "location": listing.location,
            "source": listing.source,
            "score": int(score_result.get("score") or 0),
            "tier": score_result.get("tier", ""),
            "role_family": score_result.get("role_family", ""),
            "fit_summary": score_result.get("fit_summary", ""),
            "apply_url": listing.apply_url,
            "ats_keywords": ats_text,
            "first_seen": first_seen,
            "last_updated": now,
            "scoring_status": scoring_status or score_result.get("scoring_status", ""),
            "artifact_status": artifact_status or score_result.get("artifact_status", "none"),
            "failure_reason": failure_reason or score_result.get("failure_reason", ""),
            "source_payload": source_payload or score_result.get("source_payload", ""),
            "score_payload": score_payload or score_result.get("score_payload", ""),
        }
        if run_id is not None:
            values["run_id"] = run_id
        engine = self._require_engine()
        with engine.begin() as conn:
            exists = conn.execute(
                sa.select(roles_table.c.slug).where(roles_table.c.slug == listing.slug)
            ).first()
            if exists:
                update_values = {k: v for k, v in values.items() if k not in {"slug", "first_seen"}}
                conn.execute(
                    roles_table.update()
                    .where(roles_table.c.slug == listing.slug)
                    .values(**update_values)
                )
                logger.debug(f"Tracker: updated '{listing.title}' @ {listing.company}")
            else:
                conn.execute(
                    roles_table.insert().values(
                        **values,
                        rank=0,
                        cv_ready=False,
                        letter_ready=False,
                        status="Not Applied",
                    )
                )
                self._append_log_conn(
                    conn,
                    "new_role",
                    f"{listing.company} -- {listing.title} [{listing.source}] "
                    f"score={score_result.get('score')}",
                    slug=listing.slug,
                )
                logger.debug(f"Tracker: inserted '{listing.title}' @ {listing.company}")

    def upsert_record(self, record: RoleRecord) -> None:
        values = {
            "slug": record.slug,
            "rank": record.rank,
            "company": record.company,
            "title": record.title,
            "location": record.location,
            "source": record.source,
            "score": record.score,
            "tier": record.tier,
            "role_family": record.role_family,
            "fit_summary": record.fit_summary,
            "apply_url": record.apply_url,
            "cv_ready": record.cv_ready,
            "letter_ready": record.letter_ready,
            "status": record.status,
            "applied_date": _parse_date(record.applied_date),
            "first_seen": _parse_datetime(record.first_seen),
            "last_updated": _parse_datetime(record.last_updated) or _now(),
            "ats_keywords": record.ats_keywords,
            "run_id": record.run_id,
            "scoring_status": record.scoring_status,
            "artifact_status": record.artifact_status,
            "failure_reason": record.failure_reason,
            "source_payload": record.source_payload,
            "score_payload": record.score_payload,
        }
        engine = self._require_engine()
        with engine.begin() as conn:
            exists = conn.execute(
                sa.select(roles_table.c.slug).where(roles_table.c.slug == record.slug)
            ).first()
            if exists:
                conn.execute(
                    roles_table.update().where(roles_table.c.slug == record.slug).values(**values)
                )
            else:
                conn.execute(roles_table.insert().values(**values))

    def set_status(self, slug: str, status: str) -> None:
        engine = self._require_engine()
        with engine.begin() as conn:
            conn.execute(
                roles_table.update()
                .where(roles_table.c.slug == slug)
                .values(status=status, last_updated=_now())
            )

    def mark_draft(self, slug: str) -> None:
        self.set_status(slug, "Draft")

    def mark_ready_for_apply(self, slug: str) -> None:
        self.set_status(slug, "Ready")

    def mark_applied(self, slug: str, applied_date: str) -> None:
        engine = self._require_engine()
        with engine.begin() as conn:
            conn.execute(
                roles_table.update()
                .where(roles_table.c.slug == slug)
                .values(
                    status="Applied",
                    applied_date=_parse_date(applied_date),
                    last_updated=_now(),
                )
            )
            self._append_log_conn(conn, "applied", f"slug={slug} date={applied_date}", slug=slug)

    def mark_cv_ready(self, slug: str) -> None:
        engine = self._require_engine()
        with engine.begin() as conn:
            conn.execute(
                roles_table.update()
                .where(roles_table.c.slug == slug)
                .values(cv_ready=True, last_updated=_now())
            )
            self._append_log_conn(conn, "cv_ready", f"slug={slug}", slug=slug)

    def mark_letter_ready(self, slug: str) -> None:
        engine = self._require_engine()
        with engine.begin() as conn:
            conn.execute(
                roles_table.update()
                .where(roles_table.c.slug == slug)
                .values(letter_ready=True, last_updated=_now())
            )
            self._append_log_conn(conn, "letter_ready", f"slug={slug}", slug=slug)

    def get_row_by_slug(self, slug: str) -> RoleRecord | None:
        engine = self._require_engine()
        with engine.begin() as conn:
            row = conn.execute(sa.select(roles_table).where(roles_table.c.slug == slug)).mappings().first()
        return RoleRecord.from_mapping(dict(row)) if row else None

    def get_all_slugs(self) -> set[str]:
        engine = self._require_engine()
        with engine.begin() as conn:
            rows = conn.execute(sa.select(roles_table.c.slug)).scalars().all()
        return set(rows)

    def get_known_dedup_keys(self) -> set[str]:
        engine = self._require_engine()
        with engine.begin() as conn:
            rows = conn.execute(sa.select(roles_table.c.title, roles_table.c.company)).all()
        return {dedup_key(str(title or ""), str(company or "")) for title, company in rows}

    def list_pipeline_rows(
        self,
        *,
        drafts_only: bool = False,
        include_applied: bool = True,
    ) -> list[RoleRecord]:
        engine = self._require_engine()
        stmt = sa.select(roles_table)
        if drafts_only:
            stmt = stmt.where(roles_table.c.status == "Draft")
        if not include_applied:
            stmt = stmt.where(roles_table.c.status != "Applied")
        stmt = stmt.order_by(roles_table.c.rank.asc(), roles_table.c.score.desc())
        with engine.begin() as conn:
            rows = conn.execute(stmt).mappings().all()
        records = [RoleRecord.from_mapping(dict(row)) for row in rows]
        return sorted(records, key=lambda r: (r.rank <= 0, r.rank, -r.score))

    def list_events(self, limit: int | None = None) -> list[EventRecord]:
        engine = self._require_engine()
        stmt = sa.select(events_table).order_by(events_table.c.timestamp.asc())
        if limit:
            stmt = stmt.limit(limit)
        with engine.begin() as conn:
            rows = conn.execute(stmt).mappings().all()
        return [
            EventRecord(
                timestamp=row["timestamp"].isoformat() if row["timestamp"] else None,
                event=row["event"],
                detail=row["detail"],
                slug=row["slug"],
            )
            for row in rows
        ]

    def rerank(self) -> None:
        engine = self._require_engine()
        with engine.begin() as conn:
            rows = conn.execute(
                sa.select(roles_table.c.slug).order_by(roles_table.c.score.desc())
            ).scalars().all()
            for rank, slug in enumerate(rows, start=1):
                conn.execute(
                    roles_table.update().where(roles_table.c.slug == slug).values(rank=rank)
                )

    def append_log(self, event: str, detail: str) -> None:
        engine = self._require_engine()
        with engine.begin() as conn:
            self._append_log_conn(conn, event, detail)

    def _append_log_conn(self, conn, event: str, detail: str, slug: str | None = None) -> None:
        conn.execute(
            events_table.insert().values(
                timestamp=_now(),
                event=event,
                detail=detail,
                slug=slug,
            )
        )

    def save(self) -> None:
        """SQLAlchemy writes are committed per operation."""
        return None

    def start_run(self, manual: bool, dry_run: bool, options: dict[str, Any] | None = None) -> int:
        engine = self._require_engine()
        now = _now()
        report: dict[str, Any] = {
            "manual": manual,
            "dry_run": dry_run,
            "options": options or {},
            "status": "running",
        }
        with engine.begin() as conn:
            result = conn.execute(
                runs_table.insert().values(
                    timestamp=now,
                    manual=manual,
                    dry_run=dry_run,
                    status="running",
                    phase="init",
                    progress_json={},
                    updated_at=now,
                    failure_reason="",
                    report_json=report,
                )
            )
            return int(result.inserted_primary_key[0])

    def update_run_progress(
        self,
        run_id: int,
        *,
        phase: str = "",
        progress: dict[str, Any] | None = None,
        report: dict[str, Any] | None = None,
    ) -> None:
        engine = self._require_engine()
        values: dict[str, Any] = {"updated_at": _now()}
        if phase:
            values["phase"] = phase
        if progress is not None:
            values["progress_json"] = progress
        if report is not None:
            values["report_json"] = report
        with engine.begin() as conn:
            conn.execute(
                runs_table.update().where(runs_table.c.id == run_id).values(**values)
            )

    def finish_run(
        self,
        run_id: int,
        status: str,
        report: dict[str, Any],
        failure_reason: str = "",
    ) -> None:
        engine = self._require_engine()
        with engine.begin() as conn:
            conn.execute(
                runs_table.update()
                .where(runs_table.c.id == run_id)
                .values(
                    status=status,
                    updated_at=_now(),
                    failure_reason=failure_reason,
                    report_json=report,
                )
            )

    def set_role_scoring(
        self,
        slug: str,
        *,
        scoring_status: str,
        failure_reason: str = "",
    ) -> None:
        engine = self._require_engine()
        with engine.begin() as conn:
            conn.execute(
                roles_table.update()
                .where(roles_table.c.slug == slug)
                .values(
                    scoring_status=scoring_status,
                    failure_reason=failure_reason,
                    last_updated=_now(),
                )
            )

    def list_by_scoring_status(self, status: str, limit: int = 100) -> list[RoleRecord]:
        engine = self._require_engine()
        with engine.begin() as conn:
            rows = conn.execute(
                sa.select(roles_table)
                .where(roles_table.c.scoring_status == status)
                .order_by(roles_table.c.last_updated.desc())
                .limit(limit)
            ).mappings().all()
        return [RoleRecord.from_mapping(dict(row)) for row in rows]

    def set_artifact_status(
        self,
        slug: str,
        artifact_status: str,
        failure_reason: str = "",
    ) -> None:
        engine = self._require_engine()
        with engine.begin() as conn:
            conn.execute(
                roles_table.update()
                .where(roles_table.c.slug == slug)
                .values(
                    artifact_status=artifact_status,
                    failure_reason=failure_reason,
                    last_updated=_now(),
                )
            )

    def record_run(self, report: dict[str, Any]) -> int:
        engine = self._require_engine()
        with engine.begin() as conn:
            result = conn.execute(
                runs_table.insert().values(
                    timestamp=_now(),
                    manual=bool(report.get("manual")),
                    dry_run=bool(report.get("dry_run")),
                    status=str(report.get("status", "complete")),
                    phase=str(report.get("phase", "")),
                    progress_json=report.get("progress"),
                    updated_at=_now(),
                    failure_reason=str(report.get("error", "")),
                    report_json=report,
                )
            )
            return int(result.inserted_primary_key[0])
