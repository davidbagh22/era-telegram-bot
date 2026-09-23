from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.deps import get_current_user, get_settings
from app.config import Settings
from app.database.models import User
from app.services.feature_flags import visible_features

router = APIRouter(tags=["features"])


@router.get("/features")
async def read_features(
    user: User = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
) -> dict[str, bool]:
    return visible_features(settings, user.telegram_id)
