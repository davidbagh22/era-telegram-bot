"""Human-confirmed event certificates; no implicit awards or external sends."""
import hashlib
import json
from datetime import datetime, timezone

from sqlalchemy import select, text

from app.database.certificate_models import CertificateIssue
from app.database.models import Event, EventRegistration, PortfolioItem, User
from app.services.audit_service import audit
from app.services.staff_access_service import can_operate_queue
from app.utils.constants import ApplicationStatus, RegistrationStatus

TEMPLATE_VERSION = "era-event-v1"


async def require_issuer(session, actor, settings):
    if not await can_operate_queue(session, actor, settings, "portfolio.review"):
        raise PermissionError("certificate_access_denied")


async def _lock(session, key):
    if session.bind.dialect.name == "postgresql":
        lock = int.from_bytes(hashlib.sha256(key.encode()).digest()[:8], "big", signed=True)
        await session.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": lock})


async def certificate_snapshot(session, user_id, event_id, signatory):
    signatory = (signatory or "").strip()
    if not 3 <= len(signatory) <= 150 or "\n" in signatory or "\r" in signatory:
        raise ValueError("Укажите подписанта одной строкой, от 3 до 150 символов.")
    target = await session.scalar(select(User).where(User.id == user_id).execution_options(populate_existing=True))
    event = await session.scalar(select(Event).where(Event.id == event_id).execution_options(populate_existing=True))
    reg = await session.scalar(select(EventRegistration).where(EventRegistration.user_id == user_id,
                                                             EventRegistration.event_id == event_id))
    if (not target or target.is_blocked or target.is_archived
            or target.application_status != ApplicationStatus.APPROVED
            or not event or not reg or reg.status != RegistrationStatus.ATTENDED):
        raise ValueError("Выдача доступна только одобренному участнику с подтверждённым посещением.")
    return dict(full_name=f"{target.first_name} {target.last_name or ''}".strip(),
                event_title=event.title, event_date=event.event_date.isoformat(),
                signatory=signatory, template_version=TEMPLATE_VERSION)


def snapshot_hash(snapshot):
    return hashlib.sha256(json.dumps(snapshot, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


async def issue_certificate(session, actor, settings, *, user_id, event_id, signatory, request_key, expected_hash):
    await require_issuer(session, actor, settings)
    if not request_key or len(request_key) > 64:
        raise ValueError("invalid_certificate_request")
    basis = f"event:{event_id}:user:{user_id}"
    await _lock(session, basis)
    existing_request = await session.scalar(select(CertificateIssue).where(CertificateIssue.request_key == request_key))
    if existing_request:
        if existing_request.basis_key != basis or snapshot_hash(existing_request.snapshot) != expected_hash:
            raise ValueError("certificate_request_conflict")
        return existing_request
    snapshot = await certificate_snapshot(session, user_id, event_id, signatory)
    if snapshot_hash(snapshot) != expected_hash:
        raise ValueError("Данные изменились. Подготовьте новый предпросмотр.")
    previous = await session.scalar(select(CertificateIssue).where(CertificateIssue.basis_key == basis)
                                    .order_by(CertificateIssue.revision.desc()).limit(1))
    if previous and previous.status == "issued":
        if previous.snapshot != snapshot:
            raise ValueError("Сертификат уже выдан. Перед исправлением отзовите прежний документ.")
        return previous
    now = datetime.now(timezone.utc)
    item = PortfolioItem(user_id=user_id, title=f"Участие: {snapshot['event_title']}", item_type="certificate",
                         description="Подтверждённое участие в мероприятии ЭРА", related_event_id=event_id,
                         issued_by=actor.id, verified_by=actor.id, status="verified", issued_at=now.date())
    session.add(item)
    await session.flush()
    issue = CertificateIssue(user_id=user_id, event_id=event_id, portfolio_item_id=item.id,
                             basis_key=basis, revision=previous.revision + 1 if previous else 1,
                             request_key=request_key, snapshot=snapshot, issued_by=actor.id, issued_at=now,
                             status="issued")
    session.add(issue)
    await session.flush()
    item.description = f"{issue.document_number}. Подтверждённое участие в мероприятии ЭРА."
    await audit(session, actor_id=actor.id, action="certificate.issued", entity_type="certificate", entity_id=issue.id,
                new_value={"number": issue.document_number, "revision": issue.revision, "template": TEMPLATE_VERSION})
    return issue


async def revoke_certificate(session, actor, settings, issue_id, reason):
    await require_issuer(session, actor, settings)
    if not reason or not 3 <= len(reason.strip()) <= 1000:
        raise ValueError("Укажите причину отзыва от 3 до 1000 символов.")
    issue = await session.get(CertificateIssue, issue_id)
    if issue is None:
        raise ValueError("Сертификат не найден.")
    await _lock(session, issue.basis_key)
    issue = await session.scalar(select(CertificateIssue).where(CertificateIssue.id == issue_id)
                                 .with_for_update().execution_options(populate_existing=True))
    if issue.status == "revoked":
        return issue
    issue.status, issue.revoked_by = "revoked", actor.id
    issue.revoked_at, issue.revocation_reason = datetime.now(timezone.utc), reason.strip()
    item = await session.get(PortfolioItem, issue.portfolio_item_id)
    item.status = "revoked"
    await audit(session, actor_id=actor.id, action="certificate.revoked", entity_type="certificate", entity_id=issue.id,
                new_value={"reason": reason.strip()})
    return issue
