from __future__ import annotations

import asyncio
import html
import io
import json
import logging
import secrets
from datetime import datetime, timedelta, timezone

from aiogram import F
from aiogram.dispatcher.event.bases import SkipHandler
from aiogram.enums import ChatType
from aiogram.filters import CommandObject, CommandStart
from aiogram.types import BufferedInputFile, CallbackQuery, Message
from openpyxl import load_workbook

from app.commission_bot import _kb
from app.commission_bot_engagement import CommissionBotEngagement, _dict
from app.commission_bot_ultimate import DEFAULT_TZ, _localize, _safe

log = logging.getLogger(__name__)

ONLINE_DDL = r"""
ALTER TABLE broadcasts ADD COLUMN IF NOT EXISTS join_url TEXT;
ALTER TABLE broadcasts ADD COLUMN IF NOT EXISTS join_reveal_minutes INTEGER NOT NULL DEFAULT 15;
ALTER TABLE broadcasts ADD COLUMN IF NOT EXISTS materials_url TEXT;
ALTER TABLE broadcasts ADD COLUMN IF NOT EXISTS faq JSONB NOT NULL DEFAULT '[]'::jsonb;
ALTER TABLE broadcasts ADD COLUMN IF NOT EXISTS speaker_questions_enabled BOOLEAN NOT NULL DEFAULT TRUE;
ALTER TABLE broadcasts ADD COLUMN IF NOT EXISTS feedback_enabled BOOLEAN NOT NULL DEFAULT TRUE;
ALTER TABLE broadcasts ADD COLUMN IF NOT EXISTS featured BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE broadcasts ADD COLUMN IF NOT EXISTS approval_required BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE broadcasts ADD COLUMN IF NOT EXISTS cancelled_at TIMESTAMPTZ;
ALTER TABLE broadcasts ADD COLUMN IF NOT EXISTS archived_at TIMESTAMPTZ;
ALTER TABLE broadcasts ADD COLUMN IF NOT EXISTS duration_minutes INTEGER NOT NULL DEFAULT 90;

CREATE TABLE IF NOT EXISTS event_confirmations (
  broadcast_id BIGINT NOT NULL REFERENCES broadcasts(id) ON DELETE CASCADE,
  telegram_id BIGINT NOT NULL REFERENCES users(telegram_id) ON DELETE CASCADE,
  answer TEXT NOT NULL,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  PRIMARY KEY (broadcast_id, telegram_id)
);
CREATE TABLE IF NOT EXISTS event_favorites (
  broadcast_id BIGINT NOT NULL REFERENCES broadcasts(id) ON DELETE CASCADE,
  telegram_id BIGINT NOT NULL REFERENCES users(telegram_id) ON DELETE CASCADE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  PRIMARY KEY (broadcast_id, telegram_id)
);
CREATE TABLE IF NOT EXISTS event_views (
  broadcast_id BIGINT NOT NULL REFERENCES broadcasts(id) ON DELETE CASCADE,
  telegram_id BIGINT NOT NULL REFERENCES users(telegram_id) ON DELETE CASCADE,
  source TEXT NOT NULL DEFAULT 'bot',
  first_viewed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  last_viewed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  PRIMARY KEY (broadcast_id, telegram_id)
);
CREATE TABLE IF NOT EXISTS speaker_questions (
  id BIGSERIAL PRIMARY KEY,
  broadcast_id BIGINT NOT NULL REFERENCES broadcasts(id) ON DELETE CASCADE,
  telegram_id BIGINT NOT NULL REFERENCES users(telegram_id) ON DELETE CASCADE,
  body TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'new',
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS online_event_feedback (
  broadcast_id BIGINT NOT NULL REFERENCES broadcasts(id) ON DELETE CASCADE,
  telegram_id BIGINT NOT NULL REFERENCES users(telegram_id) ON DELETE CASCADE,
  score INTEGER NOT NULL,
  comment TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  PRIMARY KEY (broadcast_id, telegram_id)
);
CREATE TABLE IF NOT EXISTS event_service_notifications (
  dedupe_key TEXT PRIMARY KEY,
  broadcast_id BIGINT NOT NULL REFERENCES broadcasts(id) ON DELETE CASCADE,
  telegram_id BIGINT NOT NULL REFERENCES users(telegram_id) ON DELETE CASCADE,
  kind TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'pending',
  error TEXT,
  sent_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS event_referral_sources (
  id BIGSERIAL PRIMARY KEY,
  broadcast_id BIGINT NOT NULL REFERENCES broadcasts(id) ON DELETE CASCADE,
  name TEXT NOT NULL,
  token TEXT NOT NULL UNIQUE,
  created_by BIGINT NOT NULL REFERENCES users(telegram_id),
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS pending_registration_sources (
  telegram_id BIGINT NOT NULL REFERENCES users(telegram_id) ON DELETE CASCADE,
  broadcast_id BIGINT NOT NULL REFERENCES broadcasts(id) ON DELETE CASCADE,
  source TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  PRIMARY KEY (telegram_id, broadcast_id)
);
CREATE TABLE IF NOT EXISTS participant_notes (
  id BIGSERIAL PRIMARY KEY,
  telegram_id BIGINT NOT NULL REFERENCES users(telegram_id) ON DELETE CASCADE,
  author_id BIGINT NOT NULL REFERENCES users(telegram_id),
  note TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS event_certificates (
  broadcast_id BIGINT NOT NULL REFERENCES broadcasts(id) ON DELETE CASCADE,
  telegram_id BIGINT NOT NULL REFERENCES users(telegram_id) ON DELETE CASCADE,
  certificate_url TEXT,
  file_id TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  PRIMARY KEY (broadcast_id, telegram_id)
);
CREATE INDEX IF NOT EXISTS idx_event_views_deadline ON event_views(broadcast_id,last_viewed_at);
CREATE INDEX IF NOT EXISTS idx_questions_event ON speaker_questions(broadcast_id,status,created_at);
"""

RSVP_LABELS = {"yes": "✅ Буду", "maybe": "🤔 Пока не уверен(а)", "no": "❌ Не смогу"}


def _ics_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


