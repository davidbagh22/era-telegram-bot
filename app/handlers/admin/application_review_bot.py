"""Native application decisions reuse the existing domain service and ledger."""
from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message, InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import Settings
from app.database.models import User
from app.services.staff_access_service import can_operate_queue
from app.services.application_review_service import (
    application_review_version, approve_application, deliver_application_notices,
    reject_application, request_more_info, stage_application_notice,
)
from app.utils import texts
from app.utils.constants import ApplicationStatus

router = Router(name='native_application_review')


class ApplicationComment(StatesGroup):
    text = State()


async def _target(session: AsyncSession, user_id: int, revision: int) -> User | None:
    target = await session.scalar(select(User).where(User.id == user_id).with_for_update()
                                  .execution_options(populate_existing=True))
    if (target is None or target.is_archived or target.is_blocked
        or target.application_status not in {ApplicationStatus.PENDING, ApplicationStatus.NEEDS_INFO}
        or await application_review_version(session, target.id) != revision):
        return None
    return target


async def _finish(message, session, bot, settings, target, *, action, comment, actor_id):
    if action == 'approve':
        result = await approve_application(session, target, actor_id=actor_id)
        notice = texts.APPLICATION_APPROVED + '\n\n' + texts.CHAT_RULES
        label = 'Заявка одобрена'
    elif action == 'reject':
        result = await reject_application(session, target, actor_id=actor_id, comment=comment)
        notice = texts.APPLICATION_REJECTED + '\n\nПричина решения: ' + comment
        label = 'Заявка отклонена'
    else:
        result = await request_more_info(session, target, actor_id=actor_id, comment=comment)
        notice = texts.APPLICATION_NEEDS_INFO.format(comment=comment)
        label = 'Уточнение отправлено в очередь доставки'
    if not result.changed:
        await message.answer('Заявка уже рассмотрена. Обновите её карточку.')
        return
    key = await stage_application_notice(session, target, text=notice)
    factory = async_sessionmaker(session.bind, expire_on_commit=False)
    await session.commit()
    await deliver_application_notices(bot, settings, factory, only_key=key)
    await message.answer(f'✅ {label}. Решение сохранено.',
                         reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="← Заявки", callback_data="admin:applications")]]))


@router.callback_query(F.data.regexp(r'^admin:application_action:(approve|reject|info):\d+:\d+$'))
async def application_action(call: CallbackQuery, user: User | None, settings: Settings,
                             session: AsyncSession, state: FSMContext, bot: Bot) -> None:
    if not await can_operate_queue(session, user, settings, "applications.review"):
        await call.answer(texts.NO_ACCESS, show_alert=True)
        return
    _, _, action, raw_id, raw_revision = call.data.split(':')
    target = await _target(session, int(raw_id), int(raw_revision))
    if target is None:
        await call.answer('Карточка устарела. Откройте заявку заново.', show_alert=True)
        return
    await call.answer()
    if action == 'approve':
        await _finish(call.message, session, bot, settings, target, action=action,
                      comment='', actor_id=user.id if user else None)
        return
    await state.set_state(ApplicationComment.text)
    await state.update_data(application_id=target.id, application_revision=int(raw_revision), application_action=action)
    await call.message.answer(
        'Напишите причину отклонения. Этот текст получит заявитель.\n\n/cancel — отменить.'
        if action == 'reject' else 'Напишите, что нужно уточнить. Этот вопрос получит заявитель.\n\n/cancel — отменить.')


@router.message(ApplicationComment.text)
async def application_comment(message: Message, user: User | None, settings: Settings,
                              session: AsyncSession, state: FSMContext, bot: Bot) -> None:
    if not await can_operate_queue(session, user, settings, "applications.review"):
        await message.answer(texts.NO_ACCESS)
        return
    comment = (message.text or '').strip()
    if not comment or len(comment) > 1500 or comment.startswith('/'):
        await message.answer('Напишите текст от 1 до 1500 символов или /cancel для отмены.')
        return
    data = await state.get_data()
    target = await _target(session, int(data['application_id']), int(data['application_revision']))
    if target is None:
        await state.clear()
        await message.answer('Заявка уже изменилась. Откройте актуальную карточку.')
        return
    await _finish(message, session, bot, settings, target, action=data['application_action'],
                  comment=comment, actor_id=user.id if user else None)
    await state.clear()
