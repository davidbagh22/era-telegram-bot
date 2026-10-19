from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base


class CertificateIssue(Base):
    """Immutable issued document snapshot, linked to the canonical portfolio."""
    __tablename__ = "certificate_issues"
    __table_args__ = (UniqueConstraint("basis_key", "revision", name="uq_certificate_basis_revision"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id"), index=True)
    portfolio_item_id: Mapped[int] = mapped_column(ForeignKey("portfolio_items.id"))
    basis_key: Mapped[str] = mapped_column(String(100), index=True)
    revision: Mapped[int] = mapped_column(default=1)
    request_key: Mapped[str] = mapped_column(String(64), unique=True)
    status: Mapped[str] = mapped_column(String(20), default="issued")
    snapshot: Mapped[dict[str, Any]] = mapped_column(JSON)
    issued_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revocation_reason: Mapped[str | None] = mapped_column(Text)

    @property
    def document_number(self) -> str:
        return f"ERA-CERT-{self.id:06d}"
