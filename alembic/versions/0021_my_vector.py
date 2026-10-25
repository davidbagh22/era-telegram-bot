"""add My Vector self-reflection system

Revision ID: 0021_my_vector
Revises: 0020_event_experience
"""

from __future__ import annotations

from alembic import op

from app.database.base import Base
import app.database.models  # noqa: F401
import app.database.development_models  # noqa: F401

revision = "0021_my_vector"
down_revision = "0020_event_experience"
branch_labels = None
depends_on = None

_TABLES = [
    "assessment_definitions",
    "assessment_versions",
    "assessment_scales",
    "assessment_questions",
    "assessment_options",
    "assessment_scoring_rules",
    "assessment_sessions",
    "assessment_answers",
    "assessment_scores",
    "user_vector_profiles",
    "monthly_checkins",
    "monthly_context",
    "weekly_pulses",
    "development_goals",
    "goal_reviews",
    "personal_insights",
    "personal_notes",
    "recommendations",
    "recommendation_history",
    "assessment_consents",
    "admin_visibility_settings",
    "analytics_snapshots",
    "development_audit_logs",
]


def upgrade() -> None:
    bind = op.get_bind()
    for table_name in _TABLES:
        Base.metadata.tables[table_name].create(bind, checkfirst=True)


def downgrade() -> None:
    bind = op.get_bind()
    for table_name in reversed(_TABLES):
        Base.metadata.tables[table_name].drop(bind, checkfirst=True)
