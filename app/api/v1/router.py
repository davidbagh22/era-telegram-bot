from __future__ import annotations

from fastapi import APIRouter

from app.api.v1 import (
    activity,
    admin,
    admin_analytics_details,
    admin_application_decisions,
    admin_applications,
    admin_autocontent,
    admin_career,
    admin_development,
    admin_drilldown,
    admin_event_attendance,
    admin_event_create,
    admin_event_operations,
    admin_executive_export,
    admin_participation,
    admin_people_detail,
    admin_project_detail,
    admin_verification,
    auctions,
    auth,
    career,
    community_users,
    development,
    engagement,
    era_pro,
    event_attendance,
    event_posters,
    events,
    home,
    leader,
    leaderboard,
    leadership,
    me,
    media,
    media_extras,
    media_rich_publish,
    opportunities,
    participation,
    positions,
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
api_router.include_router(participation.router)
api_router.include_router(engagement.router)
api_router.include_router(development.router)
api_router.include_router(career.router)
api_router.include_router(referrals.router)
api_router.include_router(era_pro.router)
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
# Must precede media.router because it intentionally owns the same publish-now
# path and adapts only the Telegram rendering step; the original Media Desk
# router still owns every other endpoint.
api_router.include_router(media_rich_publish.router)
api_router.include_router(media.router)
api_router.include_router(media_extras.router)
api_router.include_router(auctions.router)
api_router.include_router(rewards.router)
api_router.include_router(surveys.router)
api_router.include_router(admin_applications.router)
api_router.include_router(admin_application_decisions.router)
api_router.include_router(admin_autocontent.router)
api_router.include_router(admin_career.router)
api_router.include_router(admin_development.router)
api_router.include_router(admin_analytics_details.router)
api_router.include_router(admin_drilldown.router)
api_router.include_router(admin_executive_export.router)
api_router.include_router(admin_participation.router)
api_router.include_router(admin_people_detail.router)
api_router.include_router(admin_project_detail.router)
api_router.include_router(admin_verification.router)
api_router.include_router(admin_event_create.router)
api_router.include_router(admin_event_operations.router)
api_router.include_router(admin_event_attendance.router)
api_router.include_router(admin.router)
api_router.include_router(system.router)
api_router.include_router(profile.router)
api_router.include_router(leader.router)
api_router.include_router(leadership.router)
api_router.include_router(positions.router)
