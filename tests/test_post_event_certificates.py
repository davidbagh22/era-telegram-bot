import asyncio
from datetime import date, datetime, time, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import app.database  # noqa: F401
from app.config import Settings
from app.database.base import Base
from app.database.certificate_models import CertificateIssue
from app.database.event_experience import EventExperience
from app.database.models import AppSetting, AttendanceProof, Event, EventRegistration, PermissionGrant, PortfolioItem, User
from app.handlers import post_event_certificates as handlers
from app.services import attendance_proof_service, certificate_service
from app.services import post_event_certificate_service as service
from app.services.notification_service import NotificationDeliveryResult
from app.utils.constants import ApplicationStatus, EventStatus, RegistrationStatus, Role

NOW = datetime(2026, 11, 20, 12, 0, tzinfo=timezone.utc)  # 16:00 in Asia/Yerevan


def run(coro):
    return asyncio.run(coro)


async def make_db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return engine, async_sessionmaker(engine, expire_on_commit=False)


def sent(status="sent"):
    return NotificationDeliveryResult(sent=status == "sent", status=status, duplicate=False, attempt_count=1)


async def seed(session, *, owner_is_chair=True):
    owner = User(telegram_id=9001, first_name="Давид", application_status=ApplicationStatus.APPROVED)
    lead = User(telegram_id=9002, first_name="Ответственный", application_status=ApplicationStatus.APPROVED)
    outsider = User(telegram_id=9003, first_name="Участник", application_status=ApplicationStatus.APPROVED)
    ann = User(telegram_id=9101, first_name="Анна", last_name="Был", application_status=ApplicationStatus.APPROVED)
    boris = User(telegram_id=9102, first_name="Борис", last_name="Записан", application_status=ApplicationStatus.APPROVED)
    vera = User(telegram_id=9103, first_name="Вера", last_name="Отменила", application_status=ApplicationStatus.APPROVED)
    gleb = User(telegram_id=9104, first_name="Глеб", last_name="Ожидание", application_status=ApplicationStatus.APPROVED)
    dina = User(telegram_id=9105, first_name="Дина", last_name="Заблокирована",
                application_status=ApplicationStatus.APPROVED, is_blocked=True)
    session.add_all([owner, lead, outsider, ann, boris, vera, gleb, dina])
    await session.flush()

    def event(title, day, at=time(10), status=EventStatus.PUBLISHED):
        return Event(title=title, description="Тест", event_date=day, event_time=at, location="Ереван",
                     format="offline", created_by=owner.id, responsible_id=lead.id, status=status)

    ended = event("Форум лидеров", date(2026, 11, 20))
    upcoming = event("Вечерняя встреча", date(2026, 11, 20), time(18))
    old = event("Прошлый проект", date(2026, 11, 10))
    cancelled = event("Отменённое", date(2026, 11, 20), status=EventStatus.CANCELLED)
    empty = event("Без регистраций", date(2026, 11, 20))
    late = event("Ночной квиз", date(2026, 11, 19), time(21))
    session.add_all([ended, upcoming, old, cancelled, empty, late])
    await session.flush()
    session.add(EventExperience(event_id=late.id, end_time=time(1)))
    regs = [
        (ended, ann, RegistrationStatus.ATTENDED), (ended, boris, RegistrationStatus.REGISTERED),
        (ended, vera, RegistrationStatus.CANCELLED), (ended, gleb, RegistrationStatus.WAITLIST),
        (ended, dina, RegistrationStatus.REGISTERED),
        (upcoming, ann, RegistrationStatus.REGISTERED), (old, ann, RegistrationStatus.REGISTERED),
        (cancelled, ann, RegistrationStatus.REGISTERED), (late, boris, RegistrationStatus.WILL_COME),
    ]
    session.add_all([EventRegistration(event_id=e.id, user_id=u.id, status=s) for e, u, s in regs])
    await session.commit()
    settings = Settings(bot_token="0000000000:TEST", timezone="Asia/Yerevan",
                        era_chair_user_id=owner.id if owner_is_chair else None)
    return SimpleNamespace(settings=settings, owner=owner, lead=lead, outsider=outsider, ann=ann, boris=boris,
                           vera=vera, gleb=gleb, dina=dina, ended=ended, upcoming=upcoming, old=old,
                           cancelled=cancelled, empty=empty, late=late)


