from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, TimestampMixin


class MediaContentItem(TimestampMixin, Base):
    __tablename__ = "media_content_items"
    __table_args__ = (UniqueConstraint("source_key", name="uq_media_content_source_key"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    source_kind: Mapped[str] = mapped_column(String(32), index=True)
    source_key: Mapped[str] = mapped_column(String(160), index=True)
    source_type: Mapped[str | None] = mapped_column(String(32), index=True)
    source_id: Mapped[int | None] = mapped_column(Integer, index=True)
    week: Mapped[int | None] = mapped_column(Integer, index=True)
    title: Mapped[str | None] = mapped_column(String(255))
    theme: Mapped[str | None] = mapped_column(String(120))
    rubric: Mapped[str | None] = mapped_column(String(120))
    kind: Mapped[str] = mapped_column(String(24), default="text", index=True)
    body: Mapped[str | None] = mapped_column(Text)
    poll_question: Mapped[str | None] = mapped_column(Text)
    poll_options: Mapped[list[str]] = mapped_column(JSON, default=list)
    channel_id: Mapped[str | None] = mapped_column(String(128))
    needs_visual: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    needs_video: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    status: Mapped[str] = mapped_column(String(24), default="PLANNED", index=True)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), index=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    telegram_message_id: Mapped[int | None] = mapped_column(Integer)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class MediaChannelDelivery(TimestampMixin, Base):
    __tablename__ = "media_channel_deliveries"
    __table_args__ = (UniqueConstraint("delivery_key", name="uq_media_delivery_key"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    content_id: Mapped[int] = mapped_column(ForeignKey("media_content_items.id", ondelete="CASCADE"), index=True)
    delivery_key: Mapped[str] = mapped_column(String(255), index=True)
    status: Mapped[str] = mapped_column(String(24), default="claimed", index=True)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    claimed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    telegram_message_id: Mapped[int | None] = mapped_column(Integer)
    last_error: Mapped[str | None] = mapped_column(String(500))


class MediaContentTask(TimestampMixin, Base):
    __tablename__ = "media_content_tasks"
    __table_args__ = (
        UniqueConstraint("content_id", "task_kind", name="uq_media_content_task_kind"),
        UniqueConstraint("task_id", name="uq_media_content_task_task"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    content_id: Mapped[int] = mapped_column(ForeignKey("media_content_items.id", ondelete="CASCADE"), index=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"), index=True)
    task_kind: Mapped[str] = mapped_column(String(32), index=True)


class MediaLibraryItem(TimestampMixin, Base):
    __tablename__ = "media_library_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(32), index=True)
    category: Mapped[str] = mapped_column(String(64), default="archive", index=True)
    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text)
    url: Mapped[str] = mapped_column(String(1000))
    sort_order: Mapped[int] = mapped_column(Integer, default=100)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)


class MediaRequest(TimestampMixin, Base):
    __tablename__ = "media_requests"
    __table_args__ = (
        UniqueConstraint("source_type", "source_id", "package_type", name="uq_media_request_source_package"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    source_type: Mapped[str] = mapped_column(String(24), index=True)
    source_id: Mapped[int] = mapped_column(Integer, index=True)
    package_type: Mapped[str] = mapped_column(String(32), index=True)
    requester_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    content_id: Mapped[int | None] = mapped_column(ForeignKey("media_content_items.id", ondelete="SET NULL"), index=True)
    status: Mapped[str] = mapped_column(String(24), default="open", index=True)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class MediaChatNotice(TimestampMixin, Base):
    __tablename__ = "media_chat_notices"
    __table_args__ = (UniqueConstraint("notice_key", name="uq_media_chat_notice_key"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    notice_key: Mapped[str] = mapped_column(String(255), index=True)
    notice_kind: Mapped[str] = mapped_column(String(32), index=True)
    ref_type: Mapped[str] = mapped_column(String(32), index=True)
    ref_id: Mapped[int] = mapped_column(Integer, index=True)
    telegram_message_id: Mapped[int | None] = mapped_column(Integer)
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class MediaAttachment(TimestampMixin, Base):
    """Pending chat replies become attached only after explicit confirmation."""

    __tablename__ = "media_attachments"
    __table_args__ = (
        UniqueConstraint(
            "source_chat_id",
            "source_message_id",
            "uploader_id",
            name="uq_media_attachment_chat_message_user",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    target_type: Mapped[str] = mapped_column(String(24), index=True)
    target_id: Mapped[int] = mapped_column(Integer, index=True)
    uploader_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    status: Mapped[str] = mapped_column(String(24), default="pending", index=True)
    media_type: Mapped[str] = mapped_column(String(24), index=True)
    telegram_file_id: Mapped[str | None] = mapped_column(String(512))
    telegram_file_unique_id: Mapped[str | None] = mapped_column(String(255))
    external_url: Mapped[str | None] = mapped_column(String(1000))
    filename: Mapped[str | None] = mapped_column(String(255))
    mime_type: Mapped[str | None] = mapped_column(String(160))
    source_chat_id: Mapped[int | None] = mapped_column(Integer, index=True)
    source_message_id: Mapped[int | None] = mapped_column(Integer, index=True)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
