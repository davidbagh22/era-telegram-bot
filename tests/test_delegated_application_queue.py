import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.handlers.admin.application_review_bot import application_comment
from app.handlers.admin.dashboard_block_a import _application_guard


def test_revoked_application_permission_blocks_queue_and_pending_comment():
    async def scenario():
        message=SimpleNamespace(from_user=SimpleNamespace(id=12),answer=AsyncMock(),text='Причина решения')
        with patch('app.services.staff_access_service.can_operate_queue',new=AsyncMock(return_value=False)):
            assert not await _application_guard(message,None,None,None)
        with patch('app.handlers.admin.application_review_bot.can_operate_queue',new=AsyncMock(return_value=False)), \
             patch('app.handlers.admin.application_review_bot._target',new=AsyncMock()) as target:
            await application_comment(message,None,None,None,SimpleNamespace(),None)
            target.assert_not_awaited()
    asyncio.run(scenario())


def test_only_application_handlers_move_outside_full_admin_root():
    from app.handlers.admin import router,project_review_router
    from app.handlers.admin.dashboard_block_a import applications_router
    assert applications_router.parent_router is project_review_router
    assert router.message.filter is not None
    from app.handlers.admin.legacy_action_bridge import LEGACY_ADMIN_ACTIONS
    assert 'admin:applications' not in LEGACY_ADMIN_ACTIONS
