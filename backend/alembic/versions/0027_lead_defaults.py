"""Leads created without a status or a currency get Open and USD

Revision ID: 0027_lead_defaults
Revises: 0026_expected_timeline_date
Create Date: 2026-09-14

From 14 Sep 2026 every new lead starts Open, in USD, as its own primary
pursuit, unless the user says otherwise — applied in create_lead
(app/routers/leads.py), so a lead created from a deal registration or as an
expansion off a Deal gets the same as "+ New Lead".

Before that, only the New Lead page filled in a status, and nothing filled in
a currency. A lead with no currency counts as $0 in every pipeline total
(app/revenue.py flags it no_currency), so leads created from a registration
were missing from the dashboard's open pipeline.

This backfills the leads that missed it: a blank status becomes OPEN, a blank
currency becomes USD at FX rate 1. Only blanks are filled — a value somebody
chose is never overwritten — and the upgrade prints every lead it touched.
is_primary_pursuit is not touched: a secondary is secondary because its
pursuit group says so, not because of a default.

A blank Opportunity status is filled the same way (Deals already were).

The downgrade leaves the values in place. They are valid, and which ones were
blank is not recorded anywhere to put back.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0027_lead_defaults"
down_revision = "0026_expected_timeline_date"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    rows = bind.execute(
        sa.text(
            "SELECT lead_id, opportunity_name, lead_status, currency FROM leads "
            "WHERE coalesce(btrim(lead_status), '') = '' OR coalesce(btrim(currency), '') = '' "
            "ORDER BY lead_id"
        )
    ).all()

    bind.execute(sa.text("UPDATE leads SET lead_status = 'OPEN' WHERE coalesce(btrim(lead_status), '') = ''"))
    bind.execute(
        sa.text(
            "UPDATE leads SET currency = 'USD', fx_rate_at_entry = coalesce(fx_rate_at_entry, 1) "
            "WHERE coalesce(btrim(currency), '') = ''"
        )
    )
    opportunities = bind.execute(
        sa.text("UPDATE opportunities SET lead_status = 'OPEN' WHERE coalesce(btrim(lead_status), '') = ''")
    ).rowcount

    if rows:
        print(f"  Filled blanks on {len(rows)} lead(s):")
        for lead_id, name, lead_status, currency in rows:
            filled = [
                label
                for label, was in (("status Open", lead_status), ("currency USD", currency))
                if not (was or "").strip()
            ]
            print(f"    {name or lead_id}: {', '.join(filled)}")
    if opportunities:
        print(f"  Filled a blank status on {opportunities} opportunity(ies).")


def downgrade() -> None:
    pass
