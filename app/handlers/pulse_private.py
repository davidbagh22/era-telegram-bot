from __future__ import annotations
from html import escape
from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import (
    CallbackQuery,
    Message,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from aiogram.exceptions import TelegramAPIError
from app.services.weekly_pulse_cycle_service import upsert_leader_membership
from app.services.pulse_questionnaire_service import current_form, create_inboxes
from app.services.leadership_weekly_service import submit_weekly_pulse

router = Router(name="pulse_private")


class PulseState(StatesGroup):
    answer = State()


def keyboard(data, preview=False):
    buttons = []
    if not preview:
        for i, choice in enumerate(data["questions"][data["index"]].get("choices", [])):
            buttons.append([InlineKeyboardButton(text=choice, callback_data=f"pulse_form:choice:{i}")])
    if preview:
        buttons.append(
            [
                InlineKeyboardButton(
                    text="Отправить Пульс", callback_data="pulse_form:submit"
                )
            ]
        )
    elif not data["questions"][data["index"]]["required"]:
        buttons.append(
            [InlineKeyboardButton(text="Пропустить", callback_data="pulse_form:skip")]
        )
    if data["index"] > 0:
        buttons.append(
            [InlineKeyboardButton(text="Назад", callback_data="pulse_form:back")]
        )
    buttons.append(
        [
            InlineKeyboardButton(
                text="Продолжить позже", callback_data="pulse_form:pause"
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=buttons)


async def access(sender, bot, settings, session, user):
    if not user or user.is_archived or user.is_blocked or not settings.leaders_chat_id:
        return False
    try:
        member = await bot.get_chat_member(settings.leaders_chat_id, sender.id)
    except TelegramAPIError:
        return False
    row = await upsert_leader_membership(
        session,
        leader_chat_id=settings.leaders_chat_id,
        telegram_user_id=sender.id,
        membership_status=member.status,
        username=sender.username,
        display_name=sender.full_name,
        is_member=getattr(member, "is_member", None),
    )
    return row.is_weekly_pulse_eligible


async def show(message, data):
    index = data["index"]
    qs = data["questions"]
    if index >= len(qs):
        lines = ["<b>Проверь свой Пульс</b>"]
        for q in qs:
            lines += [
                escape(q["text"]),
                escape(data["draft"].get(q["key"], "—")[:120]),
                "",
            ]
        await message.answer(
            "\n".join(lines),
            parse_mode="HTML",
            reply_markup=keyboard(data, True),
        )
    else:
        q = qs[index]
        await message.answer(
            f"<b>Пульс ЭРА · {index + 1}/{len(qs)}</b>\n\n{escape(q['text'])}\n\nОтвет сохраняется автоматически.",
            parse_mode="HTML",
            reply_markup=keyboard(data),
        )


@router.message(
    CommandStart(deep_link=True, magic=F.args == "pulse_connect"),
    F.chat.type == "private",
)
@router.message(Command("pulse"), F.chat.type == "private")
async def start_pulse(
    message: Message, state: FSMContext, bot, settings, session, user
):
    if not await access(message.from_user, bot, settings, session, user):
        await message.answer(
            "Пульс доступен участникам чата ЛИДЕРЫ с зарегистрированным аккаунтом ЭРА. Если аккаунта ещё нет, начни с /start."
        )
        return
    form = await current_form(session, user.id, settings.leaders_chat_id)
    if not form:
        await message.answer(
            "Сейчас нет открытого сбора Пульса. Подключение к чату сохранено; при открытии недели придёт напоминание."
        )
        return
    cycle, view, data = form
    if view.report.submitted_at and data.get("index",0) >= len(data["questions"]):
        data = {**data, "index": 0}
        view.pulse.answers_json = data
    await state.set_state(PulseState.answer)
    # Submitted answers remain authoritative until the edited draft is submitted again.
    await message.answer(
        f"Неделя {cycle.week_number}. Система видит: выполнено задач {view.pulse.system_snapshot.get('tasks_completed_this_week',0)}, "
        f"мероприятий {view.pulse.system_snapshot.get('events_this_week',0)}. Добавь то, чего в ней нет."
    )
    await show(message, data)


@router.message(PulseState.answer, F.chat.type == "private", ~F.text.startswith("/"))
async def answer_pulse(
    message: Message, state: FSMContext, bot, settings, session, user
):
    if not await access(message.from_user, bot, settings, session, user):
        await state.clear()
        await message.answer("Доступ к Пульсу закрыт.")
        return
    form = await current_form(session, user.id, settings.leaders_chat_id)
    if not form:
        await state.clear()
        await message.answer("Срок этой недели завершён.")
        return
    _, view, data = form
    if data["index"] >= len(data["questions"]):
        await show(message, data)
        return
    answer = (message.text or message.caption or "").strip()
    attachment = message.document or (message.photo[-1] if message.photo else None)
    if not answer and attachment:
        answer = "Прикреплён материал"
    if not answer:
        await message.answer("Отправь текст, ссылку, фото или документ.")
        return
    if len(answer) > 2000:
        await message.answer("Сократи ответ до 2000 символов.")
        return
    data = dict(data)
    data["draft"] = dict(data["draft"])
    key = data["questions"][data["index"]]["key"]
    data["draft"][key] = answer
    attachments = dict(data.get("attachments", {}))
    attachments.pop(key, None)
    data["attachments"] = attachments
    if attachment:
        attachments = dict(data.get("attachments", {}))
        attachments[key] = attachment.file_id
        data["attachments"] = attachments
    data["index"] += 1
    view.pulse.answers_json = data
    await session.flush()
    await show(message, data)


@router.callback_query(
    F.data.startswith("pulse_form:"), F.message.chat.type == "private"
)
async def pulse_action(
    call: CallbackQuery, state: FSMContext, bot, settings, session, user
):
    await call.answer()
    if not await access(call.from_user, bot, settings, session, user):
        await state.clear()
        return
    form = await current_form(session, user.id, settings.leaders_chat_id)
    if not form:
        await state.clear()
        await call.message.answer("Срок этой недели завершён.")
        return
    cycle, view, data = form
    data = dict(data)
    action = call.data.split(":")[1]
    if action == "choice" and data["index"] < len(data["questions"]):
        question = data["questions"][data["index"]]
        choices = question.get("choices", [])
        index = int(call.data.split(":")[-1])
        if index >= len(choices): return
        data["draft"] = {**data["draft"], question["key"]: choices[index]}
        if question["key"] == "done" and choices[index] == "Не было активности":
            data["questions"] = list(data["questions"])
            data["questions"][data["index"]+1] = {"key":"result","text":"Почему не было активности? Учёба, работа, поездка, нет задач или блокер?","required":True}
        data["index"] += 1
        view.pulse.answers_json = data
        await session.flush()
        await show(call.message, data)
        return
    if action == "pause":
        await state.clear()
        await call.message.answer("Черновик сохранён. Вернуться: /pulse")
        return
    if action == "back":
        data["index"] = max(0, data["index"] - 1)
    elif (
        action == "skip"
        and data["index"] < len(data["questions"])
        and not data["questions"][data["index"]]["required"]
    ):
        data["draft"] = dict(data["draft"])
        data["draft"].pop(data["questions"][data["index"]]["key"], None)
        data["index"] += 1
    elif action == "submit":
        if data["index"] < len(data["questions"]) or any(
            q["required"] and not data["draft"].get(q["key"]) for q in data["questions"]
        ):
            return
        draft = data["draft"]
        blocker = draft.get("blocker", "")
        if blocker.lower().strip() in {"нет","ничего","нет проблем"}: blocker = ""
        await submit_weekly_pulse(
            session,
            owner_id=user.id,
            period_start=cycle.date_from,
            status="yellow" if blocker else "green",
            main_result="\n".join(
                filter(None, [draft.get("done"), draft.get("result"), draft.get("chair_decisions")])
            ),
            blocker_note=blocker,
            next_priorities=draft.get("plans", draft.get("chair_risk", "")).splitlines()[:3],
            needs_help=bool(blocker),
            bot=bot,
            settings=settings,
        )
        from sqlalchemy import select
        from app.database.leadership_models import WeeklyPulseParticipant
        participant = await session.scalar(select(WeeklyPulseParticipant).where(WeeklyPulseParticipant.cycle_id==cycle.id, WeeklyPulseParticipant.user_id==user.id))
        if participant: participant.status = "submitted"
        await create_inboxes(session, view.report, draft)
        data["submitted"] = dict(draft)
        data["submitted_attachments"] = dict(data.get("attachments", {}))
        view.pulse.answers_json = data
        await state.clear()
        await call.message.answer(
            "Готово ✓ Пульс сохранён. Изменить ответ до срока: /pulse"
        )
        return
    view.pulse.answers_json = data
    await state.set_state(PulseState.answer)
    await session.flush()
    await show(call.message, data)
