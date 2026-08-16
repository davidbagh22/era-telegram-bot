from __future__ import annotations

from fastapi import APIRouter

from app.api.v1 import (
    activity,
    admin,
    admin_analytics_details,
    admin_applications,
    admin_autocontent,
    admin_career,
    admin_development,
    admin_event_attendance,
    admin_event_create,
    admin_event_operations,
    admin_people_detail,
    admin_project_detail,
    auctions,
    auth,
    career,
    community_users,
    development,
    event_attendance,
    event_posters,
    events,
    home,
    leader,
    leaderboard,
    me,
    opportunities,
    profile,
    project_builder,
    projects,
    referrals,
    rewards,
    surveys,
    system,
    tasks,
)

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(auth.router)
api_router.include_router(me.router)
api_router.include_router(home.router)
api_router.include_router(development.router)
api_router.include_router(career.router)
api_router.include_router(referrals.router)
api_router.include_router(leaderboard.router)
api_router.include_router(community_users.router)
api_router.include_router(event_posters.router)
api_router.include_router(event_attendance.router)
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
# Career evidence/recommendation review owns dedicated routes and enforces the
# portfolio.review capability without widening the legacy admin surface.
api_router.include_router(admin_career.router)
# Development summaries and aggregate analytics have their own privacy gate
# and audit trail; register them before the large legacy admin router.
api_router.include_router(admin_development.router)
# Exact analytics drill-down lists are registered before the large legacy
# admin router so /admin/analytics/details/{section} cannot be shadowed.
api_router.include_router(admin_analytics_details.router)
# Full participant intelligence card must own GET /admin/users/{id}; legacy
# admin.py keeps the mutation endpoints and their compact response models.
api_router.include_router(admin_people_detail.router)
# Full project review detail is also registered before the large admin router
# so reviewers can inspect the complete submitted form before deciding.
api_router.include_router(admin_project_detail.router)
# Rich event creator/operations are registered before the legacy admin router.
# Attendance lifecycle/code endpoints are kept before the large admin router
# so start/completion and confirmation-code state cannot be shadowed.
api_router.include_router(admin_event_create.router)
api_router.include_router(admin_event_operations.router)
api_router.include_router(admin_event_attendance.router)
api_router.include_router(admin.router)
api_router.include_router(system.router)
api_router.include_router(profile.router)
api_router.include_router(leader.router)
