"""One native editor for text/photo, backed by the existing event draft API."""
import hashlib
import json
import re
import secrets
from datetime import date, time
from html import escape
from io import BytesIO

from aiogram import F, Router
from aiogram.exceptions import TelegramAPIError, TelegramBadRequest
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from fastapi import HTTPException, UploadFile
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.datastructures import Headers

from app.config import Settings
from app.database.event_experience import EventExperience
from app.database.models import AppSetting, Event, User
from app.services.authorization_service import can_manage_events
from app.services.event_publication_service import announcement_text, escaped_text_parts
from app.utils.constants import EventStatus
from app.utils.validators import parse_date, parse_time

router = Router(name='native_event_quick_composer')
router.message.filter(F.chat.type == 'private')
router.callback_query.filter(F.message.chat.type == 'private')


class QuickEventStates(StatesGroup):
    input = State()


FIELDS = {'title': 'Название', 'date': 'Дата · ДД.ММ.ГГГГ', 'time': 'Время · ЧЧ:ММ',
          'location': 'Место', 'limit': 'Лимит · 0 без лимита', 'points': 'Баллы · 0–1000'}


def enabled(settings, telegram_id):
    mode = getattr(settings, 'feature_native_event_composer', 'OFF')
    return mode == 'ALL' or (mode == 'TESTERS' and telegram_id in
        (settings.native_event_composer_tester_ids or settings.feature_tester_ids))


async def guard(call, user, settings):
    if not user or user.is_blocked or user.is_archived or user.telegram_id != call.from_user.id or not enabled(settings, call.from_user.id) or not can_manage_events(user, settings, call.from_user.id):
        target = call.message if isinstance(call, CallbackQuery) else call
        if isinstance(call, CallbackQuery):
            await call.answer('Нет доступа к этой форме.', show_alert=True)
        else:
            await target.answer('Нет доступа к этой форме.')
        return False
    return True


