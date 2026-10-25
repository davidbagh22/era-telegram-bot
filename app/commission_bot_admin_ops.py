from __future__ import annotations

import asyncio
import html
import json
import logging
from datetime import datetime, timezone

from aiogram import F
from aiogram.dispatcher.event.bases import SkipHandler
from aiogram.enums import ChatType
from aiogram.types import CallbackQuery, Message

from app.commission_bot import _kb
from app.commission_bot_admin_helpers import CRM_TAGS
from app.commission_bot_online_ops import CommissionBotOnlineOps

log = logging.getLogger(__name__)

ADMIN_OPS_DDL = r"""
CREATE TABLE IF NOT EXISTS lifecycle_notifications (
  dedupe_key TEXT PRIMARY KEY,
  telegram_id BIGINT NOT NULL REFERENCES users(telegram_id) ON DELETE CASCADE,
  kind TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'sent',
  sent_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_lifecycle_notifications_user ON lifecycle_notifications(telegram_id,kind,sent_at DESC);
"""


class CommissionBotAdminOps(CommissionBotOnlineOps):
    async def init_db(self) -> None:
        await super().init_db()
        await self.execute(ADMIN_OPS_DDL)

    async def _show_management(self, chat_id: int, user) -> None:
        if user["role"] not in {"admin", "owner"}:
            return await self.bot.send_message(chat_id, "Этот раздел доступен администратору и владельцу.")
        rows = [
            [("🎯 Рассылки и сегменты", "seg:menu"), ("🚨 Срочное сообщение", "urgent:menu")],
            [("📣 Чаты и каналы", "tg:list"), ("👥 База участников", "crm:menu")],
            [("📈 Эффективность", "svadm:menu"), ("📊 Аналитика", "ux:analytics")],
            [("💬 Обращения", "support:staff:list")],
        ]
        if user["role"] == "owner":
            rows.append([("👥 Команда", "ux:team")])
        rows.extend([
            [("🔔 Уведомления", "ux:notifications"), ("👤 Профиль", "ux:profile")],
            [("❓ Как пользоваться", "ux:help")],
            [("⬅️ Главное меню", "menu")],
        ])
        await self.bot.send_message(
            chat_id,
            "<b>⚙️ Управление</b>\n\nАудитории, площадки, база участников, качество движения и служебные инструменты.",
            reply_markup=_kb(rows),
        )

    async def _show_segment_builder(self, chat_id: int, uid: int, p: dict) -> None:
        seg = p.setdefault("segment", {})
        channels = p.setdefault("channels", {"dm": True, "targets": False})
        users_count, targets_count = await self._estimate_segment(seg, channels)
        p["estimate"] = {"users": users_count, "targets": targets_count}
        await self.state_set(uid, "segment:builder", p)
        rows = [
            [("🌍 География", "seg:geo"), ("🎂 Возраст", "seg:age")],
            [("👤 Статус", "seg:status"), ("✨ Интересы", "seg:interest")],
            [("🏷 Теги участников", "seg:tags")],
            [("✅ Только активные" if seg.get("active_only") else "▫️ Только активные", "seg:active")],
            [("✅ Личные" if channels.get("dm") else "▫️ Личные", "seg:ch:dm"), ("✅ Чаты" if channels.get("targets") else "▫️ Чаты", "seg:ch:targets")],
            [(f"👥 Проверить аудиторию · {users_count + targets_count}", "seg:estimate")],
            [("✍️ Написать сообщение", "seg:compose")],
            [("✖️ Отмена", "seg:cancel")],
        ]
        await self.bot.send_message(
            chat_id,
            "<b>🎯 Новая точная рассылка</b>\n\n" + self._segment_summary(p) +
            f"\n\nСейчас получателей: <b>{users_count}</b> участников и <b>{targets_count}</b> чатов/каналов.\n\n"
            "Фильтры между разными группами работают как AND, внутри одной группы — как OR. Ничего не отправится без финального подтверждения.",
            reply_markup=_kb(rows),
        )

    async def _crm_card(self, chat_id: int, viewer, uid: int) -> None:
        if viewer["role"] not in {"editor", "admin", "owner"}:
            return
        user = await self.fetchrow("SELECT * FROM users WHERE telegram_id=$1", uid)
        if not user:
            return await self.bot.send_message(chat_id, "Участник не найден.")
        tags = await self.fetch("SELECT tag FROM user_tags WHERE telegram_id=$1 ORDER BY tag", uid)
        notes = await self.fetch(
            "SELECT n.*,u.first_name author_name,u.username author_username FROM participant_notes n LEFT JOIN users u ON u.telegram_id=n.author_id WHERE n.telegram_id=$1 ORDER BY n.id DESC LIMIT 5",
            uid,
        )
        stats = await self.fetchrow(
            """SELECT COUNT(*) FILTER(WHERE status IN ('registered','attended')) registered,
            COUNT(*) FILTER(WHERE status='cancelled') cancelled,
            COUNT(*) FILTER(WHERE status='waitlist') waitlist,
            COUNT(DISTINCT source) sources
            FROM registrations WHERE telegram_id=$1""", uid,
        )
        name = user["registration_name"] or " ".join(x for x in [user["first_name"], user["last_name"]] if x) or str(uid)
        lines = [
            f"<b>👤 {html.escape(name)}</b>",
            f"@{html.escape(user['username'])}" if user["username"] else f"Telegram ID: <code>{uid}</code>",
            "",
            f"🌍 {html.escape(user['country_name'] or '—')} · {html.escape(user['city'] or '—')}",
            f"🎂 {user['age'] or '—'} · {html.escape(user['participant_status'] or '—')}",
            f"🏢 {html.escape(user['organization'] or '—')}",
            f"📱 {html.escape(user['phone'] or '—')}",
            f"✉️ {html.escape(user['email'] or '—')}",
            f"🔗 {html.escape(user['social_url'] or '—')}",
            "",
            f"⚡ Активность: <b>{html.escape(user['activity_level'] or 'new')}</b>",
            f"🎟 Участий/регистраций: {stats['registered']} · отмен: {stats['cancelled']} · waitlist: {stats['waitlist']}",
            "🏷 " + (", ".join(html.escape(r["tag"]) for r in tags) if tags else "тегов нет"),
        ]
        if notes:
            lines.append("\n<b>Внутренние заметки</b>")
            for note in notes:
                author = note["author_name"] or note["author_username"] or str(note["author_id"])
                lines.append(f"• {html.escape(note['note'])} <i>— {html.escape(author)}</i>")
        await self.bot.send_message(
            chat_id,
            "\n".join(lines),
            reply_markup=_kb([
                [("🏷 Теги", f"crm:tags:{uid}"), ("📝 Заметка", f"crm:note:{uid}")],
                [("📚 История участия", f"crm:history:{uid}")],
                [("⬅️ База участников", "crm:menu")],
            ]),
            disable_web_page_preview=True,
        )

    async def _lifecycle_tick(self) -> None:
        now = datetime.now(timezone.utc)
        quarter = f"{now.year}-Q{(now.month - 1) // 3 + 1}"
        rows = await self.fetch(
            """SELECT telegram_id FROM users
            WHERE onboarding_complete=TRUE AND telegram_opt_in=TRUE AND activity_level='inactive'
              AND role='viewer' AND last_activity_at<NOW()-INTERVAL '90 days'
            LIMIT 200"""
        )
        for row in rows:
            key = f"reactivate:{quarter}:{row['telegram_id']}"
            if await self.fetchrow("SELECT 1 FROM lifecycle_notifications WHERE dedupe_key=$1", key):
                continue
            try:
                await self.bot.send_message(
                    row["telegram_id"],
                    "<b>Давно не виделись 👋</b>\n\nЗа это время появились новые онлайн-встречи и возможности. Без длинной рассылки — просто оставлю кнопку, если захочешь посмотреть, что актуально сейчас.",
                    reply_markup=_kb([[("📅 Посмотреть события", "events:list")], [("🔕 Выключить общие рассылки", "notify:toggle")]]),
                )
                await self.execute("INSERT INTO lifecycle_notifications(dedupe_key,telegram_id,kind) VALUES($1,$2,'reactivation')", key, row["telegram_id"])
            except Exception:
                log.exception("reactivation message failed for %s", row["telegram_id"])
            await asyncio.sleep(0.05)

    async def _lifecycle_scheduler(self) -> None:
        while True:
            try:
                await self._lifecycle_tick()
            except Exception:
                log.exception("lifecycle scheduler")
            await asyncio.sleep(3600)

    async def reminders_loop(self):
        task = asyncio.create_task(self._lifecycle_scheduler())
        try:
            await super().reminders_loop()
        finally:
            task.cancel()

    def _register_handlers(self):
        r = self.router

        @r.callback_query(F.data == "seg:tags")
        async def segment_tags(c: CallbackQuery):
            await c.answer(); st = await self.state_get(c.from_user.id); p = dict(st["payload"] or {}) if st else {}; chosen = set(p.setdefault("segment", {}).get("tags") or [])
            items = list(CRM_TAGS.items()); rows=[]
            for i in range(0,len(items),2):
                rows.append([(("✅ " if key in chosen else "▫️ ") + label, f"seg:tag:{key}") for key,label in items[i:i+2]])
            rows.append([("Готово →", "seg:back")]); await c.message.answer("Теги участников — можно выбрать несколько:",reply_markup=_kb(rows))

        @r.callback_query(F.data.startswith("seg:tag:"))
        async def segment_tag_toggle(c: CallbackQuery):
            await c.answer(); tag=c.data.split(":",2)[2]
            if tag not in CRM_TAGS:return
            st=await self.state_get(c.from_user.id); p=dict(st["payload"] or {}); seg=p.setdefault("segment",{}); selected=list(seg.get("tags") or []); seg["tags"]=[x for x in selected if x!=tag] if tag in selected else selected+[tag]; await self.state_set(c.from_user.id,"segment:builder",p)

        @r.callback_query(F.data == "crm:menu")
        async def crm_menu(c: CallbackQuery):
            await c.answer(); user=await self.ensure_user(c.from_user)
            if user["role"] not in {"editor","admin","owner"}:return
            stats=await self.fetchrow("SELECT COUNT(*) total,COUNT(*) FILTER(WHERE activity_level IN ('active','very_active','core')) active,COUNT(*) FILTER(WHERE activity_level='inactive') inactive FROM users WHERE onboarding_complete=TRUE")
            await c.message.answer(f"<b>👥 База участников</b>\n\nВсего: <b>{stats['total']}</b> · активных: <b>{stats['active']}</b> · неактивных: {stats['inactive']}\n\nИщи по имени, username, email, телефону или Telegram ID.",reply_markup=_kb([[('🔎 Найти участника','crm:search')],[('⚡ Активные','crm:list:active'),('😴 Неактивные','crm:list:inactive')],[('⬅️ Управление','menu')]]))

        @r.callback_query(F.data == "crm:search")
        async def crm_search(c: CallbackQuery): await c.answer(); await self.state_set(c.from_user.id,"crm:search",{}); await c.message.answer("Напиши имя, @username, email, телефон или Telegram ID.")

        @r.callback_query(F.data.startswith("crm:list:"))
        async def crm_list(c: CallbackQuery):
            await c.answer(); mode=c.data.split(":",2)[2]
            if mode=='active': rows=await self.fetch("SELECT * FROM users WHERE onboarding_complete=TRUE AND activity_level IN ('active','very_active','core') ORDER BY last_activity_at DESC LIMIT 50")
            else: rows=await self.fetch("SELECT * FROM users WHERE onboarding_complete=TRUE AND activity_level='inactive' ORDER BY last_activity_at DESC LIMIT 50")
            if not rows:return await c.message.answer("Список пуст.")
            buttons=[]
            for u in rows:
                name=u["registration_name"] or " ".join(x for x in [u["first_name"],u["last_name"]] if x) or str(u["telegram_id"]); buttons.append([(f"{name} · {u['country_name'] or '—'}"[:60],f"crm:view:{u['telegram_id']}")])
            await c.message.answer("Участники:",reply_markup=_kb(buttons))

        @r.callback_query(F.data.startswith("crm:view:"))
        async def crm_view(c: CallbackQuery): await c.answer(); viewer=await self.ensure_user(c.from_user); await self._crm_card(c.message.chat.id,viewer,int(c.data.rsplit(":",1)[1]))

        @r.callback_query(F.data.startswith("crm:tags:"))
        async def crm_tags(c: CallbackQuery):
            await c.answer(); uid=int(c.data.rsplit(":",1)[1]); existing={x["tag"] for x in await self.fetch("SELECT tag FROM user_tags WHERE telegram_id=$1",uid)}; items=list(CRM_TAGS.items()); rows=[]
            for i in range(0,len(items),2): rows.append([(("✅ " if key in existing else "▫️ ")+label,f"crm:tag:{uid}:{key}") for key,label in items[i:i+2]])
            rows.append([("Готово →",f"crm:view:{uid}")]); await c.message.answer("Теги используются во внутренних карточках и точной сегментации:",reply_markup=_kb(rows))

        @r.callback_query(F.data.startswith("crm:tag:"))
        async def crm_tag_toggle(c: CallbackQuery):
            await c.answer(); _,_,uid_s,tag=c.data.split(":",3); uid=int(uid_s)
            if tag not in CRM_TAGS:return
            exists=await self.fetchrow("SELECT 1 FROM user_tags WHERE telegram_id=$1 AND tag=$2",uid,tag)
            if exists: await self.execute("DELETE FROM user_tags WHERE telegram_id=$1 AND tag=$2",uid,tag)
            else: await self.execute("INSERT INTO user_tags(telegram_id,tag,source,created_by) VALUES($1,$2,'manual',$3) ON CONFLICT DO NOTHING",uid,tag,c.from_user.id)
            await c.answer("Сохранено")

        @r.callback_query(F.data.startswith("crm:note:"))
        async def crm_note(c: CallbackQuery): await c.answer(); uid=int(c.data.rsplit(":",1)[1]); await self.state_set(c.from_user.id,"crm:note",{"target_uid":uid}); await c.message.answer("Внутренняя заметка. Её увидит только команда, участнику она не отправится.")

        @r.callback_query(F.data.startswith("crm:history:"))
        async def crm_history(c: CallbackQuery):
            await c.answer(); uid=int(c.data.rsplit(":",1)[1]); rows=await self.fetch("SELECT r.status,r.source,r.registered_at,b.title,b.event_at FROM registrations r JOIN broadcasts b ON b.id=r.broadcast_id WHERE r.telegram_id=$1 ORDER BY r.registered_at DESC LIMIT 30",uid)
            if not rows:return await c.message.answer("Истории участий пока нет.")
            text="<b>📚 История участия</b>\n\n"+"\n".join(f"• {html.escape(row['title'])} · {row['status']} · {html.escape(row['source'] or 'telegram')}" for row in rows); await c.message.answer(text[:3900])

        @r.callback_query(F.data == "urgent:menu")
        async def urgent_menu(c: CallbackQuery):
            await c.answer(); user=await self.ensure_user(c.from_user)
            if user["role"] not in {"admin","owner"}:return
            await c.message.answer("<b>🚨 Срочное сообщение</b>\n\nИспользуй только когда информация действительно не может ждать обычной публикации. Даже здесь бот покажет аудиторию и потребует финальное подтверждение.",reply_markup=_kb([[('👤 Всем участникам','urgent:mode:dm'),('📣 Всем площадкам','urgent:mode:targets')],[('🌐 Участники + площадки','urgent:mode:both')],[('✖️ Отмена','menu')]]))

        @r.callback_query(F.data.startswith("urgent:mode:"))
        async def urgent_mode(c: CallbackQuery):
            await c.answer(); mode=c.data.split(":",2)[2]; channels={"dm":mode in {'dm','both'},"targets":mode in {'targets','both'}}; users,targets=await self._estimate_segment({},channels)
            await self.state_set(c.from_user.id,"urgent:text",{"channels":channels,"estimate":{"users":users,"targets":targets}}); await c.message.answer(f"Аудитория: <b>{users}</b> участников + <b>{targets}</b> площадок.\n\nТеперь отправь текст срочного сообщения.")

        @r.callback_query(F.data == "urgent:send")
        async def urgent_send(c: CallbackQuery):
            await c.answer(); user=await self.ensure_user(c.from_user); st=await self.state_get(user["telegram_id"])
            if not st or st["state"]!='urgent:preview':return
            p=dict(st["payload"] or {}); users,targets=await self._estimate_segment({},p["channels"])
            if users+targets==0:return await c.message.answer("Аудитория пустая — отправка остановлена.")
            campaign=await self.fetchrow("INSERT INTO segment_campaigns(created_by,body,segment,channels,status,estimated_users,estimated_targets) VALUES($1,$2,'{}'::jsonb,$3::jsonb,'sending',$4,$5) RETURNING id",user["telegram_id"],"🚨 СРОЧНО\n\n"+p["body"],json.dumps(p["channels"]),users,targets); await self.state_clear(user["telegram_id"]); await self.audit(user["telegram_id"],"urgent_campaign_started","segment_campaign",campaign["id"],{"users":users,"targets":targets}); asyncio.create_task(self._deliver_segment_campaign(campaign["id"])); await c.message.answer(f"Срочная рассылка #{campaign['id']} запущена ✅")

        @r.callback_query(F.data.startswith("evx:fb:"))
        async def feedback_with_comment(c: CallbackQuery):
            await c.answer(); _,_,bid_s,score_s=c.data.split(":",3); bid=int(bid_s); score=int(score_s)
            if score not in range(1,6):return
            await self.execute("""INSERT INTO online_event_feedback(broadcast_id,telegram_id,score) VALUES($1,$2,$3)
                ON CONFLICT(broadcast_id,telegram_id) DO UPDATE SET score=EXCLUDED.score,created_at=NOW()""",bid,c.from_user.id,score)
            await self.state_set(c.from_user.id,"event:feedback_comment",{"broadcast_id":bid}); await c.message.answer("Спасибо за оценку 💛\n\nЕсли хочешь, добавь одну короткую мысль: что было сильным или что стоит улучшить?",reply_markup=_kb([[("Пропустить →",f"evfb:skip:{bid}")]]))

        @r.callback_query(F.data.startswith("evfb:skip:"))
        async def feedback_skip(c: CallbackQuery): await c.answer(); await self.state_clear(c.from_user.id); await c.message.answer("Готово. Спасибо за обратную связь ✨")

        @r.message(F.chat.type == ChatType.PRIVATE)
        async def admin_ops_state(m: Message):
            user=await self.ensure_user(m.from_user); st=await self.state_get(user["telegram_id"])
            if not st:raise SkipHandler
            state=str(st["state"]); p=dict(st["payload"] or {}); text=(m.text or "").strip()
            if state=='crm:search':
                q=text.lstrip('@')[:100]
                if not q:return await m.answer("Напиши данные для поиска.")
                rows=await self.fetch("""SELECT * FROM users WHERE onboarding_complete=TRUE AND (
                    CAST(telegram_id AS TEXT)=$1 OR username ILIKE $2 OR registration_name ILIKE $2 OR first_name ILIKE $2 OR last_name ILIKE $2 OR email ILIKE $2 OR phone ILIKE $2)
                    ORDER BY last_activity_at DESC LIMIT 30""",q,f"%{q}%"); await self.state_clear(user["telegram_id"])
                if not rows:return await m.answer("Совпадений не нашёл.")
                buttons=[]
                for u in rows:
                    name=u["registration_name"] or " ".join(x for x in [u["first_name"],u["last_name"]] if x) or str(u["telegram_id"]); buttons.append([(f"{name} · {u['country_name'] or '—'}"[:60],f"crm:view:{u['telegram_id']}")])
                return await m.answer("Нашёл:",reply_markup=_kb(buttons))
            if state=='crm:note':
                uid=int(p.get('target_uid') or 0)
                if not uid or not text:return await m.answer("Напиши заметку текстом.")
                await self.execute("INSERT INTO participant_notes(telegram_id,author_id,note) VALUES($1,$2,$3)",uid,user["telegram_id"],text[:1500]); await self.state_clear(user["telegram_id"]); return await m.answer("Заметка сохранена 📝")
            if state=='urgent:text':
                if not text:return await m.answer("Отправь текст сообщения.")
                if len(text)>3300:return await m.answer("Сократи текст до 3300 символов.")
                p['body']=text; users,targets=await self._estimate_segment({},p['channels']); p['estimate']={'users':users,'targets':targets}; await self.state_set(user['telegram_id'],'urgent:preview',p); return await m.answer(f"<b>🚨 Финальная проверка</b>\n\n{html.escape(text)}\n\nПолучат: <b>{users}</b> участников + <b>{targets}</b> площадок.\n\nПосле следующей кнопки отправка начнётся сразу.",reply_markup=_kb([[("🚨 Отправить срочно",'urgent:send')],[("✖️ Отмена",'seg:cancel')]]))
            if state=='event:feedback_comment':
                bid=int(p.get('broadcast_id') or 0)
                if not bid:raise SkipHandler
                await self.execute("UPDATE online_event_feedback SET comment=$3 WHERE broadcast_id=$1 AND telegram_id=$2",bid,user['telegram_id'],text[:1200] if text else None); await self.state_clear(user['telegram_id']); return await m.answer("Спасибо 💛 Комментарий сохранён.")
            raise SkipHandler

        super()._register_handlers()
