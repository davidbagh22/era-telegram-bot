from aiogram import F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy import select
from sqlalchemy import delete
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.content.literature_issues import ISSUES, render_issue
from app.database.models import AppSetting, User
from app.services.book_club_service import eligible, mark_progress, progress
from app.services.book_club_service import save_reflection, reflection_summary
from app.content.literature_issues import get_issue


class ReflectionStates(StatesGroup):
    answer = State()

router = Router(name='book_club')
router.message.filter(F.chat.type == 'private')
router.callback_query.filter(F.message.chat.type == 'private')


def button(text, callback):
    return InlineKeyboardButton(text=text, callback_data=callback)


def _keyboard(subscribed: bool = False, discussion_url: str = '') -> InlineKeyboardMarkup:
    rows = [[button('📖 Читать · 48 законов власти', 'bookclub:list:0')],
            [button('📊 Мой прогресс', 'bookclub:progress')],
            [button('📝 Мои ответы и итоги', 'bookclub:reflections')],
            [button('🔕 Отписаться' if subscribed else '🔔 Подписаться',
                    'bookclub:unsubscribe' if subscribed else 'bookclub:subscribe')]]
    if discussion_url:
        rows.append([InlineKeyboardButton(text='💬 Обсуждение в сообществе', url=discussion_url)])
    rows.append([button('🏠 Главное меню', 'menu:main')])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def issue_keyboard(number: int) -> InlineKeyboardMarkup:
    nav = []
    if number > 1:
        nav.append(button('← Предыдущий', f'bookclub:issue:{number - 1}'))
    if number < 48:
        nav.append(button('Следующий →', f'bookclub:issue:{number + 1}'))
    return InlineKeyboardMarkup(inline_keyboard=[
        [button('✅ Прочитано', f'bookclub:read:{number}'), button('📝 Задание выполнено', f'bookclub:task:{number}')],
        [button('💭 Ответить для себя', f'bookclub:reflect:{number}')],
        nav, [button('← Все выпуски', f'bookclub:list:{(number - 1) // 8}')],
        [button('📚 Литература', 'bookclub:home'), button('🔕 Отписаться', 'bookclub:unsubscribe')],
        [button('🏠 Главное меню', 'menu:main')],
    ])


async def show_home(message: Message, user: User | None, settings: Settings):
    await message.answer(
        '📚 ЭРА | Литература\n\nНачинаем с книги Роберта Грина «48 законов власти». '
        'Все 48 авторских критических разборов доступны для чтения. '
        'Это не текст книги и не безусловные советы по манипуляции.\n\n'
        'Рассылка по подписке: один выпуск в день в 19:00 по Еревану, '
        'с 10 октября по 26 ноября 2026 года. Пропущенные выпуски можно открыть в каталоге. '
        'Отписаться можно в любой момент; отметки прогресса сохранятся.\n\n'
        'Если формат будет интересен участникам, продолжим программу с другими книгами.',
        reply_markup=_keyboard(bool(user and user.book_club_subscribed), settings.general_chat_url),
    )


@router.message(F.text.in_({'📖 Книжный клуб', '📚 Литература'}))
async def book_club(message: Message, user: User | None, settings: Settings) -> None:
    await show_home(message, user, settings)


@router.callback_query(F.data == 'bookclub:home')
async def home(call: CallbackQuery, user: User | None, settings: Settings):
    await call.answer()
    await show_home(call.message, user, settings)


@router.callback_query(F.data.in_({'bookclub:subscribe', 'bookclub:unsubscribe'}))
async def change_subscription(call: CallbackQuery, user: User | None, session: AsyncSession) -> None:
    subscribed = call.data == 'bookclub:subscribe'
    if user is None or (subscribed and not eligible(user)):
        await call.answer('Подписка доступна после одобрения регистрации.', show_alert=True)
        return
    user = await session.scalar(select(User).where(User.id == user.id).with_for_update().execution_options(populate_existing=True))
    user.book_club_subscribed = subscribed
    await session.commit()
    await call.answer('Подписка включена' if subscribed else 'Подписка отключена')
    await call.message.answer(
        '✅ Подписка включена. Новые выпуски приходят в 19:00 по Еревану в дни программы.' if subscribed
        else '🔕 Подписка отключена. Новых рассылок не будет. История чтения сохранена.',
        reply_markup=_keyboard(subscribed),
    )


@router.callback_query(F.data.startswith('bookclub:reflect:'))
async def begin_reflection(call: CallbackQuery, user: User | None, state: FSMContext):
    if not eligible(user):
        await call.answer('Сначала завершите регистрацию.', show_alert=True)
        return
    try:
        issue = get_issue(int(call.data.rsplit(':', 1)[1]))
    except (ValueError, IndexError):
        await call.answer('Выпуск не найден.', show_alert=True)
        return
    await state.set_state(ReflectionStates.answer)
    await state.update_data(reflection_number=issue.number)
    await call.answer()
    await call.message.answer(
        f'💭 {issue.reflection_question}\n\nОтветьте одним сообщением (до 3000 символов). '
        'Отправляя ответ, вы сохраняете его в своём дневнике бота. '
        'В чате он не публикуется; администратор видит только число ответов. '
        'Не указывайте чужие личные данные. Ответы можно удалить кнопкой «Удалить мои ответы». '
        'Это саморефлексия, не психологическая диагностика.',
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[button('Отмена', 'bookclub:reflect_cancel')]]))


