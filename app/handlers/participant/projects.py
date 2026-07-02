from io import BytesIO

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import BufferedInputFile, CallbackQuery, Message
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import Project, User
from app.keyboards.participant import (
    project_menu_keyboard,
    project_question_keyboard,
    project_result_keyboard,
)
from app.services.audit_service import audit
from app.services.project_builder import (
    PROJECT_QUESTIONS,
    question_text,
    render_project_document,
)
from app.states.project import ProjectStates
from app.utils import texts
from app.utils.constants import ApplicationStatus, ProjectStatus
from app.utils.telegram import send_long_text
from app.utils.validators import clean_text, parse_date, parse_time

router = Router(name="projects")


def _approved(user: User | None) -> bool:
    return bool(
        user
        and user.application_status == ApplicationStatus.APPROVED
        and not user.is_blocked
        and not user.is_archived
    )


async def _send_projects_menu(message: Message, user: User | None) -> None:
    if not _approved(user):
        await message.answer(texts.APPLICATION_PENDING)
        return
    await message.answer(texts.PROJECT_MENU, reply_markup=project_menu_keyboard())


def _question_markup(index: int):
    question = PROJECT_QUESTIONS[index]
    return project_question_keyboard(index, question.ai_hint is not None)


async def _ask_question(
    message: Message, index: int, current: str | None = None
) -> None:
    body = question_text(index)
    if current:
        body += f"\n\nСейчас сохранено:\n{current}"
    await message.answer(body, reply_markup=_question_markup(index))


async def _load_owned_project(
    session: AsyncSession, project_id: int, user: User
) -> Project | None:
    project = await session.get(Project, project_id)
    return project if project is not None and project.author_id == user.id else None


@router.message(F.text == "💡 Проекты")
@router.message(Command("projects"), F.chat.type == "private")
@router.message(Command("project"), F.chat.type == "private")
async def projects_menu_button(
    message: Message, user: User | None, state: FSMContext
) -> None:
    await state.clear()
    await _send_projects_menu(message, user)


@router.callback_query(F.data == "projects:menu")
async def projects_menu(call: CallbackQuery, user: User | None) -> None:
    await call.answer()
    await _send_projects_menu(call.message, user)


@router.callback_query(F.data == "project:new:guided")
async def project_start(
    call: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
    user: User | None,
) -> None:
    await call.answer()
    if not _approved(user):
        await call.message.answer(texts.APPLICATION_PENDING)
        return
    await state.clear()
    project = Project(
        author_id=user.id,
        title="Новый проект",
        short_description="Идея формируется",
        form_data={},
        current_step=0,
        status=ProjectStatus.DRAFT,
    )
    session.add(project)
    await session.flush()
    await audit(
        session,
        actor_id=user.id,
        action="project.draft_created",
        entity_type="project",
        entity_id=project.id,
    )
    await state.update_data(project_id=project.id, question_index=0)
    await state.set_state(ProjectStates.answer)
    await call.message.answer(texts.PROJECT_INTRO)
    await _ask_question(call.message, 0)


