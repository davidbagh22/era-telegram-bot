"""Committed project decisions survive a restart before Telegram delivery."""
import json

from sqlalchemy import select

from app.database.models import AppSetting, User
from app.services.notification_service import safe_send_once


async def stage_project_review_notice(session, project, *, notice, revision):
    key = f'project-review-notice:{project.id}:{revision}'
    if await session.scalar(select(AppSetting.id).where(AppSetting.key == key)) is None:
        session.add(AppSetting(key=key, value=json.dumps({
            'author_id': project.author_id,
            'text': f'💡 {notice}\n\nПроект: {project.title}\n\nКомментарий команды ЭРА:\n{project.admin_comment}',
        }, ensure_ascii=False)))
    await session.flush()


async def deliver_project_review_notices(bot, settings, session_factory):
    async with session_factory() as session:
        keys = list((await session.scalars(select(AppSetting.key).where(
            AppSetting.key.like('project-review-notice:%')).order_by(AppSetting.key).limit(50))).all())
    for key in keys:
        async with session_factory() as session:
            row = await session.scalar(select(AppSetting).where(AppSetting.key == key).with_for_update())
            if row is None:
                continue
            data = json.loads(row.value) if isinstance(row.value, str) else row.value
            author = await session.get(User, data['author_id'])
            if author is None or author.is_blocked or author.is_archived:
                await session.delete(row)
            else:
                result = await safe_send_once(bot, settings, author.telegram_id, data['text'],
                    delivery_key=key, notification_type='project_review', parse_mode=None)
                if result.status in {'sent', 'blocked', 'unreachable', 'uncertain', 'conflict', 'skipped'} or (
                        result.status == 'failed' and result.attempt_count >= 3):
                    await session.delete(row)
            await session.commit()
