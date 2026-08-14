from __future__ import annotations

import os
import re
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from aiogram import Bot
from sqlalchemy import func, select, text

from app.config import Settings
from app.database.models import PointTransaction, TaskDelivery
from app.database.system_models import BackupHistory, SystemDiagnosticRun, SystemIncident
from app.services.notification_service import notify_admins

_SECRET_PATTERNS = (
    re.compile(
        r"(?i)(bot[_-]?token|token|secret|password|api[_-]?key)\s*[=:]\s*[^\s,;]+"
    ),
    re.compile(r"\b\d{8,12}:[A-Za-z0-9_-]{20,}\b"),
)


@dataclass(slots=True)
class HealthCheck:
    key: str
    title: str
    status: str
    severity: str
    detail: str

    def as_dict(self) -> dict[str, str]:
        return {
            "key": self.key,
            "title": self.title,
            "status": self.status,
            "severity": self.severity,
            "detail": sanitize_runtime_detail(self.detail),
        }


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def current_commit_sha() -> str | None:
    value = (
        os.getenv("RENDER_GIT_COMMIT")
        or os.getenv("GITHUB_SHA")
        or os.getenv("ERA_COMMIT_SHA")
        or ""
    ).strip()
    return value[:64] or None


def sanitize_runtime_detail(value: object, *, limit: int = 700) -> str:
    text_value = str(value or "").replace("\x00", " ")
    for pattern in _SECRET_PATTERNS:
        text_value = pattern.sub("[REDACTED]", text_value)
    text_value = re.sub(
        r"postgres(?:ql)?(?:\+asyncpg)?://[^\s]+",
        "[DATABASE_URL_REDACTED]",
        text_value,
        flags=re.I,
    )
    text_value = re.sub(r"https?://[^\s]+", "[URL_REDACTED]", text_value)
    text_value = " ".join(text_value.split())
    return text_value[:limit]


def _fix_prompt(
    check: HealthCheck,
    commit_sha: str | None,
    last_healthy_commit: str | None,
) -> str:
    return (
        "Исправь production-инцидент ERA Platform.\n\n"
        f"Категория: {check.key}\n"
        f"Критичность: {check.severity}\n"
        f"Симптом: {sanitize_runtime_detail(check.detail)}\n"
        f"Текущий commit: {commit_sha or 'unknown'}\n"
        f"Последний healthy commit: {last_healthy_commit or 'unknown'}\n\n"
        "Требования: найди корневую причину, не обходи проверки, не ослабляй "
        "авторизацию, добавь regression test, проверь миграции и не выводи "
        "секреты/персональные данные в логи."
    )


def _score(checks: list[HealthCheck]) -> tuple[int, str]:
    penalties = {"info": 0, "low": 4, "medium": 10, "high": 25, "critical": 45}
    score = max(
        0,
        100
        - sum(
            penalties.get(item.severity, 10)
            for item in checks
            if item.status != "ok"
        ),
    )
    if any(
        item.status != "ok" and item.severity == "critical" for item in checks
    ):
        return score, "critical"
    if any(item.status != "ok" for item in checks):
        return score, "degraded"
    return score, "healthy"


async def _database_check(session) -> HealthCheck:
    try:
        await session.execute(text("SELECT 1"))
        return HealthCheck("database", "База данных", "ok", "info", "Соединение с БД работает")
    except Exception as exc:  # noqa: BLE001
        return HealthCheck(
            "database",
            "База данных",
            "error",
            "critical",
            f"Database probe failed: {exc.__class__.__name__}",
        )


async def _configuration_check(settings: Settings) -> HealthCheck:
    missing: list[str] = []
    if settings.is_render_deployment and not settings.miniapp_auth_secret:
        missing.append("MINIAPP_AUTH_SECRET")
    if settings.is_render_deployment and not settings.effective_base_url.startswith("https://"):
        missing.append("HTTPS public base URL")
    if missing:
        return HealthCheck(
            "production_config",
            "Production config",
            "error",
            "critical",
            f"Не настроено: {', '.join(missing)}",
        )
    return HealthCheck(
        "production_config",
        "Production config",
        "ok",
        "info",
        "Критичная production-конфигурация присутствует; backup workflow использует GitHub OIDC",
    )


