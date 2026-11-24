"""Reading shares the bot's archive bounds, membership and subscription."""
from dataclasses import asdict
import re
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.deps import get_current_user, get_session, get_settings
from app.config import Settings
from app.content.literature_issues import get_issue
from app.database.models import User
from app.services.book_club_service import eligible, last_readable_issue_number
from app.services.game_room_presenter import GAME_CARDS, MODE_LABELS

router = APIRouter(tags=["leisure"])


def require_reader(user: User) -> None:
    if not eligible(user):
        raise HTTPException(403, "approved_membership_required")


@router.get("/literature")
async def literature_catalog(user: User = Depends(get_current_user)):
    require_reader(user)
    latest = last_readable_issue_number()
    return {"latest": latest, "subscribed": bool(user.book_club_subscribed),
            "items": [{"number": n, "title": get_issue(n).title} for n in range(latest, 0, -1)]}


@router.get("/literature/{number}")
async def literature_issue(number: int, user: User = Depends(get_current_user)):
    require_reader(user)
    if not 1 <= number <= last_readable_issue_number():
        raise HTTPException(404, "issue_not_available")
    return asdict(get_issue(number))


class SubscriptionIn(BaseModel):
    subscribed: bool


@router.patch("/literature-subscription")
async def literature_subscription(body: SubscriptionIn, user: User = Depends(get_current_user),
                                  session: AsyncSession = Depends(get_session)):
    require_reader(user)
    user.book_club_subscribed = body.subscribed
    await session.commit()
    return {"subscribed": bool(user.book_club_subscribed)}


@router.get("/leisure/games")
async def games_catalog(user: User = Depends(get_current_user), settings: Settings = Depends(get_settings)):
    require_reader(user)
    enabled = settings.feature_games == "ALL" or (
        settings.feature_games == "TESTERS" and user.telegram_id in settings.feature_tester_ids)
    username = settings.bot_username or "ERA_1bot"
    if not re.fullmatch(r"[A-Za-z0-9_]+", username):
        username = "ERA_1bot"
    return {"enabled": enabled,
            "launch_url": f"https://t.me/{username}?start=games" if enabled else None,
            "items": [{"id": key, "title": MODE_LABELS[key].split(" ", 1)[-1], **meta}
                      for key, meta in GAME_CARDS.items()] if enabled else []}
