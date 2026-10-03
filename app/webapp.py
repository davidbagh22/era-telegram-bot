from __future__ import annotations

import asyncio
import hmac
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

import aiogram
from aiogram import Bot as AiogramBot
from aiogram.client.default import DefaultBotProperties
from aiogram.types import (
    BotCommand,
    BotCommandScopeAllGroupChats,
    BotCommandScopeAllPrivateChats,
    BotCommandScopeChat,
    MenuButtonDefault,
    MenuButtonWebApp,
    Update,
    WebAppInfo,
)
from fastapi import BackgroundTasks, FastAPI, Header, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from starlette.responses import Response
from starlette.types import Scope

from app.api.v1.router import api_router
from app.bot import create_bot, create_dispatcher
from app.config import get_settings
from app.database.session import create_engine_and_sessionmaker
from app.request_context import RequestIDLogFilter, new_request_id, request_id_var
from app.services.ai_service import AIService
from app.services.chat_permissions_service import enforce_general_chat_writable
from app.services.general_chat_menu_service import ensure_general_chat_miniapp_menu
from app.services.scheduler_service import create_scheduler
from app.services.seed_service import seed_reference_data
from app.services.system_scheduler import add_system_jobs


class _CommissionCompatBot(AiogramBot):
    """Compatibility adapter for the isolated Commission bot."""

    def __init__(self, token: str, parse_mode=None, **kwargs):
        if parse_mode is not None and "default" not in kwargs:
            kwargs["default"] = DefaultBotProperties(parse_mode=parse_mode)
        super().__init__(token=token, **kwargs)


# aiogram >=3.7 removed Bot(parse_mode=...). Keep the Commission module isolated
# without changing ERA's bot construction.
_original_aiogram_bot = aiogram.Bot
aiogram.Bot = _CommissionCompatBot
try:
    from app.commission_bot_plus import run_commission_bot_plus as run_commission_bot
finally:
    aiogram.Bot = _original_aiogram_bot


logger = logging.getLogger(__name__)

DEPLOYED_COMMIT = os.environ.get("RENDER_GIT_COMMIT", "unknown")[:7]

FRONTEND_DIST = Path(__file__).resolve().parent.parent / "frontend" / "dist"


class _MiniAppStaticFiles(StaticFiles):
    """Serve hashed assets with long cache lifetime and index.html without caching."""

    async def get_response(self, path: str, scope: Scope) -> Response:
        response = await super().get_response(path, scope)
        if path.replace(os.sep, "/").startswith("assets/"):
            response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        else:
            response.headers["Cache-Control"] = "no-cache"
        return response


def _mount_frontend(app: FastAPI, dist_dir: Path) -> None:
    """Serve hashed assets and the Mini App when it was built."""
    if dist_dir.is_dir():
        app.mount("/app", _MiniAppStaticFiles(directory=str(dist_dir), html=True), name="miniapp")
    else:
        logger.warning(
            "Mini App static files not found at %s; run `npm run build` in "
            "frontend/ to serve it locally",
            dist_dir,
        )


USER_COMMANDS = [
    BotCommand(command="start", description="Запустить ЭРА"),
    BotCommand(command="navigation", description="Навигация по ЭРА"),
    BotCommand(command="contact", description="Связь с командой"),
]

ADMIN_COMMANDS = USER_COMMANDS + [
    BotCommand(command="status", description="Состояние системы"),
    BotCommand(command="backup", description="Резервные копии"),
    BotCommand(command="org", description="Состояние организации"),
    BotCommand(command="version", description="Версия запущенного бота"),
]


def _chat_menu_button(miniapp_url: str) -> MenuButtonWebApp | MenuButtonDefault:
    """Persistent Mini App button in the bot's private chat."""
    if not miniapp_url:
        return MenuButtonDefault()
    return MenuButtonWebApp(text="Открыть ЭРА", web_app=WebAppInfo(url=miniapp_url))


def _menu_button_matches(expected, actual) -> bool:
    if expected.type == "web_app":
        return actual.type == "web_app" and expected.web_app.url == actual.web_app.url
    return actual.type in ("default", "commands")


async def _configure_command_scopes(bot, settings) -> None:
    """Keep slash autocomplete private and remove it from every group scope."""
    await bot.set_my_commands([])
    await bot.set_my_commands(USER_COMMANDS, scope=BotCommandScopeAllPrivateChats())
    await bot.set_my_commands([], scope=BotCommandScopeAllGroupChats())

    group_chat_ids = {
        settings.general_chat_id,
        settings.internal_department_chat_id,
        settings.external_department_chat_id,
        settings.leaders_chat_id,
    }
    for chat_id in group_chat_ids:
        if chat_id:
            await bot.set_my_commands([], scope=BotCommandScopeChat(chat_id=int(chat_id)))

    for admin_id in settings.admin_ids:
        await bot.set_my_commands(ADMIN_COMMANDS, scope=BotCommandScopeChat(chat_id=admin_id))


