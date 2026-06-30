from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import (
    TelegramIdentity,
    get_current_user,
    get_optional_user,
    get_session,
    get_telegram_identity,
)
from app.api.schemas import (
    ProjectCreateRequest,
    QuestionCreateRequest,
    RegistrationRequest,
    TaskStatusRequest,
)
from app.database.models import (
    Event,
    EventRegistration,
    PointTransaction,
    PortfolioItem,
    Project,
    Task,
    User,
    UserQuestion,
)
from app.repositories.users import (
    create_user_from_registration,
    rating,
    user_stats,
)
from app.services.ai_service import AIUnavailableError, fallback_project_document
from app.services.audit_service import audit
from app.services.event_service import (
    available_places,
    published_events,
    register_for_event,
)
from app.services.notification_service import notify_admins
from app.services.points_service import add_points
from app.services.project_service import create_project
from app.services.subscription_service import is_channel_member
from app.utils.constants import (
    ApplicationStatus,
    DEPARTMENTS,
    PRIVILEGED_ROLES,
    ROLE_LABELS,
    STATUS_LABELS,
    ProjectStatus,
    Role,
)

router = APIRouter(prefix="/api")


def _user_payload(user: User, stats: dict[str, int] | None = None) -> dict:
    stats = stats or {}
    return {
        "id": user.id,
        "telegram_id": user.telegram_id,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "username": user.username,
        "age": user.age,
        "city": user.city,
        "education_work": user.education_work,
        "occupation": user.occupation,
        "skills": user.skills,
        "role": user.role,
        "role_label": ROLE_LABELS.get(user.role, user.role),
        "participation_status": user.participation_status,
        "status_label": STATUS_LABELS.get(
            user.participation_status, user.participation_status
        ),
        "application_status": user.application_status,
        "departments": [item.department.name for item in user.departments],
        "directions": [item.direction.name for item in user.directions],
        "is_privileged": user.role in PRIVILEGED_ROLES,
        "is_admin": user.role == Role.ADMIN,
        "stats": stats,
    }