async def _chat_config_check(settings: Settings) -> HealthCheck:
    expected = {
        "general": settings.general_chat_id,
        "internal": settings.internal_department_chat_id,
        "external": settings.external_department_chat_id,
        "leaders": settings.leaders_chat_id,
    }
    missing = [key for key, chat_id in expected.items() if not chat_id]
    if missing:
        commands = ", ".join(f"/bind {key}" for key in missing)
        return HealthCheck(
            "chat_bindings",
            "Чаты ЭРА",
            "warning",
            "medium",
            f"Нет chat_id: {', '.join(missing)}. Историческое auto-recovery не нашло однозначный ID; выполните в соответствующих чатах: {commands}",
        )
    return HealthCheck(
        "chat_bindings",
        "Чаты ЭРА",
        "ok",
        "info",
        "Все четыре организационных чата настроены",
    )


async def _delivery_check(session) -> HealthCheck:
    since = _now() - timedelta(hours=24)
    try:
        failed = int(
            await session.scalar(
                select(func.count(TaskDelivery.id)).where(
                    TaskDelivery.status == "failed",
                    TaskDelivery.created_at >= since,
                )
            )
            or 0
        )
    except Exception as exc:  # pragma: no cover
        return HealthCheck(
            "task_delivery",
            "Доставка задач",
            "error",
            "high",
            f"Delivery diagnostic failed: {exc.__class__.__name__}",
        )
    if failed:
        severity = "high" if failed >= 5 else "medium"
        return HealthCheck(
            "task_delivery",
            "Доставка задач",
            "warning",
            severity,
            f"Неуспешных доставок за 24 часа: {failed}",
        )
    return HealthCheck(
        "task_delivery",
        "Доставка задач",
        "ok",
        "info",
        "Неуспешных доставок задач за 24 часа нет",
    )


async def _points_integrity_check(session) -> HealthCheck:
    try:
        negative_users = list(
            (
                await session.execute(
                    select(PointTransaction.user_id)
                    .group_by(PointTransaction.user_id)
                    .having(func.sum(PointTransaction.points) < 0)
                    .limit(6)
                )
            ).scalars()
        )
    except Exception as exc:  # pragma: no cover
        return HealthCheck(
            "points_integrity",
            "Целостность баллов",
            "error",
            "high",
            f"Points diagnostic failed: {exc.__class__.__name__}",
        )
    if negative_users:
        return HealthCheck(
            "points_integrity",
            "Целостность баллов",
            "error",
            "high",
            f"Найдены отрицательные итоговые балансы: {len(negative_users)}+ аккаунтов",
        )
    return HealthCheck(
        "points_integrity",
        "Целостность баллов",
        "ok",
        "info",
        "Отрицательных итоговых балансов не найдено",
    )