def signature(form):
    return hashlib.sha256(json.dumps(form, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:8]


def parse_announcement(raw):
    form = {'description': raw.strip(), 'title': next((line.strip() for line in raw.splitlines() if line.strip()), '')[:255],
            }
    dates = set(re.findall(r'\b\d{1,2}\.\d{1,2}\.\d{4}\b', raw))
    times = set(re.findall(r'\b\d{1,2}:\d{2}\b', raw))
    if len(dates) == 1 and (value := parse_date(next(iter(dates)))):
        form['date'] = value.isoformat()
    if len(times) == 1 and (value := parse_time(next(iter(times)))):
        form['time'] = value.isoformat(timespec='minutes')
    location = re.search(r'^\s*(?:📍\s*|Место\s*:\s*|Локация\s*:\s*)([^\n]+)', raw, re.IGNORECASE | re.MULTILINE)
    if location:
        form['location'] = location[1].strip()[:255]
    limit = re.search(r'^\s*(?:Лимит|Мест)\s*:\s*(\d+)\s*$', raw, re.IGNORECASE | re.MULTILINE)
    if limit and int(limit[1]) <= 2147483647:
        form['limit'] = int(limit[1]) or None
    return form


def missing(form):
    return [key for key in ('title', 'description', 'date', 'time', 'location') if not form.get(key)]


def key_for(user, token):
    return f'native-event-draft:{user.id}:{token}'


async def draft_lock(session, key):
    if session.bind.dialect.name == 'postgresql':
        value = int.from_bytes(hashlib.sha256(key.encode()).digest()[:8], 'big', signed=True)
        await session.execute(text('SELECT pg_advisory_xact_lock(:key)'), {'key': value})


async def save_form(session, user, settings, bot, token, form):
    # Reuse the live draft creation, validation and image upload implementation.
    from app.api.v1.admin_event_create import (
        EventDraftCreateIn,
        EventDraftPatch,
        create_event_draft,
        save_event_draft_step,
        upload_event_poster,
    )
    key = key_for(user, token)
    await draft_lock(session, key)
    row = await session.scalar(select(AppSetting).where(AppSetting.key == key).with_for_update())
    saved = json.loads(row.value) if row else {}
    if not saved:
        draft = await create_event_draft(admin=user, session=session, payload=EventDraftCreateIn(creation_mode='quick'))
        saved = {'event_id': draft.id, 'form': {}}
        row = AppSetting(key=key, value='{}')
        session.add(row)
    event = await session.get(Event, saved['event_id'])
    if event is None or event.created_by != user.id or event.status != EventStatus.DRAFT:
        raise ValueError('draft_already_submitted')
    await save_event_draft_step(event.id, EventDraftPatch(
        creation_mode='quick', title=form.get('title') or 'Новое мероприятие',
        full_description=form.get('description', ''), short_description=form.get('description', '')[:500],
        event_date=date.fromisoformat(form['date']) if form.get('date') else None,
        event_time=time.fromisoformat(form['time']) if form.get('time') else None,
        location=form.get('location', ''), registration_required=True, participant_limit=form.get('limit'),
        points_for_visit=form.get('points', 0), attendance_mode='offline', broadcast_enabled=False, broadcast_targets=['chat'],
    ), _admin=user, session=session, settings=settings, bot=None)
    photo_id = form.get('photo')
    if photo_id and saved.get('form', {}).get('photo') != photo_id:
        image = await bot.download(photo_id)
        content = image.getvalue()
        mime = 'image/png' if content.startswith(b'\x89PNG') else 'image/jpeg'
        await upload_event_poster(event.id, file=UploadFile(file=BytesIO(content), filename='poster',
            headers=Headers({'content-type': mime})), _admin=user, session=session)
        event.poster_file_id = photo_id
    experience = await session.get(EventExperience, event.id)
    form['photo_hash'] = hashlib.sha256(experience.poster_bytes or b'').hexdigest()
    saved.update(form=form, signature=signature(form))
    row.value = json.dumps(saved, ensure_ascii=False)
    await session.commit()
    return event.id


async def show_card(message, state):
    data = await state.get_data()
    form = data.get('quick_form', {})
    ref = data['quick_token'] + '~' + signature(form)
    rows = []
    fields = list(FIELDS)
    for index in range(0, len(fields), 2):
        rows.append([InlineKeyboardButton(text=FIELDS[field], callback_data=f'leader:eventq:edit_{field}:{ref}') for field in fields[index:index+2]])
    if not missing(form):
        rows.append([InlineKeyboardButton(text='👁 Полный предпросмотр с фото', callback_data=f'leader:eventq:preview:{ref}')])
        if data.get('quick_previewed') == signature(form):
            rows.append([InlineKeyboardButton(text='✅ Подтвердить публикацию', callback_data=f'leader:eventq:publish:{ref}')])
    rows.append([InlineKeyboardButton(text='Отмена · сохранить черновик', callback_data=f'leader:eventq:cancel:{ref}')])
    body = (f"⚡ <b>Мероприятие · одна форма</b>\n\n<b>{escape(form.get('title', 'Новое мероприятие'))}</b>\n"
            + escape(form.get('description', '')[:650]) + ('…' if len(form.get('description', '')) > 650 else '')
            + f"\n\nДата: {escape(form.get('date', 'нужно указать'))} · Время: {escape(form.get('time', 'нужно указать'))}"
            + f"\nМесто: {escape(form.get('location', 'нужно указать'))}"
            + f"\nЛимит: {form.get('limit') or 'без лимита'} · Баллы: {form.get('points', 0)}"
            + f"\nФото: {'прикреплено' if form.get('photo') else 'можно прикрепить отдельным сообщением'}"
            + '\n\nМеняйте поля кнопками. Новый текст или фото обновят эту форму. Данные сохранены в черновике.')
    markup = InlineKeyboardMarkup(inline_keyboard=rows)
    if data.get('quick_card_id'):
        try:
            await message.bot.edit_message_text(chat_id=message.chat.id, message_id=data['quick_card_id'], text=body, reply_markup=markup, parse_mode='HTML')
            return
        except TelegramBadRequest as exc:
            if 'not modified' in str(exc).lower():
                return
            if 'message to edit not found' not in str(exc).lower():
                raise
    card = await message.answer(body, reply_markup=markup, parse_mode='HTML')
    await state.update_data(quick_card_id=card.message_id)


@router.callback_query(F.data == 'leader:eventq:new')
async def new_quick(call: CallbackQuery, user: User | None, settings: Settings, state: FSMContext):
    if not await guard(call, user, settings):
        return
    await call.answer()
    await state.clear()
    await state.update_data(quick_token=secrets.token_hex(8), quick_form={'points': 0, 'limit': None})
    await state.set_state(QuickEventStates.input)
    await call.message.answer('Пришлите готовый текст, фото с подписью или сначала текст, затем фото.\n\n'
        'Дату, время и место можно вставить в текст:\nДата: 07.11.2026\nВремя: 18:00\nМесто: Дом Москвы\nМест: 30\n\n'
        'После этого появится одна редактируемая карточка. /cancel сохраняет черновик.')


@router.message(QuickEventStates.input, (F.text & ~F.text.startswith('/')) | F.photo)
async def quick_input(message: Message, user: User | None, settings: Settings, session: AsyncSession, state: FSMContext):
    if not await guard(message, user, settings):
        return
    data = await state.get_data()
    form = dict(data.get('quick_form', {}))
    raw = (message.text or message.caption or '').strip()
    field = data.get('quick_edit')
    if message.photo and not raw:
        field = None
    if field:
        value = raw
        if field == 'date':
            parsed = parse_date(raw)
            value = parsed.isoformat() if parsed else None
        elif field == 'time':
            parsed = parse_time(raw)
            value = parsed.isoformat(timespec='minutes') if parsed else None
        elif field in {'limit', 'points'}:
            try:
                value = int(raw)
                if not 0 <= value <= (1000 if field == 'points' else 2147483647):
                    raise ValueError
            except ValueError:
                value = None
            if field == 'limit' and value == 0:
                value = None
                form[field] = None
                field = None
        if field and (value is None or (isinstance(value, str) and (not value or len(value) > 255))):
            await message.answer('Проверьте формат поля. Данные формы сохранены; попробуйте ещё раз.')
            return
        if field:
            form[field] = value
    elif raw:
        if len(raw) > 10000:
            await message.answer('Текст слишком длинный. Отправьте до 10 000 символов.')
            return
        parsed = parse_announcement(raw)
        form.update(parsed)
    if message.photo:
        if message.photo[-1].file_size and message.photo[-1].file_size > 5*1024*1024:
            await message.answer('Нужно фото размером до 5 МБ.')
            return
        form['photo'] = message.photo[-1].file_id
    if not raw and not message.photo:
        await message.answer('Пришлите текст или фото. Форма сохранена.')
        return
    try:
        event_id = await save_form(session, user, settings, message.bot, data['quick_token'], form)
    except (TelegramAPIError, HTTPException, ValueError):
        await session.rollback()
        await state.update_data(quick_form=form, quick_unsaved=True, quick_edit=None)
        ref = data['quick_token']+'~'+signature(form)
        await message.answer('Не удалось сохранить изменение. Ввод сохранён в форме; можно повторить сохранение.',
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='↻ Сохранить ещё раз', callback_data='leader:eventq:retry:'+ref)]]))
        return
    await state.update_data(quick_form=form, quick_edit=None, quick_event_id=event_id, quick_unsaved=False)
    await show_card(message, state)


