"""Operator-authorized, encrypted and replay-safe fresh-registration reset.

Only an exact Telegram ID + expected database ID can be reset. Historical
foreign keys are retained on an archived identity; the live Telegram identity
and its private FSM become available for a genuinely new application.
"""
import json
import os
import re
from datetime import datetime, timezone

from aiogram.fsm.storage.base import StorageKey
from cryptography.fernet import Fernet
from sqlalchemy import inspect, select, text

from app.database.community_verification_models import CommunityMemberIdentity
from app.database.models import AppSetting, User
from app.services.audit_service import audit
from app.utils.constants import Role


async def apply_registration_reset(settings, session_factory, storage, bot_id, *, command=None, backup_key=None):
    raw = command if command is not None else os.environ.get("ERA_REGISTRATION_RESET", "")
    if not raw:
        return "disabled"
    request = json.loads(raw)
    tg, expected = int(request["telegram_id"]), int(request["expected_user_id"])
    operation = request["request_id"]
    if tg <= 0 or expected <= 0 or not re.fullmatch(r"[A-Za-z0-9_-]{8,50}", operation):
        raise ValueError("invalid_registration_reset_command")
    if tg in settings.admin_ids:
        raise ValueError("protected_registration_reset_target")
    cipher = Fernet((backup_key or os.environ.get("ERA_REGISTRATION_RESET_BACKUP_KEY", "")).encode())
    key = f"registration-reset:{operation}"
    fsm_key = StorageKey(bot_id=bot_id, chat_id=tg, user_id=tg)
    async with session_factory() as session:
        if session.bind.dialect.name == "postgresql":
            # Serialize all reset operations, including retries with a new key.
            await session.execute(text("SELECT pg_advisory_xact_lock(8461202026)"))
        receipt = await session.scalar(select(AppSetting).where(AppSetting.key == key).with_for_update())
        if receipt:
            if receipt.value["telegram_id"] != tg or receipt.value["user_id"] != expected:
                raise ValueError("registration_reset_request_conflict")
            if receipt.value["status"] == "complete":
                return "already_complete"
        else:
            target = await session.scalar(select(User).where(User.id == expected, User.telegram_id == tg)
                                          .with_for_update().execution_options(populate_existing=True))
            if target is None or target.role != Role.PARTICIPANT or target.is_blocked:
                raise ValueError("registration_reset_target_mismatch_or_protected")
            identity = await session.get(CommunityMemberIdentity, tg)
            if identity and identity.user_id not in {None, target.id}:
                raise ValueError("registration_reset_identity_conflict")
            snapshot = {
                "user": {c.key: getattr(target, c.key) for c in inspect(User).column_attrs},
                "identity_user_id": identity.user_id if identity else None,
                "fsm_state": await storage.get_state(fsm_key), "fsm_data": await storage.get_data(fsm_key),
            }
            plaintext = json.dumps(snapshot, ensure_ascii=False, default=str).encode()
            encrypted = cipher.encrypt(plaintext).decode()
            if cipher.decrypt(encrypted.encode()) != plaintext:
                raise ValueError("registration_reset_backup_verification_failed")
            synthetic_id = -(tg * 1000000 + target.id)
            if await session.scalar(select(User.id).where(User.telegram_id == synthetic_id)):
                raise ValueError("registration_reset_archive_identity_conflict")
            receipt = AppSetting(key=key, value={"telegram_id": tg, "user_id": expected, "status": "db_reset",
                "encrypted_snapshot": encrypted, "cipher": "fernet-v1", "created_at": datetime.now(timezone.utc).isoformat()})
            session.add(receipt)
            target.telegram_id, target.username = synthetic_id, None
            target.is_archived = True
            target.archived_at = target.archived_at or datetime.now(timezone.utc)
            # The verified identity map must not silently restore the old row.
            if identity:
                identity.user_id = None
            await audit(session, actor_id=None, action="registration.reset_requested", entity_type="user", entity_id=target.id,
                        new_value={"operation": operation, "backup": "encrypted", "history": "preserved"})
            await session.commit()
    # Cross-system operation: commit the encrypted backup + database reset
    # first. If Redis fails, replay resumes here without resetting a new User.
    await storage.set_state(fsm_key, None)
    await storage.set_data(fsm_key, {})
    if await storage.get_state(fsm_key) is not None or await storage.get_data(fsm_key):
        raise ValueError("registration_reset_fsm_not_cleared")
    async with session_factory() as session:
        receipt = await session.scalar(select(AppSetting).where(AppSetting.key == key).with_for_update())
        receipt.value = {**receipt.value, "status": "complete", "completed_at": datetime.now(timezone.utc).isoformat()}
        await session.commit()
    return "complete"
