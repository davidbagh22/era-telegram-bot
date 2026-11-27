from __future__ import annotations

from datetime import date
from io import BytesIO
import re

from aiogram import Bot
from aiogram.types import BufferedInputFile
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_bot, get_current_user, get_session, get_settings
from app.config import Settings
from app.database.career_models import CareerPortfolioItem, RecommendationRequest
from app.database.certificate_models import CertificateIssue
from app.database.models import User
from app.services import career_service
from app.services.career_pdf_service import RESUME_MODES, build_official_recommendation
from app.services.resume_export_service import (
    ResumeAttachmentError,
    assemble_resume_export,
    attachment_preview,
    attachments_caption,
    encode_manifest_header,
    parse_skip_keys,
    telegram_file_fetcher,
)

router = APIRouter(prefix="/career", tags=["career"])


@router.get("/certificates")
async def my_certificates(user: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)):
    rows = (await session.scalars(select(CertificateIssue).where(CertificateIssue.user_id == user.id)
                                  .order_by(CertificateIssue.id.desc()))).all()
    return [{"id": row.id, "number": row.document_number, "title": row.snapshot["event_title"],
             "status": row.status, "issued_at": row.issued_at.isoformat()} for row in rows]


@router.get("/certificates/{issue_id}.pdf")
async def certificate_pdf(issue_id: int, user: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)):
    from app.services.certificate_pdf_service import build_certificate_pdf
    issue = await session.get(CertificateIssue, issue_id)
    if issue is None or issue.user_id != user.id:
        raise HTTPException(status_code=404, detail="certificate_not_found")
    return Response(build_certificate_pdf(issue.snapshot, number=issue.document_number, issued_at=issue.issued_at,
                                           revoked=issue.status == "revoked"), media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="{issue.document_number}.pdf"',
                             "Cache-Control": "private, no-store"})

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
    skills: list[str] | None = None


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
    mode: str = "portfolio"
    attach_certificates: bool = False
    skip: list[str] = Field(default_factory=list, max_length=50)


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
        skills=payload.skills,
    )
    await session.refresh(user)
    return {
        "headline": profile.headline or "",
        "about": profile.about or "",
        "languages": profile.languages or [],
        "skills": [str(skill).strip() for skill in (user.skills or []) if str(skill).strip()],
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
    if item.status in {"verified", "revoked"}:
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
    if item.status in {"verified", "revoked"}:
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


def _attachment_error(exc: ResumeAttachmentError) -> HTTPException:
    return HTTPException(status_code=409, detail=exc.detail())


def _skip_keys_or_400(raw) -> frozenset[str]:
    try:
        return parse_skip_keys(raw)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="invalid_skip_keys") from exc


@router.get("/resume/attachments")
async def resume_attachments_preview(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    return await attachment_preview(session, user.id)


@router.get("/resume.pdf")
async def download_resume(
    purpose: str = "universal",
    mode: str = "portfolio",
    attach_certificates: bool = False,
    skip: str | None = None,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    bot: Bot = Depends(get_bot),
) -> Response:
    if purpose not in career_service.RESUME_PURPOSES:
        raise HTTPException(status_code=400, detail="invalid_purpose")
    if mode not in RESUME_MODES:
        raise HTTPException(status_code=400, detail="invalid_resume_mode")
    try:
        export = await assemble_resume_export(
            session,
            user,
            purpose=purpose,
            mode=mode,
            attach=attach_certificates,
            fetch_file=telegram_file_fetcher(bot),
            skip_keys=_skip_keys_or_400(skip),
        )
    except ResumeAttachmentError as exc:
        raise _attachment_error(exc) from exc
    filename = f"ERA_{mode}_{user.id}_{purpose}.pdf"
    return Response(
        content=export.pdf,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "X-ERA-Resume-Manifest": encode_manifest_header(export.manifest),
            "X-ERA-Attached-Count": str(len(export.manifest["attached"])),
            "Access-Control-Expose-Headers": "X-ERA-Resume-Manifest, X-ERA-Attached-Count",
            "Cache-Control": "private, no-store",
        },
    )


@router.post("/resume/send")
async def send_resume_to_bot_chat(
    payload: PurposeIn,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    bot: Bot = Depends(get_bot),
) -> dict:
    if payload.purpose not in career_service.RESUME_PURPOSES:
        raise HTTPException(status_code=400, detail="invalid_purpose")
    if payload.mode not in RESUME_MODES:
        raise HTTPException(status_code=400, detail="invalid_resume_mode")
    try:
        export = await assemble_resume_export(
            session,
            user,
            purpose=payload.purpose,
            mode=payload.mode,
            attach=payload.attach_certificates,
            fetch_file=telegram_file_fetcher(bot),
            skip_keys=_skip_keys_or_400(payload.skip),
        )
    except ResumeAttachmentError as exc:
        raise _attachment_error(exc) from exc
    caption = "Твоё портфолио ЭРА готово."
    extra = attachments_caption(export.manifest)
    if extra:
        caption = f"{caption}\n{extra}"
    try:
        sent = await bot.send_document(
            user.telegram_id,
            BufferedInputFile(export.pdf, filename="Портфолио_ЭРА.pdf"),
            caption=caption,
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail="resume_delivery_unavailable") from exc
    if sent.document is None:
        raise HTTPException(status_code=502, detail="resume_delivery_unavailable")
    return {"sent": True, "manifest": export.manifest}


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
