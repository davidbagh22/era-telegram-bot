from __future__ import annotations

from collections.abc import Callable, Coroutine
from typing import Any

from fastapi import Depends, HTTPException, Request

from app.api.deps import get_current_user, get_settings
from app.config import Settings
from app.database.models import User
from app.services.feature_flags import Feature, feature_enabled


def require_feature(feature: Feature) -> Callable[..., Coroutine[Any, Any, None]]:
    async def dependency(
        request: Request,
        user: User = Depends(get_current_user),
        settings: Settings = Depends(get_settings),
    ) -> None:
        path = request.url.path
        # Feature flags control participant-facing rollout only. Operational
        # admin endpoints must stay available so enabled testers can still be
        # reviewed and managed while a module is OFF/TESTERS for participants.
        if path.startswith("/api/v1/admin/"):
            return
        if feature == Feature.MEDIA and (
            path.startswith("/api/v1/media/team/")
            or path.startswith("/api/v1/media/desk/")
        ):
            return
        if not feature_enabled(settings, feature, user.telegram_id):
            # Treat disabled participant modules as absent instead of leaking
            # hidden routes.
            raise HTTPException(status_code=404, detail="feature_unavailable")

    return dependency
