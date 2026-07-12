from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import BufferedInputFile, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.database.management_models import AdminSurvey, AdminSurveyResponse
from app.database.models import User
from app.handlers.admin.management_ready import _analytics_payload, _guard
from app.services.notification_service import safe_send
from app.services.survey_excel_service import build_survey_workbook
from app.services.survey_service import (
    MONTHLY_SURVEY_DESCRIPTION,
    MONTHLY_SURVEY_QUESTIONS,
    MONTHLY_SURVEY_TITLE,
    answer_items,
    parse_survey_text,
    questions_payload,
    survey_questions,
)
from app.utils.constants import ApplicationStatus

router = Router(name="admin_surveys_analytics")


class AdminSurveyStates(StatesGroup):
    create_text = State()
    edit_text = State()


def _status_label(status: str) -> str:
    return {
        "draft": "Черновик",
        "active": "Активен",
        "sent": "Отправлен",
        "archived": "Архив",
    }.get(status, status)


def _survey_keyboard(survey_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📤 Подготовить рассылку", callback_data=f"admin:survey:prepare:{survey_id}")],
            [InlineKeyboardButton(text="📊 Результаты", callback_data=f"admin:survey:results:{survey_id}")],
            [InlineKeyboardButton(text="✏️ Редактировать", callback_data=f"admin:survey:edit:{survey_id}")],
            [InlineKeyboardButton(text="🗄 В архив", callback_data=f"admin:survey:archive:{survey_id}")],
            [InlineKeyboardButton(text="← Все опросы", callback_data="admin:surveys")],
        ]
    )


def _survey_create_hint() -> str:
    return (
        "Отправьте опрос одним сообщением в таком формате:\n\n"
        "Название опроса\n"
        "Короткое описание — можно пропустить\n"
        "---\n"
        "Первый вопрос\n"
        "Второй вопрос\n"
        "Третий вопрос\n\n"
        "Пример: ежемесячная обратная связь, настроение команды, идеи для мероприятий"
    )


async def _survey_response_count(session: AsyncSession, survey_id: int) -> int:
    return int(
        await session.scalar(
            select(func.count())
            .select_from(AdminSurveyResponse)
            .where(AdminSurveyResponse.survey_id == survey_id)
        )
        or 0
    )


async def _show_survey(message: Message, session: AsyncSession, survey: AdminSurvey) -> None:
    questions = survey_questions(survey)
    response_count = await _survey_response_count(session, survey.id)
    question_lines = "\n".join(f"{idx}. {question}" for idx, question in enumerate(questions, 1))
    text = (
        f"🗳 {survey.title}\n\n"
        f"Статус: {_status_label(survey.status)}\n"
        f"Тип: {'ежемесячный' if survey.is_monthly else 'разовый'}\n"
        f"Ответов: {response_count}\n"
        f"Вопросов: {len(questions)}\n"
        f"Последняя рассылка: {survey.sent_at:%d.%m.%Y %H:%M}" if survey.sent_at else f"🗳 {survey.title}\n\nСтатус: {_status_label(survey.status)}\nТип: {'ежемесячный' if survey.is_monthly else 'разовый'}\nОтветов: {response_count}\nВопросов: {len(questions)}\nПоследняя рассылка: ещё не отправлялся"
    )
    if survey.description:
        text += f"\n\nОписание:\n{survey.description}"
    text += f"\n\nВопросы:\n{question_lines or 'вопросов пока нет'}"
    await message.answer(text, reply_markup=_survey_keyboard(survey.id))


async def _load_surveys_with_responses(session: AsyncSession) -> tuple[list[AdminSurvey], list[AdminSurveyResponse], list[User]]:
    surveys = list(
        (
            await session.scalars(
                select(AdminSurvey).order_by(AdminSurvey.created_at.desc(), AdminSurvey.id.desc())
            )
        ).all()
    )
    if not surveys:
        return [], [], []
    survey_ids = [survey.id for survey in surveys]
    responses = list(
        (
            await session.scalars(
                select(AdminSurveyResponse)
                .where(AdminSurveyResponse.survey_id.in_(survey_ids))
                .order_by(AdminSurveyResponse.created_at.desc())
            )
        ).all()
    )
    user_ids = sorted({response.user_id for response in responses})
    users = []
    if user_ids:
        users = list((await session.scalars(select(User).where(User.id.in_(user_ids)))).all())
    return surveys, responses, users


