from __future__ import annotations

import hmac
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from aiogram.types import (
    BotCommand,
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
from app.services.scheduler_service import create_scheduler
from app.services.seed_service import seed_reference_data

logger = logging.getLogger(__name__)

# Render sets RENDER_GIT_COMMIT automatically for every deploy; no extra
# render.yaml configuration is needed. Falls back to "unknown" locally
# or on any host that doesn't set it.
DEPLOYED_COMMIT = os.environ.get("RENDER_GIT_COMMIT", "unknown")[:7]

FRONTEND_DIST = Path(__file__).resolve().parent.parent / "frontend" / "dist"


class _MiniAppStaticFiles(StaticFiles):
    """Plain StaticFiles sends no Cache-Control at all — browsers fall back
    to a conditional GET (If-None-Match) on next navigation, which is fine
    on the open web, but Telegram's in-app WebView is known to skip that
    revalidation for an already-open Mini App and just keep rendering
    whatever it loaded first. A user re-opening the Mini App after a deploy
    could see the old build indefinitely without a full Telegram restart
    (confirmed live on 2026-08-12 — the new build was already being served
    correctly by the origin, the client simply never asked again).

    Vite's own output makes the fix cheap: every file under assets/ is
    content-hashed (a changed file gets a new filename), so those can be
    cached forever, while index.html — the one file whose *reference* to
    those hashes actually changes between deploys — must never be cached at
    all, forcing a revalidation on every load instead of relying on the
    client's own judgment about when to check again.
    """

    async def get_response(self, path: str, scope: Scope) -> Response:
        response = await super().get_response(path, scope)
        # `path` uses the platform's own separator (Starlette builds it with
        # os.path.join) — normalize before the prefix check so this doesn't
        # silently fall through to "no-cache" on Windows, even though the
        # only place that would ever bite in practice is local dev/testing
        # (the Docker image this actually serves from is Linux).
        if path.replace(os.sep, "/").startswith("assets/"):
            response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        else:
            response.headers["Cache-Control"] = "no-cache"
        return response


def _mount_frontend(app: FastAPI, dist_dir: Path) -> None:
    """Serve the built Mini App from the same service, when it was built.

    `frontend/dist` only exists in the production Docker image (built by a
    dedicated Node stage in the Dockerfile). Locally and in CI it is absent,
    so this must not raise — the bot and API keep working without it.
    """
    if dist_dir.is_dir():
        app.mount("/app", _MiniAppStaticFiles(directory=str(dist_dir), html=True), name="miniapp")
    else:
        logger.warning(
            "Mini App static files not found at %s; run `npm run build` in "
            "frontend/ to serve it locally",
            dist_dir,
        )


# 2026-08 bot cleanup: the / autocomplete list used to advertise
# /profile, /data, /events, /tasks, /opportunities, /points, /contact,
# /help — most of which are Mini App screens now, so typing / showed a
# second interface competing with the app. Down to exactly 3, per the
# brief: Mini App = work inside ЭРА; Bot = entry, navigation, and
# Telegram-native actions. Every dropped command still has a live
# handler (registered in app/handlers/participant/commands_ready.py) —
# it just answers with a "this lives in the app now" redirect instead
# of opening a bot-native menu; see that file's own docstring.
USER_COMMANDS = [
    BotCommand(command="start", description="Запустить ЭРА"),
    BotCommand(command="navigation", description="Навигация по ЭРА"),
    BotCommand(command="contact", description="Связь с командой"),
]

# The old in-bot admin panel tree (/panel, /admin,
# app/handlers/admin/management_ready.py + dashboard_block_a.py,
# app/handlers/admin/panel.py's admin_panel_keyboard()-rooted menu tree)
# is not advertised here and, as of this cleanup, has no live entry
# point left anywhere in the bot (see app/handlers/admin/addons.py's
# _reset_admin_state) — Excel/analytics export, monthly goals, the
# organizations-contacts database, the department/direction structure
# editor, general broadcast, and test-data maintenance were all ported
# to Admin Mode in the Mini App. /panel and /admin only show a "this
# lives in the Mini App now" redirect (kept live, not deleted, as a
# compatibility handler for anyone who still types the old command) —
# the underlying handler tree itself stays in the codebase (not
# archived yet, tracked separately) but is no longer reachable.
# /version is the one genuinely bot-native, admin-only diagnostic left.
ADMIN_COMMANDS = USER_COMMANDS + [
    BotCommand(command="version", description="Версия запущенного бота"),
]


def _chat_menu_button(miniapp_url: str) -> MenuButtonWebApp | MenuButtonDefault:
    """The persistent button next to the message input (Telegram's "chat
    menu button" — distinct from the "🔥 Открыть ЭРА" inline button in
    main_inline_keyboard(), which only appears after the bot has actually
    sent a message carrying it). Opens the Mini App in one tap from
    anywhere once it's actually configured (`miniapp_url` is
    `Settings.effective_miniapp_url`, already empty until
    `MINIAPP_AUTH_SECRET` is set); falls back to the plain commands list
    otherwise, rather than shipping a button that would error.
    """
    if not miniapp_url:
        return MenuButtonDefault()
    return MenuButtonWebApp(text="Открыть ЭРА", web_app=WebAppInfo(url=miniapp_url))


def _menu_button_matches(expected, actual) -> bool:
    """Compares what we asked Telegram to set against what
    `getChatMenuButton` actually reports back. Setting a menu button is a
    fire-and-forget API call — this is the only way to know Telegram
    genuinely accepted and stored it, rather than assuming success from
    "the call didn't raise".

    Confirmed against real production behavior (not assumed): when we
    send `default` (meaning "no explicit choice, let Telegram decide"),
    Telegram's own client — since this bot has commands registered via
    `setMyCommands` — normalizes that into reporting back type `commands`.
    That's Telegram's own documented behavior, not a failure to apply our
    setting, so it must not be treated as a mismatch; only a mismatch
    against an explicitly requested `web_app` is a real problem.
    """
    if expected.type == "web_app":
        return actual.type == "web_app" and expected.web_app.url == actual.web_app.url
    return actual.type in ("default", "commands")


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    settings.assert_safe_for_deployment()
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s | %(levelname)s | %(name)s | [%(request_id)s] | %(message)s",
    )
    # A Filter added to a Logger only fires for records logged directly on
    # that logger, not ones propagated up from `app.webapp`/etc.'s own
    # `__name__`-scoped loggers — it has to go on the root's *handler*
    # (what basicConfig() just created) to see every record regardless of
    # which module's logger originated it.
    for handler in logging.getLogger().handlers:
        handler.addFilter(RequestIDLogFilter())
    logger.info("Starting ERA bot, commit=%s", DEPLOYED_COMMIT)

    engine, session_factory = create_engine_and_sessionmaker(settings.database_url)
    async with session_factory() as session:
        await seed_reference_data(session, settings)

    bot = create_bot(settings)
    dispatcher = create_dispatcher(settings, session_factory)
    app.state.settings = settings
    app.state.engine = engine
    app.state.session_factory = session_factory
    app.state.bot = bot
    app.state.dispatcher = dispatcher

    # Redis is dedicated to aiogram FSM storage in this service. Clear stale
    # production forms on deploy; PostgreSQL user and organization data is
    # stored separately and is not affected.
    recovery_marker = "era:recovery:fsm-global-v2"
    redis_client = dispatcher.storage.redis
    if not await redis_client.exists(recovery_marker):
        await redis_client.flushdb()
        await redis_client.set(recovery_marker, "done")
        logger.warning("Redis FSM storage cleared during recovery deploy")

    app.state.ai_service = AIService(settings)
    scheduler = create_scheduler(bot, settings, session_factory)
    scheduler.start()
    app.state.scheduler = scheduler
    app.state.bot_diagnostics = {"error": "webhook_not_configured"}

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
            # Fire-and-forget setChatMenuButton succeeding is not proof
            # Telegram actually stored it — read it back and compare.
            # Logged, not just asserted, so a real mismatch is visible in
            # production logs immediately after every deploy, not
            # discovered later by a confused user.
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
            await bot.set_my_commands(USER_COMMANDS)
            for admin_id in settings.admin_ids:
                await bot.set_my_commands(
                    ADMIN_COMMANDS,
                    scope=BotCommandScopeChat(chat_id=admin_id),
                )
            logger.info("Telegram webhook configured: %s", webhook_url)
        else:
            logger.warning("PUBLIC_BASE_URL is not set; Telegram webhook is disabled")
        yield
    finally:
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
    # Baseline hardening headers. No CORS header is set here on purpose —
    # the Mini App is served same-origin in production (see
    # _mount_frontend below), so cross-origin requests should keep failing
    # closed by default rather than being explicitly allowed. If the
    # frontend is ever hosted on a separate domain, add an explicit
    # allowlisted CORSMiddleware then — never a wildcard.
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["X-Frame-Options"] = "SAMEORIGIN"
    if request.url.scheme == "https":
        response.headers["Strict-Transport-Security"] = (
            "max-age=63072000; includeSubDomains"
        )
    return response


@app.get("/health")
async def health() -> dict[str, str]:
    """Liveness only — must stay cheap and dependency-free so it keeps
    answering even if the database or Redis are degraded. Use /ready for
    an actual dependency check."""
    return {"status": "ok", "version": "2.1.0", "commit": DEPLOYED_COMMIT}


@app.get("/ready")
async def ready(request: Request) -> dict[str, str]:
    """Readiness check: verifies the database is actually reachable,
    without leaking connection details in the response."""
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


@app.get("/diag")
async def diag(request: Request) -> dict:
    """Non-sensitive bot-configuration diagnostics, cached at startup (see
    lifespan()'s menu-button verification) — not a live Telegram call per
    request. Exists so "is the running process actually the bot I'm
    talking to, correctly configured" can be checked from the outside
    (e.g. `curl`) without needing BOT_TOKEN or a Telegram session — the
    same fields are also available live, in more detail, via the /version
    bot command for admins. No token, secret, or connection string is
    ever included: bot_id/bot_username are public (Telegram search finds
    them), webhook_host is a domain, not the secret validated separately
    via the webhook's header token."""
    return {
        "commit": DEPLOYED_COMMIT,
        **getattr(request.app.state, "bot_diagnostics", {"error": "not_available"}),
    }


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
