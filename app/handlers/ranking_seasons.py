from datetime import date
from uuid import uuid4

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from app.handlers.certificates import kb
from app.services import ranking_season_service as service
from app.services.staff_access_service import can_operate_queue
from app.utils.constants import ApplicationStatus

router=Router(name="ranking_seasons")
router.message.filter(F.chat.type=="private")
router.callback_query.filter(F.message.chat.type=="private")


class SeasonFlow(StatesGroup):
    definition=State()
    confirm=State()


async def show(message,user,session,settings):
    if not user or user.application_status!=ApplicationStatus.APPROVED or user.is_blocked or user.is_archived:
        return
    rows=sorted(await service.seasons(session),key=lambda r:r.value['starts_at'],reverse=True)
    buttons=[(r.value['title'],f"season:view:{r.value['id']}") for r in rows[:30]]
    from app.services.authorization_service import is_full_admin
    if is_full_admin(user,settings,user.telegram_id):
        buttons.append(("Создать сезон","season:new"))
    await message.answer("Сезоны рейтинга\n\n"+("Выберите период." if rows else "Сезоны пока не объявлены. Общий рейтинг и баланс продолжают работать."),reply_markup=kb(buttons))


@router.message(Command("seasons"))
async def season_list(message:Message,user,session,settings):
    await show(message,user,session,settings)


@router.callback_query(F.data=="season:list")
async def season_list_callback(call:CallbackQuery,user,session,settings):
    await call.answer()
    await show(call.message,user,session,settings)


@router.callback_query(F.data.regexp(r"^season:view:[a-f0-9]{32}$"))
async def view(call:CallbackQuery,user,session):
    await call.answer()
    if not user or user.application_status!=ApplicationStatus.APPROVED or user.is_blocked or user.is_archived:
        return
    sid=call.data.rsplit(":",1)[-1]
    from sqlalchemy import select
    from app.database.models import AppSetting
    row=await session.scalar(select(AppSetting).where(AppSetting.key==service.PREFIX+sid))
    if not row:
        await call.message.answer("Сезон не найден.")
        return
    board=await service.season_leaderboard(session,user,sid,limit=10)
    await session.commit()
    text=row.value['title']+"\n\n"+row.value['rules']+"\n\n"+'\n'.join(f"{e.rank}. {e.display_name} • {e.points}" for e in board.entries)
    if board.me:
        text+=f"\n\nВаше место: {board.me.rank} • {board.me.points} баллов"
    await call.message.answer(text,parse_mode=None)


@router.callback_query(F.data=="season:new")
async def new(call:CallbackQuery,user,session,settings,state:FSMContext):
    await call.answer()
    from app.services.authorization_service import is_full_admin
    if not await can_operate_queue(session,user,settings,"settings.manage") or not is_full_admin(user,settings,user.telegram_id):
        return
    await state.set_state(SeasonFlow.definition)
    await call.message.answer("Название | первый день | последний день\nНапример: Зимний сезон | 2026-12-01 | 2027-02-28\n\nОба дня включены, часовой пояс "+settings.timezone+". Правила и даты будут зафиксированы после подтверждения. /cancel - отменить.")


@router.message(SeasonFlow.definition)
async def definition(message:Message,user,session,settings,state:FSMContext):
    if not await can_operate_queue(session,user,settings,"settings.manage"):
        await state.clear();return
    parts=[p.strip() for p in (message.text or '').split('|')]
    try:
        if len(parts)!=3 or not 3<=len(parts[0])<=100 or date.fromisoformat(parts[2])<date.fromisoformat(parts[1]):
            raise ValueError()
    except ValueError:
        await message.answer("Проверьте формат: название | ГГГГ-ММ-ДД | ГГГГ-ММ-ДД")
        return
    key=uuid4().hex
    await state.update_data(season_parts=parts,season_key=key)
    await state.set_state(SeasonFlow.confirm)
    await message.answer(f"{parts[0]}\n{parts[1]} - {parts[2]} включительно\n{settings.timezone}\n\n{service.RULES}\n\nПосле конца рейтинг замораживается; общий баланс не обнуляется. Подтверждением вы утверждаете эти правила.",
                         parse_mode=None,reply_markup=kb([("Утвердить сезон",f"season:confirm:{key}")]))


@router.callback_query(F.data.regexp(r"^season:confirm:[a-f0-9]{32}$"))
async def confirm(call:CallbackQuery,user,session,settings,state:FSMContext):
    await call.answer()
    data=await state.get_data()
    if data.get('season_key')!=call.data.rsplit(':',1)[-1]:
        await call.message.answer("Предпросмотр устарел. Откройте /seasons заново.")
        return
    try:
        title,start,end=data['season_parts']
        await service.create_season(session,user,settings,title=title,starts_on=start,ends_on=end)
        await session.commit()
    except (ValueError,PermissionError) as exc:
        await call.message.answer(str(exc),parse_mode=None);return
    await state.clear()
    await call.message.answer("Сезон утверждён. Доступен в /seasons и в рейтинге приложения.")