async def review_keys(session):
    return set(await session.scalars(select(AppSetting.key).where(AppSetting.key.like("post-event-certs:%"))))


def test_scan_creates_one_request_per_freshly_ended_event_and_notifies_owner_once():
    async def scenario():
        engine, factory = await make_db()
        try:
            async with factory() as session:
                d = await seed(session)
            send = AsyncMock(return_value=sent())
            with patch("app.services.notification_service.safe_send_once", send):
                await service.scan_ended_events(SimpleNamespace(), d.settings, factory, now=NOW)
                await service.scan_ended_events(SimpleNamespace(), d.settings, factory, now=NOW)
            async with factory() as session:
                keys = await review_keys(session)
                assert keys == {
                    f"post-event-certs:review:{d.ended.id}", f"post-event-certs:notice-done:{d.ended.id}",
                    f"post-event-certs:review:{d.late.id}", f"post-event-certs:notice-done:{d.late.id}",
                }
                review = await service.load_review(session, d.ended.id)
                assert review.value["state"] == "open"
                assert review.value["selected"] == [d.ann.id]  # attendance marks preselect, nobody else
                assert await session.scalar(select(func.count()).select_from(CertificateIssue)) == 0
            # Two events, owner + responsible each, and the second scan sent nothing new.
            assert send.await_count == 4
            chats = sorted(call.args[2] for call in send.await_args_list)
            assert chats == [9001, 9001, 9002, 9002]
            first = next(c for c in send.await_args_list if f":{d.ended.id}:" in c.kwargs["delivery_key"])
            assert "Форум лидеров" in first.args[3] and "Зарегистрировались: 3" in first.args[3]
            assert "Отметили присутствие: 1" in first.args[3]
            assert first.kwargs["reply_markup"].inline_keyboard[0][0].callback_data == f"pec:v:{d.ended.id}:0"
        finally:
            await engine.dispose()
    run(scenario())


def test_scan_without_any_recipient_keeps_request_and_records_outcome():
    async def scenario():
        engine, factory = await make_db()
        try:
            async with factory() as session:
                d = await seed(session, owner_is_chair=False)
                d.lead.is_archived = True
                await session.commit()
            send = AsyncMock(return_value=sent())
            with patch("app.services.notification_service.safe_send_once", send):
                await service.scan_ended_events(SimpleNamespace(), d.settings, factory, now=NOW)
            send.assert_not_awaited()
            async with factory() as session:
                done = await session.scalar(select(AppSetting).where(
                    AppSetting.key == f"post-event-certs:notice-done:{d.ended.id}"))
                assert done.value["outcome"] == "no_recipient"
                assert await service.load_review(session, d.ended.id) is not None
        finally:
            await engine.dispose()
    run(scenario())


def test_scan_is_disabled_by_flag_and_skips_events_where_everyone_has_a_certificate():
    async def scenario():
        engine, factory = await make_db()
        try:
            async with factory() as session:
                d = await seed(session)
                for person in (d.ann, d.boris):
                    await certificate_service.issue_post_event_certificate(
                        session, d.owner, user_id=person.id, event_id=d.ended.id)
                await session.commit()
            send = AsyncMock(return_value=sent())
            off = d.settings.model_copy(update={"post_event_certificate_review_enabled": False})
            with patch("app.services.notification_service.safe_send_once", send):
                await service.scan_ended_events(SimpleNamespace(), off, factory, now=NOW)
                async with factory() as session:
                    assert await review_keys(session) == set()
                await service.scan_ended_events(SimpleNamespace(), d.settings, factory, now=NOW)
            async with factory() as session:
                review = await service.load_review(session, d.ended.id)
                assert review.value["state"] == "covered"
                assert f"post-event-certs:notice-done:{d.ended.id}" not in await review_keys(session)
            assert all(f":{d.ended.id}:" not in c.kwargs["delivery_key"] for c in send.await_args_list)
        finally:
            await engine.dispose()
    run(scenario())


