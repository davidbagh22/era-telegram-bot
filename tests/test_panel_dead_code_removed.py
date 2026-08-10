from __future__ import annotations

import unittest

from app.handlers.admin import panel


class PanelDeadCodeRemovedTests(unittest.TestCase):
    """PR 33 removed 15 functions from app/handlers/admin/panel.py, and
    PR 34 removed 11 more, that a router-precedence analysis (comparing
    every panel.py callback_data/Command/state filter against all other
    admin handler files, in app/handlers/admin/__init__.py's actual
    registration order — including custom filter functions like
    is_profile_callback and multi-filter/state-scoped decorators the
    original AST pass couldn't parse, resolved by manual reading) proved
    were permanently unreachable — an earlier-registered file's router
    always won the same update first. See docs/ERA_PLATFORM_PROGRESS.md's
    PR 33 and PR 34 sections for the full list and the shadowing file for
    each.

    PR 34 also removed admin_user_archive_confirm, which was not itself
    shadowed but became orphaned once admin_user_archive_start (its sole
    callback_data generator) was removed — the two were deleted together.

    This just guards against the dead code silently creeping back in.
    """

    REMOVED_NAMES = [
        "admin_command",
        "admin_panel",
        "admin_submenu",
        "approve_user",
        "pending_events",
        "pending_projects",
        "event_activity_submissions",
        "approve_entity",
        "auctions_admin_menu",
        "auction_results",
        "auction_select_winner",
        "tasks_for_review",
        "analytics",
        "analytics_excel",
        "offices_menu",
        # PR 34
        "event_activity_decide",
        "project_review_start",
        "review_entity_start",
        "admin_user_card",
        "admin_user_role_menu",
        "admin_user_set_role",
        "admin_user_archive_start",
        "admin_user_archive_confirm",
        "office_view",
        "permissions_user",
        "permission_toggle",
    ]

    def test_dead_functions_stay_removed(self) -> None:
        for name in self.REMOVED_NAMES:
            with self.subTest(name=name):
                self.assertFalse(
                    hasattr(panel, name),
                    f"panel.{name} reappeared — confirm it's actually reachable "
                    "(no earlier-registered admin router wins the same callback_data/"
                    "Command first) before re-adding it.",
                )

    def test_still_reachable_helpers_kept(self) -> None:
        # _start_user_review is shared with reject_user_start/info_user_start,
        # both still live — removing approve_user must not have taken it too.
        self.assertTrue(hasattr(panel, "_start_user_review"))


if __name__ == "__main__":
    unittest.main()