@router.callback_query(F.data == "admin:analytics")
async def analytics_overview(
    call: CallbackQuery,
    user: User | None,
    settings: Settings,
    session: AsyncSession,
) -> None:
    if not await _guard(call, user, settings):
        return
    payload = await _analytics_payload(session)
    survey_count = int(await session.scalar(select(func.count()).select_from(AdminSurvey)) or 0)
    survey_response_count = int(await session.scalar(select(func.count()).select_from(AdminSurveyResponse)) or 0)
    approved = len(payload["users"])
    pending = int(
        await session.scalar(
            select(func.count()).select_from(User).where(User.application_status == ApplicationStatus.PENDING)
        )
        or 0
    )
    text = (
        "📊 Аналитика ЭРА\n\n"
        f"Участников: {approved}\n"
        f"Новых заявок: {pending}\n"
        f"Мероприятий: {len(payload['events'])}\n"
        f"Проектов: {len(payload['projects'])}\n"
        f"Опросов: {survey_count}\n"
        f"Ответов на опросы: {survey_response_count}\n\n"
        "Здесь можно скачать Excel, посмотреть работу направлений и запустить управленческий опрос"
    )
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="📘 Базовый Excel", callback_data="admin:analytics:excel:all"),
                InlineKeyboardButton(text="🗳 Excel опросов", callback_data="admin:analytics:excel:surveys"),
            ],
            [InlineKeyboardButton(text="🗳 Управленческие опросы", callback_data="admin:surveys")],
            [
                InlineKeyboardButton(text="👥 Участники", callback_data="admin:analytics:excel:users"),
                InlineKeyboardButton(text="🏛 Департаменты", callback_data="admin:analytics:excel:departments"),
            ],
            [
                InlineKeyboardButton(text="📅 Мероприятия", callback_data="admin:analytics:excel:events"),
                InlineKeyboardButton(text="💡 Проекты", callback_data="admin:analytics:excel:projects"),
            ],
            [InlineKeyboardButton(text="← Управление", callback_data="admin:menu:system")],
        ]
    )
    await call.message.answer(text, reply_markup=keyboard)


@router.callback_query(F.data == "admin:analytics:excel:surveys")
async def survey_excel(call: CallbackQuery, user: User | None, settings: Settings, session: AsyncSession) -> None:
    if not await _guard(call, user, settings):
        return
    surveys, responses, users = await _load_surveys_with_responses(session)
    workbook = build_survey_workbook(surveys, responses, users)
    await call.message.answer_document(
        BufferedInputFile(workbook, filename="ERA_surveys.xlsx"),
        caption="🗳 Опросы и обратная связь ЭРА",
    )


@router.message(Command("admin_surveys"))
async def surveys_command(message: Message, user: User | None, settings: Settings, session: AsyncSession) -> None:
    if not await _guard(message, user, settings):
        return
    await _send_surveys_menu(message, session)


@router.callback_query(F.data == "admin:surveys")
async def surveys_menu(call: CallbackQuery, user: User | None, settings: Settings, session: AsyncSession) -> None:
    if not await _guard(call, user, settings):
        return
    await _send_surveys_menu(call.message, session)


async def _send_surveys_menu(message: Message, session: AsyncSession) -> None:
    surveys = list(
        (
            await session.scalars(
                select(AdminSurvey)
                .where(AdminSurvey.status != "archived")
                .order_by(AdminSurvey.created_at.desc(), AdminSurvey.id.desc())
                .limit(15)
            )
        ).all()
    )
    rows = [
        [InlineKeyboardButton(text="🧭 Месячный шаблон", callback_data="admin:survey:monthly")],
        [InlineKeyboardButton(text="➕ Новый опрос", callback_data="admin:survey:new")],
        [InlineKeyboardButton(text="📥 Скачать ответы", callback_data="admin:analytics:excel:surveys")],
    ]
    for survey in surveys:
        responses = await _survey_response_count(session, survey.id)
        rows.append([
            InlineKeyboardButton(
                text=f"{_status_label(survey.status)} · {responses} отв. · {survey.title[:32]}",
                callback_data=f"admin:survey:view:{survey.id}",
            )
        ])
    rows.append([InlineKeyboardButton(text="← Аналитика", callback_data="admin:analytics")])
    await message.answer(
        "🗳 Управленческие опросы\n\n"
        "Можно создать разовый опрос, редактировать вопросы, отправить его всем одобренным участникам и скачать ответы в Excel\n\n"
        "Для ежемесячной обратной связи используйте готовый шаблон «Ежемесячный пульс ЭРА»",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
    )


@router.callback_query(F.data == "admin:survey:monthly")
async def monthly_survey(call: CallbackQuery, user: User | None, settings: Settings, session: AsyncSession) -> None:
    if not await _guard(call, user, settings):
        return
    survey = await session.scalar(
        select(AdminSurvey)
        .where(AdminSurvey.is_monthly.is_(True), AdminSurvey.status != "archived")
        .order_by(AdminSurvey.created_at.desc(), AdminSurvey.id.desc())
    )
    if not survey:
        survey = AdminSurvey(
            title=MONTHLY_SURVEY_TITLE,
            description=MONTHLY_SURVEY_DESCRIPTION,
            questions_json=questions_payload(MONTHLY_SURVEY_QUESTIONS),
            audience_type="approved",
            audience_filter_json={},
            status="draft",
            is_monthly=True,
            created_by=user.id if user else None,
        )
        session.add(survey)
        await session.commit()
        await session.refresh(survey)
    await _show_survey(call.message, session, survey)


