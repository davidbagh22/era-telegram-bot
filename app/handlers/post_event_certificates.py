"""Owner screen for post-event certificates: choose people, confirm once, check delivery."""
from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from app.database.models import Event
from app.services import post_event_certificate_service as service

router = Router(name="post_event_certificates")
router.message.filter(F.chat.type == "private")
router.callback_query.filter(F.message.chat.type == "private")

PAGE_SIZE = 8
LIST_PAGE_SIZE = 10
DENIED = "Нет доступа к выдаче сертификатов по этому мероприятию."


def _button(text: str, data: str) -> InlineKeyboardButton:
    return InlineKeyboardButton(text=text[:64], callback_data=data)


async def _show(call: CallbackQuery, text: str, markup: InlineKeyboardMarkup | None) -> None:
    try:
        await call.message.edit_text(text, reply_markup=markup)
    except TelegramBadRequest as exc:
        if "message is not modified" not in str(exc):
            await call.message.answer(text, reply_markup=markup)


def _label(person: service.Candidate, selected: bool) -> str:
    if person.certificate_status == "issued":
        mark, suffix = "🎓", " · выдан"
    elif person.certificate_status == "revoked":
        mark, suffix = "🚫", " · отозван"
    elif not person.eligible:
        mark, suffix = "🚫", " · недоступен"
    else:
        mark, suffix = ("☑️" if selected else "⬜"), (" · был(а)" if person.attended else "")
    return f"{mark} {person.name[:40]}{suffix}"


