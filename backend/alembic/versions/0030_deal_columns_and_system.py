"""Deals: five columns the register promised, and the standard system fields

Revision ID: 0030_deal_columns_and_system
Revises: 0029_bid_dates_are_dates
Create Date: 2026-09-16

ONE DEFECT, SEVEN TIMES: a field_placements row saying storage='column',
status='active', with no column behind it. The API drops what is typed, the
record comes back empty, and the screen gave no hint — worse than a missing
field, because the form said the value had been taken.

FIVE BUSINESS COLUMNS

    overall_rag, next_milestone, next_milestone_date    Health & Forecast
    po_number, payment_schedule_confirmed               STAGE 7 - CLOSE

Leads and Opportunities have carried the three health columns since the split;
Deals never had them, which is why app/routers/dashboard.py read a Deal's RAG
out of custom_fields and always found nothing. The Close pair became urgent
when a converted Deal started opening at Stage 7: two of that section's three
fields could not save.

THE SYSTEM SECTION

Deals stored created_by_date / modified_by_date while the register ALSO placed
created_by / created_date / modified_by / modified_date on the module. Six rows
on screen, four of them permanently blank, and no record of WHO created or last
changed a Deal anywhere but audit_log. spec/module_split.json already carries
this as a register correction ("rename in the workbook"); it is applied here.

    created_by_date  -> created_date     values preserved
    modified_by_date -> modified_date    values preserved
    created_by, modified_by              added, FK users ON DELETE SET NULL

The two new actor columns are backfilled from audit_log, which has held the
answer all along: the first `created` row names who created the Deal, the last
row of any kind names who touched it last. A Deal with no audit row keeps NULL
rather than being attributed to whoever runs this.

DEPLOY ORDER

    alembic upgrade head
    python deal_register_alignment.py --apply    (placements, then publish)
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0030_deal_columns_and_system"
down_revision = "0029_bid_dates_are_dates"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("deals", sa.Column("overall_rag", sa.String(length=10), nullable=True))
    op.add_column("deals", sa.Column("next_milestone", sa.String(length=200), nullable=True))
    op.add_column("deals", sa.Column("next_milestone_date", sa.Date(), nullable=True))
    op.add_column("deals", sa.Column("po_number", sa.String(length=50), nullable=True))
    op.add_column(
        "deals",
        sa.Column(
            "payment_schedule_confirmed",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )

    op.alter_column("deals", "created_by_date", new_column_name="created_date")
    op.alter_column("deals", "modified_by_date", new_column_name="modified_date")

    op.add_column("deals", sa.Column("created_by", sa.String(length=20), nullable=True))
    op.add_column("deals", sa.Column("modified_by", sa.String(length=20), nullable=True))
    op.create_foreign_key(
        "deals_created_by_fkey", "deals", "users", ["created_by"], ["user_id"], ondelete="SET NULL"
    )
    op.create_foreign_key(
        "deals_modified_by_fkey", "deals", "users", ["modified_by"], ["user_id"], ondelete="SET NULL"
    )

    # Who, from the only place that ever recorded it.
    op.execute(
        """
        UPDATE deals d
           SET created_by = first_audit.actor
          FROM (
                SELECT record_id,
                       actor,
                       ROW_NUMBER() OVER (
                           PARTITION BY record_id ORDER BY "timestamp" ASC, id ASC
                       ) AS rn
                  FROM audit_log
                 WHERE record_module = 'deals'
                   AND action = 'created'
                   AND actor IS NOT NULL
               ) AS first_audit
         WHERE first_audit.record_id = d.deal_id
           AND first_audit.rn = 1
        """
    )
    op.execute(
        """
        UPDATE deals d
           SET modified_by = last_audit.actor
          FROM (
                SELECT record_id,
                       actor,
                       ROW_NUMBER() OVER (
                           PARTITION BY record_id ORDER BY "timestamp" DESC, id DESC
                       ) AS rn
                  FROM audit_log
                 WHERE record_module = 'deals'
                   AND actor IS NOT NULL
               ) AS last_audit
         WHERE last_audit.record_id = d.deal_id
           AND last_audit.rn = 1
        """
    )


def downgrade() -> None:
    op.drop_constraint("deals_modified_by_fkey", "deals", type_="foreignkey")
    op.drop_constraint("deals_created_by_fkey", "deals", type_="foreignkey")
    op.drop_column("deals", "modified_by")
    op.drop_column("deals", "created_by")

    op.alter_column("deals", "modified_date", new_column_name="modified_by_date")
    op.alter_column("deals", "created_date", new_column_name="created_by_date")

    op.drop_column("deals", "payment_schedule_confirmed")
    op.drop_column("deals", "po_number")
    op.drop_column("deals", "next_milestone_date")
    op.drop_column("deals", "next_milestone")
    op.drop_column("deals", "overall_rag")
