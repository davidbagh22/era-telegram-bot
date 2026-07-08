"""Seed default partners."""

from datetime import datetime

from alembic import op
import sqlalchemy as sa

revision = "0004_seed_default_partners"
down_revision = "0003_partners"
branch_labels = None
depends_on = None

PARTNERS = (
    ("Дом Москвы в Ереване", "Партнёрская площадка для культурных, образовательных и молодёжных инициатив ЭРА."),
    ("Русский Дом в Ереване", "Партнёр для культурных, гуманитарных, образовательных и общественных проектов."),
    ("Московский Дом соотечественника", "Партнёр по программам для молодых соотечественников, развитию связей и возможностям роста."),
    ("КСОРС Армении", "Партнёрская структура для координации инициатив соотечественников и общественных проектов."),
)


def upgrade() -> None:
    # partners.created_at / updated_at are TIMESTAMP WITHOUT TIME ZONE in the
    # current schema, so seed data must use offset-naive datetimes for asyncpg.
    now = datetime.utcnow()
    table = sa.table(
        "partners",
        sa.column("name", sa.String),
        sa.column("description", sa.Text),
        sa.column("status", sa.String),
        sa.column("is_active", sa.Boolean),
        sa.column("is_archived", sa.Boolean),
        sa.column("created_at", sa.DateTime),
        sa.column("updated_at", sa.DateTime),
    )
    op.bulk_insert(
        table,
        [
            {
                "name": name,
                "description": description,
                "status": "partner",
                "is_active": True,
                "is_archived": False,
                "created_at": now,
                "updated_at": now,
            }
            for name, description in PARTNERS
        ],
    )


def downgrade() -> None:
    names = ", ".join(repr(name) for name, _ in PARTNERS)
    op.execute(f"DELETE FROM partners WHERE name IN ({names})")
