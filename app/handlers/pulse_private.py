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
from app.services.weekly_pulse_cycle_service import upsert_leader_membership, mark_cycle_participant_submitted
from app.services.pulse_questionnaire_service import current_form, create_inboxes
from app.services.leadership_weekly_service import submit_weekly_pulse

router = Router(name="pulse_private")


class PulseState(StatesGroup):
    answer = State()


def keyboard(data, preview=False):
    buttons = []
    if not preview:
        for i, choice in enumerate(data["questions"][data["index"]].get("choices", [])):
            buttons.append([InlineKeyboardButton(text=choice, callback_data=f"pulse_form:choice:{data['cycle_id']}:{data['index']}:{i}")])
    if preview:
        buttons.append(
            [
                InlineKeyboardButton(
                    text="Отправить Пульс", callback_data=f"pulse_form:submit:{data['cycle_id']}:{data['index']}"
                )
            ]
        )
    elif not data["questions"][data["index"]]["required"]:
        buttons.append(
            [InlineKeyboardButton(text="Пропустить", callback_data=f"pulse_form:skip:{data['cycle_id']}:{data['index']}")]
        )
    if data["index"] > 0:
        buttons.append(
            [InlineKeyboardButton(text="Назад", callback_data=f"pulse_form:back:{data['cycle_id']}:{data['index']}")]
        )
    buttons.append(
        [
            InlineKeyboardButton(
                text="Продолжить позже", callback_data=f"pulse_form:pause:{data['cycle_id']}:{data['index']}"
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


def callback_matches_current_cycle(parts, *, cycle_id: int, index: int) -> bool:
    """Reject buttons from earlier weeks even when the question index matches."""
    return (
        len(parts) in {4, 5}
        and parts[2].isdigit()
        and int(parts[2]) == cycle_id
        and parts[3].isdigit()
        and int(parts[3]) == index
    )


def first_missing_required(data):
    """Return the first unanswered required question, if any."""
    for index, question in enumerate(data["questions"]):
        if question.get("required") and not str(data.get("draft", {}).get(question["key"], "")).strip():
            return index
    return None



def update_activity_followup(data, *, question_index: int, selected: str) -> None:
    """Change the explanation prompt only for the inactivity answer.

    Preserve the configured result question so navigating back and changing
    the answer does not leave an unrelated mandatory explanation behind.
    """
    questions = data["questions"]
    if questions[question_index].get("key") != "done":
        return
    next_index = question_index + 1
    if next_index >= len(questions) or questions[next_index].get("key") != "result":
        return

    previous = data.get("draft", {}).get("done")
    questions = list(questions)
    if selected == "Не было активности":
        if "original_result_question" not in data:
            data["original_result_question"] = dict(questions[next_index])
        questions[next_index] = {
            **questions[next_index],
            "text": "Почему не было активности? Учёба, работа, поездка, нет задач или блокер?",
            "required": True,
        }
    elif "original_result_question" in data:
        questions[next_index] = data.pop("original_result_question")
    data["questions"] = questions

    # A previous free-text activity answer can also have a result attached.
    # Never reuse that result as the explanation for a new inactivity choice.
    if previous and previous != selected:
        data["draft"] = dict(data.get("draft", {}))
        data["draft"].pop("result", None)


def preview_pages(data, max_chars=3500):
    """Keep the review below Telegram's 4096-character HTML message limit."""
    pages = []
    current = "<b>Проверь свой Пульс</b>"
    for q in data["questions"]:
        key = q["key"]
        question_text = escape(str(q.get("text", ""))[:300])
        answer = escape(str(data.get("draft", {}).get(key, "—"))[:120])
        block = f"\n\n{question_text}\n{answer}"
        if len(current) + len(block) > max_chars:
            pages.append(current)
            current = "<b>Пульс · продолжение</b>"
        current += block
    pages.append(current)
    return pages


async def show(message, data):
    index = data["index"]
    qs = data["questions"]
    if index >= len(qs):
        pages = preview_pages(data)
        for page_index, page in enumerate(pages):
            await message.answer(
                page,
                parse_mode="HTML",
                reply_markup=keyboard(data, True) if page_index == len(pages) - 1 else None,
            )
    else:
        q = qs[index]
        await message.answer(
            f"<b>Пульс ЭРА · {index + 1}/{len(qs)}</b>\n\n{escape(str(q['text'])[:600])}{'…' if len(str(q['text'])) > 600 else ''}\n\n"
            + ("Выбери кнопку ниже или напиши ответ сообщением." if q.get('choices') else "Напиши ответ сообщением в этот чат.")
            + "\nОтвет сохраняется автоматически.",
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
    # Text answers are offered alongside buttons: keep the conditional
    # inactivity follow-up identical for both input methods.
    if key == "done":
        # Reconcile the follow-up for *every* correction, including free text
        # and attachment-only answers. Otherwise an old inactivity explanation
        # remains required after the user changes their activity answer.
        update_activity_followup(data, question_index=data["index"], selected=answer)
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
    if not await access(call.from_user, bot, settings, session, user):
        await call.answer("Доступ к Пульсу закрыт.", show_alert=True)
        await state.clear()
        return
    form = await current_form(session, user.id, settings.leaders_chat_id)
    if not form:
        await call.answer("Срок этой недели завершён.", show_alert=True)
        await state.clear()
        await call.message.answer("Срок этой недели завершён.")
        return
    cycle, view, data = form
    data = dict(data)
    parts = call.data.split(":")
    action = parts[1] if len(parts) > 1 else ""
    if not callback_matches_current_cycle(parts, cycle_id=cycle.id, index=data["index"]):
        await call.answer("Это кнопка от предыдущего вопроса. Открой актуальный вопрос ниже.", show_alert=True)
        await show(call.message, data)
        return
    if action == "submit":
        missing = first_missing_required(data)
        if data["index"] < len(data["questions"]) or missing is not None:
            if missing is not None:
                data["index"] = missing
                view.pulse.answers_json = data
                await session.flush()
            await call.answer("Чтобы отправить Пульс, ответь на обязательные вопросы.", show_alert=True)
            await show(call.message, data)
            return
    await call.answer()
    if action == "choice" and data["index"] < len(data["questions"]):
        question = data["questions"][data["index"]]
        choices = question.get("choices", [])
        if len(parts) != 5 or not parts[4].isdigit():
            return
        index = int(parts[4])
        if index >= len(choices):
            return
        selected = choices[index]
        if question["key"] == "done":
            update_activity_followup(data, question_index=data["index"], selected=selected)
        data["draft"] = {**data["draft"], question["key"]: selected}
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
        await mark_cycle_participant_submitted(session, cycle=cycle, user_id=user.id)
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
