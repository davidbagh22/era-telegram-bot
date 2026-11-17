from __future__ import annotations

import asyncio

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import app.database  # noqa: F401
from app.api.v1.projects import _to_detail, _to_summary
from app.database.base import Base
from app.database.models import Project, User
from app.utils.constants import ApplicationStatus, ProjectStatus, Role


async def _run() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        factory = async_sessionmaker(engine, expire_on_commit=False)
        async with factory() as session:
            author = User(
                telegram_id=77001,
                first_name="Автор",
                role=Role.PARTICIPANT,
                application_status=ApplicationStatus.APPROVED,
            )
            session.add(author)
            await session.flush()
            project = Project(
                author_id=author.id,
                title="Проект с обложкой",
                short_description="Коротко",
                status=ProjectStatus.DRAFT,
                cover_bytes=b"\xff\xd8\xff" + b"jpeg-bytes",
                cover_content_type="image/jpeg",
            )
            session.add(project)
            await session.commit()
            await session.refresh(project)
            await session.refresh(author)

            session.expire(project, ["cover_bytes"])
            summary = _to_summary(project)
            assert summary.cover_url is not None
            assert summary.cover_url.startswith(f"/api/v1/projects/{project.id}/cover?v=")
            assert "cover_bytes" not in project.__dict__
            detail = _to_detail(project, viewer=author)
            assert detail.can_edit_cover is True
            assert detail.cover_url == summary.cover_url
            assert "cover_bytes" not in project.__dict__
    finally:
        await engine.dispose()


def test_project_cover_summary_and_author_can_edit() -> None:
    asyncio.run(_run())