@router.callback_query(F.data == 'bookclub:reflect_cancel')
async def cancel_reflection(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await call.answer('Отменено')


@router.message(ReflectionStates.answer)
async def receive_reflection(message: Message, user: User | None, state: FSMContext, session: AsyncSession):
    if not eligible(user):
        await state.clear()
        return
    data = await state.get_data()
    answer = message.text or ''
    if not answer.strip() or len(answer) > 3000:
        await message.answer('Отправьте текст до 3000 символов.')
        return
    await save_reflection(session, user, data['reflection_number'], answer)
    await state.clear()
    await message.answer('Ответ сохранён. Изменения можно увидеть в «Мои ответы и итоги».', reply_markup=_keyboard(user.book_club_subscribed))


@router.callback_query(F.data.in_({'bookclub:reflections', 'bookclub:delete_answers', 'bookclub:delete_confirm'}))
async def my_reflections(call: CallbackQuery, user: User | None, session: AsyncSession, state: FSMContext):
    if not eligible(user):
        await call.answer('Сначала завершите регистрацию.', show_alert=True)
        return
    await state.clear()
    await call.answer()
    if call.data == 'bookclub:delete_answers':
        await call.message.answer('Удалить все ваши личные ответы?', reply_markup=InlineKeyboardMarkup(inline_keyboard=[[button('Да, удалить', 'bookclub:delete_confirm'), button('Сохранить', 'bookclub:home')]]))
        return
    if call.data == 'bookclub:delete_confirm':
        await session.execute(delete(AppSetting).where(AppSetting.key.like(f'book-reflection:{user.id}:%')))
        await session.commit()
        await call.message.answer('Все личные ответы удалены.', reply_markup=_keyboard(user.book_club_subscribed))
        return
    answers = await reflection_summary(session, user)
    counts = await progress(session, user)
    await call.message.answer(f'📊 Ваш путь чтения\nПрочитано: {counts["read"]}/48\nПрактических отметок: {counts["task"]}/48\nЛичных ответов: {len(answers)}/48\n\nСравните свои первые и последние ответы: что изменилось в решениях и общении? Это обзор вашей активности, не оценка личности.', reply_markup=InlineKeyboardMarkup(inline_keyboard=[[button('Удалить мои ответы', 'bookclub:delete_answers')], [button('📚 Литература', 'bookclub:home')]]))
    for number, answer in answers[-5:]:
        await call.message.answer(f'Выпуск {number} · {get_issue(number).title}\n\n{answer}')


@router.callback_query(F.data.startswith('bookclub:'))
async def navigate(call: CallbackQuery, user: User | None, session: AsyncSession):
    parts = call.data.split(':')
    action = parts[1]
    if action == 'progress':
        if not eligible(user):
            await call.answer('Сначала завершите регистрацию.', show_alert=True)
            return
        counts = await progress(session, user)
        await call.answer()
        await call.message.answer(f'📊 Ваши отметки\nПрочитано: {counts["read"]}/48\nЗаданий выполнено: {counts["task"]}/48\n\nЭто самостоятельные отметки, не проверка знаний и не начисление баллов.', reply_markup=_keyboard(user.book_club_subscribed))
        return
    try:
        number = int(parts[2])
        if action == 'list':
            if not 0 <= number < 6:
                raise ValueError
            rows = [[button(f'{i.number}. {i.title}', f'bookclub:issue:{i.number}')] for i in ISSUES[number * 8:number * 8 + 8]]
            pages = []
            if number:
                pages.append(button('←', f'bookclub:list:{number - 1}'))
            if number < 5:
                pages.append(button('→', f'bookclub:list:{number + 1}'))
            rows += [pages, [button('📚 Литература', 'bookclub:home')]]
            await call.answer()
            await call.message.answer(f'📖 48 законов власти · страница {number + 1}/6', reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))
        elif action == 'issue':
            text = render_issue(number)
            await call.answer()
            await call.message.answer(text, parse_mode='HTML', reply_markup=issue_keyboard(number))
        elif action in {'read', 'task'}:
            if not eligible(user):
                await call.answer('Сначала завершите регистрацию.', show_alert=True)
                return
            await mark_progress(session, user, number, action)
            await call.answer('Отметка сохранена')
        else:
            raise ValueError
    except (ValueError, IndexError):
        await call.answer('Откройте актуальный каталог литературы.', show_alert=True)
