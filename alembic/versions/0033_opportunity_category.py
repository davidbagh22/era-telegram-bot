"""Opportunity "направление результата" category.

DELTA ToR §16: the Opportunities filter sheet's "Направление результата"
facet needs real backing data -- additive column on the existing
PartnerInitiative catalog, not a second Opportunity model.

Revision ID: 0033_opportunity_category
Revises: 0032_media_library_dest_type

Idempotent like 0030-0032: 0001_initial calls the current
Base.metadata.create_all(), so a fresh database may already have this
column (and its index) by the time this revision runs.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0033_opportunity_category"
down_revision = "0032_media_library_dest_type"
branch_labels = None
depends_on = None


def _columns(table_name: str) -> set[str]:
    return {column["name"] for column in sa.inspect(op.get_bind()).get_columns(table_name)}


def _index_names(table_name: str) -> set[str]:
    return {index["name"] for index in sa.inspect(op.get_bind()).get_indexes(table_name) if index.get("name")}


def upgrade() -> None:
    if "category" not in _columns("partner_initiatives"):
        op.add_column(
            "partner_initiatives",
            sa.Column("category", sa.String(length=32), nullable=True),
        )
    if "ix_partner_initiatives_category" not in _index_names("partner_initiatives"):
        op.create_index("ix_partner_initiatives_category", "partner_initiatives", ["category"])


def downgrade() -> None:
    if "ix_partner_initiatives_category" in _index_names("partner_initiatives"):
        op.drop_index("ix_partner_initiatives_category", table_name="partner_initiatives")
    if "category" in _columns("partner_initiatives"):
        op.drop_column("partner_initiatives", "category")