async def _backup_check(session) -> HealthCheck:
    try:
        latest = await session.scalar(
            select(BackupHistory).order_by(BackupHistory.created_at.desc()).limit(1)
        )
    except Exception as exc:  # pragma: no cover
        return HealthCheck(
            "backup",
            "Резервное копирование",
            "error",
            "high",
            f"Backup diagnostic failed: {exc.__class__.__name__}",
        )
    if latest is None:
        return HealthCheck(
            "backup",
            "Резервное копирование",
            "warning",
            "medium",
            "В Backup History пока нет ни одной подтверждённой записи",
        )
    if latest.status != "success" or latest.restore_verified_at is None:
        return HealthCheck(
            "backup",
            "Резервное копирование",
            "error",
            "high",
            f"Последний backup имеет статус {latest.status}; restore verification отсутствует или завершился ошибкой",
        )

    reference_time = _as_utc(latest.completed_at or latest.created_at)
    age = _now() - reference_time
    if age > timedelta(hours=72):
        return HealthCheck(
            "backup",
            "Резервное копирование",
            "error",
            "critical",
            f"Последний проверенный backup старше 72 часов ({int(age.total_seconds() // 3600)} ч)",
        )
    if age > timedelta(hours=36):
        return HealthCheck(
            "backup",
            "Резервное копирование",
            "warning",
            "high",
            f"Последний проверенный backup старше 36 часов ({int(age.total_seconds() // 3600)} ч)",
        )
    if latest.storage_provider not in {
        "github-actions-encrypted",
        "s3-compatible-encrypted",
    }:
        return HealthCheck(
            "backup",
            "Резервное копирование",
            "warning",
            "medium",
            f"Verified backup использует неподтверждённый storage provider: {latest.storage_provider}",
        )
    return HealthCheck(
        "backup",
        "Резервное копирование",
        "ok",
        "info",
        f"Последний encrypted off-Render backup прошёл restore verification {int(age.total_seconds() // 3600)} ч назад",
    )


async def _telegram_checks(bot: Bot, settings: Settings) -> list[HealthCheck]:
    checks: list[HealthCheck] = []
    try:
        me = await bot.get_me()
        checks.append(
            HealthCheck(
                "telegram_api",
                "Telegram Bot API",
                "ok",
                "info",
                f"Bot API отвечает; bot_id={me.id}",
            )
        )
    except Exception as exc:  # noqa: BLE001
        return [
            HealthCheck(
                "telegram_api",
                "Telegram Bot API",
                "error",
                "critical",
                f"Telegram probe failed: {exc.__class__.__name__}",
            )
        ]

    bot_id = me.id
    configured = {
        "general": settings.general_chat_id,
        "internal": settings.internal_department_chat_id,
        "external": settings.external_department_chat_id,
        "leaders": settings.leaders_chat_id,
    }
    failed: list[str] = []
    for key, chat_id in configured.items():
        if not chat_id:
            continue
        try:
            member = await bot.get_chat_member(chat_id, bot_id)
            if member.status not in {"administrator", "creator", "member"}:
                failed.append(f"{key}:{member.status}")
        except Exception as exc:  # noqa: BLE001
            failed.append(f"{key}:{exc.__class__.__name__}")
    if failed:
        checks.append(
            HealthCheck(
                "telegram_chat_access",
                "Доступ бота к чатам",
                "error",
                "high",
                f"Проблемные чаты: {', '.join(failed)}",
            )
        )
    else:
        checks.append(
            HealthCheck(
                "telegram_chat_access",
                "Доступ бота к чатам",
                "ok",
                "info",
                "Бот доступен во всех настроенных чатах",
            )
        )
    return checks


async def _last_healthy_commit(session) -> str | None:
    return await session.scalar(
        select(SystemDiagnosticRun.commit_sha)
        .where(
            SystemDiagnosticRun.status == "healthy",
            SystemDiagnosticRun.commit_sha.is_not(None),
        )
        .order_by(SystemDiagnosticRun.created_at.desc())
        .limit(1)
    )


