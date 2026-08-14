from __future__ import annotations

from fastapi import APIRouter

from app.api.v1 import (
    activity,
    admin,
    admin_applications,
    auctions,
    auth,
    events,
    home,
    leader,
    leaderboard,
    me,
    opportunities,
    profile,
    projects,
    rewards,
    surveys,
    system,
    tasks,
)

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(auth.router)
api_router.include_router(me.router)
api_router.include_router(home.router)
api_router.include_router(leaderboard.router)
api_router.include_router(events.router)
api_router.include_router(tasks.router)
api_router.include_router(activity.router)
api_router.include_router(projects.router)
api_router.include_router(opportunities.router)
api_router.include_router(auctions.router)
api_router.include_router(rewards.router)
api_router.include_router(surveys.router)
# Full registration read-model must be registered before admin.router because
# the legacy admin module still contains the compact GET /admin/applications
# endpoint. FastAPI resolves matching routes in registration order. Decision
# POST endpoints continue to live in admin.router.
api_router.include_router(admin_applications.router)
api_router.include_router(admin.router)
api_router.include_router(system.router)
api_router.include_router(profile.router)
api_router.include_router(leader.router)
