from __future__ import annotations

from datetime import date
from io import BytesIO
import re

from aiogram import Bot
from aiogram.types import BufferedInputFile
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_bot, get_current_user, get_session, get_settings
from app.config import Settings
from app.database.career_models import CareerPortfolioItem, RecommendationRequest
from app.database.models import User
from app.services import career_service
from app.services.career_pdf_service import build_career_resume, build_official_recommendation
from app.services.portfolio_service import build_portfolio_data

router = APIRouter(prefix="/career", tags=["career"])

MAX_EVIDENCE_BYTES = 10 * 1024 * 1024
ALLOWED_CONTENT_TYPES = {
    "application/pdf",
    "image/jpeg",
    "image/png",
    "image/webp",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}


class CareerProfileIn(BaseModel):
    headline: str | None = Field(default=None, max_length=180)
    about: str | None = Field(default=None, max_length=1200)
    languages: list[dict[str, str]] | None = None


class CareerItemIn(BaseModel):
    item_type: str
    title: str = Field(min_length=1, max_length=255)
    organization: str | None = Field(default=None, max_length=255)
    description: str | None = Field(default=None, max_length=3000)
    issued_at: date | None = None
    url: str | None = Field(default=None, max_length=500)
    include_in_resume: bool = True


class CareerItemPatch(BaseModel):
    item_type: str | None = None
    title: str | None = Field(default=None, max_length=255)
    organization: str | None = Field(default=None, max_length=255)
    description: str | None = Field(default=None, max_length=3000)
    issued_at: date | None = None
    url: str | None = Field(default=None, max_length=500)
    include_in_resume: bool | None = None


class PurposeIn(BaseModel):
    purpose: str = "universal"


def _owned_item(item: CareerPortfolioItem | None, user: User) -> CareerPortfolioItem:
    if item is None or item.user_id != user.id:
        raise HTTPException(status_code=404, detail="career_item_not_found")
    return item


def _owned_request(request: RecommendationRequest | None, user: User) -> RecommendationRequest:
    if request is None or request.user_id != user.id:
        raise HTTPException(status_code=404, detail="recommendation_not_found")
    return request


def _safe_filename(value: str | None) -> str:
    name = (value or "document").strip() or "document"
    name = re.sub(r"[^A-Za-zА-Яа-яЁё0-9._ -]+", "_", name)
    return name[:180] or "document"


def _http_value_error(exc: ValueError) -> HTTPException:
    code = str(exc)
    status = 409 if code in {"verified_item_locked", "item_not_pending", "request_not_pending"} else 400
    return HTTPException(status_code=status, detail=code)


