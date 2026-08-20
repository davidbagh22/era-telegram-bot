from pathlib import Path

from app.api.v1.engagement import _safe_product_metadata


ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_era_pro_is_threshold_not_points_purchase() -> None:
    source = read("app/api/v1/era_pro.py")
    assert "ERA_PRO_THRESHOLD = 8_000" in source
    assert "era_pro_threshold_not_met" in source
    assert 'status="approved"' in source or 'status == "approved"' in source
    assert "add_points(" not in source
    assert "spend_points" not in source
    assert "deduct" not in source.lower()


def test_era_pro_is_reachable_from_opportunities_and_has_context_help() -> None:
    app = read("frontend/src/app/App.tsx")
    points_sheet = read("frontend/src/screens/opportunities/PointsRulesSheet.tsx")
    registry = read("frontend/src/help/helpContentRegistry.ts")
    layout = read("frontend/src/layouts/UserLayout.tsx")

    assert 'route === "era-pro"' in app
    assert "<EraProScreen" in app
    assert 'community: "#/opportunities"' in app
    assert "<EraProOpportunityCard />" in points_sheet
    assert "era_pro:" in registry
    assert "8 000 — не цена" in registry
    assert "/era[-_]?pro|mentorship/" in registry
    assert '<ContextHelp mode="user" />' in layout


def test_project_builder_is_learning_first_without_ai_autofill_controls() -> None:
    screen = read("frontend/src/screens/ProjectDetail.tsx")
    hints = read("frontend/src/help/projectBuilderHints.ts")
    builder = read("app/services/project_builder.py")

    for forbidden in (
        "Помоги сформулировать",
        "Сделай короче",
        "Улучши мой вариант",
    ):
        assert forbidden not in screen

    assert "Получить подсказку" in screen
    assert "projectBuilderHints" in screen
    assert "theory" in hints or "why" in hints
    assert builder.count("ProjectQuestion(") >= 19


def test_referral_copy_matches_backend_economy() -> None:
    service = read("app/services/referral_service.py")
    rules = read("frontend/src/screens/opportunities/PointsRulesSheet.tsx")

    assert "REGISTRATION_REFERRAL_POINTS = 30" in service
    assert "FIRST_ACTIVITY_REFERRAL_POINTS = FIRST_EVENT_REFERRAL_POINTS" in service
    assert "FIRST_EVENT_REFERRAL_POINTS = 70" in service
    assert "REFERRAL_PER_INVITEE_CAP = 100" in service
    assert "+30 — приглашённый зарегистрирован и одобрен" in rules
    assert "+70 — первое подтверждённое участие приглашённого" in rules
    assert "Максимум 100 баллов за одного приглашённого" in rules


def test_product_analytics_drops_pii_and_free_form_fields() -> None:
    metadata = _safe_product_metadata(
        {
            "screen": "era-pro",
            "source": "opportunities",
            "section": "application",
            "state": "needs_info",
            "action": "open",
            "phone": "+37400000000",
            "email": "person@example.com",
            "answer": "private questionnaire answer",
            "motivation": "private motivation text",
        }
    )

    assert metadata == {
        "screen": "era-pro",
        "source": "opportunities",
        "section": "application",
        "state": "needs_info",
        "action": "open",
    }


def test_product_analytics_is_installed_and_route_ids_are_normalized() -> None:
    main = read("frontend/src/main.tsx")
    analytics = read("frontend/src/analytics/productAnalytics.ts")
    backend = read("app/api/v1/engagement.py")

    assert "installProductAnalytics();" in main
    assert 'trackProductEvent("screen_view", { screen })' in analytics
    assert 'segment) ? ":id" : segment' in analytics
    assert "/api/v1/engagement/product-event" in analytics
    assert '_ALLOWED_PRODUCT_METADATA = {"screen", "source", "section", "state", "action"}' in backend
