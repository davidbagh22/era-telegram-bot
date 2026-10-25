from __future__ import annotations

from sqlalchemy import String, Text
from sqlalchemy.orm import mapped_column

from app.database.models import Office, PositionApplication


# Keep Office → UserOffice → PositionApplication as the single leadership
# model while extending the already-mapped legacy classes with the minimal
# persisted fields required by the unified recruitment flow. Declarative
# classes support adding mapped columns after class declaration; importing
# this module from app.database makes the fields part of Base.metadata too.
if not hasattr(Office, "recruitment_mode"):
    Office.recruitment_mode = mapped_column(String(16), default="closed")
if not hasattr(Office, "expected_result"):
    Office.expected_result = mapped_column(Text, nullable=True)
if not hasattr(Office, "workload"):
    Office.workload = mapped_column(String(255), nullable=True)

if not hasattr(PositionApplication, "relevant_experience"):
    PositionApplication.relevant_experience = mapped_column(Text, nullable=True)
if not hasattr(PositionApplication, "attachment_url"):
    PositionApplication.attachment_url = mapped_column(String(1000), nullable=True)
