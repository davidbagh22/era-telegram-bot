"""Project reviewer ownership without changing existing project IDs or form data."""
from sqlalchemy import or_, select

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


async def active_project_reviewer(session, project, settings):
    """A revoked owner leaves a historical assignment, not a queue lock."""
    from app.database.models import User
    reviewer_id = await assigned_project_reviewer(session, project.id)
    if reviewer_id is None or reviewer_id == project.author_id:
        return None
    reviewer = await session.get(User, reviewer_id, populate_existing=True)
    if reviewer and await can_review_projects(session, reviewer, settings, project):
        return reviewer_id
    return None


async def claim_project_review(session, project_id, actor, settings, *, release=False):
    project = await session.scalar(select(Project).where(Project.id == project_id)
                                   .with_for_update().execution_options(populate_existing=True))
    if project is None or not await can_review_projects(session, actor, settings, project):
        raise PermissionError('reviewer_access_required')
    if project.author_id == actor.id:
        raise PermissionError('project_self_review')
    if project.status not in {ProjectStatus.PENDING_REVIEW, ProjectStatus.INITIAL_REVIEW, ProjectStatus.VENUE_REVIEW}:
        raise ValueError('project_review_stale')
    previous = await assigned_project_reviewer(session, project.id)
    current = await active_project_reviewer(session, project, settings)
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
                old_value={'reviewer_id': previous}, new_value={'reviewer_id': reviewer_id})
    await session.flush()
    return reviewer_id


async def project_review_recipients(session, project, settings):
    """Private reviewer inboxes only; no project files in the leaders' group."""
    from app.database.models import Office, PermissionGrant, User, UserOffice
    from app.utils.constants import ApplicationStatus, Role
    assigned_id = await active_project_reviewer(session, project, settings)
    if assigned_id:
        assigned = await session.get(User, assigned_id)
        if (assigned and assigned.telegram_id > 0
                and assigned.application_status == ApplicationStatus.APPROVED
                and await can_review_projects(session, assigned, settings, project)):
            return {assigned.telegram_id}
    manual_ids = select(PermissionGrant.user_id).where(
        PermissionGrant.permission == 'projects.review', PermissionGrant.is_active.is_(True))
    office_rows = (await session.execute(select(UserOffice.user_id, Office.permission_template)
        .join(Office, Office.id == UserOffice.office_id)
        .where(UserOffice.is_active.is_(True), Office.is_active.is_(True)))).all()
    office_ids = {user_id for user_id, template in office_rows if 'projects.review' in (template or [])}
    # This is only a candidate inventory; exact scope and current appointment
    # dates are still checked per person below.
    candidates = (await session.scalars(select(User).where(
        or_(User.role == Role.ADMIN, User.telegram_id.in_(settings.admin_ids),
            User.id.in_(manual_ids), User.id.in_(office_ids)),
        User.is_blocked.is_(False), User.is_archived.is_(False),
        User.application_status == ApplicationStatus.APPROVED,
    ))).all()
    recipients = {int(i) for i in settings.admin_ids if int(i) > 0}
    for candidate in candidates:
        if candidate.id != project.author_id and candidate.telegram_id > 0 and await can_review_projects(
                session, candidate, settings, project):
            recipients.add(candidate.telegram_id)
    return recipients
