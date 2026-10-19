"""Opt-in immutable ranking windows over the existing points ledger."""
from datetime import date, datetime, time, timedelta, timezone
from uuid import uuid4
from zoneinfo import ZoneInfo

from sqlalchemy import func, or_, select

from app.database.models import AppSetting, PointTransaction, User
from app.services.audit_service import audit
from app.services.authorization_service import is_full_admin
from app.services.certificate_service import _lock
from app.services.leaderboard_service import LeaderboardSnapshot, _entry
from app.utils.constants import ApplicationStatus, PointCategory

PREFIX = "ranking-season:"
RULES = "По времени начисления: сумма баллов за период, кроме цифровой активности и списаний за награды. Исправления учитываются. Позднее подтверждение относится к периоду начисления. Общий баланс сохраняется."


def now_utc():
    return datetime.now(timezone.utc)


def status(value, now=None):
    now = now or now_utc()
    if value.get("results") is not None:
        return "closed"
    if now < datetime.fromisoformat(value["starts_at"]):
        return "upcoming"
    if now >= datetime.fromisoformat(value["ends_at"]):
        return "closing"
    return "active"


async def seasons(session):
    return list((await session.scalars(select(AppSetting).where(AppSetting.key.startswith(PREFIX))
                                      .order_by(AppSetting.key))).all())


async def create_season(session, actor, settings, *, title, starts_on, ends_on):
    from app.services.staff_access_service import can_operate_queue
    if not await can_operate_queue(session, actor, settings, "settings.manage") or not is_full_admin(actor, settings, actor.telegram_id):
        raise PermissionError("Сезоны создаёт действующий администратор.")
    title = title.strip()
    if not 3 <= len(title) <= 100:
        raise ValueError("Название сезона: от 3 до 100 символов.")
    tz = ZoneInfo(settings.timezone)
    start = datetime.combine(date.fromisoformat(starts_on), time.min, tzinfo=tz).astimezone(timezone.utc)
    end = datetime.combine(date.fromisoformat(ends_on)+timedelta(days=1), time.min, tzinfo=tz).astimezone(timezone.utc)
    if end <= start or end <= now_utc() or end-start > timedelta(days=370):
        raise ValueError("Проверьте даты: окончание в будущем, продолжительность не больше года.")
    await _lock(session,"ranking-season-registry")
    for row in await seasons(session):
        if start < datetime.fromisoformat(row.value['ends_at']) and end > datetime.fromisoformat(row.value['starts_at']):
            raise ValueError("Период пересекается с существующим сезоном.")
    sid = uuid4().hex
    row = AppSetting(key=PREFIX+sid, updated_by=actor.id,
                     value=dict(id=sid,title=title,starts_at=start.isoformat(),ends_at=end.isoformat(),
                                timezone=settings.timezone,rules=RULES,results=None))
    session.add(row)
    await audit(session,actor_id=actor.id,action="ranking.season_created",entity_type="ranking_season",new_value=row.value)
    await session.flush()
    return row


async def _scores(session, value):
    start, end = datetime.fromisoformat(value['starts_at']), datetime.fromisoformat(value['ends_at'])
    points = func.sum(PointTransaction.points)
    rows=(await session.execute(select(User.id,points).join(PointTransaction,PointTransaction.user_id==User.id)
        .where(User.application_status==ApplicationStatus.APPROVED,User.is_blocked.is_(False),User.is_archived.is_(False),
               PointTransaction.created_at>=start,PointTransaction.created_at<end,
               or_(PointTransaction.category.is_(None),PointTransaction.category.not_in([
                   PointCategory.DIGITAL_ENGAGEMENT,PointCategory.REDEMPTION])))
        .group_by(User.id).having(points>0).order_by(points.desc(),User.id))).all()
    return [{"user_id":uid,"points":int(score)} for uid,score in rows]


async def finalize_season(session, row, *, now=None):
    if status(row.value,now) not in {"closing","closed"}:
        return row
    await _lock(session,row.key)
    row=await session.scalar(select(AppSetting).where(AppSetting.id==row.id).with_for_update()
                              .execution_options(populate_existing=True))
    if row.value.get('results') is None:
        row.value={**row.value,"results":await _scores(session,row.value),"closed_at":(now or now_utc()).isoformat()}
        await audit(session,actor_id=None,action="ranking.season_closed",entity_type="ranking_season",
                    new_value={"id":row.value['id'],"participants":len(row.value['results'])})
        await session.flush()
    return row


async def season_leaderboard(session, viewer, sid, *, limit=50):
    row=await session.scalar(select(AppSetting).where(AppSetting.key==PREFIX+sid))
    if row is None:
        raise ValueError("season_not_found")
    row=await finalize_season(session,row)
    scores=row.value['results'] if row.value.get('results') is not None else await _scores(session,row.value)
    ids=[r['user_id'] for r in scores]
    users=(await session.scalars(select(User).where(User.id.in_(ids or [-1]),User.application_status==ApplicationStatus.APPROVED,
                                                   User.is_blocked.is_(False),User.is_archived.is_(False)))).all()
    by_id={u.id:u for u in users}
    entries=[_entry(rank,by_id[r['user_id']],r['points'],viewer.id) for rank,r in enumerate(
        [s for s in scores if s['user_id'] in by_id],1)]
    return LeaderboardSnapshot(entries=entries[:limit],me=next((e for e in entries if e.is_you),None))


async def close_ranking_seasons(session_factory):
    async with session_factory() as session:
        for row in await seasons(session):
            if status(row.value)=="closing":
                await finalize_season(session,row)
        await session.commit()
