"""Metadata model v2, schema: layouts, conversion mappings, global picklists

Revision ID: 0038_metadata_v2_schema
Revises: 0037_required_on_create
Create Date: 2026-09-24

Phase 2, item 2 — "every field is owned by one module", as in Zoho. The
sign-off list is docs/phase2/metadata-v2-step1-signoff.md.

THIS MIGRATION ONLY ADDS. No column is dropped, no row of the register is
moved, and not one byte of DDL touches a business table. Moving the register
into the new shape is `metadata_v2.py`, a script that reads the database it runs
on (production publishes live, so its register can differ from development's).
0039 then enforces the result. DEPLOY ORDER:

    alembic upgrade 0038_metadata_v2_schema
    python metadata_v2.py            (--dry-run first; it prints every move)
    alembic upgrade head

What it adds:

  modules.hidden          kept, but not offered in Administration — a module
                          that is not built yet, or not a module at all
                          (`administration` describes screens that are
                          hand-built). Distinct from `active`.
  modules.setup_parent    where Administration files a module: Deal
                          Registrations under Partners. NOT parent_module,
                          which is the pipeline's record lineage and drives
                          read-through; a registration inherits nothing.
  picklists.is_global     one list shared by fields on several modules
                          (Zoho's Global Sets). A local list serves one field.
  picklist_values.is_system
                          a value the server's own rules read by key — Open,
                          On Hold, Closed Lost… Its label can change; it cannot
                          be retired.
  layouts                 one per module for now ("Standard"). Sections belong
                          to a layout. The hook for several layouts per profile
                          and for record types, both deferred.
  conversion_mappings     what a conversion copies, as rows an administrator
                          can read (and later edit), instead of placement flags
                          and code.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0038_metadata_v2_schema"
down_revision = "0037_required_on_create"
branch_labels = None
depends_on = None


def _clear_premature(table: str) -> None:
    """
    Drop `table` if the application already created it, empty.

    app/main.py runs Base.metadata.create_all() on start-up, so a server
    started on this code BEFORE this migration ran creates `layouts` and
    `conversion_mappings` itself — with no rows, no backfill and no partial
    index. That happened to the development database on 24 Sep 2026 (its
    auto-reloading server picked up the phase-2 branch), and it will happen in
    production if the app is started before `alembic upgrade`. An empty table
    is dropped and created properly here; one with rows stops the migration,
    because rows mean someone used it and a person must look.
    """
    bind = op.get_bind()
    if not sa.inspect(bind).has_table(table):
        return
    rows = bind.execute(sa.text(f"SELECT count(*) FROM {table}")).scalar()
    if rows:
        raise RuntimeError(
            f"{table} already exists with {rows} rows. It was created outside this "
            f"migration. Look at it before running 0038."
        )
    op.drop_table(table)


def upgrade() -> None:
    _clear_premature("conversion_mappings")
    _clear_premature("layouts")
    op.add_column(
        "modules",
        sa.Column("hidden", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "modules",
        sa.Column(
            "setup_parent",
            sa.String(60),
            sa.ForeignKey("modules.module_key", name="fk_modules_setup_parent"),
            nullable=True,
        ),
    )
    op.add_column(
        "picklists",
        sa.Column("is_global", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "picklist_values",
        sa.Column("is_system", sa.Boolean(), nullable=False, server_default=sa.false()),
    )

    # ------------------------------------------------------------- layouts
    op.create_table(
        "layouts",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "module_key",
            sa.String(60),
            sa.ForeignKey("modules.module_key"),
            nullable=False,
            index=True,
        ),
        sa.Column("label", sa.String(120), nullable=False),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("module_key", "label", name="uq_layouts_module_label"),
    )
    op.create_index(
        "uq_layouts_one_default",
        "layouts",
        ["module_key"],
        unique=True,
        postgresql_where=sa.text("is_default"),
    )
    # Every module gets its Standard layout, and every section joins it. A
    # structural backfill, not a register decision: there is exactly one
    # possible answer.
    op.execute(
        "INSERT INTO layouts (module_key, label, is_default) "
        "SELECT module_key, 'Standard', true FROM modules"
    )
    op.add_column(
        "sections",
        sa.Column(
            "layout_id",
            sa.Integer(),
            sa.ForeignKey("layouts.id", name="fk_sections_layout"),
            nullable=True,
            index=True,
        ),
    )
    op.execute(
        "UPDATE sections s SET layout_id = l.id FROM layouts l "
        "WHERE l.module_key = s.module_key AND l.is_default"
    )
    op.alter_column("sections", "layout_id", nullable=False)

    # ------------------------------------------------- conversion mappings
    op.create_table(
        "conversion_mappings",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        # lead_to_opportunity | opportunity_to_deal | lead_to_deal_pilot
        sa.Column("path", sa.String(40), nullable=False),
        # copy: a value is copied once, when the new record is created.
        # system: shown so nothing is hidden — the server sets it (the parent
        # link, the stage, the status, the two percentages).
        sa.Column("kind", sa.String(10), nullable=False, server_default="copy"),
        sa.Column("source_module", sa.String(60), sa.ForeignKey("modules.module_key"), nullable=True),
        sa.Column("source_api_name", sa.String(120), nullable=True),
        sa.Column("target_module", sa.String(60), sa.ForeignKey("modules.module_key"), nullable=False),
        sa.Column("target_api_name", sa.String(120), nullable=False),
        # A copy that is not a plain copy, named so the screen can say so:
        # 'paid_poc_name' appends " — Paid POC". Null for a plain copy.
        sa.Column("transform", sa.String(40), nullable=True),
        # Locked rows are shown greyed and refused by the API: they carry a
        # business rule (the Won date of a paid pilot) that must not be remapped.
        sa.Column("locked", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("note", sa.String(300), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("path", "target_module", "target_api_name", name="uq_conversion_mappings_target"),
        sa.CheckConstraint(
            "path IN ('lead_to_opportunity', 'opportunity_to_deal', 'lead_to_deal_pilot')",
            name="ck_conversion_mappings_path",
        ),
        sa.CheckConstraint("kind IN ('copy', 'system')", name="ck_conversion_mappings_kind"),
        sa.CheckConstraint(
            "kind = 'system' OR (source_module IS NOT NULL AND source_api_name IS NOT NULL)",
            name="ck_conversion_mappings_source",
        ),
    )


def downgrade() -> None:
    op.drop_table("conversion_mappings")
    op.drop_column("sections", "layout_id")
    op.drop_index("uq_layouts_one_default", table_name="layouts")
    op.drop_table("layouts")
    op.drop_column("picklist_values", "is_system")
    op.drop_column("picklists", "is_global")
    op.drop_column("modules", "setup_parent")
    op.drop_column("modules", "hidden")
