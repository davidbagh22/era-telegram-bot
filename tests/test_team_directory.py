import asyncio
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from app.api.v1.teams import list_teams
from app.database.models import Base, Project, ProjectMember, User
from app.utils.constants import ApplicationStatus, ProjectStatus


def test_my_teams_include_accepted_memberships_and_exclude_pending_other_projects():
    async def run():
        engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        factory = async_sessionmaker(engine, expire_on_commit=False)
        async with factory() as session:
            viewer = User(telegram_id=1, first_name="Viewer", application_status=ApplicationStatus.APPROVED)
            author = User(telegram_id=2, first_name="Author", application_status=ApplicationStatus.APPROVED)
            session.add_all([viewer, author]); await session.flush()
            own = Project(author_id=viewer.id, title="Own", short_description="", status=ProjectStatus.APPROVED)
            joined = Project(author_id=author.id, title="Joined", short_description="", status=ProjectStatus.APPROVED)
            pending = Project(author_id=author.id, title="Pending", short_description="", status=ProjectStatus.APPROVED)
            cancelled = Project(author_id=viewer.id, title="Cancelled", short_description="", status=ProjectStatus.CANCELLED)
            session.add_all([own, joined, pending, cancelled]); await session.flush()
            session.add_all([ProjectMember(project_id=joined.id, user_id=viewer.id, status="accepted"),
                             ProjectMember(project_id=pending.id, user_id=viewer.id, status="pending")])
            await session.commit()
            mine = await list_teams(scope="mine", user=viewer, session=session, limit=50)
            assert {item.title for item in mine} == {"Own", "Joined"}
            opened = await list_teams(scope="open", user=viewer, session=session, limit=50)
            assert {item.title for item in opened} == {"Own", "Joined", "Pending"}
        await engine.dispose()
    asyncio.run(run())
