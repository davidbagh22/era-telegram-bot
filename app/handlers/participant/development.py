from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message, WebAppInfo
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.database.development_models import DevelopmentGoal, GoalReview, MonthlyCheckin
from app.database.models import User
from app.services import development_service
from app.utils.constants import ApplicationStatus
from app.utils.deep_links import miniapp_path_url

router = Router(name="participant_development")

GOAL_RESULTS = {
    "done": "Сделал",
    "partial": "Частично",
    "not_done": "Не получилось",
    "changed_mind": "Передумал",
    "lost_meaning": "Цель потеряла смысл",
}

GOAL_OBSTACLES = [
    "Не хватило времени",
    "Не хватило энергии",
    "Было непонятно, с чего начать",
    "Стало неактуально",
    "Другое",
]

PULSE_LABELS = {
    0: "Мало сил",
    1: "Нормально",
    2: "Есть энергия",
}


def _approved(user: User | None) -> bool:
    return bool(
        user
        and user.application_status == ApplicationStatus.APPROVED
        and not user.is_blocked
        and not user.is_archived
    )


def _back_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="← Главное меню", callback_data="menu:main")]
        ]
    )


def _vector_home_keyboard(*, completed: bool, started: bool, miniapp_url: str) -> InlineKeyboardMarkup:
    label = "Посмотреть результат" if completed else ("Продолжить Check-in" if started else "Проверить состояние")
    rows = [
        [InlineKeyboardButton(text=label, callback_data="vector:start")],
        [InlineKeyboardButton(text="⚡ Быстрый пульс", callback_data="vector:pulse:start")],
    ]
    if miniapp_url:
        rows.append(
            [
                InlineKeyboardButton(
                    text="Моя карта года",
                    web_app=WebAppInfo(url=miniapp_path_url(miniapp_url, "development")),
                )
            ]
        )
    rows.append([InlineKeyboardButton(text="← Главное меню", callback_data="menu:main")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _consent_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Начать свой вектор", callback_data="vector:consent")],
            [InlineKeyboardButton(text="← Главное меню", callback_data="menu:main")],
        ]
    )


def _question_keyboard(code: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=f"{option['value']} · {option['label']}",
                    callback_data=f"vector:answer:{code}:{option['value']}",
                )
            ]
            for option in development_service.ANSWER_OPTIONS
        ]
        + [[InlineKeyboardButton(text="Сохранить и выйти", callback_data="vector:home")]]
    )


def _goal_review_keyboard(goal_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=label,
                    callback_data=f"vector:goal:{goal_id}:{value}",
                )
            ]
            for value, label in GOAL_RESULTS.items()
        ]
    )


def _obstacle_keyboard(goal_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=label,
                    callback_data=f"vector:obstacle:{goal_id}:{index}",
                )
            ]
            for index, label in enumerate(GOAL_OBSTACLES)
        ]
    )


def _pulse_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=label,
                    callback_data=f"vector:pulse:{value}",
                )
            ]
            for value, label in PULSE_LABELS.items()
        ]
        + [[InlineKeyboardButton(text="← Мой вектор", callback_data="vector:home")]]
    )


async def _current_checkin(session: AsyncSession, user_id: int) -> MonthlyCheckin:
    return await development_service.get_or_create_checkin(session, user_id)


async def _unreviewed_previous_goal(
    session: AsyncSession,
    user_id: int,
    before_month: str,
) -> DevelopmentGoal | None:
    reviewed_goal_ids = select(GoalReview.goal_id)
    return await session.scalar(
        select(DevelopmentGoal)
        .where(
            DevelopmentGoal.user_id == user_id,
            DevelopmentGoal.month < before_month,
            ~DevelopmentGoal.id.in_(reviewed_goal_ids),
        )
        .order_by(desc(DevelopmentGoal.month), desc(DevelopmentGoal.id))
        .limit(1)
    )


