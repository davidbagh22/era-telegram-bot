"""Explicit issuance with a rendered preview; participant downloads on demand."""
from uuid import uuid4

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import BufferedInputFile, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy import select

from app.database.certificate_models import CertificateIssue
from app.database.models import Event, EventRegistration, User
from app.services import certificate_service as service
from app.services.certificate_pdf_service import build_certificate_pdf
from app.services.staff_access_service import can_operate_queue
from app.utils.constants import ApplicationStatus, RegistrationStatus

router = Router(name="certificates")
router.message.filter(F.chat.type == "private")
router.callback_query.filter(F.message.chat.type == "private")


class CertificateFlow(StatesGroup):
    signatory = State()
    confirm = State()
    revoke = State()


def kb(rows):
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=t, callback_data=c)] for t, c in rows])


async def allowed(message, session, user, settings):
    if await can_operate_queue(session, user, settings, "portfolio.review"):
        return True
    await message.answer("Нет права на выдачу сертификатов.")
    return False


@router.message(Command("certificates"))
async def certificate_list(message: Message, user, session, settings):
    await show_list(message, user, session, settings)


async def show_list(message, user, session, settings, offset=0):
    if not user or user.application_status != ApplicationStatus.APPROVED or user.is_blocked or user.is_archived:
        await message.answer("Сертификаты доступны одобренным участникам.")
        return
    rows = list((await session.scalars(select(CertificateIssue).where(CertificateIssue.user_id == user.id)
                                       .order_by(CertificateIssue.id.desc()).offset(offset).limit(11))).all())
    buttons = [(f"{'Отозван • ' if row.status == 'revoked' else ''}{row.document_number}", f"cert:download:{row.id}") for row in rows[:10]]
    if offset:
        buttons.append(("← Назад", f"cert:list:{max(0,offset-10)}"))
    if len(rows) > 10:
        buttons.append(("Далее →", f"cert:list:{offset+10}"))
    if await can_operate_queue(session, user, settings, "portfolio.review"):
        buttons.append(("Выдать за подтверждённое участие", "cert:issue:0"))
    await message.answer("Мои сертификаты\n\n" + ("Выберите документ." if rows else "Выданных документов пока нет."), reply_markup=kb(buttons))


@router.callback_query(F.data.regexp(r"^cert:list:\d{1,6}$"))
async def certificate_page(call: CallbackQuery, user, session, settings):
    await call.answer()
    await show_list(call.message, user, session, settings, int(call.data.rsplit(":",1)[-1]))


@router.message(Command("issue_certificate"))
async def issue_start(message: Message, user, session, settings):
    await show_events(message, user, session, settings)


async def show_events(message, user, session, settings, offset=0):
    if not await allowed(message, session, user, settings):
        return
    events = list((await session.scalars(select(Event).where(Event.id.in_(
        select(EventRegistration.event_id).where(EventRegistration.status == RegistrationStatus.ATTENDED)))
        .order_by(Event.event_date.desc(), Event.id.desc()).offset(offset).limit(11))).all())
    rows = [(f"{e.event_date:%d.%m} • {e.title[:45]}", f"cert:event:{e.id}:0") for e in events[:10]]
    if offset:
        rows.append(("← Назад", f"cert:issue:{max(0,offset-10)}"))
    if len(events)>10:
        rows.append(("Далее →", f"cert:issue:{offset+10}"))
    await message.answer("Выберите мероприятие с подтверждёнными посещениями." if events else
                         "Нет мероприятий с подтверждёнными посещениями. Сначала зафиксируйте участие штатным способом.", reply_markup=kb(rows))


@router.callback_query(F.data.regexp(r"^cert:issue:\d{1,6}$"))
async def event_page(call: CallbackQuery, user, session, settings):
    await call.answer()
    await show_events(call.message, user, session, settings, int(call.data.rsplit(":",1)[-1]))


@router.callback_query(F.data.regexp(r"^cert:event:\d+:\d{1,6}$"))
async def event_people(call: CallbackQuery, user, session, settings):
    await call.answer()
    if not await allowed(call.message, session, user, settings):
        return
    event_id, offset = map(int, call.data.split(":")[-2:])
    people = list((await session.scalars(select(User).join(EventRegistration, EventRegistration.user_id == User.id)
        .where(EventRegistration.event_id == event_id, EventRegistration.status == RegistrationStatus.ATTENDED,
               User.application_status == ApplicationStatus.APPROVED, User.is_blocked.is_(False), User.is_archived.is_(False))
        .order_by(User.last_name, User.first_name, User.id).offset(offset).limit(11))).all())
    rows = [(f"{p.first_name} {p.last_name or ''}"[:60], f"cert:person:{event_id}:{p.id}") for p in people[:10]]
    if offset:
        rows.append(("← Назад", f"cert:event:{event_id}:{max(0,offset-10)}"))
    if len(people)>10:
        rows.append(("Далее →", f"cert:event:{event_id}:{offset+10}"))
    await call.message.answer("Выберите участника. Выдаются только подтверждённые посещения.", reply_markup=kb(rows))


