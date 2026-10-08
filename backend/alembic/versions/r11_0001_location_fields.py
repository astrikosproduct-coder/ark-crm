"""Region -> Country -> State: the columns, and the maps that link them

Revision ID: r11_0001_location_fields
Revises: 0037_required_on_create
Create Date: 2026-10-06

Release 1.1 (decided 6 Oct 2026). Accounts gain Country and State; Leads keep
their Country (free text until now, a dropdown from this release) and gain a
State beside it.

The maps — which Countries a Region offers, which States a Country offers —
are two tables, per module, shaped the way Zoho's Map Dependency Fields is:
one row per (parent field, child field) pair, and one row per allowed
(parent value, child value). Setup edits them in Phase 2; until then
release_1_1_location_metadata.py loads them from backend/data/locations.json
and publishes, like any other register change.

NOT numbered 0038: the phase-2 branch already has a 0038. When phase-2 takes
this release, its first migration revises this one instead of 0037.

DEPLOY ORDER: dump -> alembic upgrade head -> release_1_1_fields_metadata.py
--apply -> release_1_1_location_metadata.py --apply -> start the new code.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "r11_0001_location_fields"
down_revision = "0037_required_on_create"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("accounts", sa.Column("country", sa.String(10), nullable=True))
    op.add_column("accounts", sa.Column("state", sa.String(10), nullable=True))
    op.add_column("leads", sa.Column("state", sa.String(10), nullable=True))

    # app/main.py's create_all makes any table the models name and the database
    # lacks — so new code started before this migration leaves these two
    # behind, EMPTY (it happened while building this release). Empty, they are
    # dropped and made properly; holding rows, they are a real problem, and
    # the migration stops rather than guess.
    bind = op.get_bind()
    existing = set(sa.inspect(bind).get_table_names())
    for table in ("field_dependency_values", "field_dependencies"):
        if table in existing:
            rows = bind.execute(sa.text(f"SELECT count(*) FROM {table}")).scalar()
            if rows:
                raise RuntimeError(f"{table} already exists and holds {rows} rows — stop and investigate")
            op.drop_table(table)

    op.create_table(
        "field_dependencies",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("module_key", sa.String(60), sa.ForeignKey("modules.module_key", ondelete="CASCADE"), nullable=False),
        sa.Column("parent_field", sa.String(120), nullable=False),
        sa.Column("child_field", sa.String(120), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("module_key", "child_field", name="uq_field_dependencies_child"),
        sa.CheckConstraint("parent_field <> child_field", name="ck_field_dependencies_not_self"),
    )
    op.create_table(
        "field_dependency_values",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "dependency_id",
            sa.Integer(),
            sa.ForeignKey("field_dependencies.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("parent_value", sa.String(120), nullable=False),
        sa.Column("child_value", sa.String(120), nullable=False),
        sa.UniqueConstraint("dependency_id", "parent_value", "child_value", name="uq_field_dependency_values"),
    )


def downgrade() -> None:
    op.drop_table("field_dependency_values")
    op.drop_table("field_dependencies")
    op.drop_column("leads", "state")
    op.drop_column("accounts", "state")
    op.drop_column("accounts", "country")
