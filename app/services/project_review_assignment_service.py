"""Project reviewer ownership without changing existing project IDs or form data."""
from sqlalchemy import select

from app.database.models import AppSetting, Project
from app.services.audit_service import audit
from app.services.authorization_service import is_full_admin
from app.services.project_workspace_service import can_review_projects
from app.utils.constants import ProjectStatus


def _key(project_id):
    return f'project-reviewer:{project_id}'


async def assigned_project_reviewer(session, project_id):
    row = await session.scalar(select(AppSetting).where(AppSetting.key == _key(project_id)))
    if row is None:
        return None
    import json
    data = json.loads(row.value) if isinstance(row.value, str) else row.value
    return data.get('reviewer_id')


async def claim_project_review(session, project_id, actor, settings, *, release=False):
    project = await session.scalar(select(Project).where(Project.id == project_id)
                                   .with_for_update().execution_options(populate_existing=True))
    if project is None or not await can_review_projects(session, actor, settings, project):
        raise PermissionError('reviewer_access_required')
    if project.author_id == actor.id:
        raise PermissionError('project_self_review')
    if project.status not in {ProjectStatus.PENDING_REVIEW, ProjectStatus.INITIAL_REVIEW, ProjectStatus.VENUE_REVIEW}:
        raise ValueError('project_review_stale')
    current = await assigned_project_reviewer(session, project.id)
    if current not in {None, actor.id} and not is_full_admin(actor, settings, actor.telegram_id):
        raise PermissionError('project_review_assigned')
    reviewer_id = None if release else actor.id
    row = await session.scalar(select(AppSetting).where(AppSetting.key == _key(project.id)))
    if row is None:
        session.add(AppSetting(key=_key(project.id), value={'reviewer_id': reviewer_id}))
    else:
        row.value = {'reviewer_id': reviewer_id}
    await audit(session, actor_id=actor.id, action='project.review.assignment',
                entity_type='project', entity_id=project.id,
                old_value={'reviewer_id': current}, new_value={'reviewer_id': reviewer_id})
    await session.flush()
    return reviewer_id


async def project_review_recipients(session, project, settings):
    """Private reviewer inboxes only; no project files in the leaders' group."""
    from app.database.models import User
    from app.utils.constants import ApplicationStatus
    assigned_id = await assigned_project_reviewer(session, project.id)
    if assigned_id:
        assigned = await session.get(User, assigned_id)
        if (assigned and assigned.telegram_id > 0
                and assigned.application_status == ApplicationStatus.APPROVED
                and await can_review_projects(session, assigned, settings, project)):
            return {assigned.telegram_id}
    candidates = (await session.scalars(select(User).where(
        User.is_blocked.is_(False), User.is_archived.is_(False),
        User.application_status == ApplicationStatus.APPROVED,
    ))).all()
    recipients = {int(i) for i in settings.admin_ids if int(i) > 0}
    for candidate in candidates:
        if candidate.id != project.author_id and candidate.telegram_id > 0 and await can_review_projects(
                session, candidate, settings, project):
            recipients.add(candidate.telegram_id)
    return recipients
