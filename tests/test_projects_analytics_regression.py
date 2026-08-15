from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_project_builder_saves_only_current_question_and_keeps_local_draft() -> None:
    source = (ROOT / "frontend/src/screens/projects/ProjectDetail.tsx").read_text(encoding="utf-8")
    assert "updateProject(projectId, { [question.key]: answer })" in source
    assert "updateProject(projectId, answers)" not in source
    assert "era:project:${projectId}:answers" in source
    assert "Попробовать снова" in source
    assert "Скопировать ответ" in source
    assert "Сохранить и выйти" in source


def test_incomplete_project_cannot_be_submitted() -> None:
    workflow = (ROOT / "app/services/project_workflow_service.py").read_text(encoding="utf-8")
    assert "not missing_required_answers(project)" in workflow


def test_analytics_has_explainable_era_pulse_and_all_exports() -> None:
    screen = (ROOT / "frontend/src/screens/admin/AdminDashboardScreen.tsx").read_text(encoding="utf-8")
    api = (ROOT / "app/api/v1/admin_analytics_details.py").read_text(encoding="utf-8")
    assert "ERA PULSE" in screen
    assert "Что сделать на этой неделе" in screen
    assert "Полный отчёт XLSX" in screen
    assert '"/weekly"' in api
    assert '"/details/{section}/export.csv"' in api
    assert '"/details/{section}/export.xlsx"' in api
    assert '"/full-report.xlsx"' in api
    assert 'fgColor="E32636"' in api


def test_community_public_api_does_not_expose_registration_pii() -> None:
    source = (ROOT / "app/api/v1/community_users.py").read_text(encoding="utf-8")
    model = source.split("class CommunityUserOut", 1)[1].split("def _departments", 1)[0]
    for private_field in ("phone", "email", "birth_date", "motivation", "experience", "skills"):
        assert private_field not in model
    assert "telegram_url" in model
    assert "events_attended" in model
