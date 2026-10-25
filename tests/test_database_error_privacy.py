from unittest import IsolatedAsyncioTestCase

from sqlalchemy import Column, Integer, MetaData, String, Table
from sqlalchemy.exc import IntegrityError

from app.database.session import create_engine_and_sessionmaker
from app.services.notification_service import _session_factory


class DatabaseErrorPrivacyTests(IsolatedAsyncioTestCase):
    async def test_request_and_notification_errors_hide_private_bound_parameters(self):
        engine, factory = create_engine_and_sessionmaker('sqlite+aiosqlite:///:memory:')
        notifications = _session_factory.__wrapped__('sqlite+aiosqlite:///:memory:')
        for name, current_engine, sessions in (
            ('request', engine, factory),
            ('notification', notifications.kw['bind'], notifications),
        ):
            with self.subTest(engine=name):
                try:
                    metadata = MetaData()
                    table = Table('privacy_probe', metadata, Column('id', Integer, primary_key=True),
                                  Column('value', String(255), nullable=False))
                    async with current_engine.begin() as connection:
                        await connection.run_sync(metadata.create_all)
                    async with sessions() as session:
                        await session.execute(table.insert().values(id=1, value='Initial'))
                        await session.commit()
                        with self.assertRaises(IntegrityError) as caught:
                            await session.execute(table.insert().values(
                                id=1, value='DO_NOT_LOG_PRIVATE_MESSAGE_OR_CONTACT'))
                        rendered = str(caught.exception)
                        self.assertIn('privacy_probe', rendered)
                        self.assertNotIn('DO_NOT_LOG_PRIVATE_MESSAGE_OR_CONTACT', rendered)
                        await session.rollback()
                finally:
                    await current_engine.dispose()
