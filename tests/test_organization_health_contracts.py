from __future__ import annotations

from io import BytesIO
from pathlib import Path
from types import SimpleNamespace

from openpyxl import Workbook, load_workbook

from app.services.excel_report_service import add_health_sheets, build_development_workbook, polish_workbook


ROOT = Path(__file__).resolve().parents[1]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def _workbook_bytes(workbook: Workbook) -> bytes:
    output = BytesIO()
    workbook.save(output)
    return output.getvalue()


def test_pulse_is_privacy_safe_aggregate_not_person_score() -> None:
    source = _read("app/services/organization_health_service.py")
    analytics = _read("app/services/development_analytics.py")

    assert "community_analytics(session, period_days=30)" in source
    assert 'pulse = None if vector_suppressed' in source
    assert "Stable traits, interests" in source
    assert "traits_json" not in source
    assert "strengths_json" not in source
    assert "personal_notes" not in source
    assert "MINIMUM_COHORT = 5" in analytics


def test_admin_health_endpoints_and_ui_are_exposed() -> None:
    api = _read("app/api/v1/admin_analytics_details.py")
    frontend = _read("frontend/src/screens/admin/AdminDashboardScreen.tsx")
    maintenance = _read("frontend/src/screens/admin/AdminMaintenanceScreen.tsx")

    assert '@router.get("/health"' in api
    assert '@router.get("/health-report.xlsx")' in api
    assert '@router.get("/full-report.xlsx")' in api
    assert "Пульс организации" in frontend
    assert "Здоровье организации · XLSX" in frontend
    assert "Показать все" in frontend
    assert "Операционный центр" in maintenance
    assert "без возврата в бот" in maintenance
    assert "Опасная зона" in maintenance
    assert "runMaintenanceReset" in maintenance


def test_polish_workbook_removes_internal_ids_and_keeps_business_columns() -> None:
    wb = Workbook()
    ws = wb.active
    ws.title = "Мероприятия"
    ws.append(["Название", "Проект ID", "Ответственный ID", "Автор ID", "Статус"])
    ws.append(["Форум ЭРА", 7, 12, 44, "active"])

    polished = load_workbook(BytesIO(polish_workbook(_workbook_bytes(wb))))
    result = polished["Мероприятия"]
    headers = [result.cell(1, col).value for col in range(1, result.max_column + 1)]

    assert headers == ["Название", "Статус"]
    assert result.sheet_view.showGridLines is False
    assert result.freeze_panes == "A2"


def test_health_report_starts_with_executive_pulse_sheets() -> None:
    wb = Workbook()
    wb.active.title = "Сводка"
    wb.active.append(["Показатель", "Значение"])
    wb.active.append(["Участники", 218])

    health = SimpleNamespace(
        pulse=67,
        pulse_label="Состояние устойчивое",
        pulse_coverage=80,
        pulse_sample_size=8,
        pulse_suppressed=False,
        vector_dimensions=[
            SimpleNamespace(key="energy", label="Энергия", value=71, delta=2),
            SimpleNamespace(key="agency", label="Опора", value=65, delta=-1),
            SimpleNamespace(key="autonomy", label="Самостоятельность", value=69, delta=0),
            SimpleNamespace(key="connection", label="Связь", value=73, delta=4),
            SimpleNamespace(key="direction", label="Направление", value=58, delta=-3),
        ],
        metrics=[
            SimpleNamespace(
                key="active_30d",
                category="Вовлечённость",
                label="Активны за 30 дней",
                value=55.0,
                display="120 · 55.0%",
                note="основной показатель текущей вовлечённости",
                score=55,
            ),
            SimpleNamespace(
                key="overdue_tasks",
                category="Исполнение",
                label="Просроченных заданий",
                value=3.0,
                display="3",
                note="срок прошёл, задача не закрыта",
                score=None,
            ),
        ],
        risks=["Просрочено заданий: 3."],
        period_label="операционные показатели: последние 7/30/90 дней",
        data_note="Пульс — безопасный агрегат текущего состояния.",
    )
    efficiency = SimpleNamespace(score=74, label="Система работает устойчиво")

    result = load_workbook(BytesIO(add_health_sheets(_workbook_bytes(wb), health, efficiency)))

    assert result.sheetnames[:3] == ["Здоровье организации", "Пульс Мой вектор", "Все показатели"]
    assert result["Здоровье организации"]["B4"].value == 74
    assert result["Здоровье организации"]["B5"].value == 67
    assert result["Пульс Мой вектор"]["B4"].value == 67
    assert result["Все показатели"].max_row >= 6


def test_suppressed_vector_export_contains_no_individual_data() -> None:
    content = build_development_workbook(
        {
            "coverage_percent": 20,
            "sample_size": 2,
            "eligible_profiles": 10,
            "minimum_cohort": 5,
            "suppressed": True,
        }
    )
    wb = load_workbook(BytesIO(content))
    values = " ".join(
        str(cell.value or "")
        for ws in wb.worksheets
        for row in ws.iter_rows()
        for cell in row
    ).lower()

    assert "недостаточно" in values
    assert "личные заметки" in values
    assert "user_id" not in values
    assert "raw" not in values
