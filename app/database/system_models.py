from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, TimestampMixin


class SystemDiagnosticRun(TimestampMixin, Base):
    """Persisted health snapshot for the runtime System screen.

    The payload is intentionally infrastructure-only: no user rows, Telegram
    initData, tokens or request bodies are stored here.
    """

    __tablename__ = "system_diagnostic_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    run_type: Mapped[str] = mapped_column(String(16), index=True)
    status: Mapped[str] = mapped_column(String(16), index=True)
    score: Mapped[int] = mapped_column(Integer)
    checks_json: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    commit_sha: Mapped[str | None] = mapped_column(String(64), index=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer)


class SystemIncident(TimestampMixin, Base):
    """Deduplicated operational incident without PII or secrets."""

    __tablename__ = "system_incidents"
    __table_args__ = (UniqueConstraint("dedupe_key", name="uq_system_incidents_dedupe_key"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    dedupe_key: Mapped[str] = mapped_column(String(160))
    category: Mapped[str] = mapped_column(String(64), index=True)
    severity: Mapped[str] = mapped_column(String(16), index=True)
    status: Mapped[str] = mapped_column(String(16), default="open", index=True)
    title: Mapped[str] = mapped_column(String(255))
    detail: Mapped[str] = mapped_column(Text)
    check_key: Mapped[str | None] = mapped_column(String(96), index=True)
    occurrence_count: Mapped[int] = mapped_column(Integer, default=1)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    current_commit: Mapped[str | None] = mapped_column(String(64))
    last_healthy_commit: Mapped[str | None] = mapped_column(String(64))
    fix_prompt: Mapped[str | None] = mapped_column(Text)
    admin_notified: Mapped[bool] = mapped_column(Boolean, default=False)
    recovery_notified: Mapped[bool] = mapped_column(Boolean, default=False)


class BackupHistory(TimestampMixin, Base):
    """Metadata for verified backups. Backup bytes never live in the DB."""

    __tablename__ = "backup_history"

    id: Mapped[int] = mapped_column(primary_key=True)
    backup_key: Mapped[str] = mapped_column(String(160), unique=True, index=True)
    backup_type: Mapped[str] = mapped_column(String(16), default="daily", index=True)
    status: Mapped[str] = mapped_column(String(16), index=True)
    storage_provider: Mapped[str] = mapped_column(String(32), default="github-actions")
    storage_reference: Mapped[str | None] = mapped_column(String(255))
    checksum_sha256: Mapped[str | None] = mapped_column(String(64))
    size_bytes: Mapped[int | None] = mapped_column(Integer)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    restore_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_code: Mapped[str | None] = mapped_column(String(96))
    error_detail: Mapped[str | None] = mapped_column(Text)