def test_only_owner_responsible_and_event_managers_may_review():
    async def scenario():
        engine, factory = await make_db()
        try:
            async with factory() as session:
                d = await seed(session)
                await service.ensure_review(session, d.ended, source="test")
                admin = User(telegram_id=9201, first_name="Админ", role=Role.ADMIN,
                             application_status=ApplicationStatus.APPROVED)
                manager = User(telegram_id=9202, first_name="Менеджер", application_status=ApplicationStatus.APPROVED)
                blocked_admin = User(telegram_id=9203, first_name="Бывший", role=Role.ADMIN, is_blocked=True,
                                     application_status=ApplicationStatus.APPROVED)
                session.add_all([admin, manager, blocked_admin])
                await session.flush()
                session.add(PermissionGrant(user_id=manager.id, permission="events.manage", scope_type="global",
                                            scope_id=0, is_active=True, granted_by=admin.id))
                await session.commit()
                await session.refresh(manager, attribute_names=["permission_grants"])
                s = d.settings
                for allowed in (d.owner, d.lead, admin, manager):
                    assert await service.can_review(session, allowed, s, d.ended), allowed.first_name
                for denied in (d.outsider, d.ann, blocked_admin, None):
                    assert not await service.can_review(session, denied, s, d.ended)
                with pytest.raises(PermissionError):
                    await service.change_selection(session, d.outsider, s, d.ended.id, "all")
                with pytest.raises(PermissionError):
                    await service.confirm(session, d.outsider, s, d.ended.id, 0)
                assert d.ended.id not in [e.id for e, _ in await service.list_reviews(session, d.outsider, s)]
                assert d.ended.id in [e.id for e, _ in await service.list_reviews(session, d.lead, s)]
        finally:
            await engine.dispose()
    run(scenario())


def test_confirm_issues_once_queues_delivery_and_shows_in_profile():
    async def scenario():
        engine, factory = await make_db()
        try:
            async with factory() as session:
                d = await seed(session)
                await service.ensure_review(session, d.ended, source="test")
                await session.commit()
                s = d.settings
                with pytest.raises(service.ReviewError):
                    await service.change_selection(session, d.owner, s, d.ended.id, "toggle", d.vera.id)
                row = await service.change_selection(session, d.owner, s, d.ended.id, "all")
                assert row.value["selected"] == sorted([d.ann.id, d.boris.id])  # not cancelled/waitlist/blocked
                await service.change_selection(session, d.owner, s, d.ended.id, "toggle", d.boris.id)
                row = await service.change_selection(session, d.owner, s, d.ended.id, "toggle", d.boris.id)
                rev = row.value["rev"]
                await session.commit()

                with pytest.raises(service.StaleReview):
                    await service.confirm(session, d.owner, s, d.ended.id, rev - 1)
                result = await service.confirm(session, d.owner, s, d.ended.id, rev)
                await session.commit()
                assert sorted(result.issued) == ["Анна Был", "Борис Записан"] and not result.skipped

                # A repeated press of the same confirmation button issues and queues nothing.
                with pytest.raises(service.StaleReview):
                    await service.confirm(session, d.owner, s, d.ended.id, rev)
                with pytest.raises(service.ReviewError):
                    await service.change_selection(session, d.owner, s, d.ended.id, "toggle", d.ann.id)

                issues = list(await session.scalars(select(CertificateIssue).order_by(CertificateIssue.user_id)))
                assert [(i.user_id, i.status, i.issued_by) for i in issues] == [
                    (d.ann.id, "issued", d.owner.id), (d.boris.id, "issued", d.owner.id)]
                pending = set(await session.scalars(select(AppSetting.key).where(
                    AppSetting.key.like("event-certificate:%"))))
                assert pending == {f"event-certificate:pending:{i.id}" for i in issues}
                boris_reg = await session.scalar(select(EventRegistration).where(
                    EventRegistration.user_id == d.boris.id, EventRegistration.event_id == d.ended.id))
                assert boris_reg.status == RegistrationStatus.REGISTERED  # no attendance or points side effects
                items = list(await session.scalars(select(PortfolioItem).where(PortfolioItem.user_id == d.boris.id)))
                assert [(i.item_type, i.status, i.related_event_id) for i in items] == [
                    ("certificate", "verified", d.ended.id)]
                review = await service.load_review(session, d.ended.id)
                assert review.value["selected"] == [] and review.value["history"][-1]["issued"] == 2
        finally:
            await engine.dispose()
    run(scenario())


