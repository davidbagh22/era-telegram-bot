from __future__ import annotations

from fastapi import FastAPI

from app.api.v1.admin_people_detail import (
    ParticipantMetricsOut,
    _recognition_suggestions,
    _signal_text,
)
from app.api.v1.router import api_router
from app.database.models import Badge


def _metrics(**overrides) -> ParticipantMetricsOut:
    data = {
        "events_registered": 0,
        "events_attended": 0,
        "no_shows": 0,
        "tasks_submitted": 0,
        "tasks_approved": 0,
        "projects_authored": 0,
        "project_memberships": 0,
        "confirmed_project_contributions": 0,
        "surveys_completed": 0,
        "activity_submissions_approved": 0,
        "events_responsible": 0,
        "points_transactions": 0,
    }
    data.update(overrides)
    return ParticipantMetricsOut(**data)


def test_leadership_signals_are_evidence_based() -> None:
    signals = _signal_text(
        _metrics(events_attended=4, tasks_approved=3, projects_authored=1, surveys_completed=2)
    )

    assert "Высокая подтверждённая вовлечённость" in signals.summary
    assert any("4 подтверждённых посещений" in item for item in signals.strengths)
    assert any("3 принятых работ" in item for item in signals.strengths)
    assert not any("нет подтверждённых посещений" in item.lower() for item in signals.growth_areas)


def test_low_data_profile_gets_growth_prompts_not_personality_judgment() -> None:
    signals = _signal_text(_metrics())

    assert "Данных пока мало" in signals.summary
    assert signals.strengths == []
    assert any("небольшую конкретную задачу" in item for item in signals.growth_areas)
    assert all("слаб" not in item.lower() for item in signals.growth_areas)


def test_system_suggests_recognition_but_does_not_award_it() -> None:
    badges = [
        Badge(id=1, name="Первый шаг"),
        Badge(id=2, name="Надёжный участник"),
        Badge(id=3, name="Проектный автор"),
    ]
    point_suggestion, badge_suggestions = _recognition_suggestions(
        _metrics(events_attended=4, tasks_approved=3, projects_authored=1),
        badges,
        recent_score=8,
        has_recent_manual_bonus=False,
        directions=[],
    )

    assert point_suggestion is not None
    assert point_suggestion.amount == 20
    assert {item.badge_name for item in badge_suggestions} >= {
        "Первый шаг",
        "Надёжный участник",
        "Проектный автор",
    }


def test_recent_manual_bonus_suppresses_duplicate_point_prompt() -> None:
    point_suggestion, _ = _recognition_suggestions(
        _metrics(events_attended=4, tasks_approved=3),
        [],
        recent_score=8,
        has_recent_manual_bonus=True,
        directions=[],
    )
    assert point_suggestion is None


def test_rich_user_route_precedes_legacy_compact_route() -> None:
    app = FastAPI()
    app.include_router(api_router)
    matches = [
        route
        for route in app.routes
        if getattr(route, "path", "") == "/api/v1/admin/users/{user_id}"
        and "GET" in getattr(route, "methods", set())
    ]
    assert len(matches) >= 2
    assert matches[0].endpoint.__module__.endswith("admin_people_detail")
