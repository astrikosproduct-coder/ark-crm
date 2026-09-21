"""
Which pipeline records still point at an Account or a Contact.

WHY THE SERVER HAS TO ASK
-------------------------
Every lookup from the pipeline onto an Account or a Contact is a foreign key
declared ON DELETE SET NULL. So if one of those rows is deleted, PostgreSQL
does not refuse: it silently blanks the End Client, Partner, Primary Contact or
demo attendee on every Lead and Deal that named it. No error, and the value is
gone.

Until 21 Sep 2026 the only guard against that was the browser's delete dialog,
because when these endpoints were written Leads and Deals still lived in the
browser store and the server could not see them. They have been PostgreSQL
tables since Phase 1, so the server checks here, and a delete that would blank
a reference is refused whatever called it.

Opportunities hold none of these columns — they read their counterparties
through their Lead — so a Lead reference covers them.
"""

from __future__ import annotations

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from .models import Deal, Lead, LeadDemoAttendee, PursuitGroup

#: Lead and Deal columns that can hold an account id.
LEAD_ACCOUNT_COLUMNS = ("end_client", "customer_partner_si", "consultant_specifier", "pre_bid_alliance_partner")
DEAL_ACCOUNT_COLUMNS = ("end_client", "customer_partner_si")


def _ids(db: Session, key, model, columns: tuple[str, ...], record_id: str) -> set[str]:
    clause = or_(*(getattr(model, c) == record_id for c in columns))
    return set(db.scalars(select(key).where(clause)))


def records_naming_account(db: Session, account_id: str) -> list[str]:
    """Lead, Deal and pursuit-group ids that name this account, sorted."""
    found = _ids(db, Lead.lead_id, Lead, LEAD_ACCOUNT_COLUMNS, account_id)
    found |= _ids(db, Deal.deal_id, Deal, DEAL_ACCOUNT_COLUMNS, account_id)
    # A demo attendee's organisation belongs to the Lead the demo was for.
    found |= _ids(db, LeadDemoAttendee.lead_id, LeadDemoAttendee, ("organisation",), account_id)
    found |= _ids(db, PursuitGroup.group_id, PursuitGroup, ("end_client",), account_id)
    return sorted(found)


def records_naming_contact(db: Session, contact_id: str) -> list[str]:
    """Lead ids that name this contact — as Primary Contact or a demo attendee."""
    found = _ids(db, Lead.lead_id, Lead, ("primary_contact",), contact_id)
    found |= _ids(db, LeadDemoAttendee.lead_id, LeadDemoAttendee, ("attendee",), contact_id)
    return sorted(found)
