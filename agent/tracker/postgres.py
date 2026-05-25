"""SQLAlchemy-backed tracker for Supabase/Postgres."""
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
    if url.startswith("postgresql://"):
        return "postgresql+psycopg://" + url.removeprefix("postgresql://")
    return url


def _ensure_sqlite_parent(url: str) -> None:
    if not url.startswith("sqlite:///"):
        return
    raw = url.removeprefix("sqlite:///")
    if raw and raw != ":memory:":
        Path(raw).expanduser().parent.mkdir(parents=True, exist_ok=True)


class PostgresTracker:
    """Tracker implementation backed by Postgres-compatible SQLAlchemy tables."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.engine: Engine | None = None

    def load_or_create(self) -> None:
        if not self.settings.database_url:
            raise RuntimeError(
                "DATABASE_URL is required for the Postgres tracker. "
                "Set it in .env, or use a sqlite:/// URL in tests."
            )
        url = _normalize_database_url(self.settings.database_url)
        _ensure_sqlite_parent(url)
        self.engine = sa.create_engine(url, future=True)
        metadata.create_all(self.engine)
        logger.info("Postgres tracker ready")

    def _require_engine(self) -> Engine:
        if self.engine is None:
            self.load_or_create()
        assert self.engine is not None
        return self.engine

    def upsert_role(self, listing: JobListing, score_result: dict) -> None:
        now = _now()
        first_seen = _parse_datetime(listing.fetched_at) or now
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
            "first_seen": first_seen,
            "last_updated": now,
        }
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

    def record_run(self, report: dict[str, Any]) -> None:
        engine = self._require_engine()
        with engine.begin() as conn:
            conn.execute(
                runs_table.insert().values(
                    timestamp=_now(),
                    manual=bool(report.get("manual")),
                    dry_run=bool(report.get("dry_run")),
                    report_json=report,
                )
            )
