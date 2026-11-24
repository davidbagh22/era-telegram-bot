"""Regression tests for visually strong career resume layout edge cases."""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace

from app.services.career_pdf_service import build_career_resume
from app.services.portfolio_service import PortfolioData, PortfolioEntry


def _user(**overrides):
    base = dict(
        first_name="Давид",
        last_name="Багдасарян",
        city="Ереван",
        email=None,
        occupation="Участник",
        experience="",
        skills=["Коммуникация"],
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def _profile(**overrides):
    base = dict(headline="Участник ЭРА", about="", languages=[{"name": "Русский", "level": "Свободный"}])
    base.update(overrides)
    return SimpleNamespace(**base)


class _Item:
    def __init__(self, *, title: str, description: str, item_type: str = "certificate"):
        self.title = title
        self.organization = "ЭРА"
        self.issued_at = date(2025, 5, 1)
        self.status = "verified"
        self.description = description
        self.include_in_resume = True
        self.item_type = item_type


def test_career_resume_fits_long_hero_name() -> None:
    pdf = build_career_resume(
        _user(first_name="Александр Александрович", last_name="Константинов"),
        _profile(),
        PortfolioData(
            full_name="Александр Александрович Константинов",
            role="Участник",
            participation_status="Активный",
            departments=[],
            directions=[],
            period="",
            city="Ереван",
            skills=["Коммуникация"],
            stats={},
        ),
        [],
        purpose="universal",
    )
    assert pdf.startswith(b"%PDF")


def test_career_resume_handles_many_events_without_sidebar_overflow() -> None:
    events = [
        PortfolioEntry(
            title=f"Мероприятие ЭРА №{idx}",
            description="Краткое описание участия",
            status="Посетил",
            date_label=f"{idx:02d}.10.2026",
            category="event",
        )
        for idx in range(1, 13)
    ]
    pdf = build_career_resume(
        _user(),
        _profile(about="Развиваю сообщество через мероприятия, проекты и партнёрства в Ереване."),
        PortfolioData(
            full_name="Давид Багдасарян",
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
        [],
        purpose="universal",
    )
    assert pdf.startswith(b"%PDF")
    assert len(pdf) > 5000


def test_career_resume_exports_very_long_description() -> None:
    long_text = ("Описание подтверждённого сертификата. " * 80).strip()
    assert len(long_text) > 2000
    pdf = build_career_resume(
        _user(),
        _profile(about="Развиваю сообщество через мероприятия, проекты и партнёрства в Ереване."),
        PortfolioData(
            full_name="Давид Багдасарян",
            role="Участник",
            participation_status="Активный",
            departments=[],
            directions=[],
            period="",
            city="Ереван",
            skills=["Коммуникация"],
            stats={},
        ),
        [_Item(title="Сертификат с длинным описанием", description=long_text)],
        purpose="universal",
    )
    assert pdf.startswith(b"%PDF")
    assert len(pdf) > 5000
