"""Expected Close Month becomes record state on all three pipeline modules

Revision ID: 0014_close_month
Revises: 0013_anchors
Create Date: 2026-09-10

WHY A COLUMN ON TWO MORE TABLES
--------------------------------
`expected_close_month` was captured at Stage 0 and therefore, by the reassign
rule in spec/module_split.json — a field follows the stage that captures it —
lived only on `leads`, whose range is 0-3. Opportunities (4-6) and Deals (7-9)
had no Expected Close Month at all: the forecast date disappeared at Stage 4
and never came back, which is to say it was absent from RFP, Commercial
Evaluation and Close, the three stages a forecast is actually read at.

It is moving to RECORD STATE — each module keeps its own instance, alongside
project_stage / lead_status / probability_pct. An own-instance placement is a
real value on that module's own record, so the two new placements need two new
columns to hold it. See close_month_record_state.py for the metadata half.

Date, not DateTime, matching leads.expected_close_month exactly. The register
calls this field a MONTH and the seed data writes it as `yyyy-MM`
(spec/seed/leads.json, normalised by src/lib/spec/seed.ts) — the day component
is noise either way, and this migration deliberately does not invent a
different shape for the two new tables than the one the first table has.

THIS IS NOT ADMINISTRATION ISSUING DDL. The rule in CLAUDE.md is that the
Administration field editor must never ALTER a business table — a field created
there lives in `custom_fields` JSONB and is never getting a column. This is the
other case: a register field with storage='column' on a module that did not
have the column yet, added by a backend migration the same way every other
register column arrived.
"""

from alembic import op
import sqlalchemy as sa

revision = "0014_close_month"
down_revision = "0013_anchors"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "opportunities", sa.Column("expected_close_month", sa.Date(), nullable=True)
    )
    op.add_column(
        "deals", sa.Column("expected_close_month", sa.Date(), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("deals", "expected_close_month")
    op.drop_column("opportunities", "expected_close_month")
