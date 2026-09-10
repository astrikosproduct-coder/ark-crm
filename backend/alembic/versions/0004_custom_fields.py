"""Dynamic admin-field values: custom_fields JSONB

Revision ID: 0004_custom_fields
Revises: 0003_picklist_sort
Create Date: 2026-09-03

Gives every business table somewhere to put the values of fields created
through the Administration Module, and records on each field definition which
of the two storage modes it uses.

    custom_fields JSONB NOT NULL DEFAULT '{}'::jsonb
        on accounts, contacts, leads, opportunities, deals

    field_metadata.storage  VARCHAR(20) NOT NULL DEFAULT 'column'

WHY A COLUMN PER TABLE AND NOT A CUSTOM-VALUES TABLE
-----------------------------------------------------
A single `custom_values(record_type, record_id, api_name, value)` table would
need a polymorphic foreign key — a text column naming another table — which
PostgreSQL cannot enforce. Deleting a Lead would silently orphan its rows, and
every read of a record would become a second query and a join. A JSONB column
travels with the row: it is deleted with it, restored with it, and read in the
same SELECT.

WHAT THIS MIGRATION DOES NOT DO
--------------------------------
It does not move a single register field into JSONB. All 566 keep their typed
columns, their foreign keys and their constraints. The two storage modes coexist
by design; neither is being migrated into the other.

Existing rows get '{}' from the server default. No typed column is read,
written, altered or dropped, so no existing record data can change — the
NOT NULL is safe precisely because the DEFAULT fills every existing row in the
same statement.

THE BACKFILL
------------
Every row that exists when this runs is a register field, so 'column' is the
right default for all of them. The two exceptions are fields an admin had
already created through the Round-6 UI before this migration existed — they are
identified by origin='Administration', which is the only evidence available
retrospectively, and switched to 'custom_fields'. From here on the API sets
`storage` explicitly at creation and nothing infers it from origin again.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = '0004_custom_fields'
down_revision: Union[str, Sequence[str], None] = '0003_picklist_sort'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

BUSINESS_TABLES = ("accounts", "contacts", "leads", "opportunities", "deals")


def upgrade() -> None:
    for table in BUSINESS_TABLES:
        op.add_column(
            table,
            sa.Column(
                "custom_fields",
                postgresql.JSONB(astext_type=sa.Text()),
                server_default=sa.text("'{}'::jsonb"),
                nullable=False,
            ),
        )

    op.add_column(
        "field_metadata",
        sa.Column(
            "storage",
            sa.String(length=20),
            server_default="column",
            nullable=False,
        ),
    )

    op.execute(
        """
        UPDATE field_metadata
           SET storage = 'custom_fields'
         WHERE origin = 'Administration'
        """
    )


def downgrade() -> None:
    # Dropping custom_fields DESTROYS every admin-created field value on every
    # record. Alembic will do it because a downgrade was asked for explicitly;
    # nothing in the application ever calls this path, and no Administration
    # action can reach it.
    op.drop_column("field_metadata", "storage")
    for table in reversed(BUSINESS_TABLES):
        op.drop_column(table, "custom_fields")
