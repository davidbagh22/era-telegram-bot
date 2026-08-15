from __future__ import annotations

from fastapi import APIRouter

from app.api.v1 import (
    activity,
    admin,
    admin_analytics_details,
    admin_applications,
    admin_autocontent,
    admin_development,
    admin_event_create,
    admin_event_operations,
    admin_people_detail,
    admin_project_detail,
    auctions,
    auth,
    community_users,
    development,
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
api_router.include_router(community_users.router)
api_router.include_router(event_posters.router)
api_router.include_router(events.router)
api_router.include_router(tasks.router)
api_router.include_router(activity.router)
api_router.include_router(project_builder.router)
api_router.include_router(projects.router)
api_router.include_router(opportunities.router)
api_router.include_router(auctions.router)
api_router.include_router(rewards.router)
api_router.include_router(surveys.router)
api_router.include_router(development.router)
api_router.include_router(admin_development.router)
api_router.include_router(admin_applications.router)
api_router.include_router(admin_autocontent.router)
api_router.include_router(admin_analytics_details.router)
api_router.include_router(admin_people_detail.router)
api_router.include_router(admin_project_detail.router)
api_router.include_router(admin_event_create.router)
api_router.include_router(admin_event_operations.router)
api_router.include_router(admin.router)
api_router.include_router(system.router)
api_router.include_router(profile.router)
api_router.include_router(leader.router)
