"""Add the issued certificate registry; code rollback preserves documents."""
from alembic import op
import sqlalchemy as sa

revision = "0063_certificates"
down_revision = "0062_support_threads"
branch_labels = None
depends_on = None


def upgrade():
    if "certificate_issues" in sa.inspect(op.get_bind()).get_table_names():
        return
    op.create_table("certificate_issues",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("event_id", sa.Integer(), sa.ForeignKey("events.id"), nullable=False),
        sa.Column("portfolio_item_id", sa.Integer(), sa.ForeignKey("portfolio_items.id"), nullable=False),
        sa.Column("basis_key", sa.String(100), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("request_key", sa.String(64), nullable=False, unique=True),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("snapshot", sa.JSON(), nullable=False),
        sa.Column("issued_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_by", sa.Integer(), sa.ForeignKey("users.id")),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.Column("revocation_reason", sa.Text()),
        sa.UniqueConstraint("basis_key", "revision", name="uq_certificate_basis_revision"))
    for col in ("user_id", "event_id", "basis_key"):
        op.create_index(f"ix_certificate_issues_{col}", "certificate_issues", [col])


def downgrade():
    raise RuntimeError("Issued certificates must be retained. Roll back application code without dropping the registry.")