async def _show_home(
    message: Message,
    user: User,
    session: AsyncSession,
    settings: Settings,
) -> None:
    if not await development_service.has_consent(session, user.id):
        await message.answer(
            "🧭 Мой вектор\n\n"
            "Это личная система наблюдения за собой: раз в месяц ты отмечаешь своё состояние, "
            "видишь изменения и выбираешь один небольшой фокус.\n\n"
            "Здесь нет рейтинга, диагноза или оценки личности. Твои ответы используются только "
            "для твоей динамики и персональных рекомендаций.",
            reply_markup=_consent_keyboard(),
        )
        return

    checkin = await _current_checkin(session, user.id)
    questions = await development_service.checkin_questions(session, user.id, checkin)
    answers = development_service.public_checkin_answers(checkin)
    answered = sum(1 for question in questions if question["code"] in answers)
    completed = checkin.status == "completed"

    if completed:
        status = f"Check-in месяца завершён · индекс {checkin.index_value or 0}/100"
    elif answered:
        status = f"Check-in начат · {answered}/{len(questions)}"
    else:
        status = "Новый Check-in готов"

    await message.answer(
        "🧭 Мой вектор\n\n"
        f"{status}\n\n"
        "Не пытайся отвечать «правильно». Отмечай то, что действительно похоже на последние две недели.",
        reply_markup=_vector_home_keyboard(
            completed=completed,
            started=bool(answered),
            miniapp_url=settings.effective_miniapp_url,
        ),
    )


async def _show_result(
    message: Message,
    user: User,
    session: AsyncSession,
    settings: Settings,
    checkin: MonthlyCheckin,
) -> None:
    insight = dict(checkin.insight_json or {})
    state = dict(checkin.state_json or {})
    state_line = " · ".join(
        f"{development_service.STATE_LABELS.get(code, code)} {value}"
        for code, value in state.items()
        if code in development_service.STATE_LABELS
    )
    focus = insight.get("focus") or insight.get("title") or "Наблюдать за собой"
    experiment = insight.get("experiment") or "Выбери один небольшой шаг, который можно проверить на практике."

    latest = await development_service.latest_goal(session, user.id)
    goal_already_saved = bool(latest and latest.month == checkin.month)

    rows: list[list[InlineKeyboardButton]] = []
    if not goal_already_saved:
        rows.append(
            [
                InlineKeyboardButton(
                    text="Зафиксировать фокус месяца",
                    callback_data=f"vector:goal_save:{checkin.id}",
                )
            ]
        )
    rows.append([InlineKeyboardButton(text="⚡ Быстрый пульс", callback_data="vector:pulse:start")])
    if settings.effective_miniapp_url:
        rows.append(
            [
                InlineKeyboardButton(
                    text="Открыть карту года",
                    web_app=WebAppInfo(
                        url=miniapp_path_url(settings.effective_miniapp_url, "development")
                    ),
                )
            ]
        )
    rows.append([InlineKeyboardButton(text="← Главное меню", callback_data="menu:main")])

    body = (
        f"🧭 Твой вектор · {checkin.index_value or 0}/100\n\n"
        f"{insight.get('support', '')}\n\n"
        f"Что изменилось\n{insight.get('change', '')}\n\n"
        f"Фокус месяца\n{focus}\n\n"
        f"Попробуй\n{experiment}"
    )
    if state_line:
        body += f"\n\n{state_line}"
    body += "\n\nЭто снимок текущего состояния, а не оценка тебя как личности."
    await message.answer(body, reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))


async def _send_next_question(
    message: Message,
    user: User,
    session: AsyncSession,
    settings: Settings,
    checkin: MonthlyCheckin,
) -> None:
    if checkin.status == "completed":
        await _show_result(message, user, session, settings, checkin)
        return

    questions = await development_service.checkin_questions(session, user.id, checkin)
    answers = development_service.public_checkin_answers(checkin)
    for index, question in enumerate(questions, start=1):
        if question["code"] in answers:
            continue
        await message.answer(
            f"{index}/{len(questions)} · {question['title']}\n\n{question['text']}",
            reply_markup=_question_keyboard(question["code"]),
        )
        return

    checkin = await development_service.complete_checkin(session, checkin)
    await development_service.audit(
        session,
        actor_user_id=user.id,
        action="development.bot_checkin.completed",
        target_user_id=user.id,
        metadata={"month": checkin.month},
    )
    await _show_result(message, user, session, settings, checkin)


