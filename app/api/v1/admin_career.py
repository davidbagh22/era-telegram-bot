from __future__ import annotations

from io import BytesIO
import re

from aiogram import Bot
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_bot, get_current_user, get_session, get_settings
from app.config import Settings
from app.database.career_models import CareerPortfolioItem, RecommendationRequest
from app.database.models import User
from app.services import career_service
from app.services.authorization_service import is_full_admin
from app.services.notification_service import safe_send

router = APIRouter(prefix="/admin/career", tags=["admin-career"])


class ReviewItemIn(BaseModel):
    decision: str
    comment: str | None = Field(default=None, max_length=1000)


class ReviewRecommendationIn(BaseModel):
    decision: str
    final_text: str | None = Field(default=None, max_length=12000)
    comment: str | None = Field(default=None, max_length=1500)


def _has_review_permission(user: User, settings: Settings) -> bool:
    if is_full_admin(user, settings, user.telegram_id):
        return True
    return any(
        grant.is_active
        and grant.permission == "portfolio.review"
        and grant.scope_type == "global"
        for grant in (user.permission_grants or [])
    )


def _require_review_permission(user: User, settings: Settings) -> None:
    if not _has_review_permission(user, settings):
        raise HTTPException(status_code=403, detail="permission_required:portfolio.review")


def _name(user: User | None) -> str:
    if user is None:
        return "Участник"
    return " ".join(part for part in (user.first_name, user.last_name) if part).strip() or "Участник"


def _safe_filename(value: str | None) -> str:
    name = re.sub(r"[^A-Za-zА-Яа-яЁё0-9._ -]+", "_", (value or "document").strip())
    return name[:180] or "document"


async def _download(bot: Bot, file_id: str) -> bytes:
    try:
        telegram_file = await bot.get_file(file_id)
        if not telegram_file.file_path:
            raise RuntimeError("missing_file_path")
        buffer = BytesIO()
        await bot.download_file(telegram_file.file_path, destination=buffer)
        return buffer.getvalue()
    except Exception as exc:
        raise HTTPException(status_code=502, detail="evidence_download_unavailable") from exc


@router.get("/pending")
async def pending_items(
    user: User = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
    session: AsyncSession = Depends(get_session),
) -> list[dict]:
    _require_review_permission(user, settings)
    rows = list(
        (
            await session.scalars(
                select(CareerPortfolioItem)
                .where(CareerPortfolioItem.status == "pending")
                .order_by(CareerPortfolioItem.submitted_at, CareerPortfolioItem.id)
            )
        ).all()
    )
    owners: dict[int, User | None] = {}
    result: list[dict] = []
    for item in rows:
        if item.user_id not in owners:
            owners[item.user_id] = await session.get(User, item.user_id)
        payload = career_service.serialize_item(item)
        payload.update({"user_id": item.user_id, "user_name": _name(owners[item.user_id])})
        result.append(payload)
    return result


@router.get("/items/{item_id}/file")
async def item_file(
    item_id: int,
    user: User = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
    session: AsyncSession = Depends(get_session),
    bot: Bot = Depends(get_bot),
) -> Response:
    _require_review_permission(user, settings)
    item = await session.get(CareerPortfolioItem, item_id)
    if item is None or not item.file_id:
        raise HTTPException(status_code=404, detail="evidence_not_found")
    content = await _download(bot, item.file_id)
    return Response(
        content=content,
        media_type="application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{_safe_filename(item.file_name)}"'},
    )


@router.post("/items/{item_id}/review")
async def review_item(
    item_id: int,
    payload: ReviewItemIn,
    user: User = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
    session: AsyncSession = Depends(get_session),
    bot: Bot = Depends(get_bot),
) -> dict:
    _require_review_permission(user, settings)
    item = await session.get(CareerPortfolioItem, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="career_item_not_found")
    try:
        item = await career_service.review_item(
            session,
            item,
            reviewer_id=user.id,
            decision=payload.decision,
            comment=payload.comment,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    owner = await session.get(User, item.user_id)
    if owner:
        if item.status == "verified":
            text = f"✓ Достижение «{item.title}» подтверждено ЭРА и теперь отмечено в портфолио."
        else:
            reason = item.admin_comment or "Нужно уточнить подтверждение."
            text = f"Проверка достижения «{item.title}»: пока не подтверждено.\n\n{reason}"
        await safe_send(bot, owner.telegram_id, text)
    return career_service.serialize_item(item)


@router.get("/recommendations/pending")
async def pending_recommendations(
    user: User = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
    session: AsyncSession = Depends(get_session),
) -> list[dict]:
    _require_review_permission(user, settings)
    rows = list(
        (
            await session.scalars(
                select(RecommendationRequest)
                .where(RecommendationRequest.status == "requested")
                .order_by(RecommendationRequest.requested_at, RecommendationRequest.id)
            )
        ).all()
    )
    owners: dict[int, User | None] = {}
    result: list[dict] = []
    for request in rows:
        if request.user_id not in owners:
            owners[request.user_id] = await session.get(User, request.user_id)
        payload = career_service.serialize_request(request)
        payload.update({"user_id": request.user_id, "user_name": _name(owners[request.user_id])})
        result.append(payload)
    return result


@router.post("/recommendations/{request_id}/review")
async def review_recommendation(
    request_id: int,
    payload: ReviewRecommendationIn,
    user: User = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
    session: AsyncSession = Depends(get_session),
    bot: Bot = Depends(get_bot),
) -> dict:
    _require_review_permission(user, settings)
    request = await session.get(RecommendationRequest, request_id)
    if request is None:
        raise HTTPException(status_code=404, detail="recommendation_not_found")
    try:
        if payload.decision == "approve":
            request = await career_service.approve_recommendation(
                session,
                request,
                reviewer_id=user.id,
                final_text=payload.final_text,
            )
        elif payload.decision == "reject":
            request = await career_service.reject_recommendation(
                session,
                request,
                reviewer_id=user.id,
                comment=payload.comment,
            )
        else:
            raise HTTPException(status_code=400, detail="invalid_decision")
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    owner = await session.get(User, request.user_id)
    if owner:
        if request.status == "approved":
            await safe_send(
                bot,
                owner.telegram_id,
                "📄 Официальное рекомендательное письмо ЭРА утверждено. Оно доступно в разделе «Моё портфолио».",
            )
        else:
            await safe_send(
                bot,
                owner.telegram_id,
                "Запрос на официальную рекомендацию рассмотрен. Открой «Моё портфолио», чтобы увидеть статус.",
            )
    return career_service.serialize_request(request)
