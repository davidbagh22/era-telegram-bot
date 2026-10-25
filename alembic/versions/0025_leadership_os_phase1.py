"""Leadership OS phase 1 — data model + scoped appointment permissions
(2026-08 Leadership OS ToR, phase 1 of 8). Additive only:

- offices / user_offices gain new nullable/defaulted columns (ToR sections
  13, 83). Existing rows keep permission_template=[] so no office gains
  elevated auto-permissions on backfill (ToR section 99).
- new tables: position_applications, leadership_goals, leadership_reports,
  leadership_recurring_templates, leadership_attention_items (ToR section
  81's data model).

Does not touch PermissionGrant, Department, Direction, or any existing
authorization check.

Originally built as 0018 off 0017_task_deliveries (the head at the time);
renumbered to 0025 and rebased onto 0024_referrals after merging main,
which had independently grown its own 0018-0024 chain (PR #235,
organization health analytics) in the meantime -- keeps a single linear
head instead of a two-way fork.

Verified: upgrade from 0017 on a fresh DB, and downgrade back to 0017, both
green on SQLite and structurally identical to Postgres' plain ALTER TABLE
path. (A downgrade-then-immediate-reupgrade cycle can hit a SQLite-only
batch/FK-recreate quirk unrelated to this data model; Postgres, which never
needs table recreation for ADD/DROP COLUMN, is unaffected -- not a concern
for the actual upgrade-forward deploy path.)
"""

import sqlalchemy as sa
from alembic import op

revision = "0025_leadership_os_phase1"
down_revision = "0024_referrals"
branch_labels = None
depends_on = None


def _table_exists(table_name: str) -> bool:
    return table_name in sa.inspect(op.get_bind()).get_table_names()


def _columns(table_name: str) -> set[str]:
    return {c["name"] for c in sa.inspect(op.get_bind()).get_columns(table_name)}


def _is_sqlite() -> bool:
    return op.get_bind().dialect.name == "sqlite"


# Plain add_column/drop_column (no batch_alter_table) for every column that
# is nullable/server-defaulted and carries no FK, since SQLite and Postgres
# both apply those as direct ALTER TABLE statements -- no table recreate, so
# no need to name offices/user_offices' pre-existing anonymous constraints
# (e.g. the 0001-era UniqueConstraint on user_offices) just to touch them.
#
# The two FK columns (reports_to_office_id, ended_by) are dialect-branched:
# Postgres (production) always applies a FK-carrying ADD COLUMN directly, no
# recreate involved, so it gets the real constraint. SQLite's behavior here
# depends on how offices/user_offices happened to be created (Base.metadata.
# create_all() in 0001 vs. an explicit op.create_table elsewhere in this
# table's history) -- sometimes it demands the batch/recreate ("copy the
# whole table") path, which then needs a name for every reflected
# constraint including anonymous ones from other migrations -- exactly the
# kind of cross-migration coupling this migration shouldn't have to reach
# into. SQLite doesn't enforce FKs by default anyway (the `foreign_keys`
# pragma is off unless a connection opts in), so skipping the DB-level
# constraint there and relying on the ORM-level relationship in models.py
# loses nothing SQLite was actually checking.


def _add_fk_column(table_name: str, column: sa.Column) -> None:
    if _is_sqlite():
        # Drop the inline FK entirely rather than fight SQLite's batch mode
        # for a constraint no SQLite connection here enforces regardless.
        op.add_column(table_name, sa.Column(column.name, column.type, nullable=column.nullable))
        return
    op.add_column(table_name, column)


