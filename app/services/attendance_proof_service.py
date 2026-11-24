from __future__ import annotations

import logging
from dataclasses import dataclass

from aiogram import Bot
from aiogram.types import BufferedInputFile, InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.event_experience import EventExperience
from app.database.models import AttendanceProof, Event, EventRegistration, User
from app.services.notification_service import safe_send, safe_send_document
from app.services.points_service import add_points, add_portfolio_item
from app.utils import texts
from app.utils.constants import RegistrationStatus

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ProofDecisionResult:
    proof: AttendanceProof
    points: int
    cert_note: str


async def list_pending_proofs(session: AsyncSession) -> list[AttendanceProof]:
    return list(
        (
            await session.scalars(
                select(AttendanceProof)
                .where(AttendanceProof.status == "pending")
                .order_by(AttendanceProof.created_at, AttendanceProof.id)
            )
        ).all()
    )


async def approve_proof(
    session: AsyncSession,
    proof: AttendanceProof,
    *,
    reviewer: User,
    bot: Bot | None = None,
) -> ProofDecisionResult:
    if proof.status != "pending":
        raise ValueError("proof_not_pending")

    event = await session.get(Event, proof.event_id)
    target = await session.get(User, proof.user_id)
    proof.status = "approved"
    proof.reviewed_by = reviewer.id

    registration = await session.scalar(
        select(EventRegistration).where(
            EventRegistration.event_id == proof.event_id,
            EventRegistration.user_id == proof.user_id,
        )
    )
    if registration:
        registration.status = RegistrationStatus.ATTENDED

    points = (event.points_for_visit if event else 5) + 5
    await add_points(
        session,
        user_id=proof.user_id,
        points=points,
        reason="Подтверждённое участие в мероприятии",
        approved_by=reviewer.id,
        related_event_id=proof.event_id,
        source_type="attendance_proof",
        source_id=proof.id,
        idempotency_key=f"attendance_proof:{proof.id}:approval",
    )
    await add_portfolio_item(
        session,
        user_id=proof.user_id,
        title=f"Участие: {event.title if event else 'мероприятие ЭРА'}",
        item_type="event",
        description="Участие подтверждено командой ЭРА",
        issued_by=reviewer.id,
        related_event_id=proof.event_id,
    )

    cert_note = ""
    experience = await session.get(EventExperience, event.id) if event else None
    if event is not None and (experience is None or experience.issue_certificate is not False):
        try:
            async with session.begin_nested():
                from app.services.certificate_pdf_service import build_certificate_pdf
                from app.services.certificate_service import auto_issue_participation_certificate

                issue = await auto_issue_participation_certificate(
                    session, reviewer, user_id=proof.user_id, event_id=proof.event_id
                )
                cert_note = f"\n\n📄 Сертификат участника: {issue.document_number}"
                if bot is not None and target is not None:
                    pdf = build_certificate_pdf(
                        issue.snapshot, number=issue.document_number, issued_at=issue.issued_at
                    )
                    await safe_send(bot, target.telegram_id, "Ваш сертификат участника ЭРА готов.")
                    await safe_send_document(
                        bot,
                        target.telegram_id,
                        BufferedInputFile(pdf, filename=f"ERA_certificate_{issue.document_number}.pdf"),
                    )
        except Exception as exc:  # noqa: BLE001 — approval must not roll back
            logger.exception("auto certificate failed: %s", exc)
            cert_note = "\n\n(Сертификат будет выдан отдельно — обратитесь к команде ЭРА.)"

    if bot is not None and target is not None:
        feedback_keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="Оставить обратную связь",
                        callback_data=f"feedback:start:{proof.event_id}",
                    )
                ]
            ]
        )
        await safe_send(
            bot,
            target.telegram_id,
            texts.SELFIE_APPROVED.format(points=points) + cert_note,
            reply_markup=feedback_keyboard,
        )

    await session.commit()
    await session.refresh(proof)
    return ProofDecisionResult(proof=proof, points=points, cert_note=cert_note)


async def reject_proof(
    session: AsyncSession,
    proof: AttendanceProof,
    *,
    reviewer: User,
    comment: str,
    bot: Bot | None = None,
) -> AttendanceProof:
    if proof.status != "pending":
        raise ValueError("proof_not_pending")
    proof.status = "rejected"
    proof.reviewed_by = reviewer.id
    proof.admin_comment = (comment or "").strip()[:500] or None
    target = await session.get(User, proof.user_id)
    await session.commit()
    await session.refresh(proof)
    if bot is not None and target is not None:
        await safe_send(
            bot,
            target.telegram_id,
            texts.SELFIE_REJECTED.format(comment=proof.admin_comment or "без комментария"),
        )
    return proof
