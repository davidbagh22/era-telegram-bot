from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config import Settings
from app.database.base import Base
from app.database.models import PermissionGrant, User
from app.handlers.admin.literature_editor import _queue, editorial_action
from app.services.staff_access_service import LITERATURE_CATEGORY_SCOPE_ID
from app.utils.constants import ApplicationStatus, Role


class ScopedLiteratureEditorTests(IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine('sqlite+aiosqlite:///:memory:')
        async with self.engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        self.sessions = async_sessionmaker(self.engine, expire_on_commit=False)
        self.settings = Settings(bot_token='0000000000:CITESTTOKEN')

    async def asyncTearDown(self):
        await self.engine.dispose()

    async def _users(self, session):
        admin = User(telegram_id=1, first_name='Admin', role=Role.ADMIN,
            application_status=ApplicationStatus.APPROVED)
        editor = User(telegram_id=2, first_name='Editor',
            application_status=ApplicationStatus.APPROVED)
        session.add_all([admin, editor])
        await session.flush()
        session.add(PermissionGrant(user_id=editor.id, permission='literature.manage',
            scope_type='literature_category', scope_id=LITERATURE_CATEGORY_SCOPE_ID,
            granted_by=admin.id, is_active=True))
        await session.flush()
        return admin, editor

    async def test_scoped_editor_queue_hides_global_schedule_settings(self):
        async with self.sessions() as session:
            await self._users(session)
            message = SimpleNamespace(answer=AsyncMock())
            await _queue(message, session, manage_settings=False)
            text = message.answer.await_args.args[0]
            markup = message.answer.await_args.kwargs['reply_markup']
            callbacks = [button.callback_data for row in markup.inline_keyboard for button in row]
            assert 'Очередь:' not in text and 'Время:' not in text
            assert 'admin:literature:new' in callbacks
            assert 'admin:literature:time' not in callbacks
            assert not any(callback.startswith(('admin:literature:enabled:', 'admin:literature:paused:'))
                for callback in callbacks)

    async def test_scoped_editor_cannot_open_module_settings_with_stale_button(self):
        async with self.sessions() as session:
            _, editor = await self._users(session)
            call = SimpleNamespace(data='admin:literature:time', answer=AsyncMock(),
                message=SimpleNamespace(answer=AsyncMock()))
            state = SimpleNamespace(set_state=AsyncMock(), update_data=AsyncMock())
            await editorial_action(call, editor, self.settings, session, state, bot=None)
            call.answer.assert_awaited_once()
            call.message.answer.assert_awaited_once()
            state.set_state.assert_not_awaited()