@router.message(Command("vector"), F.chat.type == "private")
async def vector_command(
    message: Message,
    user: User | None,
    session: AsyncSession,
    settings: Settings,
) -> None:
    if not _approved(user):
        await message.answer("Мой вектор доступен после одобрения заявки.")
        return
    await _show_home(message, user, session, settings)


@router.callback_query(F.data == "vector:home")
async def vector_home(
    call: CallbackQuery,
    user: User | None,
    session: AsyncSession,
    settings: Settings,
) -> None:
    await call.answer()
    if not _approved(user):
        return
    await _show_home(call.message, user, session, settings)


@router.callback_query(F.data == "vector:consent")
async def vector_consent(
    call: CallbackQuery,
    user: User | None,
    session: AsyncSession,
    settings: Settings,
) -> None:
    await call.answer("Готово")
    if not _approved(user):
        return
    await development_service.record_consent(session, user.id, True)
    await development_service.audit(
        session,
        actor_user_id=user.id,
        action="development.bot_consent.accepted",
        target_user_id=user.id,
    )
    await call.message.answer(
        "Готово. Начнём с короткого Check-in — обычно это занимает несколько минут."
    )
    checkin = await _current_checkin(session, user.id)
    await _send_next_question(call.message, user, session, settings, checkin)


@router.callback_query(F.data == "vector:start")
async def vector_start(
    call: CallbackQuery,
    user: User | None,
    session: AsyncSession,
    settings: Settings,
) -> None:
    await call.answer()
    if not _approved(user):
        return
    if not await development_service.has_consent(session, user.id):
        await _show_home(call.message, user, session, settings)
        return

    checkin = await _current_checkin(session, user.id)
    if checkin.status != "completed":
        previous_goal = await _unreviewed_previous_goal(session, user.id, checkin.month)
        if previous_goal is not None:
            await call.message.answer(
                "Перед новым Check-in — один короткий вопрос.\n\n"
                f"В прошлом месяце твой фокус был:\n«{previous_goal.title}»\n\n"
                "Что с ним произошло?",
                reply_markup=_goal_review_keyboard(previous_goal.id),
            )
            return
    await _send_next_question(call.message, user, session, settings, checkin)


@router.callback_query(F.data.startswith("vector:answer:"))
async def vector_answer(
    call: CallbackQuery,
    user: User | None,
    session: AsyncSession,
    settings: Settings,
) -> None:
    if not _approved(user):
        await call.answer()
        return
    try:
        _, _, code, raw_value = call.data.split(":", 3)
        value = int(raw_value)
    except (ValueError, AttributeError):
        await call.answer("Ответ не сохранён")
        return

    checkin = await _current_checkin(session, user.id)
    try:
        await development_service.save_checkin(session, checkin, {code: value})
    except ValueError:
        await call.answer("Этот вопрос уже недоступен")
        return
    await call.answer("Сохранено")
    await _send_next_question(call.message, user, session, settings, checkin)


@router.callback_query(F.data.startswith("vector:goal:"))
async def vector_goal_review(
    call: CallbackQuery,
    user: User | None,
    session: AsyncSession,
    settings: Settings,
) -> None:
    if not _approved(user):
        await call.answer()
        return
    try:
        _, _, raw_goal_id, result = call.data.split(":", 3)
        goal_id = int(raw_goal_id)
    except (ValueError, AttributeError):
        await call.answer("Не удалось сохранить")
        return
    if result not in GOAL_RESULTS:
        await call.answer("Не удалось сохранить")
        return
    await call.answer()
    if result == "not_done":
        await call.message.answer(
            "Что больше всего помешало?",
            reply_markup=_obstacle_keyboard(goal_id),
        )
        return
    try:
        await development_service.review_goal(
            session,
            user.id,
            goal_id,
            result,
            obstacle=None,
            note=None,
        )
    except ValueError:
        await call.message.answer("Этот фокус уже недоступен.")
        return
    await call.message.answer("Принято. Это не оценка результата — просто точка для сравнения с новым месяцем.")
    checkin = await _current_checkin(session, user.id)
    await _send_next_question(call.message, user, session, settings, checkin)


