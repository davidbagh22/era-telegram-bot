import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.api.deps import get_current_user, get_session, get_settings
from app.api.v1.admin import require_points_awarder
from app.api.v1.admin_event_operations import router as operations_router
from app.config import Settings
from app.handlers.admin.chat_binding_stability import _can_bind
from app.services.authorization_service import (active_global_permissions, active_permissions,
    can_manage_events, can_manage_partners, can_manage_people, can_manage_tasks, can_view_people)
from app.services.leadership_permission_service import ScopedPermission, _matches


def actor(permission, *, scope_type='department', scope_id=7, active=True):
    return SimpleNamespace(id=1, telegram_id=123, role='participant', is_blocked=False, is_archived=False,
        permission_grants=[SimpleNamespace(permission=permission, is_active=active,
                                          scope_type=scope_type, scope_id=scope_id)])


@pytest.mark.parametrize('permission,check', [
    ('people.view', can_view_people), ('people.manage', can_manage_people),
    ('events.manage', can_manage_events), ('tasks.manage', can_manage_tasks),
    ('partners.manage', can_manage_partners),
])
def test_department_grant_never_authorizes_unscoped_operations(permission, check):
    settings = Settings(bot_token='0000000000:PERMISSIONTEST')
    user = actor(permission)
    assert permission in active_permissions(user)  # UI inventory stays intact.
    assert permission not in active_global_permissions(user)
    assert not check(user, settings, user.telegram_id)
    user.permission_grants[0].scope_type, user.permission_grants[0].scope_id = 'global', 0
    assert check(user, settings, user.telegram_id)
    user.permission_grants[0].is_active = False
    assert not check(user, settings, user.telegram_id)


def test_missing_or_malformed_scope_metadata_cannot_become_global():
    user = actor('people.manage')
    for grant in (
        SimpleNamespace(permission='people.manage', is_active=True),
        SimpleNamespace(permission='people.manage', is_active=True, scope_type='global', scope_id=7),
    ):
        user.permission_grants = [grant]
        assert active_global_permissions(user) == set()


def test_scoped_permission_requires_an_explicit_matching_object_context():
    entry = ScopedPermission('events.manage', 'department', 7)
    assert _matches(entry, 'events.manage', 'department', 7)
    assert not _matches(entry, 'events.manage', 'department', 8)
    assert not _matches(entry, 'events.manage', None, None)
    assert _matches(ScopedPermission('events.manage', 'global', 0), 'events.manage', None, None)


def test_department_people_manager_cannot_rebind_global_telegram_chats():
    user = actor('people.manage')
    assert not _can_bind(user, Settings(bot_token='0000000000:PERMISSIONTEST'), user.telegram_id)


def test_department_points_grant_cannot_award_arbitrary_users():
    async def verify():
        settings = Settings(bot_token='0000000000:PERMISSIONTEST')
        user = actor('points.award')
        with pytest.raises(HTTPException) as caught:
            await require_points_awarder(user, settings)
        assert caught.value.status_code == 403
        user.permission_grants[0].scope_type, user.permission_grants[0].scope_id = 'global', 0
        assert await require_points_awarder(user, settings) is user
    asyncio.run(verify())

def test_forged_http_export_with_department_grant_is_rejected_before_reading_private_roster():
    app = FastAPI()
    app.include_router(operations_router)
    user = actor('events.manage')
    session = SimpleNamespace(get=AsyncMock(side_effect=AssertionError('No roster access allowed')))
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_settings] = lambda: Settings(bot_token='0000000000:PERMISSIONTEST')
    app.dependency_overrides[get_session] = lambda: session
    with TestClient(app) as client:
        response = client.get('/admin/events/7/participants')
    assert response.status_code == 403
    session.get.assert_not_awaited()
