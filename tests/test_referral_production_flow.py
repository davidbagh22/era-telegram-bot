from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.handlers import referral_entry


class FakeState:
    def __init__(self, data=None):
        self.data = dict(data or {})

    async def clear(self):
        self.data = {}

    async def get_data(self):
        return dict(self.data)

    async def update_data(self, **kwargs):
        self.data.update(kwargs)


@pytest.mark.asyncio
async def test_referral_start_survives_global_start_clear():
    state = FakeState()
    message = SimpleNamespace(
        from_user=SimpleNamespace(id=42),
        chat=SimpleNamespace(type="private"),
    )
    command = SimpleNamespace(args="ref_181239")
    user = None

    async def clear_inside_rescue(*args, **kwargs):
        await state.clear()

    with patch.object(
        referral_entry,
        "validate_referral_code",
        AsyncMock(return_value=(SimpleNamespace(code="181239"), SimpleNamespace())),
    ), patch.object(
        referral_entry.emergency,
        "rescue_start",
        AsyncMock(side_effect=clear_inside_rescue),
    ):
        await referral_entry.referral_aware_start(
            message,
            SimpleNamespace(),
            user,
            SimpleNamespace(),
            state,
            SimpleNamespace(),
            command,
        )

    assert state.data["referral_code"] == "181239"


@pytest.mark.asyncio
async def test_referral_survives_subscription_check_clear():
    state = FakeState({"referral_code": "181239"})
    call = SimpleNamespace(
        data="subscription:check",
        from_user=SimpleNamespace(id=42),
        message=SimpleNamespace(chat=SimpleNamespace(type="private")),
    )

    async def clear_inside_check(*args, **kwargs):
        await state.clear()

    with patch.object(
        referral_entry.start,
        "check_subscription",
        AsyncMock(side_effect=clear_inside_check),
    ):
        await referral_entry.referral_aware_subscription_check(
            call,
            SimpleNamespace(),
            None,
            SimpleNamespace(),
            state,
        )

    assert state.data["referral_code"] == "181239"


@pytest.mark.asyncio
async def test_referral_survives_registration_start_clear():
    state = FakeState({"referral_code": "181239"})
    call = SimpleNamespace(
        data="registration:start",
        from_user=SimpleNamespace(id=42),
        message=SimpleNamespace(chat=SimpleNamespace(type="private")),
    )

    async def clear_inside_registration(*args, **kwargs):
        await state.clear()

    with patch.object(
        referral_entry.registration,
        "registration_start",
        AsyncMock(side_effect=clear_inside_registration),
    ):
        await referral_entry.referral_aware_registration_start(
            call,
            state,
            SimpleNamespace(),
            SimpleNamespace(),
            None,
        )

    assert state.data["referral_code"] == "181239"


def test_referral_share_and_copy_match_production_rules():
    screen = Path("frontend/src/screens/ReferralScreen.tsx").read_text(encoding="utf-8")
    registration_copy = Path("app/handlers/referrals.py").read_text(encoding="utf-8")

    assert "encodeURIComponent(data.share_text)" in screen
    assert "URLSearchParams" not in screen
    assert "+200" not in registration_copy
    assert "+500" not in registration_copy
    assert "+30" in registration_copy
    assert "+70" in registration_copy
