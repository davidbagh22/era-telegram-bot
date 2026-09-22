from __future__ import annotations

from collections.abc import Callable, Coroutine
from typing import Any

from fastapi import Depends, HTTPException

from app.api.deps import get_current_user, get_settings
from app.config import Settings
from app.database.models import User
from app.services.feature_flags import Feature, feature_enabled


def require_feature(feature: Feature) -> Callable[..., Coroutine[Any, Any, None]]:
    async def dependency(
        user: User = Depends(get_current_user),
        settings: Settings = Depends(get_settings),
    ) -> None:
        if not feature_enabled(settings, feature, user.telegram_id):
            # Treat disabled modules as absent instead of leaking hidden routes.
            raise HTTPException(status_code=404, detail="feature_unavailable")

    return dependency