async def _ensure_commission_owner(engine) -> None:
    """Seed the configured owner after the Commission schema is initialized."""
    raw_owner_id = os.environ.get("COMMISSION_OWNER_TELEGRAM_ID", "").strip()
    if not raw_owner_id or not os.environ.get("COMMISSION_BOT_TOKEN", "").strip():
        return
    try:
        owner_id = int(raw_owner_id)
    except ValueError:
        logger.error("COMMISSION_OWNER_TELEGRAM_ID is not a valid integer")
        return

    for attempt in range(30):
        try:
            async with engine.begin() as connection:
                await connection.execute(
                    text(
                        """
                        INSERT INTO commission.users(
                            telegram_id, role, onboarding_complete,
                            telegram_opt_in, country_code, country_name,
                            consent_at, updated_at
                        )
                        VALUES (
                            :telegram_id, 'owner', TRUE,
                            TRUE, 'AM', '🇦🇲 Армения',
                            NOW(), NOW()
                        )
                        ON CONFLICT (telegram_id)
                        DO UPDATE SET
                            role='owner',
                            onboarding_complete=TRUE,
                            telegram_opt_in=TRUE,
                            country_code=COALESCE(commission.users.country_code, 'AM'),
                            country_name=COALESCE(commission.users.country_name, '🇦🇲 Армения'),
                            consent_at=COALESCE(commission.users.consent_at, NOW()),
                            updated_at=NOW()
                        """
                    ),
                    {"telegram_id": owner_id},
                )
            logger.info("Commission owner account ensured")
            return
        except Exception:
            if attempt == 29:
                logger.exception("Could not seed Commission owner account")
                return
            await asyncio.sleep(1)


async def _apply_one_time_reregistration_reset(engine) -> None:
    """Detach one ERA Telegram identity so the same person can test registration again.

    The historical user row is archived and assigned a synthetic Telegram ID instead
    of being hard-deleted because production audit/content records reference its
    internal user ID.
    """
    raw_telegram_id = os.environ.get("ERA_REREGISTRATION_RESET_TELEGRAM_ID", "").strip()
    if not raw_telegram_id:
        return
    try:
        telegram_id = int(raw_telegram_id)
    except ValueError:
        logger.error("ERA_REREGISTRATION_RESET_TELEGRAM_ID is not a valid integer")
        return

    async with engine.begin() as connection:
        row = (
            await connection.execute(
                text(
                    """
                    UPDATE public.users
                    SET telegram_id = -(telegram_id * 1000000 + id),
                        is_archived = TRUE,
                        archived_at = NOW(),
                        archived_by = NULL,
                        updated_at = NOW()
                    WHERE telegram_id = :telegram_id
                    RETURNING id
                    """
                ),
                {"telegram_id": telegram_id},
            )
        ).first()
    if row:
        logger.warning("ERA user detached for re-registration: user_id=%s", row[0])
    else:
        logger.info("ERA re-registration reset found no active Telegram identity")


