"""Field placement model: field_definitions + field_placements

Revision ID: 0008_placements
Revises: 0007_capture_stage
Create Date: 2026-09-04

Creates the two tables that replace field_metadata, and an archive copy of
field_metadata as it stood before the rebuild.

WHAT THIS MIGRATION DOES NOT DO
--------------------------------
It does not drop field_metadata, does not populate the new tables, and does not
issue one byte of DDL against a business table. Those are three separate things
and they fail in three different ways, so they are three separate steps:

    0008 (this)          create the new schema, archive the old rows
    rebuild_metadata.py  populate the new tables from the frontend-effective
                         presentation, then prove parity against it
    later migration      retire field_metadata, once parity has been proved on
                         a real database and Administration has been exercised

Rolling this back drops two empty tables and an archive. Nothing an existing
screen reads is touched, which is the property that makes the rebuild safe to
attempt at all.

THE ARCHIVE
-----------
`field_metadata_pre_round7` is a plain CREATE TABLE AS SELECT — every column,
every row, including the deleted ones and their deleted_at/deleted_by stamps.
It carries no constraints and no foreign keys on purpose: it is a photograph,
not a schema, and a photograph that refuses to load because a user was later
removed would be worse than useless.

This is the second of two recovery paths. The first is a published
metadata_versions snapshot, which rebuild_metadata.py takes before it writes.
They are independent: one is the API's own view of the configuration, the other
is the raw table. Neither depends on the new code being correct.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0008_placements"
down_revision = "0007_capture_stage"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ------------------------------------------------------------ archive
    #
    # IF NOT EXISTS so a re-run after a partial failure is not itself a
    # failure. The archive is written once and never updated: if it already
    # exists, it is already the photograph of the pre-rebuild state, and
    # overwriting it with a half-migrated table would destroy the only copy.
    op.execute(
        "CREATE TABLE IF NOT EXISTS field_metadata_pre_round7 AS "
        "SELECT * FROM field_metadata"
    )

    # ------------------------------------------------- field_definitions
    op.create_table(
        "field_definitions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        # The uniqueness scope. 'pipeline' for leads+opportunities+deals, which
        # is what makes One-Time Revenue ONE row rather than two.
        sa.Column("scope_key", sa.String(length=120), nullable=False),
        sa.Column("api_name", sa.String(length=120), nullable=False),
        sa.Column("label", sa.String(length=200), nullable=False),
        # ---- value shape: identical on every placement
        sa.Column("field_type", sa.String(length=30), nullable=False),
        sa.Column("max_length", sa.Integer(), nullable=True),
        sa.Column("picklist_key", sa.String(length=120), nullable=True),
        sa.Column("lookup_target", sa.String(length=60), nullable=True),
        sa.Column("lookup_filter", sa.Text(), nullable=True),
        sa.Column("computed_formula", sa.Text(), nullable=True),
        # ---- documentation
        sa.Column("values_note", sa.Text(), nullable=True),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("use_case", sa.Text(), nullable=False, server_default=""),
        # ---- provenance. origin_module must never decide what Administration
        # ---- shows; that is field_placements.module_key's job.
        sa.Column("origin", sa.String(length=120), nullable=False),
        sa.Column("source_ref", sa.String(length=120), nullable=True),
        sa.Column("origin_module", sa.String(length=60), nullable=True),
        # ---- logical delete of the concept
        sa.Column(
            "status", sa.String(length=10), nullable=False, server_default="active"
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_by", sa.String(length=20), nullable=True),
        sa.Column("extension", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["picklist_key"], ["picklists.picklist_key"]),
        sa.ForeignKeyConstraint(["origin_module"], ["modules.module_key"]),
        sa.ForeignKeyConstraint(
            ["deleted_by"], ["users.user_id"], ondelete="SET NULL"
        ),
        # THE GUARANTEE. One canonical definition per concept per scope, with
        # deleted rows included — creating a second copy of a deleted field is
        # refused and the API says to restore it instead.
        sa.UniqueConstraint("scope_key", "api_name", name="uq_field_definitions_scope"),
        # The target of field_placements' composite FK. This is what stops the
        # denormalised placement api_name drifting from its definition.
        sa.UniqueConstraint("id", "api_name", name="uq_field_definitions_id_api_name"),
    )
    op.create_index(
        "ix_field_definitions_scope_key", "field_definitions", ["scope_key"]
    )
    op.create_index("ix_field_definitions_api_name", "field_definitions", ["api_name"])
    op.create_index(
        "ix_field_definitions_picklist_key", "field_definitions", ["picklist_key"]
    )
    # Administration's Deleted tab, and every resolver query, filters on status
    # first. Partial rather than plain: 'active' is ~99% of the table, so an
    # index over the whole column would never be chosen for it.
    op.create_index(
        "ix_field_definitions_deleted",
        "field_definitions",
        ["status"],
        postgresql_where=sa.text("status = 'deleted'"),
    )

    # -------------------------------------------------- field_placements
    op.create_table(
        "field_placements",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("definition_id", sa.Integer(), nullable=False),
        # Denormalised so that uq_field_placements_qname can be written at all;
        # held honest by the composite FK below.
        sa.Column("api_name", sa.String(length=120), nullable=False),
        # WHERE THE USER SEES THIS FIELD.
        sa.Column("module_key", sa.String(length=60), nullable=False),
        sa.Column("scope_key", sa.String(length=120), nullable=False),
        sa.Column("section_id", sa.Integer(), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("label_override", sa.String(length=200), nullable=True),
        # ---- stage gating, which genuinely differs per module
        sa.Column("capture_stage", sa.Integer(), nullable=True),
        sa.Column(
            "capture_any_stage", sa.Boolean(), nullable=False, server_default="false"
        ),
        sa.Column("mandatory_from", sa.Integer(), nullable=True),
        sa.Column("blocks_transition", sa.String(length=40), nullable=True),
        sa.Column("requirement", sa.String(length=20), nullable=False),
        sa.Column("required_on_skip", sa.Boolean(), nullable=True),
        sa.Column("visibility_condition", sa.Text(), nullable=True),
        sa.Column("condition", sa.Text(), nullable=True),
        # ---- the value layer
        sa.Column(
            "value_mode", sa.String(length=20), nullable=False, server_default="own"
        ),
        sa.Column(
            "value_locked", sa.Boolean(), nullable=False, server_default="false"
        ),
        sa.Column("editable", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("storage", sa.String(length=20), nullable=True),
        # ---- logical delete, from this module only
        sa.Column(
            "status", sa.String(length=10), nullable=False, server_default="active"
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_by", sa.String(length=20), nullable=True),
        sa.Column(
            "deleted_by_cascade", sa.Boolean(), nullable=False, server_default="false"
        ),
        sa.Column("provenance", sa.String(length=30), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id"),
        # RESTRICT, not CASCADE: deleting a definition row out from under its
        # placements is not a thing this system does. Deletion is logical, and
        # a hard delete that silently took placements with it would be exactly
        # the destructive behaviour the whole model refuses.
        sa.ForeignKeyConstraint(
            ["definition_id"], ["field_definitions.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["module_key"], ["modules.module_key"]),
        sa.ForeignKeyConstraint(["section_id"], ["sections.id"]),
        sa.ForeignKeyConstraint(
            ["deleted_by"], ["users.user_id"], ondelete="SET NULL"
        ),
        # api_name may not drift from the definition it points at.
        sa.ForeignKeyConstraint(
            ["definition_id", "api_name"],
            ["field_definitions.id", "field_definitions.api_name"],
            name="fk_field_placements_definition_api_name",
        ),
        # One definition appears at most once per module/shape.
        sa.UniqueConstraint(
            "definition_id", "module_key", "scope_key", name="uq_field_placements_one"
        ),
        # Two DIFFERENT definitions may not collide on one record shape — a
        # record keys on api_name alone, so one would overwrite the other. This
        # is moduleSplit.ts's load-time containment assertion, moved into the
        # database where it cannot be skipped.
        sa.UniqueConstraint(
            "module_key", "scope_key", "api_name", name="uq_field_placements_qname"
        ),
        # A read-through placement stores nothing and is not editable.
        sa.CheckConstraint(
            "value_mode <> 'read_through' OR (editable = false AND storage IS NULL)",
            name="ck_field_placements_read_through",
        ),
        sa.CheckConstraint(
            "value_mode = 'read_through' OR storage IS NOT NULL",
            name="ck_field_placements_storage_required",
        ),
        sa.CheckConstraint(
            "value_mode IN ('own', 'read_through', 'carry_forward')",
            name="ck_field_placements_value_mode",
        ),
        sa.CheckConstraint(
            "storage IS NULL OR storage IN ('column', 'custom_fields')",
            name="ck_field_placements_storage",
        ),
        # value_locked is meaningless unless something was carried.
        sa.CheckConstraint(
            "value_locked = false OR value_mode = 'carry_forward'",
            name="ck_field_placements_value_locked",
        ),
    )
    op.create_index(
        "ix_field_placements_definition_id", "field_placements", ["definition_id"]
    )
    op.create_index("ix_field_placements_api_name", "field_placements", ["api_name"])
    op.create_index("ix_field_placements_scope_key", "field_placements", ["scope_key"])
    op.create_index("ix_field_placements_section_id", "field_placements", ["section_id"])
    # THE hot query: "every active field of this module, in form order". It is
    # what Administration lists, what the resolver builds fields.json from, and
    # what the custom-field writer checks on every save.
    op.create_index(
        "ix_field_placements_module_active",
        "field_placements",
        ["module_key", "status", "sort_order"],
    )
    # Carry-forward resolution walks "which placements on this module carry a
    # value from their parent", once per record creation.
    op.create_index(
        "ix_field_placements_carry",
        "field_placements",
        ["module_key", "value_mode"],
        postgresql_where=sa.text("value_mode = 'carry_forward'"),
    )


def downgrade() -> None:
    # The archive is deliberately NOT dropped. Downgrading is how somebody
    # backs out of a rebuild that went wrong, and that is precisely the moment
    # the photograph of the old rows matters most. It is a plain table with no
    # dependencies; whoever is sure they no longer need it can drop it by hand.
    op.drop_index("ix_field_placements_carry", table_name="field_placements")
    op.drop_index("ix_field_placements_module_active", table_name="field_placements")
    op.drop_index("ix_field_placements_section_id", table_name="field_placements")
    op.drop_index("ix_field_placements_scope_key", table_name="field_placements")
    op.drop_index("ix_field_placements_api_name", table_name="field_placements")
    op.drop_index("ix_field_placements_definition_id", table_name="field_placements")
    op.drop_table("field_placements")

    op.drop_index("ix_field_definitions_deleted", table_name="field_definitions")
    op.drop_index("ix_field_definitions_picklist_key", table_name="field_definitions")
    op.drop_index("ix_field_definitions_api_name", table_name="field_definitions")
    op.drop_index("ix_field_definitions_scope_key", table_name="field_definitions")
    op.drop_table("field_definitions")
