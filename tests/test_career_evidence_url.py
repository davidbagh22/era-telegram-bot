"""Isolated URL evidence validation; no real participants or external requests."""

import asyncio

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import app.database  # noqa: F401 - register all models
from app.database.base import Base
from app.database.models import User
from app.services import career_service
from app.utils.constants import ApplicationStatus, Role


@pytest.mark.parametrize("value", [
    "javascript:alert(1)",
    "data:text/html,unsafe",
    "ftp://example.org/proof",
    "//example.org/proof",
    "/relative/path",
    "https://user:pass@example.org/proof",
    "https://user@example.org/proof",
    "https://example.org:99999/proof",
    "https://example.org:abc/proof",
    "https://example.org/space in path",
    "https://example.org\\\\@attacker.example/",
    "https://example.org/\nmalformed",
    "https://example.org/" + "x" * 501,
])
def test_reject_non_browser_or_credential_evidence_urls(value: str) -> None:
    with pytest.raises(ValueError, match="^invalid_evidence_url$"):
        career_service.valid_evidence_url(value)


@pytest.mark.parametrize("value", [
    "https://example.org/evidence?id=1#part",
    "http://example.org/proof",
    " HTTPS://example.org/evidence ",
])
def test_accept_absolute_http_evidence_urls(value: str) -> None:
    assert career_service.valid_evidence_url(value) == value.strip()


def test_blank_url_can_be_cleared_without_breaking_file_evidence() -> None:
    assert career_service.valid_evidence_url(None) is None
    assert career_service.valid_evidence_url("   ") is None


async def _run_isolated_service_flow() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        factory = async_sessionmaker(engine, expire_on_commit=False)
        async with factory() as session:
            user = User(
                telegram_id=992099,
                first_name="Test",
                role=Role.PARTICIPANT,
                application_status=ApplicationStatus.APPROVED,
            )
            session.add(user)
            await session.commit()
            await session.refresh(user)

            with pytest.raises(ValueError, match="^invalid_evidence_url$"):
                await career_service.create_item(
                    session, user.id, item_type="achievement", title="Unsafe",
                    url="javascript:alert(1)",
                )
            item = await career_service.create_item(
                session, user.id, item_type="achievement", title="Original",
                url="https://example.org/proof",
            )
            with pytest.raises(ValueError, match="^invalid_evidence_url$"):
                await career_service.update_item(
                    session, item, title="Must not persist", url="data:text/html,unsafe",
                )
            assert item.title == "Original"
            assert item.url == "https://example.org/proof"

            item = await career_service.request_verification(session, item)
            assert item.status == "pending"
            item = await career_service.update_item(session, item, url="")
            assert item.url is None and item.status == "self_reported"

            # Simulate a pre-existing legacy row in disposable SQLite only.
            item.url = "javascript:alert(1)"
            await session.commit()
            with pytest.raises(ValueError, match="^evidence_required$"):
                await career_service.request_verification(session, item)
            assert item.url == "javascript:alert(1)"  # No destructive rewrite.

            # Uploaded-file evidence still works even when legacy URL is invalid.
            item = await career_service.attach_file(
                session, item, file_id="local-file-id", file_name="proof.pdf",
            )
            item = await career_service.request_verification(session, item)
            assert item.status == "pending"
            assert item.url == "javascript:alert(1)"

            # A legacy pending URL-only request cannot be approved without proof,
            # but a reviewer can still reject it without rewriting its URL.
            legacy = await career_service.create_item(
                session, user.id, item_type="achievement", title="Legacy pending",
            )
            legacy.url = "data:text/html,unsafe"
            legacy.status = "pending"
            await session.commit()
            with pytest.raises(ValueError, match="^evidence_required$"):
                await career_service.review_item(
                    session, legacy, reviewer_id=user.id, decision="approve", comment=None,
                )
            assert legacy.status == "pending"
            legacy = await career_service.review_item(
                session, legacy, reviewer_id=user.id, decision="reject", comment="Invalid proof",
            )
            assert legacy.status == "rejected"
            assert legacy.url == "data:text/html,unsafe"
    finally:
        await engine.dispose()


def test_isolated_service_rejects_unsafe_url_and_preserves_legacy_rows() -> None:
    asyncio.run(_run_isolated_service_flow())
