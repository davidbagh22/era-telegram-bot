from __future__ import annotations

from fastapi import APIRouter

from app.api.v1 import activity, auth, events, home, me, opportunities, projects, tasks

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(auth.router)
api_router.include_router(me.router)
api_router.include_router(home.router)
api_router.include_router(events.router)
api_router.include_router(tasks.router)
api_router.include_router(activity.router)
api_router.include_router(projects.router)
api_router.include_router(opportunities.router)
