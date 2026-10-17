from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import unittest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.v1.system import BackupReportIn, report_backup
from app.config import Settings
from app.database.base import Base
from app.database.system_models import BackupHistory, SystemIncident


class BackupNotificationNoiseTests(unittest.IsolatedAsyncioTestCase):
    async def test_successful_backups_persist_without_individual_messages_and_failure_stays_visible(self):
        engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        try:
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            sessions = async_sessionmaker(engine, expire_on_commit=False)
            notify = AsyncMock(return_value=(1, 0))
            settings = Settings(bot_token="1234567890:test-token")
            async with sessions() as session:
                with patch("app.api.v1.system.notify_admins", new=notify):
                    for number in (1, 2):
                        await report_backup(BackupReportIn(backup_key=f"verified-{number}", status="success", checksum_sha256="a"*64, storage_reference="encrypted-artifact", restore_verified_at=datetime.now(timezone.utc)), _identity={}, session=session, bot=object(), settings=settings)
                    await session.commit()
                    assert len((await session.scalars(select(BackupHistory))).all()) == 2
                    notify.assert_not_awaited()
                    payload = BackupReportIn(backup_key="failed-3", status="failed", error_code="restore_failed")
                    await report_backup(payload, _identity={}, session=session, bot=object(), settings=settings)
                    await report_backup(payload, _identity={}, session=session, bot=object(), settings=settings)
                    await session.commit()
                    assert notify.await_count == 1
                    assert (await session.scalar(select(SystemIncident))).status == "open"
        finally:
            await engine.dispose()
