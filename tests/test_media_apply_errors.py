"""Media application failures must be actionable and not leak internal errors."""
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException

from app.api.v1.media import apply_to_media
from app.utils.constants import ApplicationStatus


class MediaApplyErrorsTests(IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.user = SimpleNamespace(
            is_blocked=False,
            is_archived=False,
            application_status=ApplicationStatus.APPROVED,
        )
        self.session = object()
        self.settings = object()

    async def test_missing_media_direction_is_retryable_503(self) -> None:
        with (
            patch(
                "app.api.v1.media.media_service.apply_for_media",
                new_callable=AsyncMock,
                side_effect=ValueError("media_direction_missing"),
            ) as apply,
            patch("app.api.v1.media.read_media_hub", new_callable=AsyncMock) as hub,
        ):
            with self.assertRaises(HTTPException) as error:
                await apply_to_media(
                    user=self.user, session=self.session, settings=self.settings
                )
        self.assertEqual(error.exception.status_code, 503)
        self.assertEqual(error.exception.detail, "media_direction_missing")
        apply.assert_awaited_once_with(self.session, self.user)
        hub.assert_not_awaited()

    async def test_revoked_applicant_during_lock_is_403(self) -> None:
        with patch(
            "app.api.v1.media.media_service.apply_for_media",
            new_callable=AsyncMock,
            side_effect=ValueError("media_apply_forbidden"),
        ):
            with self.assertRaises(HTTPException) as error:
                await apply_to_media(
                    user=self.user, session=self.session, settings=self.settings
                )
        self.assertEqual(error.exception.status_code, 403)
        self.assertEqual(
            error.exception.detail, "media_apply_requires_approved_membership"
        )

    async def test_unexpected_internal_value_error_is_not_exposed_as_http_detail(self) -> None:
        with patch(
            "app.api.v1.media.media_service.apply_for_media",
            new_callable=AsyncMock,
            side_effect=ValueError("internal_sensitive_failure"),
        ):
            with self.assertRaisesRegex(ValueError, "internal_sensitive_failure"):
                await apply_to_media(
                    user=self.user, session=self.session, settings=self.settings
                )

    async def test_ineligible_applicant_is_rejected_without_mutating_membership(self) -> None:
        self.user.is_blocked = True
        with patch(
            "app.api.v1.media.media_service.apply_for_media",
            new_callable=AsyncMock,
        ) as apply:
            with self.assertRaises(HTTPException) as error:
                await apply_to_media(
                    user=self.user, session=self.session, settings=self.settings
                )
        self.assertEqual(error.exception.status_code, 403)
        apply.assert_not_awaited()

    async def test_success_preserves_existing_hub_response(self) -> None:
        expected = object()
        with (
            patch(
                "app.api.v1.media.media_service.apply_for_media",
                new_callable=AsyncMock,
                return_value="pending",
            ) as apply,
            patch(
                "app.api.v1.media.read_media_hub",
                new_callable=AsyncMock,
                return_value=expected,
            ) as hub,
        ):
            result = await apply_to_media(
                user=self.user, session=self.session, settings=self.settings
            )
        self.assertIs(result, expected)
        apply.assert_awaited_once_with(self.session, self.user)
        hub.assert_awaited_once_with(
            user=self.user, session=self.session, settings=self.settings
        )