@router.get("/session")
async def session_info(
    identity: TelegramIdentity = Depends(get_telegram_identity),
    user: User | None = Depends(get_optional_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    if user is None:
        return {
            "state": "needs_registration",
            "telegram_user": {
                "id": identity.telegram_id,
                "first_name": identity.first_name,
                "last_name": identity.last_name,
                "username": identity.username,
            },
            "user": None,
        }
    state = (
        "ready"
        if user.application_status == ApplicationStatus.APPROVED
        else user.application_status
    )
    return {
        "state": state,
        "telegram_user": {
            "id": identity.telegram_id,
            "first_name": identity.first_name,
            "last_name": identity.last_name,
            "username": identity.username,
        },
        "user": _user_payload(user, await user_stats(session, user.id)),
    }


@router.post("/registration", status_code=status.HTTP_201_CREATED)
async def register(
    payload: RegistrationRequest,
    request: Request,
    identity: TelegramIdentity = Depends(get_telegram_identity),
    existing_user: User | None = Depends(get_optional_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    if existing_user is not None:
        raise HTTPException(status_code=409, detail="Анкета уже создана.")
    settings = request.app.state.settings
    if not settings.dev_auth_enabled and not await is_channel_member(
        request.app.state.bot, identity.telegram_id, settings
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Сначала подпишитесь на официальный канал ЭРА.",
        )

    user = await create_user_from_registration(
        session,
        telegram_id=identity.telegram_id,
        username=identity.username,
        data=payload.model_dump(exclude={"personal_data_consent"}),
    )
    user.personal_data_consent = True
    if identity.telegram_id in settings.admin_ids:
        user.role = Role.ADMIN
        user.application_status = ApplicationStatus.APPROVED
        await add_points(
            session,
            user_id=user.id,
            points=5,
            reason="Регистрация в приложении",
            approved_by=user.id,
        )
    await audit(
        session,
        actor_id=user.id,
        action="mini_app.user_registered",
        entity_type="user",
        entity_id=user.id,
    )
    await session.flush()
    await session.refresh(user, attribute_names=["departments", "directions"])
    if user.application_status != ApplicationStatus.APPROVED:
        await notify_admins(
            request.app.state.bot,
            settings,
            f"Новая заявка из Mini App: {user.first_name} {user.last_name or ''}. "
            "Откройте панель администратора в боте.",
        )
    return {
        "state": (
            "ready"
            if user.application_status == ApplicationStatus.APPROVED
            else "pending"
        ),
        "user": _user_payload(user, await user_stats(session, user.id)),
    }


@router.get("/dashboard")
async def dashboard(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    stats = await user_stats(session, user.id)
    rating_rows = await rating(session, limit=1000)
    place = next(
        (index for index, (item, _) in enumerate(rating_rows, 1) if item.id == user.id),
        None,
    )
    events = (await published_events(session))[:3]
    tasks = (
        await session.scalars(
            select(Task)
            .where(
                Task.assignee_id == user.id,
                Task.status.not_in(["completed", "cancelled"]),
            )
            .order_by(Task.deadline)
            .limit(3)
        )
    ).all()
    return {
        "user": _user_payload(user, stats),
        "rating_place": place,
        "upcoming_events": [
            {
                "id": event.id,
                "title": event.title,
                "date": event.event_date.isoformat(),
                "time": event.event_time.strftime("%H:%M"),
                "location": event.location,
                "points": event.points_for_visit,
            }
            for event in events
        ],
        "active_tasks": [
            {
                "id": task.id,
                "title": task.title,
                "deadline": task.deadline.isoformat(),
                "status": task.status,
                "points": task.points,
            }
            for task in tasks
        ],
    }


@router.get("/events")
async def events(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[dict]:
    event_items = await published_events(session)
    registrations = {
        item.event_id: item.status
        for item in (
            await session.scalars(
                select(EventRegistration).where(EventRegistration.user_id == user.id)
            )
        ).all()
    }
    result = []
    for event in event_items:
        result.append(
            {
                "id": event.id,
                "title": event.title,
                "description": event.description,
                "date": event.event_date.isoformat(),
                "time": event.event_time.strftime("%H:%M"),
                "location": event.location,
                "format": event.format,
                "points": event.points_for_visit,
                "available_places": await available_places(session, event),
                "registration_status": registrations.get(event.id),
            }
        )
    return result


@router.post("/events/{event_id}/register")
async def register_event(
    event_id: int,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    event = await session.get(Event, event_id)
    if event is None or event.event_date < date.today():
        raise HTTPException(status_code=404, detail="Мероприятие не найдено.")
    registration, error = await register_for_event(session, event, user.id)
    if error == "already":
        raise HTTPException(status_code=409, detail="Вы уже зарегистрированы.")
    if error == "full":
        raise HTTPException(status_code=409, detail="Свободных мест больше нет.")
    return {"status": registration.status, "message": "Регистрация подтверждена."}


@router.get("/rating")
async def get_rating(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    rows = await rating(session, limit=100)
    place = next(
        (index for index, (item, _) in enumerate(rows, 1) if item.id == user.id),
        None,
    )
    return {
        "place": place,
        "items": [
            {
                "place": index,
                "name": f"{item.first_name} {item.last_name or ''}".strip(),
                "points": points,
                "is_current_user": item.id == user.id,
            }
            for index, (item, points) in enumerate(rows[:20], 1)
        ],
    }


@router.get("/portfolio")
async def portfolio(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[dict]:
    items = (
        await session.scalars(
            select(PortfolioItem)
            .where(PortfolioItem.user_id == user.id)
            .order_by(desc(PortfolioItem.created_at))
        )
    ).all()
    return [
        {
            "id": item.id,
            "title": item.title,
            "type": item.item_type,
            "description": item.description,
            "url": item.url,
            "issued_at": item.issued_at.isoformat() if item.issued_at else None,
        }
        for item in items
    ]


@router.get("/departments")
async def departments(user: User = Depends(get_current_user)) -> dict:
    return {
        "items": [
            {
                "name": name,
                "directions": list(directions),
                "selected": name in {item.department.name for item in user.departments},
            }
            for name, directions in DEPARTMENTS.items()
        ],
        "selected_directions": [item.direction.name for item in user.directions],
    }


@router.get("/projects")
async def projects(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[dict]:
    items = (
        await session.scalars(
            select(Project)
            .where(Project.author_id == user.id)
            .order_by(desc(Project.created_at))
        )
    ).all()
    return [
        {
            "id": item.id,
            "title": item.title,
            "description": item.short_description,
            "status": item.status,
            "document": item.generated_document,
            "created_at": item.created_at.isoformat(),
        }
        for item in items
    ]


@router.post("/projects", status_code=status.HTTP_201_CREATED)
async def new_project(
    payload: ProjectCreateRequest,
    request: Request,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    data = payload.model_dump(exclude={"use_ai"})
    if payload.use_ai:
        try:
            document = await request.app.state.ai_service.generate_project(data)
        except AIUnavailableError:
            document = fallback_project_document(data)
    else:
        document = fallback_project_document(data)
    project = await create_project(
        session, author_id=user.id, data=data, document=document
    )
    return {
        "id": project.id,
        "title": project.title,
        "status": project.status,
        "document": project.generated_document,
    }


@router.post("/projects/{project_id}/submit")
async def submit_project(
    project_id: int,
    request: Request,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    project = await session.get(Project, project_id)
    if project is None or project.author_id != user.id:
        raise HTTPException(status_code=404, detail="Проект не найден.")
    if project.status not in {ProjectStatus.DRAFT, ProjectStatus.NEEDS_REVISION}:
        raise HTTPException(status_code=409, detail="Проект уже отправлен.")
    project.status = ProjectStatus.PENDING_REVIEW
    await audit(
        session,
        actor_id=user.id,
        action="mini_app.project_submitted",
        entity_type="project",
        entity_id=project.id,
    )
    await notify_admins(
        request.app.state.bot,
        request.app.state.settings,
        f"Новый проект из Mini App: {project.title} (#{project.id}).",
    )
    return {"status": project.status, "message": "Проект отправлен."}


@router.get("/tasks")
async def tasks(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[dict]:
    items = (
        await session.scalars(
            select(Task).where(Task.assignee_id == user.id).order_by(Task.deadline)
        )
    ).all()
    return [
        {
            "id": item.id,
            "title": item.title,
            "description": item.description,
            "deadline": item.deadline.isoformat(),
            "status": item.status,
            "points": item.points,
        }
        for item in items
    ]


@router.patch("/tasks/{task_id}")
async def update_task(
    task_id: int,
    payload: TaskStatusRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    task = await session.get(Task, task_id)
    if task is None or task.assignee_id != user.id:
        raise HTTPException(status_code=404, detail="Задача не найдена.")
    allowed_transition = (task.status, payload.status) in {
        ("new", "in_progress"),
        ("in_progress", "review"),
    }
    if not allowed_transition:
        raise HTTPException(status_code=409, detail="Этот переход статуса недоступен.")
    task.status = payload.status
    await audit(
        session,
        actor_id=user.id,
        action="mini_app.task_status_changed",
        entity_type="task",
        entity_id=task.id,
        new_value={"status": task.status},
    )
    return {"status": task.status}


@router.post("/questions", status_code=status.HTTP_201_CREATED)
async def create_question(
    payload: QuestionCreateRequest,
    request: Request,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    question = UserQuestion(user_id=user.id, text=payload.text)
    session.add(question)
    await session.flush()
    await audit(
        session,
        actor_id=user.id,
        action="mini_app.question_created",
        entity_type="user_question",
        entity_id=question.id,
    )
    await notify_admins(
        request.app.state.bot,
        request.app.state.settings,
        f"Новый вопрос из Mini App #{question.id}: {question.text}",
    )
    return {"id": question.id, "message": "Вопрос отправлен."}


@router.get("/admin/summary")
async def admin_summary(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    if user.role != Role.ADMIN:
        raise HTTPException(status_code=403, detail="Недостаточно прав.")

    async def count(model, *conditions) -> int:
        return int(
            await session.scalar(
                select(func.count()).select_from(model).where(*conditions)
            )
            or 0
        )

    return {
        "participants": await count(
            User, User.application_status == ApplicationStatus.APPROVED
        ),
        "pending_applications": await count(
            User, User.application_status == ApplicationStatus.PENDING
        ),
        "pending_projects": await count(
            Project, Project.status == ProjectStatus.PENDING_REVIEW
        ),
        "upcoming_events": await count(Event, Event.event_date >= date.today()),
        "unanswered_questions": await count(UserQuestion, UserQuestion.status == "new"),
        "total_points": int(
            await session.scalar(
                select(func.coalesce(func.sum(PointTransaction.points), 0))
            )
            or 0
        ),
    }
