from __future__ import annotations

import unittest
from datetime import date, datetime, timezone
from io import BytesIO
from types import SimpleNamespace

from openpyxl import load_workbook
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.database.base import Base
from app.services.executive_excel_service import SHEET_NAMES, build_executive_workbook, resolve_report_period


class ExecutivePeriodTests(unittest.TestCase):
    def test_standard_periods_are_supported(self) -> None:
        today = date(2026, 8, 19)
        self.assertEqual(resolve_report_period("30d", today=today)[0], date(2026, 7, 21))
        self.assertEqual(resolve_report_period("3m", today=today)[2], "3 месяца")
        self.assertEqual(resolve_report_period("6m", today=today)[2], "6 месяцев")
        self.assertEqual(resolve_report_period("1y", today=today)[2], "1 год")

    def test_custom_period_requires_both_dates(self) -> None:
        with self.assertRaises(ValueError):
            resolve_report_period("custom", start_date=date(2026, 1, 1))
        start, end, label = resolve_report_period(
            "custom",
            start_date=date(2026, 1, 1),
            end_date=date(2026, 2, 1),
        )
        self.assertEqual((start, end), (date(2026, 1, 1), date(2026, 2, 1)))
        self.assertIn("01.01.2026", label)


class ExecutiveWorkbookTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.session_factory = async_sessionmaker(self.engine, expire_on_commit=False)

    async def asyncTearDown(self) -> None:
        await self.engine.dispose()

    async def test_report_has_old_project_work_and_no_personal_rows(self):
        from app.database.models import User, Project, ProjectMember, ProjectMilestone, PortfolioItem
        async with self.session_factory() as session:
            person = User(telegram_id=7654321, first_name='PRIVATE_NAME', username='PRIVATE_USERNAME', application_status='approved')
            session.add(person)
            await session.flush()
            project = Project(author_id=person.id, title='Постоянный проект', short_description='PRIVATE_DESCRIPTION',
                created_at=datetime(2026,9,1,tzinfo=timezone.utc), status='in_progress')
            session.add(project)
            await session.flush()
            session.add_all([
                ProjectMember(project_id=project.id, user_id=person.id, contribution_status='confirmed',
                    contribution_confirmed_at=datetime(2026,10,10,tzinfo=timezone.utc), contribution_summary='PRIVATE_CONTRIBUTION'),
                ProjectMilestone(project_id=project.id, title='Этап', status='completed', completed_at=datetime(2026,10,11,tzinfo=timezone.utc)),
                PortfolioItem(user_id=person.id, title='PRIVATE_ACHIEVEMENT', item_type='certificate', status='issued',
                    created_at=datetime(2026,10,12,tzinfo=timezone.utc)),
            ])
            await session.flush()
            content = await build_executive_workbook(session,
                analytics=SimpleNamespace(users=[person], events=[], projects=[project], department_stats=[], direction_stats=[]),
                health=SimpleNamespace(pulse=None, pulse_label='Нет данных', pulse_coverage=0, pulse_sample_size=0, vector_dimensions=[]),
                efficiency=SimpleNamespace(score=0, label='Нет данных'),
                start_date=date(2026,10,1), end_date=date(2026,10,31), period_label='Октябрь')
        wb = load_workbook(BytesIO(content))
        row = list(wb[SHEET_NAMES[7]].values)[1]
        self.assertEqual(row[0], 'Постоянный проект')
        self.assertEqual(row[3:5], (1,1))
        rendered = str([list(sheet.values) for sheet in wb.worksheets])
        for secret in ['PRIVATE_NAME', 'PRIVATE_USERNAME', 'PRIVATE_DESCRIPTION', 'PRIVATE_CONTRIBUTION', 'PRIVATE_ACHIEVEMENT', '7654321']:
            self.assertNotIn(secret, rendered)
        self.assertEqual(list(wb[SHEET_NAMES[10]].values)[1], ('certificate', 'issued', 1))

    async def test_exact_13_sheet_contract_and_vector_privacy(self) -> None:
        analytics = SimpleNamespace(
            users=[],
            events=[],
            projects=[],
            department_stats=[SimpleNamespace(name="=Название отдела", members=1, active_goals=0, done_goals=0)],
            direction_stats=[],
        )
        health = SimpleNamespace(
            pulse=67,
            pulse_label="Стабильно",
            pulse_coverage=42,
            pulse_sample_size=8,
            vector_dimensions=[SimpleNamespace(label="Энергия", value=70, delta=2)],
        )
        efficiency = SimpleNamespace(score=74, label="Устойчиво")
        async with self.session_factory() as session:
            content = await build_executive_workbook(
                session,
                analytics=analytics,
                health=health,
                efficiency=efficiency,
                start_date=date(2026, 7, 21),
                end_date=date(2026, 8, 19),
                period_label="30 дней",
            )

        wb = load_workbook(BytesIO(content), data_only=True)
        self.assertEqual(wb.sheetnames, SHEET_NAMES)
        rendered = " ".join(
            str(cell.value or "")
            for ws in wb.worksheets
            for row in ws.iter_rows()
            for cell in row
        ).casefold()
        # Executive export may explain the privacy rule in prose, but it must
        # never expose the underlying technical/raw field names or PII columns.
        for forbidden in (
            "telegram_id",
            "user_id",
            "raw_answer",
            "raw_answers",
            "personal_notes",
            "phone_number",
            "email_address",
        ):
            self.assertNotIn(forbidden, rendered)
        self.assertIn("aggregate only", rendered)
        self.assertIn("meaningful activity", rendered)
        self.assertEqual(len(wb.sheetnames), 13)
        self.assertEqual(wb[SHEET_NAMES[3]]["A2"].value, "=Название отдела")
        literal_wb = load_workbook(BytesIO(content), data_only=False)
        self.assertEqual(literal_wb[SHEET_NAMES[3]]["A2"].data_type, "s")


if __name__ == "__main__":
    unittest.main()
