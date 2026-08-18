"""Archive the legacy "КСОРС Армении" Partner stub.

0004_seed_default_partners seeded a Partner row named "КСОРС Армении"
(status="partner"). Separately, app/services/recognition_catalog.py seeds
the real, actively-used issuer "КСООРС Армении" (status="issuer", note the
extra "О") with all of its recognized documents attached. The two rows are
conceptually the same organization, but the 0004 stub never had any
PartnerInitiative/PartnerTask attached to it — it is dead data that is still
visible today in the participant-facing "🤝 Партнёры" list
(app/handlers/participant/partners.py) and in both admin partner UIs
(app/handlers/admin/partners_admin.py and the Mini App's PartnersPanel via
GET /partners), duplicating the real issuer.

Renaming it to match "КСООРС Армении" would just create a visible duplicate
card instead of a mislabeled one, and nothing references its row (checked
partner_tasks/partner_initiatives seed data and code), so this archives it
instead of deleting it — recoverable, and every list query in the app
already filters on is_archived.is_(False).

Revision ID: 0033_archive_legacy_ksors_partner
Revises: 0032_timestamp_defaults
"""

from __future__ import annotations

from datetime import datetime

import sqlalchemy as sa

from alembic import op

revision = "0033_archive_legacy_ksors_partner"
down_revision = "0032_timestamp_defaults"
branch_labels = None
depends_on = None

_LEGACY_NAME = "КСОРС Армении"
_ARCHIVE_NOTE = (
    "Archived 2026-08-18: dead duplicate of the 'КСООРС Армении' issuer "
    "seeded by recognition_catalog.seed_recognition_catalog(). Never had "
    "any offers/tasks attached. See migration 0033 for details."
)

partners = sa.table(
    "partners",
    sa.column("id", sa.Integer),
    sa.column("name", sa.String),
    sa.column("status", sa.String),
    sa.column("notes", sa.Text),
    sa.column("is_active", sa.Boolean),
    sa.column("is_archived", sa.Boolean),
    sa.column("updated_at", sa.DateTime),
)


def upgrade() -> None:
    op.execute(
        partners.update()
        .where(partners.c.name == _LEGACY_NAME)
        .where(partners.c.status == "partner")
        .where(partners.c.is_archived.is_(False))
        .values(
            is_active=False,
            is_archived=True,
            notes=_ARCHIVE_NOTE,
            updated_at=datetime.utcnow(),
        )
    )


def downgrade() -> None:
    op.execute(
        partners.update()
        .where(partners.c.name == _LEGACY_NAME)
        .where(partners.c.status == "partner")
        .where(partners.c.notes == _ARCHIVE_NOTE)
        .values(
            is_active=True,
            is_archived=False,
            notes=None,
            updated_at=datetime.utcnow(),
        )
    )
