"""Deal registrations carry a Currency

Revision ID: 0028_registration_currency
Revises: 0027_lead_defaults
Create Date: 2026-09-15

Estimated Value on a registration had no currency, so a partner's AED 18m
claim and a USD 18m claim were the same number (15 Sep 2026).

deal_registrations.currency is the storage for the SAME register field a Lead
uses — the pipeline Currency definition and its leads__currency picklist. The
placement is registration_currency_metadata.py, run after this.

Existing registrations get USD: their Estimated Value was typed into a box
that showed "$". A registration created without one gets USD on save
(routers/registrations.py), as a Lead does.

DEPLOY ORDER:
    alembic upgrade head
    python registration_currency_metadata.py --apply     (places the field and publishes)
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0028_registration_currency"
down_revision = "0027_lead_defaults"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("deal_registrations", sa.Column("currency", sa.String(length=3), nullable=True))
    filled = op.get_bind().execute(sa.text("UPDATE deal_registrations SET currency = 'USD' WHERE currency IS NULL")).rowcount
    if filled:
        print(f"  Currency set to USD on {filled} existing registration(s).")


def downgrade() -> None:
    op.drop_column("deal_registrations", "currency")