@router.message(Command('cancel'), QuickEventStates.input)
async def cancel_quick_input(message: Message, state: FSMContext):
    """Leave the editor while keeping its durable draft available for resume."""
    await state.clear()
    await message.answer('Форма закрыта. Черновик сохранён: откройте «Мои черновики», чтобы продолжить.')


@router.callback_query(F.data == 'leader:eventq:drafts')
async def quick_drafts(call: CallbackQuery, user: User | None, settings: Settings, session: AsyncSession):
    if not await guard(call, user, settings):
        return
    await call.answer()
    rows = (await session.scalars(select(AppSetting).where(AppSetting.key.like(f'native-event-draft:{user.id}:%')).limit(20))).all()
    buttons = []
    for row in rows:
        item = json.loads(row.value)
        event = await session.get(Event, item['event_id'])
        experience = await session.get(EventExperience, item['event_id'])
        if event and (event.status == EventStatus.DRAFT or (experience and experience.announcement_status in {'pending', 'uncertain', 'needs_attention'})):
            buttons.append([InlineKeyboardButton(text=(item['form'].get('title') or 'Черновик с фото')[:50],
                            callback_data='leader:eventq:resume:'+row.key.rsplit(':', 1)[-1])])
    await call.message.answer('Выберите сохранённый черновик.' if buttons else 'Сохранённых черновиков нет.',
                              reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons) if buttons else None)


