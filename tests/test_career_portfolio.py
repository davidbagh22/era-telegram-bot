import asyncio

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import app.database  # noqa: F401 - registers all metadata tables
from app.database.base import Base
from app.database.models import User
from app.services import career_service
from app.services.career_pdf_service import build_career_resume, build_official_recommendation
from app.services.portfolio_service import PortfolioData
from app.utils.constants import ApplicationStatus, Role


async def _run_flow() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        factory = async_sessionmaker(engine, expire_on_commit=False)
        async with factory() as session:
            participant = User(
                telegram_id=991001,
                first_name="Тест",
                last_name="Участник",
                role=Role.PARTICIPANT,
                application_status=ApplicationStatus.APPROVED,
                skills=["Командная работа", "Организация проектов"],
            )
            admin = User(
                telegram_id=991002,
                first_name="Администратор",
                role=Role.ADMIN,
                application_status=ApplicationStatus.APPROVED,
            )
            session.add_all([participant, admin])
            await session.commit()
            await session.refresh(participant)
            await session.refresh(admin)

            item = await career_service.create_item(
                session,
                participant.id,
                item_type="certificate",
                title="Сертификат проектной школы",
                organization="Тестовая организация",
                description="Завершил образовательную программу",
            )
            assert item.status == "self_reported"
            try:
                await career_service.request_verification(session, item)
                raise AssertionError("verification without evidence must fail")
            except ValueError as exc:
                assert str(exc) == "evidence_required"

            item = await career_service.attach_file(
                session,
                item,
                file_id="telegram-file-id",
                file_name="certificate.pdf",
            )
            item = await career_service.request_verification(session, item)
            assert item.status == "pending"
            item = await career_service.review_item(
                session,
                item,
                reviewer_id=admin.id,
                decision="approve",
                comment="Документ проверен",
            )
            assert item.status == "verified"
            try:
                await career_service.update_item(session, item, title="Подменённое название")
                raise AssertionError("verified item must be locked")
            except ValueError as exc:
                assert str(exc) == "verified_item_locked"

            profile = await career_service.update_profile(
                session,
                participant.id,
                headline="Начинающий проектный менеджер",
                about="Развиваюсь через реальные проекты и общественные инициативы.",
                languages=[{"name": "Русский", "level": "C2"}],
            )
            automatic = await career_service.automatic_recommendation(session, participant)
            assert "Моего вектора" in automatic["privacy_note"]
            assert "психологические" in automatic["privacy_note"]
            assert automatic["facts"]["verified_external_items"] == 1

            request = await career_service.request_official_recommendation(
                session, participant, "university"
            )
            request = await career_service.approve_recommendation(
                session,
                request,
                reviewer_id=admin.id,
                final_text=None,
            )
            assert request.document_number.startswith("ERA-REC-")
            assert request.verification_token
            verified = await career_service.recommendation_by_token(
                session, request.verification_token
            )
            assert verified is not None and verified.id == request.id

            portfolio = PortfolioData(
                full_name="Тест Участник",
                role="Участник",
                participation_status="Активный",
                departments=[],
                directions=[],
                period="с 01.01.2026",
                skills=["Командная работа"],
                stats={},
            )
            cv = build_career_resume(
                participant,
                profile,
                portfolio,
                [item],
                purpose="university",
            )
            assert cv.startswith(b"%PDF")
            assert len(cv) > 5000

            letter = build_official_recommendation(
                participant,
                request,
                verification_url=f"https://example.org/api/v1/career/verify/{request.verification_token}",
            )
            assert letter.startswith(b"%PDF")
            assert len(letter) > 5000
    finally:
        await engine.dispose()


def test_career_portfolio_verification_recommendation_and_pdfs() -> None:
    asyncio.run(_run_flow())
