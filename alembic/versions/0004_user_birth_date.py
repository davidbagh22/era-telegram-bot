"""Add user birth date if it is missing."""

import sqlalchemy as sa
from alembic import op

revision = "0004_user_birth_date"
down_revision = "0003_management_goals_contacts"
branch_labels = None
depends_on = None


def _has_column(table_name: str, column_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    return any(column["name"] == column_name for column in inspector.get_columns(table_name))


def _has_index(table_name: str, index_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    return any(index["name"] == index_name for index in inspector.get_indexes(table_name))


def upgrade() -> None:
    if not _has_column("users", "birth_date"):
        op.add_column("users", sa.Column("birth_date", sa.Date(), nullable=True))
    if not _has_index("users", "ix_users_birth_date"):
        op.create_index("ix_users_birth_date", "users", ["birth_date"])


def downgrade() -> None:
    if _has_index("users", "ix_users_birth_date"):
        op.drop_index("ix_users_birth_date", table_name="users")
    if _has_column("users", "birth_date"):
        op.drop_column("users", "birth_date")
