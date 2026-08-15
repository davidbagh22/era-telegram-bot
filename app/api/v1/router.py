from __future__ import annotations

from fastapi import APIRouter

from app.api.v1 import (
    activity,
    admin,
    admin_analytics_details,
    admin_applications,
    admin_autocontent,
    admin_event_create,
    admin_event_operations,
    admin_project_detail,
    auctions,
    auth,
    events,
    home,
    leader,
    leaderboard,
    me,
    opportunities,
    profile,
    project_builder,
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
api_router.include_router(project_builder.router)
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
api_router.include_router(admin_autocontent.router)
# Exact analytics drill-down lists are registered before the large legacy
# admin router so /admin/analytics/details/{section} cannot be shadowed.
api_router.include_router(admin_analytics_details.router)
# Full project review detail is also registered before the large admin router
# so reviewers can inspect the complete submitted form before deciding.
api_router.include_router(admin_project_detail.router)
# Rich event creator/operations are registered before the legacy admin router.
# This lets the new participant read-model and secure participant exports own
# the exact paths while old moderation/attendance actions remain compatible.
api_router.include_router(admin_event_create.router)
api_router.include_router(admin_event_operations.router)
api_router.include_router(admin.router)
api_router.include_router(system.router)
api_router.include_router(profile.router)
api_router.include_router(leader.router)