@router.message(ProjectStates.answer)
async def project_answer(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    user: User,
) -> None:
    state_data = await state.get_data()
    project_id = int(state_data["project_id"])
    index = int(state_data["question_index"])
    if index >= len(PROJECT_QUESTIONS):
        await state.clear()
        await message.answer("Черновик уже заполнен — откройте его в разделе «Проекты»")
        return
    project = await _load_owned_project(session, project_id, user)
    if project is None:
        await state.clear()
        await message.answer(texts.NO_ACCESS)
        return
    value = clean_text(message.text or "", 6000)
    if not value:
        await message.answer("Ответ не распознан — отправьте его обычным текстом")
        return
    question = PROJECT_QUESTIONS[index]
    if question.input_type == "date":
        parsed = parse_date(value)
        if parsed is None:
            await message.answer(
                "Укажите дату в формате ДД.ММ.ГГГГ — например, 15.09.2026"
            )
            return
        project.proposed_date = parsed
        value = parsed.strftime("%d.%m.%Y")
    elif question.input_type == "time":
        parsed = parse_time(value)
        if parsed is None:
            await message.answer("Укажите время в формате ЧЧ:ММ — например, 18:30")
            return
        project.proposed_time = parsed
        value = parsed.strftime("%H:%M")

    form_data = dict(project.form_data or {})
    form_data[question.key] = value
    project.form_data = form_data
    project.current_step = index + 1
    if question.key == "title":
        project.title = value[:255]
    elif question.key == "idea":
        project.short_description = value
    elif question.key == "target_audience":
        project.target_audience = value
    elif question.key == "format":
        project.format = value[:100]
    elif question.key == "team":
        project.team = value
    elif question.key == "risks":
        project.risks = value
    elif question.key == "success_metrics":
        project.expected_result = value
    await session.flush()

    next_index = index + 1
    if next_index < len(PROJECT_QUESTIONS):
        await state.update_data(question_index=next_index)
        await _ask_question(message, next_index)
        return

    author_name = f"{user.first_name} {user.last_name or ''}".strip()
    telegram = f"@{user.username}" if user.username else str(user.telegram_id)
    document = render_project_document(form_data, author_name, telegram)
    project.generated_document = document
    project.current_step = len(PROJECT_QUESTIONS)
    await state.clear()
    await message.answer(
        "Проект собран 🎉\n\nПроверьте документ перед отправкой команде ЭРА"
    )
    await send_long_text(
        message, document, reply_markup=project_result_keyboard(project.id)
    )
    await message.answer_document(
        BufferedInputFile(
            BytesIO(document.encode("utf-8")).getvalue(),
            filename=f"ERA_project_{project.id}.txt",
        ),
        caption="Копия проекта — файл останется в этом чате",
    )


@router.callback_query(ProjectStates.answer, F.data.startswith("project:hint:"))
async def project_hint(call: CallbackQuery, state: FSMContext) -> None:
    await call.answer()
    index = int(call.data.rsplit(":", 1)[-1])
    data = await state.get_data()
    if index != int(data.get("question_index", -1)):
        await call.message.answer("Эта подсказка относится к предыдущему шагу")
        return
    hint = PROJECT_QUESTIONS[index].ai_hint
    if hint:
        await call.message.answer(
            "Скопируйте этот запрос в удобный ИИ-чат, замените текст в скобках и верните готовый ответ сюда:\n\n"
            f"{hint}"
        )


@router.callback_query(ProjectStates.answer, F.data == "project:previous")
async def project_previous(
    call: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
    user: User,
) -> None:
    await call.answer()
    data = await state.get_data()
    index = max(0, int(data.get("question_index", 0)) - 1)
    project = await _load_owned_project(session, int(data["project_id"]), user)
    if project is None:
        await state.clear()
        await call.message.answer(texts.NO_ACCESS)
        return
    project.current_step = index
    await state.update_data(question_index=index)
    current = (project.form_data or {}).get(PROJECT_QUESTIONS[index].key)
    await _ask_question(call.message, index, current)


@router.callback_query(ProjectStates.answer, F.data == "project:pause")
async def project_pause(call: CallbackQuery, state: FSMContext) -> None:
    await call.answer()
    await state.clear()
    await call.message.answer(
        "Черновик сохранён 🌿\n\nПродолжить можно в разделе «Проекты → Черновики»"
    )


@router.callback_query(F.data.startswith("project:pause:"))
async def project_pause_finished(call: CallbackQuery) -> None:
    await call.answer()
    await call.message.answer("Проект сохранён как черновик")


@router.callback_query(F.data.startswith("project:resume:"))
async def project_resume(
    call: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
    user: User,
) -> None:
    await call.answer()
    project = await _load_owned_project(
        session, int(call.data.rsplit(":", 1)[-1]), user
    )
    if project is None:
        await call.message.answer(texts.NO_ACCESS)
        return
    if project.status not in {ProjectStatus.DRAFT, ProjectStatus.NEEDS_REVISION}:
        await call.message.answer(
            "Проект уже отправлен и сейчас недоступен для изменения"
        )
        return
    index = project.current_step
    if index >= len(PROJECT_QUESTIONS):
        index = 0
    await state.clear()
    await state.update_data(project_id=project.id, question_index=index)
    await state.set_state(ProjectStates.answer)
    current = (project.form_data or {}).get(PROJECT_QUESTIONS[index].key)
    await call.message.answer(f"Продолжаем проект «{project.title}»")
    await _ask_question(call.message, index, current)
