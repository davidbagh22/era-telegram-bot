from __future__ import annotations

import asyncio
from datetime import date, time

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import app.database  # noqa: F401
from app.database.base import Base
from app.database.models import AttendanceProof, Event, EventRegistration, User
from app.services import attendance_proof_service
from app.services.admin_dashboard_service import dashboard_metrics
from app.utils.constants import ApplicationStatus, EventStatus, RegistrationStatus, Role


async def _run() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        factory = async_sessionmaker(engine, expire_on_commit=False)
        async with factory() as session:
            admin = User(
                telegram_id=88001,
                first_name="Админ",
                role=Role.ADMIN,
                application_status=ApplicationStatus.APPROVED,
            )
            participant = User(
                telegram_id=88002,
                first_name="Участник",
                last_name="Тест",
                role=Role.PARTICIPANT,
                application_status=ApplicationStatus.APPROVED,
            )
            session.add_all([admin, participant])
            await session.flush()
            event = Event(
                title="Вечер ЭРА",
                description="d",
                event_date=date.today(),
                event_time=time(18, 0),
                location="Дом Москвы",
                format="offline",
                created_by=admin.id,
                status=EventStatus.PUBLISHED,
                points_for_visit=10,
            )
            session.add(event)
            await session.flush()
            session.add(
                EventRegistration(
                    event_id=event.id,
                    user_id=participant.id,
                    status=RegistrationStatus.REGISTERED,
                )
            )
            proof = AttendanceProof(
                event_id=event.id,
                user_id=participant.id,
                photo_file_id="tg-file-1",
                status="pending",
            )
            session.add(proof)
            await session.commit()
            await session.refresh(proof)
            await session.refresh(admin)

            metrics = await dashboard_metrics(session)
            assert metrics.values["attendance_proofs"] == 1
            assert "attendance_proofs" in (
                # ensure attention_total includes the queue
                k for k in metrics.values if metrics.values[k]
            )
            assert metrics.attention_total >= 1

            result = await attendance_proof_service.approve_proof(
                session, proof, reviewer=admin, bot=None
            )
            assert result.proof.status == "approved"
            assert result.points == 15

            metrics_after = await dashboard_metrics(session)
            assert metrics_after.values["attendance_proofs"] == 0
    finally:
        await engine.dispose()


def test_attendance_proof_approve_and_dashboard_queue() -> None:
    asyncio.run(_run())