def test_existing_or_revoked_certificates_are_never_duplicated_or_reissued():
    async def scenario():
        engine, factory = await make_db()
        try:
            async with factory() as session:
                d = await seed(session)
                s = d.settings
                earlier, created = await certificate_service.issue_post_event_certificate(
                    session, d.owner, user_id=d.ann.id, event_id=d.ended.id)
                assert created
                again, created = await certificate_service.issue_post_event_certificate(
                    session, d.owner, user_id=d.ann.id, event_id=d.ended.id)
                assert again.id == earlier.id and not created
                earlier.status = "revoked"
                await session.commit()
                await service.ensure_review(session, d.ended, source="test")
                people = {c.user_id: c for c in await service.candidates(session, d.ended.id)}
                assert not people[d.ann.id].selectable and people[d.ann.id].certificate_status == "revoked"
                review = await service.load_review(session, d.ended.id)
                assert review.value["selected"] == []  # the attended person is covered by the revoked one
                review.value = {**review.value, "selected": [d.ann.id, d.boris.id]}
                await session.commit()
                result = await service.confirm(session, d.owner, s, d.ended.id, 0)
                await session.commit()
                assert result.already == ["Анна Был"] and result.issued == ["Борис Записан"]
                assert await session.scalar(select(func.count()).select_from(CertificateIssue).where(
                    CertificateIssue.user_id == d.ann.id)) == 1
                assert not await certificate_service.enqueue_certificate_delivery(session, earlier.id)
        finally:
            await engine.dispose()
    run(scenario())


def test_failed_delivery_is_reported_and_not_blindly_retried():
    async def scenario():
        engine, factory = await make_db()
        try:
            async with factory() as session:
                d = await seed(session)
                await service.ensure_review(session, d.ended, source="test")
                await service.change_selection(session, d.owner, d.settings, d.ended.id, "all")
                rev = (await service.load_review(session, d.ended.id)).value["rev"]
                await service.confirm(session, d.owner, d.settings, d.ended.id, rev)
                await session.commit()
            outcomes = {9101: sent(), 9102: sent("uncertain")}
            send = AsyncMock(side_effect=lambda bot, settings, chat_id, *a, **k: outcomes[chat_id])
            with patch("app.services.notification_service.safe_send_once", send):
                await certificate_service.deliver_requested_certificates(SimpleNamespace(), d.settings, factory)
                await certificate_service.deliver_requested_certificates(SimpleNamespace(), d.settings, factory)
            assert sorted(c.args[2] for c in send.await_args_list) == [9101, 9102]
            assert all(c.kwargs["max_attempts"] == 1 for c in send.await_args_list)
            async with factory() as session:
                summary = await service.delivery_summary(session, d.ended.id)
                assert (summary.sent, summary.pending, summary.attention) == (1, 0, ["Борис Записан"])
        finally:
            await engine.dispose()
    run(scenario())


def test_event_end_uses_end_time_crossing_midnight_and_default_duration():
    ev = SimpleNamespace(event_date=date(2026, 11, 19), event_time=time(21))
    assert service.event_ends_at(ev, SimpleNamespace(end_time=time(1)), "Asia/Yerevan") == datetime(
        2026, 11, 19, 22, 0, tzinfo=timezone.utc)
    assert service.event_ends_at(ev, None, "Asia/Yerevan") == datetime(2026, 11, 19, 21, 0, tzinfo=timezone.utc)


class FakeCall:
    def __init__(self, data):
        self.data = data
        self.answer = AsyncMock()
        self.message = SimpleNamespace(edit_text=AsyncMock(), answer=AsyncMock())


