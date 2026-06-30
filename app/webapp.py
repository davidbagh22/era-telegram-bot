from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from aiogram.types import MenuButtonWebApp, Update, WebAppInfo
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api.routes import router as api_router
from app.bot import create_bot, create_dispatcher
from app.config import get_settings
from app.database.session import create_engine_and_sessionmaker
from app.services.ai_service import AIService
from app.services.scheduler_service import create_scheduler
from app.services.seed_service import seed_reference_data

logger = logging.getLogger(__name__)
PROJECT_ROOT = Path(__file__).resolve().parents[1]
FRONTEND_DIST = PROJECT_ROOT / "frontend" / "dist"


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )
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
    app.state.ai_service = AIService(settings)
    scheduler = create_scheduler(bot, settings, session_factory)
    scheduler.start()
    app.state.scheduler = scheduler

    base_url = settings.effective_base_url
    if base_url:
        webhook_url = f"{base_url}/telegram/webhook"
        await bot.set_webhook(
            webhook_url,
            secret_token=settings.webhook_secret or None,
            allowed_updates=dispatcher.resolve_used_update_types(),
            drop_pending_updates=False,
        )
        await bot.set_chat_menu_button(
            menu_button=MenuButtonWebApp(
                text="Открыть ЭРА", web_app=WebAppInfo(url=base_url)
            )
        )
        logger.info("Telegram webhook configured: %s", webhook_url)
    else:
        logger.warning("PUBLIC_BASE_URL is not set; Telegram webhook is disabled")

    try:
        yield
    finally:
        scheduler.shutdown(wait=False)
        await dispatcher.storage.close()
        await bot.session.close()
        await engine.dispose()


app = FastAPI(
    title="ERA Mini App API",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/api/docs",
    openapi_url="/api/openapi.json",
)
app.include_router(api_router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/telegram/webhook", include_in_schema=False)
async def telegram_webhook(
    request: Request,
    secret: str | None = Header(default=None, alias="X-Telegram-Bot-Api-Secret-Token"),
) -> dict[str, bool]:
    expected_secret = request.app.state.settings.webhook_secret
    if expected_secret and secret != expected_secret:
        raise HTTPException(status_code=403, detail="Invalid webhook secret")
    payload = await request.json()
    update = Update.model_validate(payload, context={"bot": request.app.state.bot})
    await request.app.state.dispatcher.feed_update(request.app.state.bot, update)
    return {"ok": True}


if (FRONTEND_DIST / "assets").exists():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="assets")


@app.get("/{path:path}", include_in_schema=False)
async def frontend(path: str) -> FileResponse:
    requested = FRONTEND_DIST / path
    if (
        path
        and requested.is_file()
        and requested.resolve().is_relative_to(FRONTEND_DIST.resolve())
    ):
        return FileResponse(requested)
    index = FRONTEND_DIST / "index.html"
    if not index.exists():
        raise HTTPException(status_code=503, detail="Mini App frontend is not built")
    return FileResponse(index)
