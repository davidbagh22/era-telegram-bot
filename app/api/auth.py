from __future__ import annotations

from fastapi import Depends, Header, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import User
from app.repositories.users import get_user_by_telegram_id
from app.services.telegram_auth_service import TelegramIdentity, validate_init_data


async def get_session(request: Request) -> AsyncSession:
    async with request.app.state.session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def get_telegram_identity(
    request: Request,
    init_data: str | None = Header(default=None, alias="X-Telegram-Init-Data"),
    dev_telegram_id: int | None = Header(default=None, alias="X-Dev-Telegram-Id"),
) -> TelegramIdentity:
    settings = request.app.state.settings
    if init_data:
        try:
            return validate_init_data(
                init_data,
                settings.bot_token,
                max_age_seconds=settings.init_data_max_age_seconds,
            )
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Не удалось подтвердить вход через Telegram.",
            ) from exc

    if settings.dev_auth_enabled and dev_telegram_id:
        return TelegramIdentity(
            telegram_id=dev_telegram_id,
            username="era_demo",
            first_name="Давид",
            last_name="Багд…98354 tokens truncated….support-button strong { display: block; margin-bottom: 3px; font-size: 11px; }
.support-button small { color: var(--era-muted); font-size: 8px; }
.refresh-link { align-self: center; padding: 8px; border: 0; background: transparent; color: var(--era-red); font-size: 9px; font-weight: 800; cursor: pointer; }

.portfolio-intro,
.rating-banner {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  padding: 16px;
  border-radius: 20px;
  background: linear-gradient(135deg, var(--era-soft-red), var(--era-soft-pink));
  color: var(--era-red);
}

.portfolio-intro strong,
.rating-banner strong { display: block; margin-bottom: 4px; color: var(--era-ink); font-size: 12px; }
.portfolio-intro p,
.rating-banner p { margin: 0; color: var(--era-muted); font-size: 9px; line-height: 1.5; }

.portfolio-card {
  display: flex;
  align-items: center;
  gap: 11px;
  padding: 13px;
  border: 1px solid var(--era-border);
  border-radius: 17px;
  background: #fff;
}

.portfolio-card > span { display: grid; width: 38px; height: 38px; border-radius: 13px; background: var(--era-soft-purple); color: var(--era-purple); place-items: center; }
.portfolio-card strong { display: block; margin-bottom: 3px; font-size: 10px; }
.portfolio-card small { color: var(--era-muted); font-size: 8px; }

.rating-banner { background: linear-gradient(135deg, #fff6df, #fff0ed); color: #ca8120; }
.rating-row { display: grid; align-items: center; grid-template-columns: 30px 36px minmax(0, 1fr) auto; gap: 9px; padding: 10px 12px; border: 1px solid var(--era-border); border-radius: 16px; background: #fff; }
.rating-row.is-current { border-color: rgba(213, 26, 121, 0.28); background: linear-gradient(120deg, var(--era-soft-red), #fff); }
.rating-place { color: var(--era-muted); font-size: 10px; font-weight: 800; text-align: center; }
.rating-row:nth-child(1) .rating-place { color: #d89b1e; }
.rating-row:nth-child(2) .rating-place { color: #8f99a5; }
.rating-row:nth-child(3) .rating-place { color: #b27651; }
.rating-avatar { display: grid; width: 36px; height: 36px; border-radius: 13px; background: var(--era-soft-purple); color: var(--era-purple); font-size: 11px; font-weight: 800; place-items: center; }
.rating-row > strong { overflow: hidden; font-size: 10px; text-overflow: ellipsis; white-space: nowrap; }
.rating-row > b { color: var(--era-red); font-size: 11px; }

.task-card {
  padding: 14px;
  border: 1px solid var(--era-border);
  border-radius: 19px;
  background: #fff;
}

.task-card__head { display: grid; align-items: center; grid-template-columns: 38px minmax(0, 1fr) auto; gap: 10px; }
.task-card__head > span { display: grid; width: 38px; height: 38px; border-radius: 13px; background: var(--era-soft-purple); color: var(--era-purple); place-items: center; }
.task-card__head strong { display: block; font-size: 11px; }
.task-card__head small { color: var(--era-muted); font-size: 8px; }
.task-card__head b { color: var(--era-purple); font-size: 10px; }
.task-card > p { margin: 11px 0; color: var(--era-muted); font-size: 9px; line-height: 1.55; }
.task-card__footer { display: flex; align-items: center; justify-content: space-between; gap: 10px; }
.task-card__footer > span { display: flex; align-items: center; gap: 4px; color: var(--era-muted); font-size: 8px; }
.task-card__footer button { display: flex; align-items: center; gap: 4px; padding: 7px 10px; border: 0; border-radius: 10px; background: var(--era-soft-red); color: var(--era-red); font-size: 8px; font-weight: 800; cursor: pointer; }

.registration {
  padding: calc(18px + var(--safe-top)) 18px calc(28px + var(--safe-bottom));
}

.registration-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 25px;
}

.registration-header > span { color: var(--era-muted); font-size: 10px; font-weight: 800; letter-spacing: 0.09em; text-transform: uppercase; }

.registration-progress { margin-bottom: 18px; }

.registration-card {
  min-height: 460px;
  padding: 20px;
  border: 1px solid var(--era-border);
  border-radius: 26px;
  background: rgba(255, 255, 255, 0.9);
  box-shadow: var(--shadow-soft);
}

.registration-actions { position: sticky; bottom: 0; padding-top: 15px; background: linear-gradient(180deg, transparent, var(--era-bg) 28%); }

.spin { animation: spin 0.8s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }

@media (min-width: 700px) {
  body { padding: 22px 0; }
  .app-frame,
  .page-shell { min-height: calc(100vh - 44px); border-radius: 30px; }
  .app-frame { overflow: hidden; }
  .app-header { top: 22px; border-radius: 30px 30px 0 0; }
  .bottom-nav { bottom: 22px; border-radius: 0 0 30px 30px; }
  .modal { margin-bottom: 22px; border-radius: 28px; }
  .modal--full { height: calc(100vh - 44px); }
}

@media (max-width: 370px) {
  .screen { padding-right: 14px; padding-left: 14px; }
  .stats-grid { gap: 5px; }
  .stat-card { padding-right: 3px; padding-left: 3px; }
  .quick-card { min-height: 138px; padding: 14px; }
  .registration { padding-right: 13px; padding-left: 13px; }
  .registration-card { padding: 16px; }
  .admin-metrics { grid-template-columns: repeat(2, 1fr); }
}

@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after {
    scroll-behavior: auto !important;
    animation-duration: 0.01ms !important;
    animation-iteration-count: 1 !important;
    transition-duration: 0.01ms !important;
  }
}