@router.callback_query(F.data.startswith("vector:obstacle:"))
async def vector_goal_obstacle(
    call: CallbackQuery,
    user: User | None,
    session: AsyncSession,
    settings: Settings,
) -> None:
    if not _approved(user):
        await call.answer()
        return
    try:
        _, _, raw_goal_id, raw_index = call.data.split(":", 3)
        goal_id = int(raw_goal_id)
        obstacle = GOAL_OBSTACLES[int(raw_index)]
    except (ValueError, IndexError, AttributeError):
        await call.answer("Не удалось сохранить")
        return
    try:
        await development_service.review_goal(
            session,
            user.id,
            goal_id,
            "not_done",
            obstacle=obstacle,
            note=None,
        )
    except ValueError:
        await call.answer("Этот фокус уже недоступен")
        return
    await call.answer("Сохранено")
    await call.message.answer("Понял. Учтём это при выборе нового фокуса — без чувства долга и без штрафов.")
    checkin = await _current_checkin(session, user.id)
    await _send_next_question(call.message, user, session, settings, checkin)


@router.callback_query(F.data.startswith("vector:goal_save:"))
async def vector_goal_save(
    call: CallbackQuery,
    user: User | None,
    session: AsyncSession,
) -> None:
    if not _approved(user):
        await call.answer()
        return
    try:
        checkin_id = int(call.data.rsplit(":", 1)[-1])
    except (ValueError, AttributeError):
        await call.answer("Не удалось сохранить")
        return
    checkin = await session.get(MonthlyCheckin, checkin_id)
    if checkin is None or checkin.user_id != user.id or checkin.status != "completed":
        await call.answer("Результат недоступен")
        return
    latest = await development_service.latest_goal(session, user.id)
    if latest and latest.month == checkin.month:
        await call.answer("Фокус уже сохранён")
        return
    insight = dict(checkin.insight_json or {})
    title = str(insight.get("focus") or insight.get("title") or "Наблюдать за собой")
    experiment = str(insight.get("experiment") or "") or None
    semantic_tag = str(insight.get("semantic_tag") or "") or None
    goal = await development_service.create_goal(
        session,
        user.id,
        title=title,
        experiment=experiment,
        semantic_tag=semantic_tag,
        is_custom=False,
    )
    await development_service.audit(
        session,
        actor_user_id=user.id,
        action="development.bot_goal.created",
        target_user_id=user.id,
        metadata={"goal_id": goal.id, "month": goal.month},
    )
    await call.answer("Фокус сохранён")
    await call.message.answer(
        f"Фокус месяца зафиксирован:\n«{goal.title}»\n\n"
        f"Эксперимент: {goal.experiment or 'один небольшой проверяемый шаг'}\n\n"
        "В следующем месяце бот сначала спросит, что получилось — без штрафов и серии «дней подряд».",
        reply_markup=_back_keyboard(),
    )


@router.callback_query(F.data == "vector:pulse:start")
async def vector_pulse_start(call: CallbackQuery, user: User | None) -> None:
    await call.answer()
    if not _approved(user):
        return
    await call.message.answer(
        "⚡ Быстрый пульс\n\nКак у тебя с энергией прямо сейчас?",
        reply_markup=_pulse_keyboard(),
    )


@router.callback_query(F.data.startswith("vector:pulse:"))
async def vector_pulse_save(
    call: CallbackQuery,
    user: User | None,
    session: AsyncSession,
) -> None:
    if not _approved(user):
        await call.answer()
        return
    try:
        energy = int(call.data.rsplit(":", 1)[-1])
        label = PULSE_LABELS[energy]
    except (ValueError, KeyError, AttributeError):
        await call.answer("Не удалось сохранить")
        return
    await development_service.save_weekly_pulse(session, user.id, energy)
    await development_service.audit(
        session,
        actor_user_id=user.id,
        action="development.bot_pulse.saved",
        target_user_id=user.id,
        metadata={"energy": energy},
    )
    await call.answer("Сохранено")
    await call.message.answer(
        f"Пульс сохранён: {label}.\n\nНикаких серий и штрафов — это просто ещё одна точка твоей динамики.",
        reply_markup=_back_keyboard(),
    )