async def _sync_incidents(
    session,
    checks: list[HealthCheck],
    commit_sha: str | None,
) -> tuple[list[SystemIncident], list[SystemIncident]]:
    now = _now()
    last_healthy = await _last_healthy_commit(session)
    active_keys: set[str] = set()
    opened_or_reopened: list[SystemIncident] = []
    recovered: list[SystemIncident] = []

    for check in checks:
        dedupe_key = f"health:{check.key}"
        if check.status == "ok":
            continue
        active_keys.add(dedupe_key)
        incident = await session.scalar(
            select(SystemIncident).where(SystemIncident.dedupe_key == dedupe_key)
        )
        if incident is None:
            incident = SystemIncident(
                dedupe_key=dedupe_key,
                category="runtime_health",
                severity=check.severity,
                status="open",
                title=check.title,
                detail=sanitize_runtime_detail(check.detail),
                check_key=check.key,
                occurrence_count=1,
                first_seen_at=now,
                last_seen_at=now,
                current_commit=commit_sha,
                last_healthy_commit=last_healthy,
                fix_prompt=_fix_prompt(check, commit_sha, last_healthy),
            )
            session.add(incident)
            opened_or_reopened.append(incident)
        else:
            was_open = incident.status == "open"
            incident.status = "open"
            incident.severity = check.severity
            incident.title = check.title
            incident.detail = sanitize_runtime_detail(check.detail)
            incident.last_seen_at = now
            incident.current_commit = commit_sha
            incident.last_healthy_commit = last_healthy
            incident.fix_prompt = _fix_prompt(check, commit_sha, last_healthy)
            incident.occurrence_count += 1
            incident.resolved_at = None
            incident.recovery_notified = False
            if not was_open:
                incident.admin_notified = False
                opened_or_reopened.append(incident)

    existing_open = list(
        (
            await session.scalars(
                select(SystemIncident).where(
                    SystemIncident.status == "open",
                    SystemIncident.category == "runtime_health",
                )
            )
        ).all()
    )
    for incident in existing_open:
        if incident.dedupe_key not in active_keys:
            incident.status = "resolved"
            incident.resolved_at = now
            recovered.append(incident)
    return opened_or_reopened, recovered


async def _notify_incident_changes(
    bot: Bot,
    settings: Settings,
    session_factory,
    opened_ids: list[int],
    recovered_ids: list[int],
) -> None:
    async with session_factory() as session:
        if opened_ids:
            incidents = list(
                (
                    await session.scalars(
                        select(SystemIncident).where(SystemIncident.id.in_(opened_ids))
                    )
                ).all()
            )
            for incident in incidents:
                if incident.severity not in {"high", "critical"} or incident.admin_notified:
                    continue
                sent, _ = await notify_admins(
                    bot,
                    settings,
                    "🚨 ЭРА: системный инцидент\n\n"
                    f"{incident.title}\n"
                    f"Критичность: {incident.severity}\n"
                    f"Диагностика: {incident.detail}\n\n"
                    "Откройте Admin Mode → Коммуникации → Инструменты → Система.",
                )
                incident.admin_notified = sent > 0
        if recovered_ids:
            incidents = list(
                (
                    await session.scalars(
                        select(SystemIncident).where(SystemIncident.id.in_(recovered_ids))
                    )
                ).all()
            )
            for incident in incidents:
                if not incident.admin_notified or incident.recovery_notified:
                    continue
                sent, _ = await notify_admins(
                    bot,
                    settings,
                    f"✅ ЭРА: восстановление\n\n{incident.title}\nПроверка снова проходит успешно.",
                )
                incident.recovery_notified = sent > 0
        await session.commit()


async def run_system_diagnostics(
    bot: Bot,
    settings: Settings,
    session_factory,
    *,
    run_type: str = "heartbeat",
) -> dict[str, Any]:
    started = time.perf_counter()
    commit_sha = current_commit_sha()
    async with session_factory() as session:
        checks = [
            await _database_check(session),
            await _configuration_check(settings),
            await _chat_config_check(settings),
            await _delivery_check(session),
            await _points_integrity_check(session),
            await _backup_check(session),
        ]
        if run_type == "full":
            checks.extend(await _telegram_checks(bot, settings))

        score, status = _score(checks)
        run = SystemDiagnosticRun(
            run_type=run_type,
            status=status,
            score=score,
            checks_json=[item.as_dict() for item in checks],
            commit_sha=commit_sha,
            duration_ms=int((time.perf_counter() - started) * 1000),
        )
        session.add(run)
        opened, recovered = await _sync_incidents(session, checks, commit_sha)
        await session.commit()
        await session.refresh(run)
        opened_ids = [item.id for item in opened]
        recovered_ids = [item.id for item in recovered]

    await _notify_incident_changes(
        bot,
        settings,
        session_factory,
        opened_ids,
        recovered_ids,
    )
    return {
        "id": run.id,
        "run_type": run.run_type,
        "status": status,
        "score": score,
        "checks": [item.as_dict() for item in checks],
        "commit_sha": commit_sha,
        "duration_ms": run.duration_ms,
    }


