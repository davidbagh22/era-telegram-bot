"""ECC bot simplifier: cabinet flatten, points vs signs split, opportunities hub."""
from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.handlers.participant import achievements_block4, navigation, partner_offers_block16
from app.keyboards.participant import (
    about_keyboard,
    journey_keyboard,
    opportunities_hub_keyboard,
    points_hub_keyboard,
    team_keyboard,
)
from app.utils import texts, ux_texts
from app.utils.constants import ApplicationStatus


def _labels(keyboard) -> list[str]:
    return [button.text for row in keyboard.inline_keyboard for button in row]


def _callbacks(keyboard) -> set[str]:
    return {
        button.callback_data
        for row in keyboard.inline_keyboard
        for button in row
        if button.callback_data
    }


class CabinetFlattenTests(unittest.TestCase):
    def test_journey_skips_points_hub_hop(self) -> None:
        callbacks = _callbacks(journey_keyboard())
        self.assertEqual(
            callbacks,
            {
                "cabinet:profile",
                "cabinet:tasks",
                "cabinet:portfolio",
                "cabinet:points",
                "cabinet:achievements",
                "cabinet:rating",
                "menu:main",
            },
        )

    def test_points_hub_keeps_distinct_destinations(self) -> None:
        self.assertEqual(
            _callbacks(points_hub_keyboard()),
            {
                "cabinet:points",
                "cabinet:achievements",
                "cabinet:rating",
                "cabinet:open",
            },
        )

    def test_legacy_team_keyboard_has_one_offices_entry(self) -> None:
        offices = [
            cb for cb in _callbacks(team_keyboard()) if cb == "team:offices"
        ]
        self.assertEqual(len(offices), 1)
        self.assertNotIn("👤 Руководители направлений", _labels(team_keyboard()))

    def test_about_keyboard_stays_compact_with_offers(self) -> None:
        labels = _labels(about_keyboard())
        self.assertLessEqual(len(labels), 6)
        self.assertIn("offers:menu", _callbacks(about_keyboard()))


class OpportunitiesHubParityTests(unittest.TestCase):
    def test_reply_and_callback_share_same_hub(self) -> None:
        shared = opportunities_hub_keyboard()
        via_offers = partner_offers_block16.opportunities_keyboard()
        self.assertEqual(_labels(shared), _labels(via_offers))
        self.assertEqual(_callbacks(shared), _callbacks(via_offers))
        self.assertIn("auctions:list", _callbacks(shared))
        self.assertIn("rewards:menu", _callbacks(shared))
        self.assertNotIn("Партнёрский каталог", _labels(shared))


class AchievementsPointsSplitTests(unittest.IsolatedAsyncioTestCase):
    def test_achievements_handler_filter_excludes_cabinet_points(self) -> None:
        source = open(achievements_block4.__file__, encoding="utf-8").read()
        decorator_block = source.split("async def achievements", 1)[0].rsplit("@router.callback_query", 1)[-1]
        self.assertIn("cabinet:achievements", decorator_block)
        self.assertIn("cabinet:badges", decorator_block)
        self.assertNotIn("cabinet:points", decorator_block)

    async def test_achievements_copy_is_signs_focused(self) -> None:
        call = SimpleNamespace(answer=AsyncMock(), message=SimpleNamespace(answer=AsyncMock()), data="cabinet:achievements")
        user = SimpleNamespace(
            id=1,
            role="participant",
            participation_status="active",
            application_status=ApplicationStatus.APPROVED,
            is_blocked=False,
            is_archived=False,
        )
        session = AsyncMock()
        with (
            patch.object(achievements_block4, "user_stats", new=AsyncMock(return_value={"events": 1, "tasks": 2, "projects": 0, "portfolio": 0})),
            patch.object(achievements_block4, "total_points", new=AsyncMock(return_value=40)),
            patch.object(achievements_block4, "badges_for_user", new=AsyncMock(return_value=[])),
            patch.object(achievements_block4, "send_long_text", new=AsyncMock()) as send,
        ):
            await achievements_block4.achievements(call, user, session)
        (message, body), kwargs = send.call_args
        self.assertTrue(body.startswith("🏅 Знаки ЭРА"))
        self.assertNotIn("Последние баллы", body)
        self.assertIn("cabinet:points", _callbacks(kwargs["reply_markup"]))


class NavigationCopyTests(unittest.TestCase):
    def test_navigation_copy_is_shorter(self) -> None:
        self.assertLess(len(navigation.NAVIGATION_PARTICIPANT), 520)
        self.assertIn("💡 <b>Проекты</b>", navigation.NAVIGATION_PARTICIPANT)
        self.assertIn("Режим лидера", navigation.NAVIGATION_LEADER)
        self.assertIn("Режим администратора", navigation.NAVIGATION_ADMIN)

    def test_cabinet_home_text_shared(self) -> None:
        text = ux_texts.cabinet_home_text("Анна", "участник", 12, 3)
        self.assertIn("Анна", text)
        self.assertIn("12 баллов", text)
        self.assertIn("Место в рейтинге: 3", text)

    def test_admin_panel_moved_is_short(self) -> None:
        self.assertLess(len(texts.ADMIN_PANEL_MOVED), 120)
        self.assertLess(len(texts.LEADER_PANEL_MOVED), 120)


class OpportunitiesReplyUsesHubTests(unittest.IsolatedAsyncioTestCase):
    async def test_star_opportunities_button_uses_shared_hub(self) -> None:
        message = SimpleNamespace(answer=AsyncMock())
        user = SimpleNamespace(
            id=7,
            application_status=ApplicationStatus.APPROVED,
            is_blocked=False,
            is_archived=False,
        )
        state = SimpleNamespace(clear=AsyncMock())
        session = AsyncMock()
        with patch.object(navigation, "total_points", new=AsyncMock(return_value=55)):
            await navigation.opportunities_button(message, user, session, state)
        (_text,), kwargs = message.answer.call_args
        self.assertEqual(_callbacks(kwargs["reply_markup"]), _callbacks(opportunities_hub_keyboard()))


if __name__ == "__main__":
    unittest.main()
