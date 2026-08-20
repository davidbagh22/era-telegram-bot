from dataclasses import fields
from pathlib import Path

from app.api.v1.project_builder import router as project_builder_router
from app.services.project_builder import PROJECT_QUESTIONS, ProjectQuestion


EXPECTED_KEYS = [
    "idea",
    "title",
    "problem",
    "target_audience",
    "goal",
    "project_tasks",
    "format",
    "uniqueness",
    "scenario",
    "team",
    "partners",
    "resources",
    "budget",
    "implementation_plan",
    "promotion",
    "expected_result",
    "success_metrics",
    "risks",
]


def test_project_builder_has_exactly_eighteen_theory_steps() -> None:
    assert len(PROJECT_QUESTIONS) == 18
    assert [question.key for question in PROJECT_QUESTIONS] == EXPECTED_KEYS
    assert all(question.prompt.strip() for question in PROJECT_QUESTIONS)


def test_project_question_contract_has_no_ai_hint_field() -> None:
    assert "ai_hint" not in {field.name for field in fields(ProjectQuestion)}


def test_project_builder_exposes_no_ai_assist_route() -> None:
    paths = {route.path for route in project_builder_router.routes}
    assert "/project-builder/questions" in paths
    assert "/project-builder/assist" not in paths


def test_participant_project_ui_contains_no_old_ai_writer_controls() -> None:
    root = Path(__file__).resolve().parents[1]
    frontend = (root / "frontend/src/screens/projects/ProjectDetail.tsx").read_text(encoding="utf-8")
    api = (root / "frontend/src/api/projectBuilder.ts").read_text(encoding="utf-8")
    backend = (root / "app/api/v1/project_builder.py").read_text(encoding="utf-8")
    handler = (root / "app/handlers/participant/projects.py").read_text(encoding="utf-8")

    forbidden = (
        "AI-подсказка",
        "Помоги сформулировать",
        "Сделай короче",
        "Улучши мой вариант",
        "assistProjectBuilder",
        'callback_data="project:hint:',
    )
    combined = "\n".join((frontend, api, backend, handler))
    for marker in forbidden:
        assert marker not in combined

    assert "Теория шага" in frontend
    assert "Что написать" in frontend
    assert "Удалить черновик" in frontend
