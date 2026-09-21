"""Deals record the day the PO was received — the day a deal is won

Revision ID: 0034_deal_po_received_date
Revises: 0033_description_max_length
Create Date: 2026-09-21

WHY A NEW FIELD

The Dashboard's Won tile has rendered a permanent dash since 18 Sep 2026,
because Won is defined as the day the PO arrives and no field recorded that
day. PO / LOI Reference is text — it says an award document exists, not when
it came. Booking Date is when finance booked the order in the ERP, which lags
the PO and would move a deal won on 30 June into July. A stage move records
when someone updated the CRM, not when the client decided.

Decided 21 Sep 2026: a date field beside PO / LOI Reference, captured at
Stage 7 and Mandatory on the same terms as its neighbours.

Indexed because the Dashboard filters every Won figure by it.

Nothing to backfill — no existing Deal is guessed a date, and production
starts empty.

DEPLOY ORDER — both, or the column exists and no form shows it:
    alembic upgrade head
    python po_received_date_metadata.py --apply     (places the field and publishes)
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0034_deal_po_received_date"
down_revision = "0033_description_max_length"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("deals", sa.Column("po_received_date", sa.Date(), nullable=True))
    op.create_index("ix_deals_po_received_date", "deals", ["po_received_date"])


def downgrade() -> None:
    op.drop_index("ix_deals_po_received_date", table_name="deals")
    op.drop_column("deals", "po_received_date")