class CommissionBotOnlineOps(CommissionBotEngagement):
    async def init_db(self) -> None:
        await super().init_db()
        await self.execute(ONLINE_DDL)

    async def broadcast_text(self, b, reminder=False) -> str:
        prefix = "🔔 <b>Напоминание</b>\n\n" if reminder else ""
        text = f"{prefix}<b>{_safe(b['title'])}</b>\n\n{_safe(b['description'])}"
        if b["event_at"]:
            text += f"\n\n📅 {_localize(b['event_at'], b['event_timezone'] or DEFAULT_TZ)}"
        if b["event_format"]:
            text += "\n💻 Формат: Онлайн" if b["event_format"] == "online" else f"\n📍 Формат: {_safe(b['event_format'])}"
        # For online events event_location historically contained the meeting URL. Never expose it in public broadcasts.
        if b["event_location"] and b["event_format"] != "online":
            text += f"\n📌 {_safe(b['event_location'])}"
        if b["registration_deadline"]:
            text += f"\n⏳ Регистрация до {_localize(b['registration_deadline'], b['event_timezone'] or DEFAULT_TZ)}"
        if b["capacity"]:
            text += f"\n👥 Мест: {b['capacity']}"
        if b.get("cancelled_at") if isinstance(b, dict) else False:
            text = "❌ <b>МЕРОПРИЯТИЕ ОТМЕНЕНО</b>\n\n" + text
        return text

    def _event_join_url(self, b) -> str | None:
        try:
            return b["join_url"] or (b["event_location"] if b["event_format"] == "online" and str(b["event_location"] or "").startswith(("http://", "https://")) else None)
        except Exception:
            return None

    async def register(self, chat_id: int, user, bid: int):
        b = await self.fetchrow("SELECT * FROM broadcasts WHERE id=$1", bid)
        if b and b["cancelled_at"]:
            return await self.bot.send_message(chat_id, "Это событие отменено — регистрация закрыта.")
        await super().register(chat_id, user, bid)
        source = await self.fetchrow("SELECT source FROM pending_registration_sources WHERE telegram_id=$1 AND broadcast_id=$2", user["telegram_id"], bid)
        if source:
            await self.execute("UPDATE registrations SET source=$3,updated_at=NOW() WHERE broadcast_id=$1 AND telegram_id=$2", bid, user["telegram_id"], source["source"])
            await self.execute("DELETE FROM pending_registration_sources WHERE telegram_id=$1 AND broadcast_id=$2", user["telegram_id"], bid)
        if b and b["approval_required"]:
            changed = await self.fetchrow(
                "UPDATE registrations SET status='pending_review',updated_at=NOW() WHERE broadcast_id=$1 AND telegram_id=$2 AND status IN ('registered','waitlist') RETURNING id",
                bid, user["telegram_id"],
            )
            if changed:
                await self.bot.send_message(chat_id, "<b>Заявка отправлена на рассмотрение ✨</b>\n\nКоманда проверит её и бот сообщит результат здесь. Дополнительно писать администратору не нужно.")

    async def _event_card(self, chat_id: int, user, bid: int) -> None:
        b = await self.fetchrow("SELECT * FROM broadcasts WHERE id=$1", bid)
        if not b:
            return await self.bot.send_message(chat_id, "Событие не найдено.")
        await self.execute(
            """INSERT INTO event_views(broadcast_id,telegram_id,last_viewed_at) VALUES($1,$2,NOW())
            ON CONFLICT(broadcast_id,telegram_id) DO UPDATE SET last_viewed_at=NOW()""",
            bid, user["telegram_id"],
        )
        reg = await self.fetchrow("SELECT * FROM registrations WHERE broadcast_id=$1 AND telegram_id=$2", bid, user["telegram_id"])
        fav = await self.fetchrow("SELECT 1 FROM event_favorites WHERE broadcast_id=$1 AND telegram_id=$2", bid, user["telegram_id"])
        text = await self.broadcast_text(b)
        if b["cancelled_at"]:
            text = "❌ <b>Событие отменено</b>\n\n" + text
        rows: list[list[tuple[str, str]]] = []
        if b["registration_mode"] == "internal" and not b["cancelled_at"]:
            if reg and reg["status"] not in {"cancelled", "rejected"}:
                rows.append([("✅ Моя регистрация", f"evx:reg:{bid}")])
            else:
                rows.append([("🎟 Зарегистрироваться", f"reg:{bid}")])
        rows.append([("⭐️ Убрать из избранного" if fav else "☆ В избранное", f"evx:fav:{bid}"), ("📅 В календарь", f"evx:cal:{bid}")])
        faq = b["faq"] if isinstance(b["faq"], list) else json.loads(b["faq"] or "[]")
        if faq:
            rows.append([("❓ FAQ", f"evx:faq:{bid}")])
        if b["speaker_questions_enabled"] and b["event_at"] and b["event_at"] > datetime.now(timezone.utc):
            rows.append([("🎤 Вопрос спикеру", f"evx:q:{bid}")])
        if reg and reg["status"] in {"registered", "attended"} and b["event_at"]:
            reveal_at = b["event_at"] - timedelta(minutes=int(b["join_reveal_minutes"] or 15))
            join_url = self._event_join_url(b)
            if join_url and datetime.now(timezone.utc) >= reveal_at and not b["cancelled_at"]:
                rows.append([("🔴 Подключиться", f"evx:join:{bid}")])
        if b["materials_url"] and b["event_at"] and b["event_at"] < datetime.now(timezone.utc):
            rows.append([("📚 Материалы и запись", f"evx:materials:{bid}")])
        cert = await self.fetchrow("SELECT * FROM event_certificates WHERE broadcast_id=$1 AND telegram_id=$2", bid, user["telegram_id"])
        if cert:
            rows.append([("🏅 Сертификат", f"evx:cert:{bid}")])
        if user["role"] in {"admin", "owner"}:
            rows.append([("⚙️ Управление событием", f"evops:menu:{bid}")])
        rows.append([("⬅️ К событиям", "events:list")])
        await self.bot.send_message(chat_id, text, reply_markup=_kb(rows), disable_web_page_preview=True)

    async def _event_report(self, bid: int) -> str:
        b = await self.fetchrow("SELECT * FROM broadcasts WHERE id=$1", bid)
        if not b:
            return "Событие не найдено."
        s = await self.fetchrow(
            """SELECT
            COUNT(*) FILTER (WHERE status IN ('registered','attended')) registered,
            COUNT(*) FILTER (WHERE status='pending_review') pending,
            COUNT(*) FILTER (WHERE status='waitlist') waitlist,
            COUNT(*) FILTER (WHERE status='cancelled') cancelled
            FROM registrations WHERE broadcast_id=$1""", bid,
        )
        rsvp = await self.fetchrow(
            """SELECT COUNT(*) FILTER(WHERE answer='yes') yes,COUNT(*) FILTER(WHERE answer='maybe') maybe,COUNT(*) FILTER(WHERE answer='no') no FROM event_confirmations WHERE broadcast_id=$1""", bid,
        )
        feedback = await self.fetchrow("SELECT COUNT(*) n,AVG(score) avg FROM online_event_feedback WHERE broadcast_id=$1", bid)
        questions = await self.fetchrow("SELECT COUNT(*) n FROM speaker_questions WHERE broadcast_id=$1", bid)
        sources = await self.fetch(
            "SELECT source,COUNT(*) n FROM registrations WHERE broadcast_id=$1 GROUP BY source ORDER BY n DESC", bid,
        )
        lines = [
            f"<b>📊 {_safe(b['title'])}</b>",
            "",
            f"🎟 Принято: <b>{s['registered']}</b>",
            f"🕒 На рассмотрении: {s['pending']}",
            f"⏳ Лист ожидания: {s['waitlist']}",
            f"❌ Отменили: {s['cancelled']}",
            f"✅ Подтвердили участие: {rsvp['yes']} · 🤔 {rsvp['maybe']} · ❌ {rsvp['no']}",
            f"🎤 Вопросов спикеру: {questions['n']}",
            f"⭐️ Обратная связь: {round(float(feedback['avg']),2) if feedback['avg'] else '—'} / 5 · {feedback['n']} ответов",
        ]
        if sources:
            lines.append("\n<b>Источники регистрации</b>")
            lines.extend(f"{html.escape(row['source'] or 'telegram')}: {row['n']}" for row in sources)
        return "\n".join(lines)

    async def _notify_service(self, key: str, bid: int, uid: int, kind: str, text: str, markup=None) -> bool:
        if await self.fetchrow("SELECT 1 FROM event_service_notifications WHERE dedupe_key=$1 AND status='sent'", key):
            return False
        await self.execute(
            "INSERT INTO event_service_notifications(dedupe_key,broadcast_id,telegram_id,kind) VALUES($1,$2,$3,$4) ON CONFLICT DO NOTHING",
            key, bid, uid, kind,
        )
        try:
            await self.bot.send_message(uid, text, reply_markup=markup, disable_web_page_preview=True)
            await self.execute("UPDATE event_service_notifications SET status='sent',error=NULL,sent_at=NOW() WHERE dedupe_key=$1", key)
            return True
        except Exception as exc:
            await self.execute("UPDATE event_service_notifications SET status='failed',error=$2 WHERE dedupe_key=$1", key, str(exc)[:500])
            return False

    async def _online_service_tick(self) -> None:
        now = datetime.now(timezone.utc)
        # 24h attendance confirmation.
        upcoming = await self.fetch(
            """SELECT * FROM broadcasts WHERE status='published' AND cancelled_at IS NULL AND event_at BETWEEN NOW()+INTERVAL '23 hours' AND NOW()+INTERVAL '25 hours'"""
        )
        for b in upcoming:
            regs = await self.fetch("SELECT telegram_id FROM registrations WHERE broadcast_id=$1 AND status IN ('registered','attended')", b["id"])
            for r in regs:
                await self._notify_service(
                    f"rsvp24:{b['id']}:{r['telegram_id']}", b["id"], r["telegram_id"], "rsvp",
                    f"<b>Завтра встречаемся 👋</b>\n\n<b>{_safe(b['title'])}</b>\n{_localize(b['event_at'], b['event_timezone'] or DEFAULT_TZ)}\n\nТы с нами? Ответ займёт один тап.",
                    _kb([[("✅ Буду", f"evx:rsvp:{b['id']}:yes"), ("🤔 Пока не уверен", f"evx:rsvp:{b['id']}:maybe")], [("❌ Не смогу", f"evx:rsvp:{b['id']}:no")]]),
                )
        # Meeting link shortly before start.
        due = await self.fetch("SELECT * FROM broadcasts WHERE status='published' AND cancelled_at IS NULL AND event_at BETWEEN NOW()-INTERVAL '5 minutes' AND NOW()+INTERVAL '30 minutes'")
        for b in due:
            join = self._event_join_url(b)
            if not join:
                continue
            reveal_at = b["event_at"] - timedelta(minutes=int(b["join_reveal_minutes"] or 15))
            if now < reveal_at:
                continue
            regs = await self.fetch(
                """SELECT r.telegram_id FROM registrations r LEFT JOIN event_confirmations ec ON ec.broadcast_id=r.broadcast_id AND ec.telegram_id=r.telegram_id
                WHERE r.broadcast_id=$1 AND r.status IN ('registered','attended') AND COALESCE(ec.answer,'yes')<>'no'""", b["id"],
            )
            for r in regs:
                await self._notify_service(
                    f"join:{b['id']}:{r['telegram_id']}", b["id"], r["telegram_id"], "join",
                    f"<b>Мы начинаем совсем скоро 🔴</b>\n\n{_safe(b['title'])}\n\nСсылка уже открыта — подключайся вовремя.",
                    _kb([[("🔴 Подключиться", f"evx:join:{b['id']}")]]),
                )
        # Post-event materials + feedback.
        ended = await self.fetch("SELECT * FROM broadcasts WHERE status='published' AND event_at BETWEEN NOW()-INTERVAL '7 days' AND NOW()-INTERVAL '90 minutes'")
        for b in ended:
            regs = await self.fetch("SELECT telegram_id FROM registrations WHERE broadcast_id=$1 AND status IN ('registered','attended')", b["id"])
            for r in regs:
                rows = []
                if b["materials_url"]:
                    rows.append([("📚 Материалы и запись", f"evx:materials:{b['id']}")])
                if b["feedback_enabled"]:
                    rows.append([("⭐️ Оценить встречу", f"evx:feedback:{b['id']}")])
                if rows:
                    await self._notify_service(
                        f"after:{b['id']}:{r['telegram_id']}", b["id"], r["telegram_id"], "after_event",
                        f"<b>Спасибо, что был(а) с нами 💛</b>\n\n{_safe(b['title'])}\n\nСохрани полезное и помоги сделать следующую встречу ещё сильнее.", _kb(rows),
                    )
        # One anti-spam deadline nudge for people who viewed but did not register.
        deadline_events = await self.fetch("SELECT * FROM broadcasts WHERE status='published' AND registration_mode='internal' AND registration_deadline BETWEEN NOW() AND NOW()+INTERVAL '24 hours' AND cancelled_at IS NULL")
        for b in deadline_events:
            viewers = await self.fetch(
                """SELECT v.telegram_id FROM event_views v JOIN users u ON u.telegram_id=v.telegram_id
                LEFT JOIN registrations r ON r.broadcast_id=v.broadcast_id AND r.telegram_id=v.telegram_id
                WHERE v.broadcast_id=$1 AND r.id IS NULL AND u.telegram_opt_in=TRUE""", b["id"],
            )
            for v in viewers:
                await self._notify_service(
                    f"deadline:{b['id']}:{v['telegram_id']}", b["id"], v["telegram_id"], "deadline_nudge",
                    f"<b>До закрытия регистрации меньше суток ⏳</b>\n\n{_safe(b['title'])}\n\nЕсли планировал(а) присоединиться — сейчас хороший момент не откладывать.",
                    _kb([[("🎟 Зарегистрироваться", f"reg:{b['id']}")]]),
                )
        # Archive marker and activity tiers, without changing published status or deleting data.
        await self.execute("UPDATE broadcasts SET archived_at=COALESCE(archived_at,NOW()) WHERE status='published' AND event_at<NOW()-INTERVAL '1 day' AND archived_at IS NULL")
        await self.execute(
            """UPDATE users u SET activity_level=CASE
            WHEN u.role IN ('editor','admin','owner') THEN 'core'
            WHEN (SELECT COUNT(*) FROM registrations r WHERE r.telegram_id=u.telegram_id AND r.registered_at>=NOW()-INTERVAL '180 days' AND r.status<>'cancelled')>=3 THEN 'very_active'
            WHEN u.last_activity_at>=NOW()-INTERVAL '60 days' OR EXISTS(SELECT 1 FROM registrations r WHERE r.telegram_id=u.telegram_id AND r.registered_at>=NOW()-INTERVAL '180 days' AND r.status<>'cancelled') THEN 'active'
            WHEN u.last_activity_at<NOW()-INTERVAL '90 days' THEN 'inactive'
            ELSE 'new' END"""
        )

    async def _online_scheduler(self) -> None:
        while True:
            try:
                await self._online_service_tick()
            except Exception:
                log.exception("online event service scheduler")
            await asyncio.sleep(60)

    async def reminders_loop(self):
        task = asyncio.create_task(self._online_scheduler())
        try:
            await super().reminders_loop()
        finally:
            task.cancel()

    def _register_handlers(self):
        r = self.router

        @r.message(CommandStart())
        async def source_start(m: Message, command: CommandObject):
            arg = (command.args or "").strip()
            if not arg.startswith("src_"):
                raise SkipHandler
            token = arg[4:]
            source = await self.fetchrow("SELECT * FROM event_referral_sources WHERE token=$1", token)
            if not source:
                raise SkipHandler
            user = await self.ensure_user(m.from_user)
            await self.execute(
                "INSERT INTO pending_registration_sources(telegram_id,broadcast_id,source) VALUES($1,$2,$3) ON CONFLICT(telegram_id,broadcast_id) DO UPDATE SET source=EXCLUDED.source,created_at=NOW()",
                user["telegram_id"], source["broadcast_id"], source["name"],
            )
            if not user["onboarding_complete"]:
                return await self.start_onboarding(m.chat.id, user, {"type": "register", "broadcast_id": source["broadcast_id"]})
            await self.register(m.chat.id, user, source["broadcast_id"])

        @r.callback_query(F.data == "events:list")
        async def online_events(c: CallbackQuery):
            await c.answer(); user = await self.ensure_user(c.from_user)
            rows = await self.fetch("SELECT * FROM broadcasts WHERE status='published' AND cancelled_at IS NULL AND event_at IS NOT NULL AND event_at>NOW() ORDER BY featured DESC,event_at LIMIT 20")
            if not rows:
                return await c.message.answer("Сейчас новых онлайн-событий нет. Как только появится что-то стоящее — оно будет здесь ✨")
            buttons=[]
            for b in rows:
                prefix="🔥 " if b["featured"] else ""
                buttons.append([(f"{prefix}{_localize(b['event_at'],b['event_timezone'] or DEFAULT_TZ)} · {b['title']}"[:62],f"evx:view:{b['id']}")])
            buttons.append([("🔎 Найти", "evx:search"), ("⭐️ Избранное", "evx:favorites")])
            await c.message.answer("<b>📅 Онлайн-события</b>\n\nВыбирай то, что действительно хочется не просто открыть, а посетить.",reply_markup=_kb(buttons))

        @r.callback_query(F.data.startswith("evx:view:"))
        async def event_view(c: CallbackQuery):
            await c.answer(); user=await self.ensure_user(c.from_user); await self._event_card(c.message.chat.id,user,int(c.data.split(":",2)[2]))

        @r.callback_query(F.data.startswith("evx:fav:"))
        async def event_fav(c: CallbackQuery):
            await c.answer(); bid=int(c.data.split(":",2)[2]); exists=await self.fetchrow("SELECT 1 FROM event_favorites WHERE broadcast_id=$1 AND telegram_id=$2",bid,c.from_user.id)
            if exists: await self.execute("DELETE FROM event_favorites WHERE broadcast_id=$1 AND telegram_id=$2",bid,c.from_user.id)
            else: await self.execute("INSERT INTO event_favorites(broadcast_id,telegram_id) VALUES($1,$2) ON CONFLICT DO NOTHING",bid,c.from_user.id)
            user=await self.ensure_user(c.from_user); await self._event_card(c.message.chat.id,user,bid)

        @r.callback_query(F.data == "evx:favorites")
        async def event_favorites(c: CallbackQuery):
            await c.answer(); rows=await self.fetch("SELECT b.* FROM event_favorites f JOIN broadcasts b ON b.id=f.broadcast_id WHERE f.telegram_id=$1 AND b.event_at>NOW() AND b.cancelled_at IS NULL ORDER BY b.event_at",c.from_user.id)
            if not rows: return await c.message.answer("В избранном пока пусто. Сохраняй события, к которым хочешь вернуться ⭐️")
            await c.message.answer("<b>⭐️ Избранное</b>",reply_markup=_kb([[(f"{_localize(b['event_at'],b['event_timezone'] or DEFAULT_TZ)} · {b['title']}"[:62],f"evx:view:{b['id']}")] for b in rows]))

        @r.callback_query(F.data == "evx:search")
        async def event_search_start(c: CallbackQuery):
            await c.answer(); await self.state_set(c.from_user.id,"event:search",{}); await c.message.answer("🔎 Напиши слово из названия или описания события.")

        @r.callback_query(F.data.startswith("evx:cal:"))
        async def event_calendar(c: CallbackQuery):
            await c.answer(); bid=int(c.data.split(":",2)[2]); b=await self.fetchrow("SELECT * FROM broadcasts WHERE id=$1",bid)
            if not b or not b["event_at"]: return
            start=b["event_at"].astimezone(timezone.utc); end=start+timedelta(minutes=int(b["duration_minutes"] or 90)); join=self._event_join_url(b) or ""
            ics=("BEGIN:VCALENDAR\r\nVERSION:2.0\r\nPRODID:-//MVKSRS//Events//RU\r\nBEGIN:VEVENT\r\n"+f"UID:mvksrs-{bid}@telegram\r\nDTSTAMP:{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}\r\nDTSTART:{start.strftime('%Y%m%dT%H%M%SZ')}\r\nDTEND:{end.strftime('%Y%m%dT%H%M%SZ')}\r\nSUMMARY:{_ics_escape(b['title'])}\r\nDESCRIPTION:{_ics_escape(b['description'])}\r\nURL:{_ics_escape(join)}\r\nEND:VEVENT\r\nEND:VCALENDAR\r\n")
            await self.bot.send_document(c.message.chat.id,BufferedInputFile(ics.encode("utf-8"),filename=f"event_{bid}.ics"),caption="📅 Добавь событие в календарь — время сохранено в UTC и календарь сам покажет его в твоём часовом поясе.")

        @r.callback_query(F.data.startswith("evx:join:"))
        async def event_join(c: CallbackQuery):
            await c.answer(); bid=int(c.data.split(":",2)[2]); b=await self.fetchrow("SELECT * FROM broadcasts WHERE id=$1",bid); reg=await self.fetchrow("SELECT * FROM registrations WHERE broadcast_id=$1 AND telegram_id=$2 AND status IN ('registered','attended')",bid,c.from_user.id)
            if not b or not reg: return await c.message.answer("Ссылка доступна зарегистрированным участникам.")
            reveal=b["event_at"]-timedelta(minutes=int(b["join_reveal_minutes"] or 15)) if b["event_at"] else None
            if reveal and datetime.now(timezone.utc)<reveal: return await c.message.answer(f"Ссылка появится за {b['join_reveal_minutes']} минут до начала — бот напомнит автоматически.")
            join=self._event_join_url(b)
            if not join: return await c.message.answer("Ссылка подключения ещё не добавлена командой.")
            await c.message.answer(f"🔴 <b>Подключиться</b>\n\n{html.escape(join)}",disable_web_page_preview=True)

        @r.callback_query(F.data.startswith("evx:rsvp:"))
        async def event_rsvp(c: CallbackQuery):
            await c.answer(); _,_,bid_s,answer=c.data.split(":",3); bid=int(bid_s)
            if answer not in RSVP_LABELS: return
            await self.execute("""INSERT INTO event_confirmations(broadcast_id,telegram_id,answer) VALUES($1,$2,$3)
                ON CONFLICT(broadcast_id,telegram_id) DO UPDATE SET answer=EXCLUDED.answer,updated_at=NOW()""",bid,c.from_user.id,answer)
            await c.message.answer(f"{RSVP_LABELS[answer]} — сохранил. Если планы поменяются, можно ответить заново.")

        @r.callback_query(F.data.startswith("evx:faq:"))
        async def event_faq(c: CallbackQuery):
            await c.answer(); bid=int(c.data.split(":",2)[2]); b=await self.fetchrow("SELECT faq FROM broadcasts WHERE id=$1",bid); faq=b["faq"] if b and isinstance(b["faq"],list) else json.loads(b["faq"] or "[]") if b else []
            if not faq: return await c.message.answer("FAQ пока не добавлен.")
            await c.message.answer("<b>❓ Частые вопросы</b>\n\n"+"\n\n".join(f"<b>{html.escape(str(x.get('q','')))}</b>\n{html.escape(str(x.get('a','')))}" for x in faq))

        @r.callback_query(F.data.startswith("evx:q:"))
        async def event_question_start(c: CallbackQuery):
            await c.answer(); bid=int(c.data.split(":",2)[2]); await self.state_set(c.from_user.id,"event:question",{"broadcast_id":bid}); await c.message.answer("🎤 Напиши вопрос спикеру одним сообщением. Команда увидит его в карточке события.")

        @r.callback_query(F.data.startswith("evx:materials:"))
        async def event_materials(c: CallbackQuery):
            await c.answer(); bid=int(c.data.split(":",2)[2]); b=await self.fetchrow("SELECT materials_url FROM broadcasts WHERE id=$1",bid)
            if not b or not b["materials_url"]: return await c.message.answer("Материалы ещё не опубликованы.")
            await c.message.answer(f"📚 <b>Материалы и запись</b>\n\n{html.escape(b['materials_url'])}",disable_web_page_preview=True)

        @r.callback_query(F.data.startswith("evx:feedback:"))
        async def event_feedback(c: CallbackQuery):
            await c.answer(); bid=int(c.data.split(":",2)[2]); await c.message.answer("Как тебе встреча? Одна оценка помогает команде видеть реальное качество, а не просто число регистраций.",reply_markup=_kb([[(str(i),f"evx:fb:{bid}:{i}") for i in range(1,6)]]))

        @r.callback_query(F.data.startswith("evx:fb:"))
        async def event_feedback_score(c: CallbackQuery):
            await c.answer(); _,_,bid_s,score_s=c.data.split(":",3); bid=int(bid_s); score=int(score_s)
            if score not in range(1,6): return
            await self.execute("""INSERT INTO online_event_feedback(broadcast_id,telegram_id,score) VALUES($1,$2,$3)
                ON CONFLICT(broadcast_id,telegram_id) DO UPDATE SET score=EXCLUDED.score,created_at=NOW()""",bid,c.from_user.id,score); await c.message.answer("Спасибо 💛 Оценка сохранена.")

        @r.callback_query(F.data.startswith("evx:cert:"))
        async def event_certificate(c: CallbackQuery):
            await c.answer(); bid=int(c.data.split(":",2)[2]); cert=await self.fetchrow("SELECT * FROM event_certificates WHERE broadcast_id=$1 AND telegram_id=$2",bid,c.from_user.id)
            if not cert: return
            if cert["file_id"]: await self.bot.send_document(c.message.chat.id,cert["file_id"],caption="🏅 Твой сертификат")
            elif cert["certificate_url"]: await c.message.answer(f"🏅 <b>Твой сертификат</b>\n\n{html.escape(cert['certificate_url'])}")

        @r.callback_query(F.data.startswith("evops:menu:"))
        async def event_ops(c: CallbackQuery):
            await c.answer(); user=await self.ensure_user(c.from_user)
            if user["role"] not in {"admin","owner"}: return
            bid=int(c.data.split(":",2)[2]); b=await self.fetchrow("SELECT * FROM broadcasts WHERE id=$1",bid)
            if not b:return
            await c.message.answer(f"<b>⚙️ {_safe(b['title'])}</b>\n\nJoin: {'✅' if self._event_join_url(b) else '—'} · Материалы: {'✅' if b['materials_url'] else '—'} · FAQ: {len(b['faq'] if isinstance(b['faq'],list) else json.loads(b['faq'] or '[]'))}\nОтбор заявок: {'✅' if b['approval_required'] else '❌'} · Главное: {'🔥' if b['featured'] else '—'}",reply_markup=_kb([[('🔴 Ссылка входа',f"evops:setjoin:{bid}"),('📚 Материалы',f"evops:setmaterials:{bid}")],[('❓ FAQ',f"evops:setfaq:{bid}"),('🎤 Вопросы',f"evops:questions:{bid}")],[('🧾 Заявки с отбором',f"evops:approval:{bid}"),('🔥 Главное событие',f"evops:featured:{bid}")],[('👥 Заявки',f"evops:apps:{bid}"),('🎤 Вопросы спикеру',f"evops:qlist:{bid}")],[('🔗 Источники',f"evops:refs:{bid}"),('📊 Быстрый отчёт',f"evops:report:{bid}")],[('📥 Импорт участников',f"evops:import:{bid}"),('🏅 Импорт сертификатов',f"evops:certimport:{bid}")],[('📋 Дублировать',f"evops:dup:{bid}"),('❌ Отменить событие',f"evops:cancel:{bid}")],[('⬅️ Событие',f"evx:view:{bid}")]]))

        @r.callback_query(F.data.startswith("evops:setjoin:"))
        async def set_join(c: CallbackQuery): await c.answer(); bid=int(c.data.rsplit(":",1)[1]); await self.state_set(c.from_user.id,"event:setjoin",{"broadcast_id":bid}); await c.message.answer("Отправь ссылку Zoom / Teams / Meet. Она не будет показываться публично: бот откроет её зарегистрированным участникам ближе к началу.")

        @r.callback_query(F.data.startswith("evops:setmaterials:"))
        async def set_materials(c: CallbackQuery): await c.answer(); bid=int(c.data.rsplit(":",1)[1]); await self.state_set(c.from_user.id,"event:setmaterials",{"broadcast_id":bid}); await c.message.answer("Отправь одну ссылку на запись/папку/материалы. После мероприятия бот сам предложит её участникам.")

        @r.callback_query(F.data.startswith("evops:setfaq:"))
        async def set_faq(c: CallbackQuery): await c.answer(); bid=int(c.data.rsplit(":",1)[1]); await self.state_set(c.from_user.id,"event:setfaq",{"broadcast_id":bid}); await c.message.answer("Отправь FAQ строками в формате:\n<code>Вопрос | Ответ</code>\n\nДо 10 строк. /clear — очистить.")

        @r.callback_query(F.data.startswith("evops:questions:"))
        async def toggle_questions(c: CallbackQuery): await c.answer(); bid=int(c.data.rsplit(":",1)[1]); await self.execute("UPDATE broadcasts SET speaker_questions_enabled=NOT speaker_questions_enabled WHERE id=$1",bid); await c.message.answer("Настройка вопросов спикеру изменена ✅")

        @r.callback_query(F.data.startswith("evops:approval:"))
        async def toggle_approval(c: CallbackQuery): await c.answer(); bid=int(c.data.rsplit(":",1)[1]); await self.execute("UPDATE broadcasts SET approval_required=NOT approval_required WHERE id=$1",bid); await c.message.answer("Режим отбора заявок изменён ✅")

        @r.callback_query(F.data.startswith("evops:featured:"))
        async def toggle_featured(c: CallbackQuery):
            await c.answer(); bid=int(c.data.rsplit(":",1)[1]); await self.execute("UPDATE broadcasts SET featured=FALSE WHERE featured=TRUE"); await self.execute("UPDATE broadcasts SET featured=TRUE WHERE id=$1",bid); await c.message.answer("Теперь это главное событие 🔥")

        @r.callback_query(F.data.startswith("evops:report:"))
        async def event_report(c: CallbackQuery): await c.answer(); bid=int(c.data.rsplit(":",1)[1]); await c.message.answer(await self._event_report(bid))

        @r.callback_query(F.data.startswith("evops:dup:"))
        async def duplicate_event(c: CallbackQuery):
            await c.answer(); user=await self.ensure_user(c.from_user); bid=int(c.data.rsplit(":",1)[1]); b=await self.fetchrow("SELECT * FROM broadcasts WHERE id=$1",bid)
            if not b:return
            copy=await self.fetchrow("""INSERT INTO broadcasts(content_type,title,description,media_file_id,event_timezone,event_format,event_location,registration_mode,registration_url,capacity,audience,reminder_offsets,status,created_by,registration_form,custom_questions,join_url,join_reveal_minutes,faq,speaker_questions_enabled,feedback_enabled,approval_required,duration_minutes)
                VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,'draft',$13,$14,$15,$16,$17,$18,$19,$20,$21,$22) RETURNING id""",
                b["content_type"],f"{b['title']} — копия",b["description"],b["media_file_id"],b["event_timezone"],b["event_format"],b["event_location"],b["registration_mode"],b["registration_url"],b["capacity"],b["audience"],b["reminder_offsets"],user["telegram_id"],b["registration_form"],b["custom_questions"],b["join_url"],b["join_reveal_minutes"],b["faq"],b["speaker_questions_enabled"],b["feedback_enabled"],b["approval_required"],b["duration_minutes"])
            await c.message.answer(f"Черновик-копия создан ✅ #{copy['id']}\nДата и дедлайн специально не копируются, чтобы случайно не запустить старое событие.")

        @r.callback_query(F.data.startswith("evops:cancel:"))
        async def cancel_event(c: CallbackQuery):
            await c.answer(); bid=int(c.data.rsplit(":",1)[1]); b=await self.fetchrow("UPDATE broadcasts SET cancelled_at=NOW(),status='cancelled',updated_at=NOW() WHERE id=$1 AND cancelled_at IS NULL RETURNING *",bid)
            if not b:return await c.message.answer("Событие уже отменено или недоступно.")
            regs=await self.fetch("SELECT telegram_id FROM registrations WHERE broadcast_id=$1 AND status IN ('registered','waitlist','pending_review')",bid)
            for rr in regs:
                await self._notify_service(f"cancel:{bid}:{rr['telegram_id']}",bid,rr["telegram_id"],"cancel",f"❌ <b>Событие отменено</b>\n\n{_safe(b['title'])}\n\nЕсли появится новая дата, мы сообщим отдельно.")
            await self.audit(c.from_user.id,"event_cancelled","broadcast",bid); await c.message.answer(f"Событие отменено. Уведомлены участники: {len(regs)}.")

        @r.callback_query(F.data.startswith("evops:refs:"))
        async def referrals(c: CallbackQuery):
            await c.answer(); bid=int(c.data.rsplit(":",1)[1]); rows=await self.fetch("SELECT * FROM event_referral_sources WHERE broadcast_id=$1 ORDER BY id",bid); me=await self.bot.get_me(); lines=["<b>🔗 Источники регистрации</b>"]
            for row in rows: lines.append(f"\n{html.escape(row['name'])}\n<code>https://t.me/{me.username}?start=src_{row['token']}</code>")
            await c.message.answer("\n".join(lines),reply_markup=_kb([[('➕ Новый источник',f"evops:refnew:{bid}")]]),disable_web_page_preview=True)

        @r.callback_query(F.data.startswith("evops:refnew:"))
        async def referral_new(c: CallbackQuery): await c.answer(); bid=int(c.data.rsplit(":",1)[1]); await self.state_set(c.from_user.id,"event:refname",{"broadcast_id":bid}); await c.message.answer("Название источника, например: Instagram / КСООРС Армении / Партнёр Беларусь.")

        @r.callback_query(F.data.startswith("evops:apps:"))
        async def pending_apps(c: CallbackQuery):
            await c.answer(); bid=int(c.data.rsplit(":",1)[1]); rows=await self.fetch("SELECT r.*,u.registration_name,u.first_name,u.last_name,u.username,u.country_name FROM registrations r JOIN users u ON u.telegram_id=r.telegram_id WHERE r.broadcast_id=$1 AND r.status='pending_review' ORDER BY r.registered_at LIMIT 50",bid)
            if not rows:return await c.message.answer("Заявок на рассмотрении нет.")
            buttons=[]
            for row in rows:
                name=row["registration_name"] or " ".join(x for x in [row["first_name"],row["last_name"]] if x) or str(row["telegram_id"]); buttons.append([(f"{name} · {row['country_name'] or '—'}"[:55],f"evops:app:{bid}:{row['telegram_id']}")])
            await c.message.answer("<b>Заявки на рассмотрении</b>",reply_markup=_kb(buttons))

        @r.callback_query(F.data.startswith("evops:app:"))
        async def app_view(c: CallbackQuery):
            await c.answer(); _,_,bid_s,uid_s=c.data.split(":",3); bid=int(bid_s); uid=int(uid_s); u=await self.fetchrow("SELECT * FROM users WHERE telegram_id=$1",uid)
            if not u:return
            await c.message.answer(f"<b>{_safe(u['registration_name'] or (str(u['first_name'] or '')+' '+str(u['last_name'] or '')).strip())}</b>\n{_safe(u['country_name'])} · возраст {u['age'] or '—'}\n{_safe(u['organization'])}\n@{_safe(u['username']) if u['username'] else '—'}",reply_markup=_kb([[('✅ Одобрить',f"evops:appok:{bid}:{uid}"),('❌ Отклонить',f"evops:appno:{bid}:{uid}")]]))

        @r.callback_query(F.data.startswith("evops:appok:"))
        async def app_approve(c: CallbackQuery):
            await c.answer(); _,_,bid_s,uid_s=c.data.split(":",3); bid=int(bid_s); uid=int(uid_s); b=await self.fetchrow("SELECT capacity,title FROM broadcasts WHERE id=$1",bid); status='registered'
            if b and b['capacity']:
                count=await self.fetchrow("SELECT COUNT(*) n FROM registrations WHERE broadcast_id=$1 AND status IN ('registered','attended')",bid)
                if count['n']>=b['capacity']: status='waitlist'
            await self.execute("UPDATE registrations SET status=$3,updated_at=NOW() WHERE broadcast_id=$1 AND telegram_id=$2 AND status='pending_review'",bid,uid,status); await self.bot.send_message(uid,("Заявка одобрена ✅" if status=='registered' else "Заявка одобрена, но основные места уже заняты — ты в листе ожидания ⏳")+f"\n\n<b>{_safe(b['title'])}</b>"); await c.message.answer("Готово ✅")

        @r.callback_query(F.data.startswith("evops:appno:"))
        async def app_reject(c: CallbackQuery):
            await c.answer(); _,_,bid_s,uid_s=c.data.split(":",3); bid=int(bid_s); uid=int(uid_s); b=await self.fetchrow("SELECT title FROM broadcasts WHERE id=$1",bid); await self.execute("UPDATE registrations SET status='rejected',updated_at=NOW() WHERE broadcast_id=$1 AND telegram_id=$2 AND status='pending_review'",bid,uid); await self.bot.send_message(uid,f"По этой заявке сейчас не получилось подтвердить участие.\n\n<b>{_safe(b['title'])}</b>\n\nСледи за следующими возможностями — решение относится только к этой конкретной заявке."); await c.message.answer("Заявка отклонена.")

        @r.callback_query(F.data.startswith("evops:qlist:"))
        async def question_list(c: CallbackQuery):
            await c.answer(); bid=int(c.data.rsplit(":",1)[1]); rows=await self.fetch("SELECT q.*,u.registration_name,u.first_name,u.username FROM speaker_questions q JOIN users u ON u.telegram_id=q.telegram_id WHERE q.broadcast_id=$1 ORDER BY q.created_at",bid)
            if not rows:return await c.message.answer("Вопросов спикеру пока нет.")
            text="<b>🎤 Вопросы спикеру</b>\n\n"+"\n\n".join(f"{i}. {html.escape(row['body'])}\n<small>{html.escape(row['registration_name'] or row['first_name'] or row['username'] or str(row['telegram_id']))}</small>" for i,row in enumerate(rows,1)); await c.message.answer(text[:3900])

        @r.callback_query(F.data.startswith("evops:import:"))
        async def import_start(c: CallbackQuery): await c.answer(); bid=int(c.data.rsplit(":",1)[1]); await self.state_set(c.from_user.id,"event:import",{"broadcast_id":bid}); await c.message.answer("Пришли .xlsx. В первой строке нужен столбец <b>Telegram ID</b> (или telegram_id). Опционально столбец source. Добавлю только тех, кто уже запускал бота.")

        @r.callback_query(F.data.startswith("evops:certimport:"))
        async def cert_import_start(c: CallbackQuery): await c.answer(); bid=int(c.data.rsplit(":",1)[1]); await self.state_set(c.from_user.id,"event:certimport",{"broadcast_id":bid}); await c.message.answer("Пришли .xlsx со столбцами <b>Telegram ID</b> и <b>certificate_url</b>. После импорта у участника появится кнопка «🏅 Сертификат».")

        @r.message(F.chat.type == ChatType.PRIVATE)
        async def online_text_state(m: Message):
            user=await self.ensure_user(m.from_user); st=await self.state_get(user["telegram_id"])
            if not st: raise SkipHandler
            state=str(st["state"]); p=dict(st["payload"] or {}); text=(m.text or "").strip(); bid=int(p.get("broadcast_id") or 0)
            if state == "event:search":
                if not text: return await m.answer("Напиши слово для поиска.")
                rows=await self.fetch("SELECT * FROM broadcasts WHERE status='published' AND cancelled_at IS NULL AND event_at>NOW() AND (title ILIKE $1 OR description ILIKE $1) ORDER BY event_at LIMIT 20",f"%{text[:100]}%")
                await self.state_clear(user["telegram_id"])
                if not rows:return await m.answer("Ничего не нашёл. Попробуй другое слово — иногда проще искать по теме, а не по полному названию.")
                return await m.answer("Нашёл вот что:",reply_markup=_kb([[(f"{_localize(b['event_at'],b['event_timezone'] or DEFAULT_TZ)} · {b['title']}"[:62],f"evx:view:{b['id']}")] for b in rows]))
            if state == "event:question":
                if not text:return await m.answer("Напиши вопрос текстом.")
                await self.execute("INSERT INTO speaker_questions(broadcast_id,telegram_id,body) VALUES($1,$2,$3)",bid,user["telegram_id"],text[:1500]); await self.state_clear(user["telegram_id"]); return await m.answer("Вопрос отправлен 🎤 Если спикер не успеет ответить на всё, команда всё равно увидит общую картину тем, которые волнуют участников.")
            if state == "event:setjoin":
                if not text.startswith(("http://","https://")): return await m.answer("Нужна ссылка https://…")
                await self.execute("UPDATE broadcasts SET join_url=$2,updated_at=NOW() WHERE id=$1",bid,text[:1000]); await self.state_clear(user["telegram_id"]); return await m.answer("Ссылка сохранена 🔴 Публично её не показываем до окна подключения.")
            if state == "event:setmaterials":
                if not text.startswith(("http://","https://")): return await m.answer("Нужна ссылка https://…")
                await self.execute("UPDATE broadcasts SET materials_url=$2,updated_at=NOW() WHERE id=$1",bid,text[:1000]); await self.state_clear(user["telegram_id"]); return await m.answer("Материалы сохранены 📚")
            if state == "event:setfaq":
                if text == "/clear": faq=[]
                else:
                    faq=[]
                    for line in text.splitlines()[:10]:
                        if "|" not in line: continue
                        q,a=line.split("|",1); q=q.strip(); a=a.strip()
                        if q and a: faq.append({"q":q[:300],"a":a[:700]})
                    if not faq:return await m.answer("Не увидел строк формата <code>Вопрос | Ответ</code>.")
                await self.execute("UPDATE broadcasts SET faq=$2::jsonb,updated_at=NOW() WHERE id=$1",bid,json.dumps(faq,ensure_ascii=False)); await self.state_clear(user["telegram_id"]); return await m.answer(f"FAQ сохранён ✅ Вопросов: {len(faq)}")
            if state == "event:refname":
                if not text:return await m.answer("Напиши название источника.")
                token=secrets.token_urlsafe(7).replace("-","").replace("_","")[:10]; await self.execute("INSERT INTO event_referral_sources(broadcast_id,name,token,created_by) VALUES($1,$2,$3,$4)",bid,text[:100],token,user["telegram_id"]); await self.state_clear(user["telegram_id"]); me=await self.bot.get_me(); return await m.answer(f"Источник создан ✅\n\n<b>{html.escape(text[:100])}</b>\n<code>https://t.me/{me.username}?start=src_{token}</code>",disable_web_page_preview=True)
            if state in {"event:import","event:certimport"}:
                if not m.document:return await m.answer("Пришли файл .xlsx документом.")
                if not (m.document.file_name or "").lower().endswith(".xlsx"):return await m.answer("Нужен файл .xlsx.")
                file=await self.bot.get_file(m.document.file_id); buf=io.BytesIO(); await self.bot.download_file(file.file_path,destination=buf); buf.seek(0)
                try: wb=load_workbook(buf,read_only=True,data_only=True); ws=wb.active; headers=[str(x.value or "").strip().lower() for x in ws[1]]
                except Exception:return await m.answer("Не смог прочитать Excel. Проверь, что это обычный .xlsx файл.")
                def col(*names):
                    for n in names:
                        if n in headers:return headers.index(n)
                    return -1
                id_col=col("telegram id","telegram_id","telegramid")
                if id_col<0:return await m.answer("Не найден столбец Telegram ID / telegram_id.")
                success=unknown=bad=0
                if state == "event:import":
                    source_col=col("source","источник")
                    for row in ws.iter_rows(min_row=2,values_only=True):
                        try: uid=int(row[id_col])
                        except Exception: bad+=1; continue
                        if not await self.fetchrow("SELECT 1 FROM users WHERE telegram_id=$1",uid): unknown+=1; continue
                        source=str(row[source_col] or "excel")[:100] if source_col>=0 else "excel"
                        await self.execute("""INSERT INTO registrations(broadcast_id,telegram_id,status,source,updated_at) VALUES($1,$2,'registered',$3,NOW())
                            ON CONFLICT(broadcast_id,telegram_id) DO UPDATE SET status='registered',source=EXCLUDED.source,updated_at=NOW()""",bid,uid,source); success+=1
                else:
                    url_col=col("certificate_url","certificate url","сертификат")
                    if url_col<0:return await m.answer("Не найден столбец certificate_url.")
                    for row in ws.iter_rows(min_row=2,values_only=True):
                        try: uid=int(row[id_col]); url=str(row[url_col] or "").strip()
                        except Exception: bad+=1; continue
                        if not url.startswith(("http://","https://")): bad+=1; continue
                        if not await self.fetchrow("SELECT 1 FROM users WHERE telegram_id=$1",uid): unknown+=1; continue
                        await self.execute("""INSERT INTO event_certificates(broadcast_id,telegram_id,certificate_url) VALUES($1,$2,$3)
                            ON CONFLICT(broadcast_id,telegram_id) DO UPDATE SET certificate_url=EXCLUDED.certificate_url,file_id=NULL""",bid,uid,url[:1500]); success+=1
                await self.state_clear(user["telegram_id"]); return await m.answer(f"Импорт завершён ✅\nДобавлено/обновлено: {success}\nПользователь не запускал бота: {unknown}\nНекорректных строк: {bad}")
            raise SkipHandler

        super()._register_handlers()
