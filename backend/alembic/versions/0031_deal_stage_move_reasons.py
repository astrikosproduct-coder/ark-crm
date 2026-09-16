"""Deals keep their skip and reversal reasons, as Leads and Opportunities do

Revision ID: 0031_deal_stage_move_reasons
Revises: 0030_deal_columns_and_system
Create Date: 2026-09-16

Leads and Opportunities store the reason for their latest stage skip and their
latest stage reversal on the record itself (String(500) each), written by the
Update Stage dialog in the same save as the move, and listed read-only in the
Reasons & Justifications panel on the Details tab. Deals stored neither: the
dialog had no field to write, so a Deal's reason existed only on its row in
stage_transitions and the panel had nothing to show.

On instruction (16 Sep 2026) Deals now work the same way. The transitions table
stays the full history — one reason per move — and these two columns hold the
latest of each, exactly as on the other two modules.

BACKFILLED from stage_transitions: each Deal takes the reason of its most
recent skip and of its most recent reversal, so a Deal that was already moved
back (DEAL-00002, 8 -> 7) shows its reason on day one rather than a blank.

DEPLOY ORDER

    alembic upgrade head
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0031_deal_stage_move_reasons"
down_revision = "0030_deal_columns_and_system"
branch_labels = None
depends_on = None

BACKFILL = """
    UPDATE deals d
       SET {column} = latest.reason
      FROM (
            SELECT record_id,
                   reason,
                   ROW_NUMBER() OVER (
                       PARTITION BY record_id ORDER BY "timestamp" DESC, id DESC
                   ) AS rn
              FROM stage_transitions
             WHERE module = 'deals'
               AND {flag}
               AND reason IS NOT NULL
               AND btrim(reason) <> ''
           ) AS latest
     WHERE latest.record_id = d.deal_id
       AND latest.rn = 1
"""


def upgrade() -> None:
    op.add_column("deals", sa.Column("stage_skip_reason", sa.String(length=500), nullable=True))
    op.add_column("deals", sa.Column("stage_reversal_reason", sa.String(length=500), nullable=True))
    op.execute(BACKFILL.format(column="stage_skip_reason", flag="is_skip"))
    op.execute(BACKFILL.format(column="stage_reversal_reason", flag="is_reversal"))


def downgrade() -> None:
    op.drop_column("deals", "stage_reversal_reason")
    op.drop_column("deals", "stage_skip_reason")
