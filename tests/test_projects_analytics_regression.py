from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_project_builder_saves_only_current_question() -> None:
    source = (ROOT / "frontend/src/screens/projects/ProjectDetail.tsx").read_text(encoding="utf-8")
    assert "updateProject(projectId, { [question.key]: value })" in source
    assert "updateProject(projectId, answers)" not in source
    assert "Сохранить и выйти" in source


def test_incomplete_project_cannot_be_submitted() -> None:
    workflow = (ROOT / "app/services/project_workflow_service.py").read_text(encoding="utf-8")
    assert "not missing_required_answers(project)" in workflow


def test_analytics_has_weekly_efficiency_and_exports() -> None:
    screen = (ROOT / "frontend/src/screens/admin/AdminDashboardScreen.tsx").read_text(encoding="utf-8")
    api = (ROOT / "app/api/v1/admin_analytics_details.py").read_text(encoding="utf-8")
    assert "Эффективность ЭРА" in screen
    assert "Что делать дальше" in screen
    assert "Полный отчёт ЭРА" in screen
    assert '"/weekly"' in api
    assert '"/details/{section}/export.csv"' in api
    assert '"/full-report.xlsx"' in api