def upgrade() -> None:
    offices_cols = _columns("offices")
    if "scope_id" not in offices_cols:
        op.add_column("offices", sa.Column("scope_id", sa.Integer(), nullable=True))
    if "reports_to_office_id" not in offices_cols:
        _add_fk_column(
            "offices",
            sa.Column("reports_to_office_id", sa.Integer(), sa.ForeignKey("offices.id"), nullable=True),
        )
    if "responsibilities" not in offices_cols:
        op.add_column(
            "offices", sa.Column("responsibilities", sa.JSON(), nullable=False, server_default="[]")
        )
    if "permission_template" not in offices_cols:
        op.add_column(
            "offices",
            sa.Column("permission_template", sa.JSON(), nullable=False, server_default="[]"),
        )
    if "analytics_scope" not in offices_cols:
        op.add_column("offices", sa.Column("analytics_scope", sa.String(length=32), nullable=True))
    if "default_term_days" not in offices_cols:
        op.add_column("offices", sa.Column("default_term_days", sa.Integer(), nullable=True))
    if "probation_days" not in offices_cols:
        op.add_column("offices", sa.Column("probation_days", sa.Integer(), nullable=True))
    if "max_holders" not in offices_cols:
        op.add_column("offices", sa.Column("max_holders", sa.Integer(), nullable=True))
    if "application_enabled" not in offices_cols:
        op.add_column(
            "offices",
            sa.Column("application_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        )
    if "application_deadline" not in offices_cols:
        op.add_column(
            "offices", sa.Column("application_deadline", sa.DateTime(timezone=True), nullable=True)
        )
    if "requirements" not in offices_cols:
        op.add_column("offices", sa.Column("requirements", sa.Text(), nullable=True))
    if "kpi_template" not in offices_cols:
        op.add_column(
            "offices", sa.Column("kpi_template", sa.JSON(), nullable=False, server_default="{}")
        )
    if "recurring_task_template" not in offices_cols:
        op.add_column(
            "offices",
            sa.Column("recurring_task_template", sa.JSON(), nullable=False, server_default="{}"),
        )
    if "is_public" not in offices_cols:
        op.add_column(
            "offices", sa.Column("is_public", sa.Boolean(), nullable=False, server_default=sa.true())
        )

    user_offices_cols = _columns("user_offices")
    if "appointment_type" not in user_offices_cols:
        op.add_column(
            "user_offices",
            sa.Column(
                "appointment_type", sa.String(length=16), nullable=False, server_default="regular"
            ),
        )
    if "probation_ends_at" not in user_offices_cols:
        op.add_column("user_offices", sa.Column("probation_ends_at", sa.Date(), nullable=True))
    if "ended_by" not in user_offices_cols:
        _add_fk_column(
            "user_offices", sa.Column("ended_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True)
        )
    if "end_reason" not in user_offices_cols:
        op.add_column("user_offices", sa.Column("end_reason", sa.String(length=255), nullable=True))
    if "scope_type" not in user_offices_cols:
        op.add_column("user_offices", sa.Column("scope_type", sa.String(length=32), nullable=True))
    if "scope_id" not in user_offices_cols:
        op.add_column("user_offices", sa.Column("scope_id", sa.Integer(), nullable=True))

    if not _table_exists("position_applications"):
        op.create_table(
            "position_applications",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("office_id", sa.Integer(), sa.ForeignKey("offices.id"), nullable=False),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("status", sa.String(length=16), nullable=False, server_default="draft"),
            sa.Column("motivation", sa.Text(), nullable=True),
            sa.Column("plan", sa.Text(), nullable=True),
            sa.Column("availability", sa.String(length=100), nullable=True),
            sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("reviewed_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("review_note", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        )
        op.create_index(
            "ix_position_applications_office_id", "position_applications", ["office_id"]
        )
        op.create_index("ix_position_applications_user_id", "position_applications", ["user_id"])
        op.create_index("ix_position_applications_status", "position_applications", ["status"])

    if not _table_exists("leadership_goals"):
        op.create_table(
            "leadership_goals",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("owner_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column(
                "office_assignment_id", sa.Integer(), sa.ForeignKey("user_offices.id"), nullable=True
            ),
            sa.Column("scope_type", sa.String(length=32), nullable=False, server_default="global"),
            sa.Column("scope_id", sa.Integer(), nullable=True),
            sa.Column("period_type", sa.String(length=16), nullable=False, server_default="month"),
            sa.Column("period_start", sa.Date(), nullable=False),
            sa.Column("period_end", sa.Date(), nullable=False),
            sa.Column("title", sa.String(length=255), nullable=False),
            sa.Column("metric", sa.String(length=150), nullable=True),
            sa.Column("target", sa.Float(), nullable=True),
            sa.Column("progress", sa.Float(), nullable=False, server_default="0"),
            sa.Column("status", sa.String(length=16), nullable=False, server_default="active"),
            sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        )
        op.create_index("ix_leadership_goals_owner_id", "leadership_goals", ["owner_id"])
        op.create_index("ix_leadership_goals_status", "leadership_goals", ["status"])

    if not _table_exists("leadership_reports"):
        op.create_table(
            "leadership_reports",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("owner_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column(
                "office_assignment_id", sa.Integer(), sa.ForeignKey("user_offices.id"), nullable=True
            ),
            sa.Column("scope_type", sa.String(length=32), nullable=False, server_default="global"),
            sa.Column("scope_id", sa.Integer(), nullable=True),
            sa.Column("period_start", sa.Date(), nullable=False),
            sa.Column("period_end", sa.Date(), nullable=False),
            sa.Column("status", sa.String(length=16), nullable=False, server_default="green"),
            sa.Column("main_result", sa.Text(), nullable=True),
            sa.Column("blocker_type", sa.String(length=32), nullable=True),
            sa.Column("blocker_note", sa.Text(), nullable=True),
            sa.Column("next_priorities", sa.JSON(), nullable=False, server_default="[]"),
            sa.Column("needs_help", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        )
        op.create_index("ix_leadership_reports_owner_id", "leadership_reports", ["owner_id"])

    if not _table_exists("leadership_recurring_templates"):
        op.create_table(
            "leadership_recurring_templates",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("office_id", sa.Integer(), sa.ForeignKey("offices.id"), nullable=True),
            sa.Column("title", sa.String(length=255), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("frequency", sa.String(length=16), nullable=False, server_default="monthly"),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        )
        op.create_index(
            "ix_leadership_recurring_templates_office_id",
            "leadership_recurring_templates",
            ["office_id"],
        )
        op.create_index(
            "ix_leadership_recurring_templates_is_active",
            "leadership_recurring_templates",
            ["is_active"],
        )

    if not _table_exists("leadership_attention_items"):
        op.create_table(
            "leadership_attention_items",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("type", sa.String(length=50), nullable=False),
            sa.Column("severity", sa.String(length=16), nullable=False, server_default="medium"),
            sa.Column("scope_type", sa.String(length=32), nullable=False, server_default="global"),
            sa.Column("scope_id", sa.Integer(), nullable=True),
            sa.Column("owner_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("responsible_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("status", sa.String(length=16), nullable=False, server_default="open"),
            sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("resolution", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        )
        op.create_index("ix_leadership_attention_items_type", "leadership_attention_items", ["type"])
        op.create_index(
            "ix_leadership_attention_items_status", "leadership_attention_items", ["status"]
        )


def downgrade() -> None:
    for table in (
        "leadership_attention_items",
        "leadership_recurring_templates",
        "leadership_reports",
        "leadership_goals",
        "position_applications",
    ):
        if _table_exists(table):
            op.drop_table(table)

    # Plain drop_column throughout: on Postgres, DROP COLUMN works directly
    # even for the two FK-carrying columns (no batch/recreate involved on
    # that dialect at all); on SQLite, those two never got a DB-level FK in
    # the first place (see _add_fk_column in upgrade()), so SQLite's
    # FK-column drop restriction never applies here either.
    user_offices_cols = _columns("user_offices")
    for col in (
        "scope_id",
        "scope_type",
        "probation_ends_at",
        "appointment_type",
        "end_reason",
        "ended_by",
    ):
        if col in user_offices_cols:
            op.drop_column("user_offices", col)

    offices_cols = _columns("offices")
    for col in (
        "is_public",
        "recurring_task_template",
        "kpi_template",
        "requirements",
        "application_deadline",
        "application_enabled",
        "max_holders",
        "probation_days",
        "default_term_days",
        "analytics_scope",
        "permission_template",
        "responsibilities",
        "scope_id",
        "reports_to_office_id",
    ):
        if col in offices_cols:
            op.drop_column("offices", col)