@router.callback_query(F.data.regexp(r"^cert:person:\d+:\d+$"))
async def select_person(call: CallbackQuery, user, session, settings, state: FSMContext):
    await call.answer()
    if not await allowed(call.message, session, user, settings):
        return
    event_id, user_id = map(int, call.data.split(":")[-2:])
    await state.set_state(CertificateFlow.signatory)
    await state.update_data(cert_event=event_id, cert_user=user_id)
    await call.message.answer("Укажите ФИО и должность подписанта одной строкой. Подтвердите его полномочия перед выдачей. /cancel - отменить.")


@router.message(CertificateFlow.signatory)
async def preview(message: Message, user, session, settings, state: FSMContext):
    if not await allowed(message, session, user, settings):
        await state.clear()
        return
    data = await state.get_data()
    try:
        snapshot = await service.certificate_snapshot(session, data["cert_user"], data["cert_event"], message.text)
    except ValueError as exc:
        await message.answer(str(exc), parse_mode=None)
        return
    key = uuid4().hex
    await state.update_data(cert_snapshot=snapshot, cert_hash=service.snapshot_hash(snapshot), cert_key=key)
    await state.set_state(CertificateFlow.confirm)
    await message.answer_document(BufferedInputFile(build_certificate_pdf(snapshot), filename="ERA_certificate_preview.pdf"),
        caption="Проверьте ФИО, событие, дату, подписанта и оформление. Подтверждением вы утверждаете этот шаблон и основание выдачи. Факсимиле и цифровая подпись не добавляются.",
        reply_markup=kb([("Подтвердить выдачу", f"cert:confirm:{key}")]))


@router.callback_query(F.data.regexp(r"^cert:confirm:[a-f0-9]{32}$"))
async def confirm(call: CallbackQuery, user, session, settings, state: FSMContext):
    await call.answer()
    if not await allowed(call.message, session, user, settings):
        return
    data = await state.get_data()
    if call.data.rsplit(":",1)[-1] != data.get("cert_key"):
        await call.message.answer("Предпросмотр устарел. Откройте /issue_certificate заново.")
        return
    try:
        issue = await service.issue_certificate(session, user, settings, user_id=data["cert_user"], event_id=data["cert_event"],
            signatory=data["cert_snapshot"]["signatory"], request_key=data["cert_key"], expected_hash=data["cert_hash"])
        await session.commit()
    except (ValueError, PermissionError) as exc:
        await call.message.answer(str(exc), parse_mode=None)
        return
    await state.clear()
    await call.message.answer(f"{issue.document_number}: {'отозван' if issue.status == 'revoked' else 'выдан'}. Документ сохранён в портфолио. Участник может скачать его через /certificates.",
                              reply_markup=kb([("Скачать документ", f"cert:download:{issue.id}")]))


@router.callback_query(F.data.regexp(r"^cert:download:\d+$"))
async def download(call: CallbackQuery, user, session, settings):
    await call.answer()
    issue = await session.get(CertificateIssue, int(call.data.rsplit(":",1)[-1]))
    staff = await can_operate_queue(session, user, settings, "portfolio.review")
    if (not user or not issue or user.is_blocked or user.is_archived
            or user.application_status != ApplicationStatus.APPROVED
            or (issue.user_id != user.id and not staff)):
        await call.message.answer("Документ недоступен.")
        return
    await call.message.answer_document(BufferedInputFile(build_certificate_pdf(issue.snapshot, number=issue.document_number,
        issued_at=issue.issued_at, revoked=issue.status == "revoked"), filename=f"{issue.document_number}.pdf"),
        caption=f"{issue.document_number} • {'ОТОЗВАН' if issue.status == 'revoked' else 'Выдан'}",
        reply_markup=kb([("Отозвать документ", f"cert:revoke:{issue.id}")]) if staff and issue.status == "issued" else None)


@router.callback_query(F.data.regexp(r"^cert:revoke:\d+$"))
async def revoke_start(call: CallbackQuery, user, session, settings, state: FSMContext):
    await call.answer()
    if not await allowed(call.message, session, user, settings):
        return
    await state.set_state(CertificateFlow.revoke)
    await state.update_data(cert_revoke=int(call.data.rsplit(":",1)[-1]))
    await call.message.answer("Укажите причину отзыва. Документ останется в истории, но перестанет быть подтверждённым достижением. /cancel - отменить.")


@router.message(CertificateFlow.revoke)
async def revoke_finish(message: Message, user, session, settings, state: FSMContext):
    data = await state.get_data()
    try:
        issue = await service.revoke_certificate(session, user, settings, data["cert_revoke"], message.text)
        await session.commit()
    except (ValueError, PermissionError) as exc:
        await message.answer(str(exc), parse_mode=None)
        return
    await state.clear()
    await message.answer(f"{issue.document_number} отозван. Для исправленного документа создайте новый предпросмотр.")
