"""Metadata model v2, enforced: one owning module per field; field_metadata retired

Revision ID: 0039_metadata_v2_enforce
Revises: 0038_metadata_v2_schema
Create Date: 2026-09-25

Runs AFTER metadata_v2.py. DEPLOY ORDER (see 0038):

    alembic upgrade 0038_metadata_v2_schema
    python metadata_v2.py --apply
    alembic upgrade head                      <- this

1. THE GUARANTEE. Every field has exactly one owning module: at most one
   placement per definition that is not read-through. metadata_v2.py creates
   the index itself; this makes it part of the schema, and refuses to run if
   the register was never moved (a definition still in the shared `pipeline`
   scope), naming the script to run first.

2. field_metadata IS DROPPED. It was the Round 6 register table, replaced by
   field_definitions + field_placements in Round 7 (0008), whose docstring
   promised "a later migration retires field_metadata, once parity has been
   proved on a real database and Administration has been exercised". Both
   happened long ago; nothing has read it since, and v2 made its rows wrong
   (its module_key still files registrations under partners). Its 568 rows are
   in the database dump taken before this migration — that dump, not a
   downgrade, is how to get them back.

   Not a business table: this is register metadata, and dropping it is the
   retirement the architecture planned, not Administration issuing DDL.

Downgrade removes the index and recreates field_metadata EMPTY, with its old
shape, so earlier migrations can run their own downgrades. It cannot restore
the rows.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0039_metadata_v2_enforce"
down_revision = "0038_metadata_v2_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    left = bind.execute(
        sa.text("SELECT count(*) FROM field_definitions WHERE scope_key = 'pipeline'")
    ).scalar()
    if left:
        raise RuntimeError(
            f"{left} fields are still in the shared pipeline scope. Run "
            f"`python metadata_v2.py --apply` first (see 0038's DEPLOY ORDER)."
        )
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_field_placements_one_owner "
        "ON field_placements (definition_id) WHERE value_mode <> 'read_through'"
    )
    op.execute("DROP TABLE IF EXISTS field_metadata")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_field_placements_one_owner")
    op.execute(
        """
        CREATE TABLE field_metadata (
            id serial PRIMARY KEY,
            module_key varchar(60) NOT NULL REFERENCES modules(module_key),
            section_id integer NOT NULL REFERENCES sections(id),
            api_name varchar(120) NOT NULL,
            label varchar(200) NOT NULL,
            field_type varchar(30) NOT NULL,
            sort_order integer NOT NULL,
            max_length integer,
            picklist_key varchar(120) REFERENCES picklists(picklist_key),
            lookup_target varchar(60),
            lookup_filter text,
            values_note text,
            capture_stage integer,
            capture_any_stage boolean NOT NULL DEFAULT false,
            mandatory_from integer,
            blocks_transition varchar(40),
            requirement varchar(20) NOT NULL,
            origin varchar(120) NOT NULL,
            source_ref varchar(120),
            description text NOT NULL,
            use_case text NOT NULL,
            required_on_skip boolean,
            visibility_condition text,
            condition text,
            computed_formula text,
            status varchar(10) NOT NULL DEFAULT 'active',
            deleted_at timestamptz,
            deleted_by varchar(20) REFERENCES users(user_id) ON DELETE SET NULL,
            extension jsonb,
            created_at timestamptz NOT NULL,
            updated_at timestamptz NOT NULL,
            storage varchar(20) NOT NULL DEFAULT 'column',
            CONSTRAINT uq_field_metadata_qref UNIQUE (module_key, section_id, api_name),
            CONSTRAINT ck_field_metadata_description_max_length
                CHECK (description IS NULL OR char_length(description) <= 255)
        )
        """
    )
    for column in ("api_name", "module_key", "picklist_key", "section_id"):
        op.execute(f"CREATE INDEX ix_field_metadata_{column} ON field_metadata ({column})")
