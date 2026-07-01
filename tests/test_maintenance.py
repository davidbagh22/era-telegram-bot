import unittest

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from app.database import Base
from app.database.models import (
    AppSetting,
    ChatGreeting,
    Department,
    Direction,
    User,
    UserQuestion,
)
from app.keyboards.participant import main_menu
from app.services.maintenance_service import reset_operational_data, reset_preview
from app.utils.constants import ApplicationStatus, Role


class MaintenanceTests(unittest.IsolatedAsyncioTestCase):
    async def test_reset_keeps_admin_structure_and_settings(self) -> None:
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)

        class AsyncAdapter:
            def __init__(self, sync_session: Session) -> None:
                self.sync_session = sync_session

            async def scalar(self, statement):
                return self.sync_session.scalar(statement)

            async def scalars(self, statement):
                return self.sync_session.scalars(statement)

            async def execute(self, statement):
                return self.sync_session.execute(statement)

        with Session(engine, expire_on_commit=False) as sync_session:
            session = AsyncAdapter(sync_session)
            admin = User(
                telegram_id=1,
                first_name="Администратор",
                role=Role.ADMIN,
                application_status=ApplicationStatus.APPROVED,
            )
            participant = User(
                telegram_id=2,
                first_name="Тест",
                role=Role.PARTICIPANT,
                application_status=ApplicationStatus.APPROVED,
            )
            sync_session.add_all([admin, participant])
            sync_session.flush()
            department = Department(name="Внутренние связи", leader_id=participant.id)
            sync_session.add(department)
            sync_session.flush()
            sync_session.add(
                Direction(
                    name="Культура",
                    department_id=department.id,
                    leader_id=participant.id,
                )
            )
            sync_session.add_all(
                [
                    AppSetting(
                        key="general_chat_url",
                        value="https://t.me/example",
                        updated_by=participant.id,
                    ),
                    ChatGreeting(
                        chat_key="general",
                        title="Общий чат",
                        text="Добро пожаловать, {name}",
                        updated_by=participant.id,
                    ),
                    UserQuestion(user_id=participant.id, text="Тестовый вопрос"),
                ]
            )
            sync_session.commit()

            preview = await reset_preview(session, [1])
            self.assertEqual(preview["users"], 1)
            self.assertEqual(preview["user_questions"], 1)

            await reset_operational_data(session, [1])
            sync_session.commit()

            users = (await session.scalars(select(User))).all()
            self.assertEqual([item.telegram_id for item in users], [1])
            self.assertEqual(
                await session.scalar(select(func.count()).select_from(UserQuestion)),
                0,
            )
            setting = await session.scalar(select(AppSetting))
            greeting = await session.scalar(select(ChatGreeting))
            kept_department = await session.scalar(select(Department))
            self.assertIsNone(setting.updated_by)
            self.assertIsNone(greeting.updated_by)
            self.assertIsNone(kept_department.leader_id)
        engine.dispose()

    async def test_main_menu_explains_the_bot(self) -> None:
        keyboard = main_menu("https://t.me/era")
        labels = {button.text for row in keyboard.keyboard for button in row}
        self.assertIn("⭐ Возможности", labels)


if __name__ == "__main__":
    unittest.main()
