from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import Department, Direction, Project
from app.services.audit_service import audit


async def create_project(
    session: AsyncSession,
    *,
    author_id: int,
    data: dict,
    document: str,
) -> Project:
    department = await session.scalar(
        select(Department).where(Department.name == data.get("department"))
    )
    direction = await session.scalar(
        select(Direction).where(Direction.name == data.get("direction"))
    )
    idea = data.get("idea", "Новый проект")
    title = idea.split(".", 1)[0][:200]
    project = Project(
        author_id=author_id,
        department_id=department.id if department else None,
        direction_id=direction.id if direction else None,
        title=title,
        short_description=idea,
        relevance=data.get("relevance"),
        goal=data.get("goal"),
        target_audience=data.get("target_audience"),
        format=data.get("format"),
        program=data.get("program"),
        resources=data.get("resources"),
        team=data.get("team"),
        expected_result=data.get("expected_result"),
        needs_from_era=data.get("needs_from_era"),
        generated_document=document,
        status="draft",
    )
    session.add(project)
    await session.flush()
    await audit(
        session,
        actor_id=author_id,
        action="project.created",
        entity_type="project",
        entity_id=project.id,
    )
    return project
