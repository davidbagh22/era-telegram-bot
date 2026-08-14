from __future__ import annotations

import hmac
import os
from datetime import datetime, timezone
from typing import Literal

from aiogram import Bot
from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_bot, get_current_user, get_session, get_settings
from app.api.rate_limit import enforce_rate_limit
from app.config import Settings
from app.database.models import User
from app.database.system_models import BackupHistory, SystemIncident
from app.services.audit_service import audit
from app.services.authorization_service import is_full_admin
from app.services.notification_service import notify_admins
from app.services.system_health_service import (
    current_commit_sha,
    run_system_diagnostics,
    sanitize_runtime_detail,
    system_snapshot,
)

router = APIRouter(tags=["system"])


async def require_system_admin(
    user: User = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
) -> User:
    if not is_full_admin(user, settings, user.telegram_id):
        raise HTTPException(status_code=403, detail="admin_access_required")
    return user


class DiagnosticRunIn(BaseModel):
    run_type: Literal["heartbeat", "full"] = "full"


@router.get("/admin/system")
async def read_system_snapshot(
    _admin: User = Depends(require_system_admin),
    session: AsyncSession = Depends(get_session),
) -> dict:
    return await system_snapshot(session)


@router.post("/admin/system/diagnostics")
async def run_diagnostics_now(
    payload: DiagnosticRunIn,
    request: Request,
    admin: User = Depends(require_system_admin),
    bot: Bot | None = Depends(get_bot),
    settings: Settings = Depends(get_settings),
    session: AsyncSession = Depends(get_session),
) -> dict:
    await enforce_rate_limit(
        request,
        key_prefix="admin_system_diagnostic",
        limit=6,
        window_seconds=600,
    )
    if bot is None:
        raise HTTPException(status_code=503, detail="bot_runtime_unavailable")
    await audit(
        session,
        actor_id=admin.id,
        action="system.diagnostic.run",
        entity_type="system",
        new_value={"run_type": payload.run_type},
    )
    return await run_system_diagnostics(
        bot,
        settings,
        request.app.state.session_factory,
        run_type=payload.run_type,
    )


class BackupReportIn(BaseModel):
    backup_key: str = Field(min_length=4, max_length=160)
    backup_type: Literal["daily", "weekly", "monthly", "manual"] = "daily"
    status: Literal["success", "failed"]
    storage_provider: str = Field(default="github-actions", min_length=2, max_length=32)
    storage_reference: str | None = Field(default=None, max_length=255)
    checksum_sha256: str | None = Field(default=None, min_length=64, max_length=64)
    size_bytes: int | None = Field(default=None, ge=0)
    started_at: datetime | None = None
    completed_at: datetime | None = None
    restore_verified_at: datetime | None = None
    error_code: str | None = Field(default=None, max_length=96)
    error_detail: str | None = Field(default=None, max_length=1000)


def _backup_secret() -> str:
    return os.getenv("BACKUP_REPORT_SECRET", "").strip()


def _backup_fix_prompt(detail: str) -> str:
    return (
        "Исправь сбой production backup ERA Platform.\n\n"
        f"Симптом: {sanitize_runtime_detail(detail)}\n"
        f"Текущий commit: {current_commit_sha() or 'unknown'}\n\n"
        "Проверь workflow database-backup.yml, pg_dump, checksum, restore verification, "
        "external storage и retention. Не выводи DATABASE_URL, токены или персональные данные. "
        "После исправления обязательно выполни реальный restore-test."
    )


@router.post("/internal/backup/report")
async def report_backup(
    payload: BackupReportIn,
    x_era_backup_secret: str | None = Header(default=None),
    session: AsyncSession = Depends(get_session),
    bot: Bot | None = Depends(get_bot),
    settings: Settings = Depends(get_settings),
) -> dict[str, object]:
    expected = _backup_secret()
    if not expected:
        raise HTTPException(status_code=503, detail="backup_reporting_not_configured")
    supplied = (x_era_backup_secret or "").strip()
    if not supplied or not hmac.compare_digest(supplied, expected):
        raise HTTPException(status_code=401, detail="invalid_backup_report_secret")

    now = datetime.now(timezone.utc)
    row = await session.scalar(select(BackupHistory).where(BackupHistory.backup_key == payload.backup_key))
    if row is None:
        row = BackupHistory(backup_key=payload.backup_key, status=payload.status)
        session.add(row)
    row.backup_type = payload.backup_type
    row.status = payload.status
    row.storage_provider = payload.storage_provider
    row.storage_reference = payload.storage_reference
    row.checksum_sha256 = payload.checksum_sha256
    row.size_bytes = payload.size_bytes
    row.started_at = payload.started_at
    row.completed_at = payload.completed_at or now
    row.restore_verified_at = payload.restore_verified_at
    row.error_code = sanitize_runtime_detail(payload.error_code, limit=96) if payload.error_code else None
    row.error_detail = sanitize_runtime_detail(payload.error_detail) if payload.error_detail else None

    incident = await session.scalar(select(SystemIncident).where(SystemIncident.dedupe_key == "backup:workflow"))
    if payload.status == "failed":
        detail = row.error_detail or row.error_code or "Backup workflow завершился ошибкой"
        if incident is None:
            incident = SystemIncident(
                dedupe_key="backup:workflow",
                category="backup",
                severity="high",
                status="open",
                title="Сбой резервного копирования",
                detail=detail,
                check_key="backup",
                occurrence_count=1,
                first_seen_at=now,
                last_seen_at=now,
                current_commit=current_commit_sha(),
                fix_prompt=_backup_fix_prompt(detail),
            )
            session.add(incident)
        else:
            incident.status = "open"
            incident.severity = "high"
            incident.detail = detail
            incident.last_seen_at = now
            incident.resolved_at = None
            incident.occurrence_count += 1
            incident.current_commit = current_commit_sha()
            incident.fix_prompt = _backup_fix_prompt(detail)
            incident.recovery_notified = False
        await session.flush()
        if bot is not None and not incident.admin_notified:
            sent, _ = await notify_admins(
                bot,
                settings,
                "🚨 ЭРА: backup завершился ошибкой\n\n"
                f"Код: {row.error_code or 'backup_failed'}\n"
                f"Диагностика: {detail}\n\n"
                "Откройте Admin Mode → Коммуникации → Инструменты → Система.",
            )
            incident.admin_notified = sent > 0
    else:
        if incident is not None and incident.status == "open":
            incident.status = "resolved"
            incident.resolved_at = now
            if bot is not None and incident.admin_notified and not incident.recovery_notified:
                await notify_admins(bot, settings, "✅ ЭРА: backup снова выполняется и проходит restore verification.")
                incident.recovery_notified = True
        if bot is not None:
            await notify_admins(
                bot,
                settings,
                "💾 ЭРА: резервная копия готова\n\n"
                f"Тип: {payload.backup_type}\n"
                f"Restore verification: {'пройден' if payload.restore_verified_at else 'не подтверждён'}",
            )

    await audit(
        session,
        actor_id=None,
        action="backup.report",
        entity_type="backup",
        old_value=None,
        new_value={
            "backup_key": payload.backup_key,
            "backup_type": payload.backup_type,
            "status": payload.status,
            "restore_verified": bool(payload.restore_verified_at),
        },
    )
    return {"ok": True, "backup_key": payload.backup_key, "status": payload.status}
