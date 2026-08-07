"""Add consent_log table — technical foundation for consent auditability.

See docs/DATA_INVENTORY.md section 5 and docs/PRODUCTION_READINESS_AUDIT.md
finding #16. Additive only; does not touch the existing
users.personal_data_consent bool, which remains the field actually
checked anywhere in the app.
"""

import sqlalchemy as sa
from alembic import op

revision = "0014_consent_log"
down_revision = "0013_saved_opportunities"
branch_labels = None
depends_on = None


def _table_exists(table_name: str) -> bool:
    return table_name in sa.inspect(op.get_bind()).get_table_names()


def upgrade() -> None:
    if _table_exists("consent_log"):
        return
    op.create_table(
        "consent_log",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("consent_type", sa.String(length=64), nullable=False),
        sa.Column("policy_version", sa.String(length=32), nullable=False),
        sa.Column("granted", sa.Boolean(), nullable=False),
        sa.Column("source", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_consent_log_user_id", "consent_log", ["user_id"])
    op.create_index("ix_consent_log_consent_type", "consent_log", ["consent_type"])


def downgrade() -> None:
    if not _table_exists("consent_log"):
        return
    op.drop_index("ix_consent_log_consent_type", table_name="consent_log")
    op.drop_index("ix_consent_log_user_id", table_name="consent_log")
    op.drop_table("consent_log")
