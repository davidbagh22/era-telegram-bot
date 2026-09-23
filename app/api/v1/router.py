from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.feature_gate import require_feature
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
    admin_partner_edit,
    admin_participation,
    admin_people_detail,
    admin_project_detail,
    admin_recruitment,
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
    features,
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
from app.services.feature_flags import Feature

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(auth.router)
api_router.include_router(me.router)
api_router.include_router(features.router)
api_router.include_router(home.router)
api_router.include_router(participation.router)
api_router.include_router(engagement.router)
api_router.include_router(development.router, dependencies=[Depends(require_feature(Feature.VECTOR))])
api_router.include_router(career.router)
api_router.include_router(referrals.router, dependencies=[Depends(require_feature(Feature.REFERRALS))])
# ERA PRO contains both participant and admin operations. Participant-only
# endpoints enforce the flag inside era_pro.py so operational review remains
# available during OFF/TESTERS rollouts.
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
# require_feature deliberately exempts /media/team/* and /media/desk/*, so
# participant Media Hub routes respect rollout flags without disabling the
# operational desk used to manage enabled testers and content.
api_router.include_router(media_rich_publish.router)
api_router.include_router(media.router, dependencies=[Depends(require_feature(Feature.MEDIA))])
api_router.include_router(media_extras.router, dependencies=[Depends(require_feature(Feature.MEDIA))])
api_router.include_router(auctions.router, dependencies=[Depends(require_feature(Feature.AUCTIONS))])
api_router.include_router(rewards.router, dependencies=[Depends(require_feature(Feature.REWARDS))])
api_router.include_router(surveys.router, dependencies=[Depends(require_feature(Feature.SURVEYS))])
api_router.include_router(admin_applications.router)
api_router.include_router(admin_application_decisions.router)
api_router.include_router(admin_autocontent.router)
api_router.include_router(admin_career.router)
api_router.include_router(admin_development.router)
api_router.include_router(admin_analytics_details.router)
api_router.include_router(admin_drilldown.router)
api_router.include_router(admin_executive_export.router)
api_router.include_router(admin_partner_edit.router)
api_router.include_router(admin_participation.router)
api_router.include_router(admin_people_detail.router)
api_router.include_router(admin_project_detail.router)
api_router.include_router(admin_recruitment.router)
api_router.include_router(admin_verification.router)
api_router.include_router(admin_event_create.router)
api_router.include_router(admin_event_operations.router)
api_router.include_router(admin_event_attendance.router)
api_router.include_router(admin.router)
api_router.include_router(system.router)
api_router.include_router(profile.router)
api_router.include_router(leader.router)
api_router.include_router(leadership.router)
api_router.include_router(positions.router, dependencies=[Depends(require_feature(Feature.ROLE_RECRUITMENT))])