@router.get("/dashboard")
async def read_dashboard(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    return await career_service.dashboard(session, user)


@router.patch("/profile")
async def patch_profile(
    payload: CareerProfileIn,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    profile = await career_service.update_profile(
        session,
        user.id,
        headline=payload.headline,
        about=payload.about,
        languages=payload.languages,
    )
    return {
        "headline": profile.headline or "",
        "about": profile.about or "",
        "languages": profile.languages or [],
    }


@router.post("/items")
async def add_item(
    payload: CareerItemIn,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    try:
        item = await career_service.create_item(
            session,
            user.id,
            item_type=payload.item_type,
            title=payload.title,
            organization=payload.organization,
            description=payload.description,
            issued_at=payload.issued_at,
            url=payload.url,
            include_in_resume=payload.include_in_resume,
        )
    except ValueError as exc:
        raise _http_value_error(exc) from exc
    return career_service.serialize_item(item)


@router.patch("/items/{item_id}")
async def patch_item(
    item_id: int,
    payload: CareerItemPatch,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    item = _owned_item(await session.get(CareerPortfolioItem, item_id), user)
    changes = payload.model_dump(exclude_unset=True)
    try:
        item = await career_service.update_item(session, item, **changes)
    except ValueError as exc:
        raise _http_value_error(exc) from exc
    return career_service.serialize_item(item)


@router.delete("/items/{item_id}")
async def delete_item(
    item_id: int,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, bool]:
    item = _owned_item(await session.get(CareerPortfolioItem, item_id), user)
    if item.status == "verified":
        raise HTTPException(status_code=409, detail="verified_item_locked")
    await session.delete(item)
    await session.commit()
    return {"deleted": True}


@router.post("/items/{item_id}/file")
async def upload_evidence(
    item_id: int,
    upload: UploadFile = File(...),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    bot: Bot = Depends(get_bot),
) -> dict:
    item = _owned_item(await session.get(CareerPortfolioItem, item_id), user)
    if item.status == "verified":
        raise HTTPException(status_code=409, detail="verified_item_locked")
    if upload.content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(status_code=415, detail="unsupported_evidence_type")
    content = await upload.read(MAX_EVIDENCE_BYTES + 1)
    if not content:
        raise HTTPException(status_code=400, detail="empty_evidence_file")
    if len(content) > MAX_EVIDENCE_BYTES:
        raise HTTPException(status_code=413, detail="evidence_file_too_large")
    filename = _safe_filename(upload.filename)
    try:
        sent = await bot.send_document(
            user.telegram_id,
            BufferedInputFile(content, filename=filename),
            caption=f"📎 Подтверждение для портфолио: {item.title[:120]}",
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail="evidence_storage_unavailable") from exc
    if sent.document is None:
        raise HTTPException(status_code=502, detail="evidence_storage_unavailable")
    item = await career_service.attach_file(
        session,
        item,
        file_id=sent.document.file_id,
        file_name=filename,
    )
    return career_service.serialize_item(item)


async def _download_telegram_file(bot: Bot, file_id: str) -> bytes:
    try:
        telegram_file = await bot.get_file(file_id)
        if not telegram_file.file_path:
            raise RuntimeError("missing_file_path")
        buffer = BytesIO()
        await bot.download_file(telegram_file.file_path, destination=buffer)
        return buffer.getvalue()
    except Exception as exc:
        raise HTTPException(status_code=502, detail="evidence_download_unavailable") from exc


@router.get("/items/{item_id}/file")
async def download_evidence(
    item_id: int,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    bot: Bot = Depends(get_bot),
) -> Response:
    item = _owned_item(await session.get(CareerPortfolioItem, item_id), user)
    if not item.file_id:
        raise HTTPException(status_code=404, detail="evidence_not_found")
    content = await _download_telegram_file(bot, item.file_id)
    return Response(
        content=content,
        media_type="application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{_safe_filename(item.file_name)}"'},
    )


@router.post("/items/{item_id}/verification")
async def submit_item_for_verification(
    item_id: int,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    item = _owned_item(await session.get(CareerPortfolioItem, item_id), user)
    try:
        item = await career_service.request_verification(session, item)
    except ValueError as exc:
        raise _http_value_error(exc) from exc
    return career_service.serialize_item(item)


@router.get("/resume.pdf")
async def download_resume(
    purpose: str = "universal",
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> Response:
    if purpose not in career_service.RESUME_PURPOSES:
        raise HTTPException(status_code=400, detail="invalid_purpose")
    profile = await career_service.get_or_create_profile(session, user.id)
    items = await career_service.list_items(session, user.id)
    portfolio = await build_portfolio_data(session, user)
    pdf = build_career_resume(user, profile, portfolio, items, purpose=purpose)
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="ERA_CV_{user.id}_{purpose}.pdf"'},
    )


@router.get("/recommendation/automatic")
async def read_automatic_recommendation(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    return await career_service.automatic_recommendation(session, user)


@router.post("/recommendation/request")
async def request_recommendation(
    payload: PurposeIn,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    try:
        request = await career_service.request_official_recommendation(
            session, user, payload.purpose
        )
    except ValueError as exc:
        raise _http_value_error(exc) from exc
    return career_service.serialize_request(request)


@router.get("/recommendation/{request_id}.pdf")
async def download_recommendation(
    request_id: int,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> Response:
    request = _owned_request(await session.get(RecommendationRequest, request_id), user)
    if request.status != "approved" or not request.verification_token:
        raise HTTPException(status_code=409, detail="recommendation_not_approved")
    verification_url = (
        f"{settings.effective_base_url}/api/v1/career/verify/{request.verification_token}"
        if settings.effective_base_url
        else f"/api/v1/career/verify/{request.verification_token}"
    )
    pdf = build_official_recommendation(user, request, verification_url=verification_url)
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{request.document_number}.pdf"'},
    )


@router.get("/verify/{token}")
async def verify_recommendation(
    token: str,
    session: AsyncSession = Depends(get_session),
) -> dict:
    request = await career_service.recommendation_by_token(session, token)
    if request is None or request.status != "approved":
        return {"valid": False}
    owner = await session.get(User, request.user_id)
    if owner is None:
        return {"valid": False}
    return {
        "valid": True,
        "document_number": request.document_number,
        "issued_to": " ".join(part for part in (owner.first_name, owner.last_name) if part),
        "issued_at": request.approved_at.date().isoformat() if request.approved_at else None,
        "issuer": "Объединение лидеров и культурных инициатив (ЭРА)",
    }