async def render_review(session, event: Event, page: int = 0):
    review = await service.load_review(session, event.id)
    people = await service.candidates(session, event.id)
    value = review.value if review else {}
    selected = set(value.get("selected") or [])
    selectable = [p for p in people if p.selectable]
    chosen = [p for p in selectable if p.user_id in selected]
    attended = sum(1 for p in people if p.attended)
    issued = sum(1 for p in people if p.certificate_status == "issued")
    lines = [f"🎓 {event.title[:200]}", f"{event.event_date:%d.%m.%Y}",
             f"Зарегистрировались: {len(people)} · отметили присутствие: {attended}",
             f"Сертификат уже выдан: {issued} · выбрано сейчас: {len(chosen)}"]
    if value.get("state") == "dismissed":
        lines.append("\nЗапрос скрыт из списка. Его можно вернуть.")
    lines.append("\nНажмите на участника, чтобы отметить или снять отметку. "
                 "«был(а)» — присутствие подтверждено. Участникам ничего не отправится до подтверждения.")
    pages = max(1, (len(people) + PAGE_SIZE - 1) // PAGE_SIZE)
    page = min(max(page, 0), pages - 1)
    rows = [[_button(_label(p, p.user_id in selected), f"pec:t:{event.id}:{p.user_id}:{page}")]
            for p in people[page * PAGE_SIZE:(page + 1) * PAGE_SIZE]]
    nav = []
    if page > 0:
        nav.append(_button("←", f"pec:v:{event.id}:{page - 1}"))
    if page + 1 < pages:
        nav.append(_button("→", f"pec:v:{event.id}:{page + 1}"))
    if nav:
        rows.append(nav)
    if selectable:
        rows.append([_button("Выбрать всех", f"pec:a:{event.id}:{page}"),
                     _button("Снять все", f"pec:n:{event.id}:{page}")])
        if any(p.attended for p in selectable):
            rows.append([_button("Только отметившиеся", f"pec:p:{event.id}:{page}")])
    if chosen:
        rows.append([_button(f"🎓 Выдать выбранным ({len(chosen)})", f"pec:c:{event.id}")])
    rows.append([_button("📬 Статус отправки", f"pec:s:{event.id}")])
    if value.get("state") == "dismissed":
        rows.append([_button("Вернуть в список", f"pec:r:{event.id}")])
    else:
        rows.append([_button("Скрыть запрос", f"pec:x:{event.id}")])
    return "\n".join(lines), InlineKeyboardMarkup(inline_keyboard=rows)


async def _event_for(call: CallbackQuery, session, user, settings, event_id: int) -> Event | None:
    event = await session.get(Event, event_id)
    if not await service.can_review(session, user, settings, event):
        await call.answer(DENIED, show_alert=True)
        return None
    return event


async def _list_markup(session, user, settings, offset: int, hidden: bool):
    reviews = await service.list_reviews(session, user, settings, hidden=hidden)
    flag = "h" if hidden else "o"
    rows = []
    for event, value in reviews[offset:offset + LIST_PAGE_SIZE]:
        waiting = len(value.get("selected") or [])
        rows.append([_button(f"{event.event_date:%d.%m} • {event.title[:40]}" + (f" · {waiting}" if waiting else ""),
                             f"pec:v:{event.id}:0")])
    nav = []
    if offset:
        nav.append(_button("←", f"pec:l:{max(0, offset - LIST_PAGE_SIZE)}:{flag}"))
    if len(reviews) > offset + LIST_PAGE_SIZE:
        nav.append(_button("→", f"pec:l:{offset + LIST_PAGE_SIZE}:{flag}"))
    if nav:
        rows.append(nav)
    rows.append([_button("Открытые запросы", "pec:l:0:o") if hidden else _button("Скрытые запросы", "pec:l:0:h")])
    if hidden:
        text = "Скрытые запросы на сертификаты." if reviews else "Скрытых запросов нет."
    else:
        text = ("Прошедшие мероприятия: выберите, кому выдать сертификат." if reviews
                else "Открытых запросов на выдачу сертификатов нет.")
    return text, InlineKeyboardMarkup(inline_keyboard=rows)


@router.message(Command("event_certificates"))
async def review_list(message: Message, user, session, settings):
    text, markup = await _list_markup(session, user, settings, 0, False)
    await message.answer(text, reply_markup=markup)


@router.callback_query(F.data.regexp(r"^pec:l:\d{1,5}:[oh]$"))
async def review_list_page(call: CallbackQuery, user, session, settings):
    _, _, offset, flag = call.data.split(":")
    text, markup = await _list_markup(session, user, settings, int(offset), flag == "h")
    await call.answer()
    await _show(call, text, markup)


@router.callback_query(F.data.regexp(r"^pec:v:\d+:\d{1,4}$"))
async def review_view(call: CallbackQuery, user, session, settings):
    _, _, event_id, page = call.data.split(":")
    event = await _event_for(call, session, user, settings, int(event_id))
    if event is None:
        return
    if await service.load_review(session, event.id) is None:
        await call.answer("Запрос для этого мероприятия не найден.", show_alert=True)
        return
    await call.answer()
    await _show(call, *await render_review(session, event, int(page)))


async def _apply(call: CallbackQuery, session, user, settings, event_id: int, page: int, mode: str,
                 target: int | None = None) -> None:
    try:
        await service.change_selection(session, user, settings, event_id, mode, target)
        await session.commit()
    except PermissionError:
        await call.answer(DENIED, show_alert=True)
        return
    except service.ReviewError as exc:
        await call.answer(str(exc), show_alert=True)
        return
    await call.answer()
    await _show(call, *await render_review(session, await session.get(Event, event_id), page))


@router.callback_query(F.data.regexp(r"^pec:t:\d+:\d+:\d{1,4}$"))
async def review_toggle(call: CallbackQuery, user, session, settings):
    _, _, event_id, target, page = call.data.split(":")
    await _apply(call, session, user, settings, int(event_id), int(page), "toggle", int(target))


@router.callback_query(F.data.regexp(r"^pec:[anp]:\d+:\d{1,4}$"))
async def review_bulk(call: CallbackQuery, user, session, settings):
    _, code, event_id, page = call.data.split(":")
    mode = {"a": "all", "n": "none", "p": "attended"}[code]
    await _apply(call, session, user, settings, int(event_id), int(page), mode)


@router.callback_query(F.data.regexp(r"^pec:c:\d+$"))
async def review_ask_confirm(call: CallbackQuery, user, session, settings):
    event = await _event_for(call, session, user, settings, int(call.data.rsplit(":", 1)[-1]))
    if event is None:
        return
    review = await service.load_review(session, event.id)
    selected = set((review.value if review else {}).get("selected") or [])
    chosen = [p for p in await service.candidates(session, event.id) if p.selectable and p.user_id in selected]
    if not chosen:
        await call.answer("Никто не выбран.", show_alert=True)
        return
    await call.answer()
    names = "\n".join(f"• {p.name}" for p in chosen[:15])
    if len(chosen) > 15:
        names += f"\n… и ещё {len(chosen) - 15}"
    text = (f"Выдать сертификаты: {len(chosen)}\n{event.title[:200]}\n\n{names}\n\n"
            "Каждый получит PDF в чат с ботом, документ появится в профиле. "
            "Повторное нажатие второй раз не отправит.")
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [_button("✅ Подтвердить выдачу", f"pec:ok:{event.id}:{review.value.get('rev') or 0}")],
        [_button("← К списку", f"pec:v:{event.id}:0")],
    ])
    await _show(call, text, markup)