def _log_commission_task_result(task: asyncio.Task) -> None:
    if task.cancelled():
        return
    try:
        exc = task.exception()
    except asyncio.CancelledError:
        return
    if exc is not None:
        logger.error(
            "Commission bot background task stopped unexpectedly: %s",
            exc,
            exc_info=(type(exc), exc, exc.__traceback__),
        )
    else:
        logger.info("Commission bot background task exited")


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    settings.assert_safe_for_deployment()
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s | %(levelname)s | %(name)s | [%(request_id)s] | %(message)s",
    )
    for handler in logging.getLogger().handlers:
        handler.addFilter(RequestIDLogFilter())
    logger.info("Starting ERA bot, commit=%s", DEPLOYED_COMMIT)

    engine, session_factory = create_engine_and_sessionmaker(settings.database_url)
    async with session_factory() as session:
        await seed_reference_data(session, settings)

    await _apply_one_time_reregistration_reset(engine)

    bot = create_bot(settings)
    dispatcher = create_dispatcher(settings, session_factory)
    app.state.settings = settings
    app.state.engine = engine
    app.state.session_factory = session_factory
    app.state.bot = bot
    app.state.dispatcher = dispatcher

    fixed, failed = await enforce_general_chat_writable(bot, settings, session_factory)
    logger.info("General chat write permissions enforced: fixed=%s failed=%s", fixed, failed)

    menu_ok = await ensure_general_chat_miniapp_menu(
        bot,
        settings.general_chat_id,
        session_factory,
    )
    logger.info("General chat direct Mini App menu enforced: ok=%s", menu_ok)

    recovery_marker = "era:recovery:fsm-global-v2"
    redis_client = dispatcher.storage.redis
    if not await redis_client.exists(recovery_marker):
        await redis_client.flushdb()
        await redis_client.set(recovery_marker, "done")
        logger.warning("Redis FSM storage cleared during recovery deploy")

    app.state.ai_service = AIService(settings)
    scheduler = create_scheduler(bot, settings, session_factory)

    # Legacy editorial automation had a morning + evening slot and a recovery
    # loop. It is deliberately removed from the live scheduler. The only public
    # general-chat editorial cadence is now run_daily_public_content: one quote
    # per Moscow calendar day at a deterministic varying time in 09:00–22:00.
    for legacy_job_id in (
        "general-content-morning",
        "general-content-evening",
        "general-content-recovery",
    ):
        scheduler.remove_job(legacy_job_id)

    add_system_jobs(scheduler, bot, settings, session_factory)
    scheduler.start()
    app.state.scheduler = scheduler
    app.state.bot_diagnostics = {"error": "webhook_not_configured"}

    commission_task = asyncio.create_task(
        run_commission_bot(settings.database_url),
        name="commission-bot",
    )
    commission_task.add_done_callback(_log_commission_task_result)
    commission_owner_task = asyncio.create_task(
        _ensure_commission_owner(engine),
        name="commission-owner-seed",
    )

    try:
        base_url = settings.effective_base_url
        if base_url:
            webhook_url = f"{base_url}/telegram/webhook?v=2.1.0"
            await bot.set_webhook(
                webhook_url,
                secret_token=settings.effective_webhook_secret or None,
                allowed_updates=dispatcher.resolve_used_update_types(),
                drop_pending_updates=False,
            )
            expected_menu_button = _chat_menu_button(settings.effective_miniapp_url)
            await bot.set_chat_menu_button(menu_button=expected_menu_button)
            actual_menu_button = await bot.get_chat_menu_button()
            menu_button_verified = _menu_button_matches(expected_menu_button, actual_menu_button)
            me = await bot.get_me()
            if menu_button_verified:
                logger.info(
                    "Chat menu button verified: bot=@%s type=%s",
                    me.username,
                    actual_menu_button.type,
                )
            else:
                logger.error(
                    "Chat menu button mismatch: bot=@%s expected type=%s got type=%s "
                    "— Telegram did not store the configuration we sent",
                    me.username,
                    expected_menu_button.type,
                    actual_menu_button.type,
                )
            app.state.bot_diagnostics = {
                "bot_id": me.id,
                "bot_username": me.username,
                "menu_button_type": actual_menu_button.type,
                "menu_button_verified": menu_button_verified,
                "miniapp_configured": bool(settings.effective_miniapp_url),
                "webhook_host": base_url,
            }
            await _configure_command_scopes(bot, settings)
            logger.info("Telegram webhook configured: %s", webhook_url)
        else:
            logger.warning("PUBLIC_BASE_URL is not set; Telegram webhook is disabled")
        yield
    finally:
        for task in (commission_owner_task, commission_task):
            if not task.done():
                task.cancel()
        for task in (commission_owner_task, commission_task):
            try:
                await task
            except asyncio.CancelledError:
                pass
            except Exception:
                logger.exception("Commission background task shutdown error")
        scheduler.shutdown(wait=False)
        await dispatcher.storage.close()
        await bot.session.close()
        await engine.dispose()


app = FastAPI(
    title="ERA Telegram Bot Service",
    version="2.1.0",
    lifespan=lifespan,
    docs_url=None,
    openapi_url=None,
)


@app.middleware("http")
async def request_id_middleware(request: Request, call_next):
    request_id = new_request_id(request.headers.get("X-Request-ID"))
    token = request_id_var.set(request_id)
    try:
        response = await call_next(request)
    finally:
        request_id_var.reset(token)
    response.headers["X-Request-ID"] = request_id
    return response


@app.middleware("http")
async def security_headers_middleware(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["X-Frame-Options"] = "SAMEORIGIN"
    if request.url.scheme == "https":
        response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains"
    return response


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "version": "2.1.0", "commit": DEPLOYED_COMMIT}


@app.get("/ready")
async def ready(request: Request) -> dict[str, str]:
    session_factory = getattr(request.app.state, "session_factory", None)
    if session_factory is None:
        raise HTTPException(status_code=503, detail="not_ready")
    try:
        async with session_factory() as session:
            await session.execute(text("SELECT 1"))
    except Exception:
        logger.exception("Readiness check failed: database unreachable")
        raise HTTPException(status_code=503, detail="database_unavailable")
    return {"status": "ready"}


app.include_router(api_router)
_mount_frontend(app, FRONTEND_DIST)


@app.post("/telegram/webhook", include_in_schema=False)
async def telegram_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    secret: str | None = Header(default=None, alias="X-Telegram-Bot-Api-Secret-Token"),
) -> dict[str, bool]:
    expected_secret = request.app.state.settings.effective_webhook_secret
    if expected_secret and not hmac.compare_digest(secret or "", expected_secret):
        raise HTTPException(status_code=403, detail="Invalid webhook secret")
    payload = await request.json()
    update = Update.model_validate(payload, context={"bot": request.app.state.bot})
    background_tasks.add_task(
        request.app.state.dispatcher.feed_update,
        request.app.state.bot,
        update,
    )
    return {"ok": True}
