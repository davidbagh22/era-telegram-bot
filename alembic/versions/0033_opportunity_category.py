"""Opportunity "направление результата" category.

DELTA ToR §16: the Opportunities filter sheet's "Направление результата"
facet needs real backing data -- additive column on the existing
PartnerInitiative catalog, not a second Opportunity model.

Revision ID: 0033_opportunity_category
Revises: 0032_media_library_dest_type
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0033_opportunity_category"
down_revision = "0032_media_library_dest_type"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "partner_initiatives",
        sa.Column("category", sa.String(length=32), nullable=True),
    )
    op.create_index("ix_partner_initiatives_category", "partner_initiatives", ["category"])


def downgrade() -> None:
    op.drop_index("ix_partner_initiatives_category", table_name="partner_initiatives")
    op.drop_column("partner_initiatives", "category")