@router.callback_query(F.data.regexp(r"^pec:ok:\d+:\d{1,9}$"))
async def review_confirm(call: CallbackQuery, user, session, settings):
    _, _, event_id, rev = call.data.split(":")
    try:
        result = await service.confirm(session, user, settings, int(event_id), int(rev))
        await session.commit()
    except PermissionError:
        await call.answer(DENIED, show_alert=True)
        return
    except service.ReviewError as exc:
        await call.answer(str(exc), show_alert=True)
        return
    await call.answer("Готово")
    lines = [f"Выдано сертификатов: {len(result.issued)}."]
    if result.already:
        lines.append(f"Уже были выданы раньше: {len(result.already)} — повторно не отправляются.")
    if result.skipped:
        lines.append(f"Пропущено: {len(result.skipped)} (участник недоступен): " + ", ".join(result.skipped[:10]))
    if result.issued:
        lines.append("PDF уходят участникам в фоне, по одному разу. Документы уже в их профиле.")
    markup = InlineKeyboardMarkup(inline_keyboard=[[_button("📬 Статус отправки", f"pec:s:{event_id}")],
                                                   [_button("← К списку", f"pec:v:{event_id}:0")]])
    await _show(call, "\n".join(lines), markup)


@router.callback_query(F.data.regexp(r"^pec:s:\d+$"))
async def review_delivery(call: CallbackQuery, user, session, settings):
    event = await _event_for(call, session, user, settings, int(call.data.rsplit(":", 1)[-1]))
    if event is None:
        return
    await call.answer()
    summary = await service.delivery_summary(session, event.id)
    lines = [f"📬 Отправка сертификатов\n{event.title[:200]}", "",
             f"Доставлено: {summary.sent}", f"В очереди: {summary.pending}"]
    if summary.attention:
        lines.append(f"Не доставлено: {len(summary.attention)} — повторно автоматически не отправляется, "
                     "участник может скачать документ через /certificates: " + ", ".join(summary.attention[:10]))
    if summary.skipped:
        lines.append(f"Пропущено (аккаунт недоступен): {summary.skipped}")
    if summary.not_queued:
        lines.append(f"Выданы без отправки в чат: {summary.not_queued}")
    markup = InlineKeyboardMarkup(inline_keyboard=[[_button("Обновить", f"pec:s:{event.id}")],
                                                   [_button("← К списку", f"pec:v:{event.id}:0")]])
    await _show(call, "\n".join(lines), markup)


@router.callback_query(F.data.regexp(r"^pec:[xr]:\d+$"))
async def review_hide(call: CallbackQuery, user, session, settings):
    _, code, event_id = call.data.split(":")
    try:
        await service.set_hidden(session, user, settings, int(event_id), code == "x")
        await session.commit()
    except PermissionError:
        await call.answer(DENIED, show_alert=True)
        return
    except service.ReviewError as exc:
        await call.answer(str(exc), show_alert=True)
        return
    await call.answer("Скрыто" if code == "x" else "Возвращено")
    await _show(call, *await render_review(session, await session.get(Event, int(event_id))))