@router.callback_query(F.data.startswith('leader:eventq:resume:'))
async def quick_resume(call: CallbackQuery, user: User | None, settings: Settings, session: AsyncSession, state: FSMContext):
    if not await guard(call, user, settings):
        return
    await call.answer()
    token = call.data.rsplit(':', 1)[-1]
    if not re.fullmatch('[0-9a-f]{16}', token):
        return
    row = await session.scalar(select(AppSetting).where(AppSetting.key == key_for(user, token)))
    if row is None:
        await call.message.answer('Черновик не найден.')
        return
    saved = json.loads(row.value)
    event = await session.get(Event, saved['event_id'])
    if event is None or event.created_by != user.id:
        return
    await state.clear()
    await state.set_state(QuickEventStates.input)
    await state.update_data(quick_form=saved['form'], quick_token=token, quick_event_id=event.id)
    await show_card(call.message, state)


@router.callback_query(F.data.startswith('leader:eventq:'))
async def quick_action(call: CallbackQuery, user: User | None, settings: Settings, session: AsyncSession, state: FSMContext):
    if not await guard(call, user, settings):
        return
    parts = (call.data or '').split(':')
    data = await state.get_data()
    form = data.get('quick_form', {})
    if len(parts) != 4 or parts[3] != data.get('quick_token', '')+'~'+signature(form):
        await call.answer('Эта карточка уже обработана или обновлена. Откройте текущую форму.', show_alert=True)
        return
    action = parts[2]
    await call.answer()
    if action.startswith('edit_') and action[5:] in FIELDS:
        await state.update_data(quick_edit=action[5:])
        await call.message.answer('Введите значение: '+FIELDS[action[5:]]+'. Можно отменить ввод через /cancel.')
        return
    if action == 'cancel':
        await state.clear()
        await call.message.answer('Черновик сохранён. Его можно открыть из списка черновиков.')
        return
    if action == 'retry':
        try:
            event_id = await save_form(session, user, settings, call.bot, data['quick_token'], form)
        except (TelegramAPIError, HTTPException, ValueError):
            await session.rollback()
            await call.message.answer('Сохранение пока недоступно. Ввод остаётся в форме.')
            return
        await state.update_data(quick_form=form, quick_event_id=event_id, quick_unsaved=False)
        await show_card(call.message, state)
        return
    if data.get('quick_unsaved'):
        await call.message.answer('Сначала сохраните изменения кнопкой «Сохранить ещё раз».')
        return
    key = key_for(user, data['quick_token'])
    await draft_lock(session, key)
    row = await session.scalar(select(AppSetting).where(AppSetting.key == key).with_for_update())
    saved = json.loads(row.value) if row else {}
    if saved.get('signature') != signature(form) or missing(form):
        await call.message.answer('Черновик изменился. Обновите форму перед публикацией.')
        return
    event = await session.scalar(select(Event).where(Event.id == saved['event_id']).with_for_update())
    if event is None or event.created_by != user.id:
        return
    experience = await session.get(EventExperience, event.id)
    if (event.title != form['title'] or event.description != form['description'] or
        event.event_date.isoformat() != form['date'] or event.event_time.isoformat(timespec='minutes') != form['time'] or
        event.location != form['location'] or event.participant_limit != form.get('limit') or
        event.points_for_visit != form.get('points', 0) or
        hashlib.sha256(experience.poster_bytes or b'').hexdigest() != form.get('photo_hash')):
        await call.message.answer('Черновик изменён в другом окне. Откройте его заново, чтобы проверить данные.')
        return
    if action == 'preview':
        from aiogram.types import BufferedInputFile
        poster = BufferedInputFile(experience.poster_bytes, filename='poster') if experience.poster_bytes else None
        for index, part in enumerate(escaped_text_parts(announcement_text(event, experience), 1000 if poster else 4000)):
            if index == 0 and poster:
                await call.message.answer_photo(poster, caption=part, parse_mode='HTML')
            else:
                await call.message.answer(part, parse_mode='HTML')
        await session.commit()
        await state.update_data(quick_previewed=signature(form))
        await show_card(call.message, state)
    elif action == 'publish' and data.get('quick_previewed') == signature(form):
        from app.api.v1.admin_event_create import publish_event
        try:
            outcome = await publish_event(event.id, admin=user, session=session, settings=settings, bot=call.bot)
        except HTTPException:
            await session.rollback()
            await call.message.answer('Публикация не подтверждена. Черновик сохранён; проверьте поля формы.')
            return
        if outcome.announcement_status == 'sent':
            await state.clear()
            await call.message.answer(f'✅ Мероприятие #{event.id} опубликовано. Регистрация открыта.')
        else:
            await call.message.answer(f'Мероприятие #{event.id} сохранено. Доставка анонса пока не подтверждена. Повторная проверка использует это же событие.')
