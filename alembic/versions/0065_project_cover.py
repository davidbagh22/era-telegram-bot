"""Add optional cover image bytes to projects."""
from alembic import op
import sqlalchemy as sa

revision = "0065_project_cover"
down_revision = "0064_telegram_analytics"
branch_labels = None
depends_on = None


def upgrade():
    inspector = sa.inspect(op.get_bind())
    columns = {column["name"] for column in inspector.get_columns("projects")}
    if "cover_content_type" not in columns:
        op.add_column("projects", sa.Column("cover_content_type", sa.String(100), nullable=True))
    if "cover_bytes" not in columns:
        op.add_column("projects", sa.Column("cover_bytes", sa.LargeBinary(), nullable=True))


def downgrade():
    inspector = sa.inspect(op.get_bind())
    columns = {column["name"] for column in inspector.get_columns("projects")}
    if "cover_bytes" in columns:
        op.drop_column("projects", "cover_bytes")
    if "cover_content_type" in columns:
        op.drop_column("projects", "cover_content_type")