@router.callback_query(F.data == "admin:survey:new")
async def new_survey(call: CallbackQuery, user: User | None, settings: Settings, state: FSMContext) -> None:
    if not await _guard(call, user, settings):
        return
    await state.set_state(AdminSurveyStates.create_text)
    await call.message.answer(_survey_create_hint())


@router.message(AdminSurveyStates.create_text)
async def save_new_survey(message: Message, user: User | None, settings: Settings, session: AsyncSession, state: FSMContext) -> None:
    if not await _guard(message, user, settings):
        return
    try:
        title, description, questions = parse_survey_text(message.text or "")
    except ValueError:
        await message.answer("Не получилось собрать опрос. Проверьте формат: название, затем ---, затем вопросы по одному в строке")
        return
    survey = AdminSurvey(
        title=title,
        description=description,
        questions_json=questions,
        audience_type="approved",
        audience_filter_json={},
        status="draft",
        is_monthly=False,
        created_by=user.id if user else None,
    )
    session.add(survey)
    await session.commit()
    await session.refresh(survey)
    await state.clear()
    await message.answer("Опрос создан. Перед рассылкой можно ещё раз проверить текст")
    await _show_survey(message, session, survey)


@router.callback_query(F.data.startswith("admin:survey:view:"))
async def view_survey(call: CallbackQuery, user: User | None, settings: Settings, session: AsyncSession) -> None:
    if not await _guard(call, user, settings):
        return
    survey = await session.get(AdminSurvey, int(call.data.rsplit(":", 1)[-1]))
    if not survey:
        await call.message.answer("Опрос не найден")
        return
    await _show_survey(call.message, session, survey)


@router.callback_query(F.data.startswith("admin:survey:edit:"))
async def edit_survey(call: CallbackQuery, user: User | None, settings: Settings, session: AsyncSession, state: FSMContext) -> None:
    if not await _guard(call, user, settings):
        return
    survey = await session.get(AdminSurvey, int(call.data.rsplit(":", 1)[-1]))
    if not survey:
        await call.message.answer("Опрос не найден")
        return
    questions = "\n".join(survey_questions(survey))
    current = f"{survey.title}\n{survey.description or ''}\n---\n{questions}".strip()
    await state.set_state(AdminSurveyStates.edit_text)
    await state.update_data(survey_id=survey.id)
    await call.message.answer(
        "Отправьте новую версию опроса в том же формате. Сейчас он выглядит так:\n\n"
        f"{current}"
    )


@router.message(AdminSurveyStates.edit_text)
async def save_edited_survey(message: Message, user: User | None, settings: Settings, session: AsyncSession, state: FSMContext) -> None:
    if not await _guard(message, user, settings):
        return
    data = await state.get_data()
    survey = await session.get(AdminSurvey, int(data.get("survey_id", 0)))
    if not survey:
        await state.clear()
        await message.answer("Опрос не найден")
        return
    try:
        title, description, questions = parse_survey_text(message.text or "")
    except ValueError:
        await message.answer("Не получилось обновить опрос. Оставьте название, затем ---, затем вопросы по одному в строке")
        return
    survey.title = title
    survey.description = description
    survey.questions_json = questions
    survey.updated_by = user.id if user else None
    await session.commit()
    await state.clear()
    await message.answer("Опрос обновлён")
    await _show_survey(message, session, survey)


@router.callback_query(F.data.startswith("admin:survey:prepare:"))
async def prepare_send(call: CallbackQuery, user: User | None, settings: Settings, session: AsyncSession) -> None:
    if not await _guard(call, user, settings):
        return
    survey = await session.get(AdminSurvey, int(call.data.rsplit(":", 1)[-1]))
    if not survey or not survey_questions(survey):
        await call.message.answer("Опрос не найден или в нём нет вопросов")
        return
    recipients_count = int(
        await session.scalar(
            select(func.count())
            .select_from(User)
            .where(
                User.application_status == ApplicationStatus.APPROVED,
                User.is_blocked.is_(False),
                User.is_archived.is_(False),
            )
        )
        or 0
    )
    await call.message.answer(
        f"Подтвердите рассылку опроса\n\n"
        f"Опрос: {survey.title}\n"
        f"Получателей: {recipients_count}\n"
        f"Вопросов: {len(survey_questions(survey))}\n\n"
        "После отправки участники получат кнопку «Ответить на опрос»",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="✅ Отправить участникам", callback_data=f"admin:survey:send:{survey.id}")],
                [InlineKeyboardButton(text="← Не отправлять", callback_data=f"admin:survey:view:{survey.id}")],
            ]
        ),
    )