async def system_snapshot(session) -> dict[str, Any]:
    latest = await session.scalar(
        select(SystemDiagnosticRun)
        .order_by(SystemDiagnosticRun.created_at.desc())
        .limit(1)
    )
    latest_full = await session.scalar(
        select(SystemDiagnosticRun)
        .where(SystemDiagnosticRun.run_type == "full")
        .order_by(SystemDiagnosticRun.created_at.desc())
        .limit(1)
    )
    incidents = list(
        (
            await session.scalars(
                select(SystemIncident)
                .order_by(
                    SystemIncident.status.asc(),
                    SystemIncident.last_seen_at.desc(),
                )
                .limit(50)
            )
        ).all()
    )
    backups = list(
        (
            await session.scalars(
                select(BackupHistory)
                .order_by(BackupHistory.created_at.desc())
                .limit(30)
            )
        ).all()
    )
    return {
        "latest": _run_payload(latest),
        "latest_full": _run_payload(latest_full),
        "incidents": [_incident_payload(item) for item in incidents],
        "backups": [_backup_payload(item) for item in backups],
    }


def _run_payload(run: SystemDiagnosticRun | None) -> dict[str, Any] | None:
    if run is None:
        return None
    return {
        "id": run.id,
        "run_type": run.run_type,
        "status": run.status,
        "score": run.score,
        "checks": run.checks_json,
        "commit_sha": run.commit_sha,
        "duration_ms": run.duration_ms,
        "created_at": run.created_at.isoformat() if run.created_at else None,
    }


def _incident_payload(item: SystemIncident) -> dict[str, Any]:
    return {
        "id": item.id,
        "severity": item.severity,
        "status": item.status,
        "title": item.title,
        "detail": item.detail,
        "check_key": item.check_key,
        "occurrence_count": item.occurrence_count,
        "first_seen_at": item.first_seen_at.isoformat(),
        "last_seen_at": item.last_seen_at.isoformat(),
        "resolved_at": item.resolved_at.isoformat() if item.resolved_at else None,
        "current_commit": item.current_commit,
        "last_healthy_commit": item.last_healthy_commit,
        "fix_prompt": item.fix_prompt,
    }


def _backup_payload(item: BackupHistory) -> dict[str, Any]:
    return {
        "id": item.id,
        "backup_key": item.backup_key,
        "backup_type": item.backup_type,
        "status": item.status,
        "storage_provider": item.storage_provider,
        "storage_reference": item.storage_reference,
        "checksum_sha256": item.checksum_sha256,
        "size_bytes": item.size_bytes,
        "completed_at": item.completed_at.isoformat() if item.completed_at else None,
        "restore_verified_at": (
            item.restore_verified_at.isoformat() if item.restore_verified_at else None
        ),
        "error_code": item.error_code,
        "error_detail": item.error_detail,
        "created_at": item.created_at.isoformat() if item.created_at else None,
    }


async def send_daily_system_summary(
    bot: Bot,
    settings: Settings,
    session_factory,
) -> None:
    async with session_factory() as session:
        snapshot = await system_snapshot(session)
    latest = snapshot["latest"]
    open_incidents = [
        item for item in snapshot["incidents"] if item["status"] == "open"
    ]
    latest_backup = snapshot["backups"][0] if snapshot["backups"] else None
    await notify_admins(
        bot,
        settings,
        "🩺 ЭРА: ежедневное состояние системы\n\n"
        f"Health: {latest['status'] if latest else 'нет данных'}"
        f" · {latest['score'] if latest else '—'}/100\n"
        f"Открытых инцидентов: {len(open_incidents)}\n"
        f"Последний backup: {latest_backup['status'] if latest_backup else 'нет данных'}",
    )