def test_handlers_deny_outsiders_and_double_confirm_sends_once():
    async def scenario():
        engine, factory = await make_db()
        try:
            async with factory() as session:
                d = await seed(session)
                await service.ensure_review(session, d.ended, source="test")
                await session.commit()

                call = FakeCall(f"pec:a:{d.ended.id}:0")
                await handlers.review_bulk(call, d.outsider, session, d.settings)
                call.answer.assert_awaited_with(handlers.DENIED, show_alert=True)
                assert (await service.load_review(session, d.ended.id)).value["selected"] == [d.ann.id]
                view = FakeCall(f"pec:v:{d.ended.id}:0")
                await handlers.review_view(view, d.outsider, session, d.settings)
                view.message.edit_text.assert_not_awaited()

                await handlers.review_bulk(FakeCall(f"pec:a:{d.ended.id}:0"), d.lead, session, d.settings)
                ask = FakeCall(f"pec:c:{d.ended.id}")
                await handlers.review_ask_confirm(ask, d.lead, session, d.settings)
                markup = ask.message.edit_text.await_args.kwargs["reply_markup"]
                ok_data = markup.inline_keyboard[0][0].callback_data
                assert ok_data.startswith(f"pec:ok:{d.ended.id}:")

                first, second = FakeCall(ok_data), FakeCall(ok_data)
                await handlers.review_confirm(first, d.lead, session, d.settings)
                await handlers.review_confirm(second, d.lead, session, d.settings)
                assert "Выдано сертификатов: 2." in first.message.edit_text.await_args.args[0]
                second.message.edit_text.assert_not_awaited()
                assert second.answer.await_args.kwargs == {"show_alert": True}
                assert await session.scalar(select(func.count()).select_from(CertificateIssue)) == 2
                assert await session.scalar(select(func.count()).select_from(AppSetting).where(
                    AppSetting.key.like("event-certificate:pending:%"))) == 2

                text, markup = await handlers.render_review(session, d.ended)
                labels = [row[0].text for row in markup.inline_keyboard if row[0].callback_data.startswith("pec:t:")]
                assert labels == ["🎓 Анна Был · выдан", "🎓 Борис Записан · выдан", "🚫 Дина Заблокирована · недоступен"]
                assert "Зарегистрировались: 3" in text
        finally:
            await engine.dispose()
    run(scenario())


async def _pdf_sends(factory, settings, chat_id):
    send = AsyncMock(return_value=sent())
    with patch("app.services.notification_service.safe_send_once", send):
        await certificate_service.deliver_requested_certificates(SimpleNamespace(), settings, factory)
    return [c for c in send.await_args_list if c.args[2] == chat_id]


def test_certificate_is_sent_once_whatever_the_order_of_owner_issue_and_proof_approval():
    async def scenario(order):
        bot = AsyncMock()
        engine, factory = await make_db()
        try:
            async with factory() as session:
                d = await seed(session)
                proof = AttendanceProof(event_id=d.ended.id, user_id=d.boris.id, photo_file_id="tg-photo",
                                        status="pending")
                session.add(proof)
                await session.commit()
                await session.refresh(proof)
                await service.ensure_review(session, d.ended, source="test")
                await service.change_selection(session, d.owner, d.settings, d.ended.id, "toggle", d.boris.id)
                rev = (await service.load_review(session, d.ended.id)).value["rev"]
                await session.commit()

                async def owner_issue():
                    async with factory() as s:
                        owner = await s.get(User, d.owner.id)
                        await service.confirm(s, owner, d.settings, d.ended.id, rev)
                        await s.commit()

                async def approve():
                    async with factory() as s:
                        reviewer = await s.get(User, d.owner.id)
                        live = await s.get(AttendanceProof, proof.id)
                        with patch("app.services.attendance_proof_service.safe_send", AsyncMock()):
                            await attendance_proof_service.approve_proof(s, live, reviewer=reviewer, bot=bot)
                        await s.commit()

                steps = [owner_issue, approve] if order == "owner_first" else [approve, owner_issue]
                for step in steps:
                    await step()
                first = await _pdf_sends(factory, d.settings, d.boris.telegram_id)
                again = await _pdf_sends(factory, d.settings, d.boris.telegram_id)
            assert len(first) == 1 and again == []
            bot.send_document.assert_not_awaited()
            assert first[0].kwargs["delivery_key"].startswith("event-certificate:")
            async with factory() as session:
                issues = list(await session.scalars(select(CertificateIssue).where(CertificateIssue.user_id == d.boris.id)))
                assert len(issues) == 1 and issues[0].status == "issued"
        finally:
            await engine.dispose()
    run(scenario("owner_first"))
    run(scenario("proof_first"))


