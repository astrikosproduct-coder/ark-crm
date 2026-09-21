"""Leads record the paid pilot's PO date, which becomes its Deal's Won date

Revision ID: 0035_lead_pilot_po_received_date
Revises: 0034_deal_po_received_date
Create Date: 2026-09-21

A paid POC/pilot counts as Won (decided 21 Sep 2026), and Won is read from
deals.po_received_date alone. Marking a pilot Paid creates its Deal on the
Lead's save (app/progression.py::spin_off_pilot_deal), so the date has to be
asked for there: Pilot PO Received Date, shown beside Pilot Fee once the pilot
is Paid, and copied into the new Deal. Not defaulted to the day of the click —
that records when someone updated the CRM, not when the PO arrived.

DEPLOY ORDER — both, or the column exists and no form shows it:
    alembic upgrade head
    python pilot_po_received_date_metadata.py --apply
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0035_lead_pilot_po_received_date"
down_revision = "0034_deal_po_received_date"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("leads", sa.Column("pilot_po_received_date", sa.Date(), nullable=True))


def downgrade() -> None:
    op.drop_column("leads", "pilot_po_received_date")
