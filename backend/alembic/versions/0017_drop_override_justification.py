"""Drop override_justification — the reason lives in the register's own field

Revision ID: 0017_drop_override_justification
Revises: 0016_progression
Create Date: 2026-09-11

0016 added a bespoke `override_justification` text column to leads,
opportunities and deals, alongside a dedicated chip UI to collect it. That
duplicated a mechanism the register already had:
`probability_override_justification` — a real Conditional field on all three
modules, stage-scoped 'sticky', already wired into the read-only Reasons &
Justifications panel since Phase A3.

The duplication was the bug, not a stage on the way to the right design: a
reviewer checking "why was this overridden" had two places to look, and
whichever one nobody thought to check would read as if no reason was ever
given. Overriding Probability % now writes into the register's own field
instead — through the ordinary custom_fields path every other per-stage value
already uses (`probability_override_justification__s<stage>`) — so the reason
appears exactly where the panel already knows to show it. See
app/progression.py's Part 4 section docstring for the full account.

is_overridden, overridden_by and overridden_date are NOT touched here. They
carry no text and cannot duplicate a register field the way a free-text
justification column could; is_overridden is now DERIVED at evaluation time
rather than stamped, but the column still holds it for the API to read.

THE COLUMN HELD LIVE DATA. This migration does not try to salvage it into
probability_override_justification's custom_fields JSONB, because a
mechanical copy would land it at whatever stage a record happened to be at
during the migration, not the stage the override was actually made at — which
is not information this column recorded and cannot be reconstructed. Anything
in it is printed to the migration log before the column is dropped, so an
operator can transcribe it by hand if it matters.
"""

from alembic import op
import sqlalchemy as sa

revision = "0017_drop_override_justification"
down_revision = "0016_progression"
branch_labels = None
depends_on = None

#: Table -> its primary key column, for the log line below. Irregular on
#: purpose — "opportunities"[:-1] is "opportunitie", not "opportunity".
PIPELINE_TABLES = {
    "leads": "lead_id",
    "opportunities": "opportunity_id",
    "deals": "deal_id",
}


def upgrade() -> None:
    conn = op.get_bind()

    for table, id_column in PIPELINE_TABLES.items():
        rows = conn.execute(
            sa.text(
                f"SELECT {id_column}, override_justification FROM {table} "
                f"WHERE override_justification IS NOT NULL AND override_justification <> ''"
            )
        ).fetchall()
        for record_id, text_value in rows:
            print(f"  [0017] {table}.{record_id}: {text_value!r} (not migrated — see docstring)")

    for table in PIPELINE_TABLES:
        op.drop_column(table, "override_justification")


def downgrade() -> None:
    for table in PIPELINE_TABLES:
        op.add_column(table, sa.Column("override_justification", sa.Text(), nullable=True))
