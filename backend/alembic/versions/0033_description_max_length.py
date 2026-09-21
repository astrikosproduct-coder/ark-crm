"""A field's description is capped at 255 characters

Revision ID: 0033_description_max_length
Revises: 0032_feedback
Create Date: 2026-09-18

WHY A CAP AT ALL

A field description is read in four places, and three of them have no room to
grow: the ⓘ tooltip beside a field label on every form, row 4 of the Excel
import template ("what to enter"), the export workbook, and the Administration
field list. A paragraph renders fine in the fourth and is unreadable in the
first three -- a tooltip that needs scrolling has stopped being a tooltip.

The cap is therefore a LAYOUT contract, not a storage saving. 255 characters is
about three plain sentences, which is what the house style asks for: what the
field is, when to fill it, and what counts. Anything that genuinely needs more
is either two fields or a decision that belongs in the Playbook.

WHY A CHECK AND NOT varchar(255)

Changing the type would rewrite both tables and, more to the point, would make
an over-long value fail with Postgres's own wording -- "value too long for type
character varying(255)" -- which is a database sentence, not something a person
editing a field in Administration should ever be shown. A named CHECK leaves the
column as text, costs no rewrite, and the constraint name is recognisable enough
for the API layer to turn into a real message. The real guard is Pydantic's
max_length in app/schemas_metadata.py, which refuses the write before it reaches
here with wording from app/messages.py; this is the floor under it, for anything
that writes to the table by another route.

SAFE TO APPLY AS-IS

Checked on the live database before writing this: 585 field_definitions rows and
568 field_metadata rows, 0 over the cap, longest 196 characters. Nothing is
truncated and nothing needs backfilling. The downgrade simply drops the
constraints.

NULLs pass the check by design -- field_metadata.description is nullable on some
rows and an absent description is a gap for the register pass to close, not a
constraint violation to fail a migration on.
"""

from __future__ import annotations

from alembic import op

revision = "0033_description_max_length"
down_revision = "0032_feedback"
branch_labels = None
depends_on = None

#: Three plain sentences. See the note above before changing it — the number is
#: a promise to the tooltip and the spreadsheet template, not a storage limit.
MAX_DESCRIPTION = 255

TABLES = ("field_definitions", "field_metadata")


def upgrade() -> None:
    for table in TABLES:
        op.create_check_constraint(
            f"ck_{table}_description_max_length",
            table,
            f"description IS NULL OR char_length(description) <= {MAX_DESCRIPTION}",
        )


def downgrade() -> None:
    for table in TABLES:
        op.drop_constraint(f"ck_{table}_description_max_length", table, type_="check")
