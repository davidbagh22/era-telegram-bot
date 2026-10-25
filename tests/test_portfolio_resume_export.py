from __future__ import annotations

from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

from aiogram.exceptions import TelegramForbiddenError
from aiogram.methods import SendDocument

from app.database.models import User
from app.keyboards.participant import (
    about_keyboard,
    journey_keyboard,
    main_inline_keyboard,
    portfolio_keyboard,
    profile_sections_keyboard,
)
from app.services.portfolio_service import PortfolioData, PortfolioEntry, portfolio_summary_text
from app.services.resume_service import build_era_resume


ROOT = Path(__file__).resolve().parents[1]


def _labels(keyboard) -> list[str]:
    return [button.text for row in keyboard.inline_keyboard for button in row]


def _callbacks(keyboard) -> set[str]:
    return {
        button.callback_data
        for row in keyboard.inline_keyboard
        for button in row
        if button.callback_data
    }


def _portfolio_data(**overrides) -> PortfolioData:
    base = dict(
        full_name="Анна Иванова",
        role="Лидер",
        participation_status="Активный участник",
        departments=["Культура"],
        directions=["Медиа"],
        period="с 01.09.2025",
        city="Ереван",
        email="anna@example.com",
        education_work="Студентка",
        occupation="Проекты и коммуникации",
        experience="Вела события и помогала новым участникам",
        motivation="Развивать сообщество",
        skills=["организация", "публичные выступления", "SMM & тексты"],
        stats={"points": 120, "events": 3, "projects": 2, "tasks": 4},
        projects=[
            PortfolioEntry(
                title="Очень длинный проект ЭРА про культуру, команду и развитие молодёжи в Армении",
                description="Автор концепции и координатор",
                status="Одобрен",
                date_label="10.10.2025",
            )
        ],
        events=[PortfolioEntry(title="Мастер-класс «Голос ЭРА»", status="Посетил", date_label="11.11.2025")],
        tasks=[PortfolioEntry(title="Подготовить афишу", description="Сдано без правок", status="approved")],
        volunteer=[PortfolioEntry(title="Волонтёрство", description="Помощь на регистрации", status="approved")],
        leadership=[PortfolioEntry(title="Куратор направления", description="Команда медиа")],
        badges=[PortfolioEntry(title="Голос ЭРА", description="За вклад в коммуникации")],
        certificates=[PortfolioEntry(title="Сертификат участника", description="Русский Дом & ЭРА")],
        recommendations=[PortfolioEntry(title="Рекомендация", description="Для партнёрской программы")],
        uploaded_items=[PortfolioEntry(title="Загруженный файл", status="на проверке")],
        confirmed_items=[PortfolioEntry(title="Подтверждённое достижение", description="Победа в проекте")],
        pending_items=[PortfolioEntry(title="Ожидает проверки", status="на проверке")],
    )
    base.update(overrides)
    return PortfolioData(**base)


def test_resume_pdf_builds_full_portfolio_with_cyrillic_and_special_chars() -> None:
    content = build_era_resume(_portfolio_data(full_name="Анна & Давид <ЭРА>"))

    assert content.startswith(b"%PDF")
    assert len(content) > 2500


def test_resume_pdf_builds_empty_portfolio_without_none_values() -> None:
    content = build_era_resume(
        _portfolio_data(
            departments=[],
            directions=[],
            city="",
            email="",
            education_work="",
            occupation="",
            experience="",
            skills=[],
            projects=[],
            events=[],
            tasks=[],
            volunteer=[],
            leadership=[],
            badges=[],
            certificates=[],
            recommendations=[],
            uploaded_items=[],
            confirmed_items=[],
            pending_items=[],
            stats={},
        )
    )

    assert content.startswith(b"%PDF")
    service_source = (ROOT / "app/services/resume_service.py").read_text(encoding="utf-8")
    assert "fallback: str = \"не указано\"" in service_source
    assert "пока не выбраны" in service_source


def test_portfolio_summary_separates_internal_portfolio_and_export() -> None:
    text = portfolio_summary_text(_portfolio_data())

    assert "Что уже собрано" in text
    assert "В документ попадут" in text
    assert "подтверждённые достижения" in text
    assert "на проверке: 1" in text


def test_portfolio_navigation_exposes_resume_without_deep_hiding() -> None:
    assert "🎓 Портфолио" in _labels(journey_keyboard())
    assert "🎓 Портфолио" in _labels(profile_sections_keyboard())
    callbacks = _callbacks(portfolio_keyboard())
    assert {"portfolio:view", "portfolio:upload", "portfolio:resume", "cabinet:open"}.issubset(callbacks)


def test_top_level_opportunities_open_the_same_hub() -> None:
    assert "offers:menu" in _callbacks(main_inline_keyboard())
    assert "offers:menu" in _callbacks(about_keyboard())


def test_empty_events_screen_has_way_back() -> None:
    source = (ROOT / "app/handlers/participant/events_stability_block8.py").read_text(encoding="utf-8")

    assert "Сейчас нет открытых мероприятий" in source
    assert "callback_data=\"menu:main\"" in source


def test_resume_handler_has_loading_error_and_no_temp_file_contracts() -> None:
    source = (ROOT / "app/handlers/participant/cabinet.py").read_text(encoding="utf-8")

    assert "Собираю Ваше портфолио в PDF" in source
    assert "BufferedInputFile(content" in source
    assert "ERA_portfolio_" in source
    assert "logger.exception(\"Could not build ERA resume" in source
    assert "logger.exception(\"Could not send ERA resume" in source
    assert "NamedTemporaryFile" not in source
    assert "FSInputFile" not in source


def test_legacy_resume_export_does_not_run_parallel_queries() -> None:
    source = (ROOT / "app/handlers/participant/cabinet.py").read_text(encoding="utf-8")

    assert "build_portfolio_data(session, user)" in source
    assert "build_era_resume(data)" in source
    assert "PortfolioItem.user_id == user.id,\n                PortfolioItem.status == \"verified\"" not in source


def test_resume_send_error_type_is_covered() -> None:
    error = TelegramForbiddenError(
        method=SendDocument(chat_id=1, document="file"),
        message="bot was blocked",
    )

    assert isinstance(error, TelegramForbiddenError)


def test_repeated_export_uses_fresh_buffered_file_name_contract() -> None:
    first = build_era_resume(_portfolio_data(full_name="Анна Иванова"))
    second = build_era_resume(_portfolio_data(full_name="Анна Иванова"))

    assert first.startswith(b"%PDF")
    assert second.startswith(b"%PDF")
    assert abs(len(first) - len(second)) < 500


def test_portfolio_data_accepts_user_without_photo_or_certificates() -> None:
    user = User(
        id=1,
        telegram_id=123,
        first_name="Давид",
        last_name=None,
        role="participant",
        participation_status="new_member",
        created_at=datetime(2025, 1, 1),
        skills=[],
    )
    data = _portfolio_data(
        full_name=user.first_name,
        certificates=[],
        uploaded_items=[],
        confirmed_items=[],
        pending_items=[],
    )

    assert data.full_name == "Давид"
    assert data.certificates == []
