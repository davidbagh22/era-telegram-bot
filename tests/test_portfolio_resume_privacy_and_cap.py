"""P2 regressions: resume privacy flag + short résumé layout budget."""

from __future__ import annotations

import asyncio
from datetime import date
from io import BytesIO
from types import SimpleNamespace

from pypdf import PdfReader
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import app.database  # noqa: F401 — registers metadata + career columns
from app.database.base import Base
from app.database.models import PortfolioItem, User
from app.services.career_pdf_service import (
    RESUME_SECTION_CAP,
    RESUME_TOTAL_CAP,
    _cap_resume_content,
    _era_sections,
    build_career_resume,
)
from app.services.portfolio_service import PortfolioData, PortfolioEntry, build_portfolio_data
from app.utils.constants import ApplicationStatus, Role


def _user(**overrides):
    base = dict(
        first_name="Анна",
        last_name="Тестова",
        city="Ереван",
        email=None,
        occupation="Участник",
        experience="",
        skills=["Коммуникация"],
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def _profile(**overrides):
    base = dict(headline="Участник ЭРА", about="Коротко о себе для резюме.", languages=[])
    base.update(overrides)
    return SimpleNamespace(**base)


class _CareerItem:
    def __init__(
        self,
        *,
        title: str,
        item_type: str = "achievement",
        include_in_resume: bool = True,
        description: str = "Краткое описание",
    ):
        self.title = title
        self.organization = "ЭРА"
        self.issued_at = date(2025, 5, 1)
        self.status = "verified"
        self.description = description
        self.include_in_resume = include_in_resume
        self.item_type = item_type


def test_era_sections_skips_hidden_certificates() -> None:
    visible = PortfolioEntry(
        title="Видимый сертификат",
        category="certificate",
        include_in_resume=True,
    )
    hidden = PortfolioEntry(
        title="СКРЫТЫЙ_СЕРТИФИКАТ_XYZ",
        category="certificate",
        include_in_resume=False,
    )
    portfolio = PortfolioData(
        full_name="Анна",
        role="Участник",
        participation_status="Активный",
        departments=[],
        directions=[],
        period="",
        certificates=[visible, hidden],
    )
    era = _era_sections(portfolio)
    titles = [item.title for item in era["certificate"]]
    assert "Видимый сертификат" in titles
    assert "СКРЫТЫЙ_СЕРТИФИКАТ_XYZ" not in titles


def test_career_pdf_keeps_legacy_confirmed_items_and_recommendations() -> None:
    """Codex P2: bot PDF must not drop verified PortfolioItem / recommendation rows."""
    portfolio = PortfolioData(
        full_name="Анна Тестова",
        role="Участник",
        participation_status="Активный",
        departments=[],
        directions=[],
        period="",
        city="Ереван",
        skills=["Коммуникация"],
        confirmed_items=[
            PortfolioEntry(
                title="ЛЕГАСИ_ДОСТИЖЕНИЕ_БОТА",
                description="Победа в хакатоне",
                category="award",
                date_label="01.05.2025",
                include_in_resume=True,
            )
        ],
        recommendations=[
            PortfolioEntry(
                title="ЛЕГАСИ_РЕКОМЕНДАЦИЯ_ПАРТНЁРА",
                description="Для грантовой программы",
                category="partner_recommendation",
                date_label="02.05.2025",
                include_in_resume=True,
            )
        ],
    )
    era = _era_sections(portfolio)
    assert "ЛЕГАСИ_ДОСТИЖЕНИЕ_БОТА" in [item.title for item in era["achievement"]]
    assert "ЛЕГАСИ_РЕКОМЕНДАЦИЯ_ПАРТНЁРА" in [item.title for item in era["recommendation"]]

    # Empty career_items list: export must still render legacy verified rows from PortfolioData.
    pdf = build_career_resume(
        _user(),
        _profile(),
        portfolio,
        [],
        purpose="universal",
        mode="portfolio",
    )
    text = "\n".join(page.extract_text() or "" for page in PdfReader(BytesIO(pdf)).pages)
    assert "ЛЕГАСИ_ДОСТИЖЕНИЕ_БОТА" in text
    assert "ЛЕГАСИ_РЕКОМЕНДАЦИЯ_ПАРТНЁРА" in text


def test_resume_mode_bounds_career_and_era_items() -> None:
    events = [
        PortfolioEntry(title=f"Мероприятие {idx}", status="Посетил", date_label=f"{idx:02d}.01.2026")
        for idx in range(1, 12)
    ]
    career_items = [
        _CareerItem(title=f"Достижение {idx}", item_type="achievement") for idx in range(1, 25)
    ]
    era = _era_sections(
        PortfolioData(
            full_name="Анна",
            role="Участник",
            participation_status="Активный",
            departments=[],
            directions=[],
            period="",
            events=events,
        )
    )
    grouped: dict[str, list] = {}
    for item in career_items:
        grouped.setdefault(item.item_type, []).append(item)
    capped_era, capped_grouped = _cap_resume_content(era, grouped, purpose="universal")
    total = sum(len(v) for v in capped_era.values()) + sum(len(v) for v in capped_grouped.values())
    assert total <= RESUME_TOTAL_CAP
    assert len(capped_era.get("event", [])) <= RESUME_SECTION_CAP
    assert len(capped_grouped.get("achievement", [])) <= RESUME_SECTION_CAP

    pdf = build_career_resume(
        _user(),
        _profile(),
        PortfolioData(
            full_name="Анна Тестова",
            role="Участник",
            participation_status="Активный",
            departments=[],
            directions=[],
            period="",
            city="Ереван",
            skills=["Коммуникация"],
            stats={},
            events=events,
        ),
        career_items,
        purpose="universal",
        mode="resume",
    )
    assert pdf.startswith(b"%PDF")
    pages = len(PdfReader(BytesIO(pdf)).pages)
    assert pages <= 2, f"resume mode must stay within 1–2 pages, got {pages}"


def test_hidden_verified_certificate_omitted_from_portfolio_data_and_pdf() -> None:
    async def _run() -> None:
        engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        try:
            async with engine.begin() as connection:
                await connection.run_sync(Base.metadata.create_all)
            factory = async_sessionmaker(engine, expire_on_commit=False)
            async with factory() as session:
                user = User(
                    telegram_id=880011,
                    first_name="Анна",
                    last_name="Приват",
                    role=Role.PARTICIPANT,
                    application_status=ApplicationStatus.APPROVED,
                    skills=[],
                )
                session.add(user)
                await session.commit()
                await session.refresh(user)

                visible = PortfolioItem(
                    user_id=user.id,
                    title="Открытый сертификат",
                    item_type="certificate",
                    description="Можно в PDF",
                    status="verified",
                    include_in_resume=True,
                )
                hidden = PortfolioItem(
                    user_id=user.id,
                    title="СКРЫТЫЙ_СЕРТИФИКАТ_PRIVACY_FLAG",
                    item_type="certificate",
                    description="Нельзя в PDF",
                    status="verified",
                    include_in_resume=False,
                )
                session.add_all([visible, hidden])
                await session.commit()

                portfolio = await build_portfolio_data(session, user, preview_limit=None)
                cert_titles = [item.title for item in portfolio.certificates]
                assert "Открытый сертификат" in cert_titles
                assert "СКРЫТЫЙ_СЕРТИФИКАТ_PRIVACY_FLAG" not in cert_titles
                # Management list still retains the verified row.
                confirmed_titles = [item.title for item in portfolio.confirmed_items]
                assert "СКРЫТЫЙ_СЕРТИФИКАТ_PRIVACY_FLAG" in confirmed_titles

                pdf = build_career_resume(
                    user,
                    _profile(),
                    portfolio,
                    [visible, hidden],
                    purpose="universal",
                    mode="portfolio",
                )
                text = "\n".join(page.extract_text() or "" for page in PdfReader(BytesIO(pdf)).pages)
                assert "Открытый сертификат" in text
                assert "СКРЫТЫЙ_СЕРТИФИКАТ_PRIVACY_FLAG" not in text
        finally:
            await engine.dispose()

    asyncio.run(_run())


def test_tasks_tab_keeps_details_and_pack_meta_strip() -> None:
    """Earlier TasksTab P2s must stay fixed on this branch."""
    from pathlib import Path

    source = (Path(__file__).resolve().parents[1] / "frontend/src/screens/activity/TasksTab.tsx").read_text(
        encoding="utf-8"
    )
    assert "Подробнее" in source
    assert 'pendingId === task.id ? "Сохраняем…" : "Взять"' in source
    assert "Boundary unclear — keep a truncated original" in source
    assert "packMeta" in source
