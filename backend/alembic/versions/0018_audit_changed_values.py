"""audit_log.changed — the before/after values, so history is readable

Revision ID: 0018_audit_changed_values
Revises: 0017_drop_override_justification
Create Date: 2026-09-12

`audit_log.changed_fields` records which api_names a write CARRIED. Because the
record editor PUTs a whole section, a save that altered one field lists twenty,
and no old value is kept at all — so the question a manager actually asks,
"who dropped the probability, and from what", could not be answered from this
table.

This adds one nullable JSONB column holding the diff the write produced:
[{field, from, to}] for scalars, {field, kind: 'list'} for child lists, raw
values rather than labels. See app/changes.py for the shape and why labels are
resolved at render time instead.

NOTHING IS BACKFILLED, AND NOTHING CAN BE. The old values were never stored
anywhere — not in this table, not in a shadow copy, not in the business row,
which holds only the current value. Existing rows keep `changed = NULL`, and
the History tab prints an explicit "field-level history starts <date>" line
rather than rendering a silent gap that would read as "nothing happened".

changed_fields is deliberately NOT dropped. It is cheap, already relied on, and
answers a different question ("was this record touched at all") that the diff
cannot: a write that changed nothing still carried fields.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0018_audit_changed_values"
down_revision = "0017_drop_override_justification"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "audit_log",
        sa.Column("changed", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("audit_log", "changed")