@router.callback_query(F.data.startswith("admin:survey:send:"))
async def send_survey(
    call: CallbackQuery,
    user: User | None,
    settings: Settings,
    session: AsyncSession,
    bot: Bot,
) -> None:
    if not await _guard(call, user, settings):
        return
    survey = await session.get(AdminSurvey, int(call.data.rsplit(":", 1)[-1]))
    if not survey or not survey_questions(survey):
        await call.message.answer("Опрос не найден или в нём нет вопросов")
        return
    recipients = list(
        (
            await session.scalars(
                select(User).where(
                    User.application_status == ApplicationStatus.APPROVED,
                    User.is_blocked.is_(False),
                    User.is_archived.is_(False),
                )
            )
        ).all()
    )
    if not recipients:
        await call.message.answer("Нет одобренных участников для рассылки")
        return
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="Ответить на опрос", callback_data=f"survey:start:{survey.id}")]]
    )
    sent = failed = 0
    for participant in recipients:
        ok = await safe_send(
            bot,
            participant.telegram_id,
            f"🗳 {survey.title}\n\n{survey.description or 'Команда ЭРА собирает обратную связь, чтобы принимать решения точнее'}\n\nОтвет займёт несколько минут",
            keyboard,
        )
        if ok:
            sent += 1
        else:
            failed += 1
    now = datetime.now(ZoneInfo(settings.timezone))
    survey.status = "sent"
    survey.sent_at = now
    if survey.is_monthly:
        survey.last_sent_month = now.strftime("%Y-%m")
    survey.updated_by = user.id if user else None
    await session.commit()
    await call.message.answer(f"Опрос отправлен\n\nДоставлено: {sent}\nНе доставлено: {failed}")


@router.callback_query(F.data.startswith("admin:survey:results:"))
async def survey_results(call: CallbackQuery, user: User | None, settings: Settings, session: AsyncSession) -> None:
    if not await _guard(call, user, settings):
        return
    survey_id = int(call.data.rsplit(":", 1)[-1])
    survey = await session.get(AdminSurvey, survey_id)
    if not survey:
        await call.message.answer("Опрос не найден")
        return
    responses = list(
        (
            await session.scalars(
                select(AdminSurveyResponse)
                .where(AdminSurveyResponse.survey_id == survey_id)
                .order_by(AdminSurveyResponse.created_at.desc())
                .limit(30)
            )
        ).all()
    )
    if not responses:
        await call.message.answer("Ответов по этому опросу пока нет", reply_markup=_survey_keyboard(survey.id))
        return
    user_ids = sorted({response.user_id for response in responses})
    users = {item.id: item for item in (await session.scalars(select(User).where(User.id.in_(user_ids)))).all()}
    question_counts: dict[str, int] = {}
    recent: list[str] = []
    for response in responses:
        respondent = users.get(response.user_id)
        name = f"{respondent.first_name} {respondent.last_name or ''}".strip() if respondent else f"ID {response.user_id}"
        for item in answer_items(response):
            question_counts[item["question"]] = question_counts.get(item["question"], 0) + 1
        first_answer = next(iter(answer_items(response)), None)
        if first_answer and len(recent) < 6:
            recent.append(f"• {name}: {first_answer['answer'][:180]}")
    stats = "\n".join(f"{idx}. {count} ответов" for idx, count in enumerate(question_counts.values(), 1))
    await call.message.answer(
        f"📊 Результаты опроса\n\n"
        f"{survey.title}\n"
        f"Ответов: {len(responses)}\n\n"
        f"По вопросам:\n{stats or 'пока нет'}\n\n"
        f"Последние ответы:\n" + "\n".join(recent),
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="📥 Скачать Excel", callback_data="admin:analytics:excel:surveys")],
                [InlineKeyboardButton(text="← К опросу", callback_data=f"admin:survey:view:{survey.id}")],
            ]
        ),
    )


@router.callback_query(F.data.startswith("admin:survey:archive:"))
async def archive_survey(call: CallbackQuery, user: User | None, settings: Settings, session: AsyncSession) -> None:
    if not await _guard(call, user, settings):
        return
    survey = await session.get(AdminSurvey, int(call.data.rsplit(":", 1)[-1]))
    if not survey:
        await call.message.answer("Опрос не найден")
        return
    survey.status = "archived"
    survey.updated_by = user.id if user else None
    await session.commit()
    await call.message.answer("Опрос перенесён в архив", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="← Все опросы", callback_data="admin:surveys")]]))
