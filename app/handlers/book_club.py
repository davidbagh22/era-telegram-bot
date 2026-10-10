from aiogram import F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.content.literature_issues import ISSUES, render_issue
from app.database.models import User
from app.services.book_club_service import eligible, mark_progress, progress

router = Router(name='book_club')
router.message.filter(F.chat.type == 'private')
router.callback_query.filter(F.message.chat.type == 'private')


def button(text, callback):
    return InlineKeyboardButton(text=text, callback_data=callback)


def _keyboard(subscribed: bool = False, discussion_url: str = '') -> InlineKeyboardMarkup:
    rows = [[button('📖 Читать · 48 законов власти', 'bookclub:list:0')],
            [button('📊 Мой прогресс', 'bookclub:progress')],
            [button('🔕 Отписаться' if subscribed else '🔔 Подписаться',
                    'bookclub:unsubscribe' if subscribed else 'bookclub:subscribe')]]
    if discussion_url:
        rows.append([InlineKeyboardButton(text='💬 Обсуждение в сообществе', url=discussion_url)])
    rows.append([button('🏠 Главное меню', 'menu:main')])
    return InlineKeyboardMarkup(inline_keyboard=rows)


AUDIOBOOK_PARTS = (
    'https://www.litres.ru/audiobook/robert-grin/48-zakonov-vlasti-zakony-1-16-8337924/',
    'https://www.litres.ru/audiobook/robert-grin/48-zakonov-vlasti-zakony-17-32-8486701/',
    'https://www.litres.ru/audiobook/robert-grin/48-zakonov-vlasti-zakony-33-48-8645049/',
)


def issue_keyboard(number: int) -> InlineKeyboardMarkup:
    nav = []
    if number > 1:
        nav.append(button('← Предыдущий', f'bookclub:issue:{number - 1}'))
    if number < 48:
        nav.append(button('Следующий →', f'bookclub:issue:{number + 1}'))
    return InlineKeyboardMarkup(inline_keyboard=[
        [button('✅ Прочитано', f'bookclub:read:{number}'), button('📝 Задание выполнено', f'bookclub:task:{number}')],
        [InlineKeyboardButton(text='🎧 Аудиокнига · Литрес', url=AUDIOBOOK_PARTS[(number - 1) // 16])],
        nav, [button('← Все выпуски', f'bookclub:list:{(number - 1) // 8}')],
        [button('📚 Литература', 'bookclub:home'), button('🔕 Отписаться', 'bookclub:unsubscribe')],
        [button('🏠 Главное меню', 'menu:main')],
    ])


async def show_home(message: Message, user: User | None, settings: Settings):
    await message.answer(
        '📚 ЭРА | Литература\n\nНачинаем с книги Роберта Грина «48 законов власти». '
        'Все 48 авторских критических разборов доступны для чтения. '
        'Это не текст книги и не безусловные советы по манипуляции.\n\n'
        'Рассылка по подписке: три выпуска в неделю (понедельник, среда, пятница) '
        'в 19:00 по Еревану, начиная с 12 октября 2026 года. '
        'Пропущенные выпуски можно открыть в каталоге. '
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
        '✅ Подписка включена. Выпуски приходят по понедельникам, средам и пятницам в 19:00 по Еревану.' if subscribed
        else '🔕 Подписка отключена. Новых рассылок не будет. История чтения сохранена.',
        reply_markup=_keyboard(subscribed),
    )


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
