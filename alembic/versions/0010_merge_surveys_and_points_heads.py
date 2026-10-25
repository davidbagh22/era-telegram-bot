"""Merge surveys and points idempotency heads."""

revision = "0010_merge_heads"
down_revision = ("0009_points_idempotency", "0003_admin_surveys")
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