def test_approval_after_delivery_already_happened_sends_nothing_more():
    async def scenario():
        bot = AsyncMock()
        engine, factory = await make_db()
        try:
            async with factory() as session:
                d = await seed(session)
                await service.ensure_review(session, d.ended, source="test")
                await service.change_selection(session, d.owner, d.settings, d.ended.id, "toggle", d.boris.id)
                rev = (await service.load_review(session, d.ended.id)).value["rev"]
                await service.confirm(session, d.owner, d.settings, d.ended.id, rev)
                session.add(AttendanceProof(event_id=d.ended.id, user_id=d.boris.id, photo_file_id="tg-photo",
                                            status="pending"))
                await session.commit()
            assert len(await _pdf_sends(factory, d.settings, d.boris.telegram_id)) == 1
            async with factory() as session:
                proof = await session.scalar(select(AttendanceProof).where(AttendanceProof.user_id == d.boris.id))
                reviewer = await session.get(User, d.owner.id)
                with patch("app.services.attendance_proof_service.safe_send", AsyncMock()):
                    await attendance_proof_service.approve_proof(session, proof, reviewer=reviewer, bot=bot)
                await session.commit()
            assert await _pdf_sends(factory, d.settings, d.boris.telegram_id) == []
            bot.send_document.assert_not_awaited()
        finally:
            await engine.dispose()
    run(scenario())


def test_confirm_refuses_event_rescheduled_to_future_or_cancelled():
    async def scenario(change):
        engine, factory = await make_db()
        try:
            async with factory() as session:
                d = await seed(session)
                await service.ensure_review(session, d.ended, source="test")
                await service.change_selection(session, d.owner, d.settings, d.ended.id, "toggle", d.boris.id)
                rev = (await service.load_review(session, d.ended.id)).value["rev"]
                await session.commit()
            async with factory() as session:
                change(await session.get(Event, d.ended.id))
                await session.commit()
            async with factory() as session:
                owner = await session.get(User, d.owner.id)
                with pytest.raises(service.ReviewError):
                    await service.confirm(session, owner, d.settings, d.ended.id, rev)
            async with factory() as session:
                assert await session.scalar(select(func.count()).select_from(CertificateIssue)) == 0
        finally:
            await engine.dispose()

    def reschedule(event):
        event.event_date = date(2099, 1, 1)

    def cancel(event):
        event.status = EventStatus.CANCELLED

    run(scenario(reschedule))
    run(scenario(cancel))


def test_owner_issue_before_attendance_confirmation_does_not_break_it():
    from app.services import event_attendance_service

    async def scenario():
        engine, factory = await make_db()
        try:
            async with factory() as session:
                manager = User(telegram_id=9201, first_name="Менеджер", role=Role.ADMIN,
                               application_status=ApplicationStatus.APPROVED)
                participant = User(telegram_id=9202, first_name="Участник", role=Role.PARTICIPANT,
                                   application_status=ApplicationStatus.APPROVED)
                session.add_all([manager, participant])
                await session.flush()
                event = Event(title="Тест посещения", description="Тест", event_date=date(2026, 11, 20),
                              event_time=time(10), location="Ереван", format="offline", responsible_id=manager.id,
                              participant_limit=30, points_for_visit=25, selfie_required=True,
                              status=EventStatus.REGISTRATION_CLOSED, created_by=manager.id)
                session.add(event)
                await session.flush()
                session.add(EventExperience(event_id=event.id, issue_certificate=True))
                session.add(EventRegistration(event_id=event.id, user_id=participant.id,
                                              status=RegistrationStatus.REGISTERED))
                await session.commit()

                await event_attendance_service.start_event(session, event.id, actor_user_id=manager.id,
                                                           bot=None, miniapp_url="")
                completed = await event_attendance_service.complete_event(session, event.id,
                                                                          actor_user_id=manager.id, bot=None,
                                                                          miniapp_url="")
                code = completed.session.attendance_code
                issue, created = await certificate_service.issue_post_event_certificate(
                    session, manager, user_id=participant.id, event_id=event.id)
                await session.commit()
                assert created is True

                result = await event_attendance_service.confirm_attendance(session, event.id, participant.id, code)
                await session.commit()
                assert result.points_awarded == 25

            async with factory() as session:
                keys = list(await session.scalars(select(AppSetting.key).where(
                    AppSetting.key.like("event-certificate:%"))))
                assert keys == [f"event-certificate:pending:{issue.id}"]
        finally:
            await engine.dispose()
    run(scenario())
