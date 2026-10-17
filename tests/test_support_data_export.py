import json
from unittest import IsolatedAsyncioTestCase

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.database.base import Base
from app.database.models import SupportMessage, User, UserQuestion
from app.services.data_rights_service import export_user_data


class SupportDataExportTests(IsolatedAsyncioTestCase):
    async def test_export_contains_own_conversation_including_staff_answers_but_not_other_tickets(self):
        engine = create_async_engine('sqlite+aiosqlite:///:memory:')
        try:
            async with engine.begin() as connection:
                await connection.run_sync(Base.metadata.create_all)
            sessions = async_sessionmaker(engine, expire_on_commit=False)
            async with sessions() as session:
                owner = User(telegram_id=22, first_name='Owner', role='admin')
                staff = User(telegram_id=11, first_name='Staff')
                stranger = User(telegram_id=33, first_name='Stranger')
                session.add_all([owner, staff, stranger])
                await session.flush()
                mine = UserQuestion(user_id=owner.id, text='My original question', category='general',
                                    admin_answer='My legacy answer', assigned_to=staff.id)
                other = UserQuestion(user_id=stranger.id, text='DO_NOT_EXPORT_OTHER_OWNER_QUESTION')
                session.add_all([mine, other])
                await session.flush()
                session.add_all([
                    SupportMessage(question_id=mine.id, author_id=owner.id, direction='participant',
                        source_key='export:mine:1', text='My followup', file_id='own-photo', delivery_status='sent'),
                    SupportMessage(question_id=mine.id, author_id=staff.id, direction='staff',
                        source_key='export:mine:2', text='Staff response for me', delivery_status='sent'),
                    SupportMessage(question_id=other.id, author_id=owner.id, direction='staff',
                        source_key='export:other', text='DO_NOT_EXPORT_THIRD_PARTY_CONVERSATION', delivery_status='sent'),
                ])
                await session.commit()
                await session.refresh(owner, attribute_names=['departments', 'directions'])
                exported = await export_user_data(session, owner)
                self.assertEqual([row['id'] for row in exported['support_questions']], [mine.id])
                self.assertEqual(exported['support_questions'][0]['admin_answer'], 'My legacy answer')
                self.assertEqual([row['text'] for row in exported['support_messages']],
                                 ['My followup', 'Staff response for me'])
                self.assertEqual(exported['support_messages'][0]['file_id'], 'own-photo')
                self.assertNotIn('DO_NOT_EXPORT', json.dumps(exported, ensure_ascii=False))
                for row in exported['support_messages']:
                    self.assertNotIn('author_id', row)
                self.assertNotIn('assigned_to', exported['support_questions'][0])
        finally:
            await engine.dispose()
