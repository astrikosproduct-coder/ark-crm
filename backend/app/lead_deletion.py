"""
Deleting a Lead — only while nothing but Accounts and Contacts is linked to it.

    deletion_plan(db, lead)            what stops the delete, and which linked
                                       Accounts and Contacts could go with it
    delete_lead_and_linked(db, lead)   does it, or refuses with 409

WHAT BLOCKS IT (decided 15 Sep 2026)
------------------------------------
Anything linked to the lead other than an Account or a Contact:

    an Opportunity or Deal it became          opportunities / deals.parent_lead
    a deal registration it came from, or      leads.partner_deal_registration,
      that links to it                        deal_registrations.linked_lead
    the Pursuit Group it is a member of       leads.pursuit_group
    the Deal it was opened off as expansion   leads.parent_deal
    a Lead naming it as parent_pursuit        (superseded, still honoured)

Its own rows go with it (demo attendees, feature gaps). Its stage transitions
and audit entries are history and stay.

ACCOUNTS AND CONTACTS ARE NEVER DELETED BY DEFAULT. Asked to (`with_linked`),
each Account and Contact the lead names is deleted only when nothing ELSE uses
it: another lead, a deal, a registration, a pursuit group, or — for an Account
— a contact of its own that is not going too. One still in use is kept, and the
plan says what uses it, so the dialog can say why before anyone confirms.
"""

from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from .audit import record_audit
from .models import (
    Account,
    Contact,
    Deal,
    DealRegistration,
    Lead,
    LeadDemoAttendee,
    Opportunity,
    PursuitGroup,
)
from .pursuits import group_display_name
from .schemas import LEAD_LOOKUPS

#: The lead's own lookup columns into each collection — schemas.LEAD_LOOKUPS,
#: never restated here.
ACCOUNT_COLUMNS = tuple(name for name, collection in LEAD_LOOKUPS.items() if collection == "accounts")
CONTACT_COLUMNS = tuple(name for name, collection in LEAD_LOOKUPS.items() if collection == "contacts")

#: The child list whose rows name a Contact (attendee) and an Account
#: (organisation) — models.LeadDemoAttendee.
DEMO_ATTENDEES = "demo_attendees"


def blockers_of(db: Session, lead: Lead) -> list[dict]:
    """Every record, other than an Account or Contact, linked to this lead."""
    out: list[dict] = []
    for opp in db.scalars(select(Opportunity).where(Opportunity.parent_lead == lead.lead_id)):
        out.append({"kind": "opportunity", "id": opp.opportunity_id, "name": lead.opportunity_name})
    for deal in db.scalars(select(Deal).where(Deal.parent_lead == lead.lead_id)):
        out.append({"kind": "deal", "id": deal.deal_id, "name": deal.deal_name})

    registrations = set(
        db.scalars(select(DealRegistration.registration_id).where(DealRegistration.linked_lead == lead.lead_id))
    )
    if lead.partner_deal_registration:
        registrations.add(lead.partner_deal_registration)
    for registration_id in sorted(registrations):
        registration = db.get(DealRegistration, registration_id)
        if registration is not None:
            out.append({"kind": "registration", "id": registration_id, "name": registration.project_name})

    if lead.pursuit_group:
        group = db.get(PursuitGroup, lead.pursuit_group)
        out.append(
            {
                "kind": "pursuit_group",
                "id": lead.pursuit_group,
                "name": (group_display_name(db, group) if group is not None else None) or lead.pursuit_group,
            }
        )
    if lead.parent_deal:
        deal = db.get(Deal, lead.parent_deal)
        out.append({"kind": "expansion_of", "id": lead.parent_deal, "name": deal.deal_name if deal else None})
    for child in db.scalars(select(Lead).where(Lead.parent_pursuit == lead.lead_id)):
        out.append({"kind": "lead", "id": child.lead_id, "name": child.opportunity_name})
    return out


def _linked(lead: Lead) -> tuple[dict[str, list[str]], dict[str, list[str]]]:
    """account id -> the lead fields naming it, and the same for contacts."""
    accounts: dict[str, list[str]] = {}
    contacts: dict[str, list[str]] = {}

    def add(into: dict[str, list[str]], record_id: str | None, via: str) -> None:
        if record_id and via not in into.setdefault(record_id, []):
            into[record_id].append(via)

    for column in ACCOUNT_COLUMNS:
        add(accounts, getattr(lead, column, None), column)
    for column in CONTACT_COLUMNS:
        add(contacts, getattr(lead, column, None), column)
    for row in lead.demo_attendees:
        add(contacts, row.attendee, DEMO_ATTENDEES)
        add(accounts, row.organisation, DEMO_ATTENDEES)
    return accounts, contacts


def _contact_usage(db: Session, contact_id: str, lead_id: str) -> dict[str, int]:
    leads = set(
        db.scalars(select(Lead.lead_id).where(Lead.primary_contact == contact_id, Lead.lead_id != lead_id))
    )
    leads |= set(
        db.scalars(
            select(LeadDemoAttendee.lead_id).where(
                LeadDemoAttendee.attendee == contact_id, LeadDemoAttendee.lead_id != lead_id
            )
        )
    )
    return {"leads": len(leads)} if leads else {}


def _account_usage(db: Session, account_id: str, lead_id: str, leaving_contacts: set[str]) -> dict[str, int]:
    names_it = or_(*(getattr(Lead, column) == account_id for column in ACCOUNT_COLUMNS))
    leads = set(db.scalars(select(Lead.lead_id).where(names_it, Lead.lead_id != lead_id)))
    leads |= set(
        db.scalars(
            select(LeadDemoAttendee.lead_id).where(
                LeadDemoAttendee.organisation == account_id, LeadDemoAttendee.lead_id != lead_id
            )
        )
    )
    found = {
        "leads": leads,
        "deals": db.scalars(
            select(Deal.deal_id).where(or_(Deal.end_client == account_id, Deal.customer_partner_si == account_id))
        ).all(),
        "registrations": db.scalars(
            select(DealRegistration.registration_id).where(
                or_(DealRegistration.partner == account_id, DealRegistration.end_client == account_id)
            )
        ).all(),
        "pursuit_groups": db.scalars(
            select(PursuitGroup.group_id).where(PursuitGroup.end_client == account_id)
        ).all(),
        "contacts": [
            contact_id
            for contact_id in db.scalars(select(Contact.contact_id).where(Contact.account == account_id))
            if contact_id not in leaving_contacts
        ],
    }
    return {kind: len(items) for kind, items in found.items() if items}


def deletion_plan(db: Session, lead: Lead) -> dict:
    """
    What deleting this lead would mean, computed fresh every time it is asked —
    the delete itself recomputes it rather than trusting what a dialog saw.

    Contacts are judged first, because an Account is only free to go when the
    contacts of its own that stay behind are none.
    """
    linked_accounts, linked_contacts = _linked(lead)

    contacts = []
    for contact_id, via in linked_contacts.items():
        contact = db.get(Contact, contact_id)
        if contact is None:
            continue
        used_by = _contact_usage(db, contact_id, lead.lead_id)
        contacts.append(
            {"id": contact_id, "name": contact.full_name, "via": via, "used_by": used_by, "deletable": not used_by}
        )
    leaving = {c["id"] for c in contacts if c["deletable"]}

    accounts = []
    for account_id, via in linked_accounts.items():
        account = db.get(Account, account_id)
        if account is None:
            continue
        used_by = _account_usage(db, account_id, lead.lead_id, leaving)
        accounts.append(
            {"id": account_id, "name": account.account_name, "via": via, "used_by": used_by, "deletable": not used_by}
        )

    return {
        "lead": lead.lead_id,
        "name": lead.opportunity_name,
        "blockers": blockers_of(db, lead),
        "accounts": accounts,
        "contacts": contacts,
    }


def delete_lead_and_linked(db: Session, lead: Lead, *, actor: str, with_linked: bool) -> dict[str, list[str]]:
    """Delete the lead, and — only when asked — its linked records nothing else uses. Commits."""
    plan = deletion_plan(db, lead)
    if plan["blockers"]:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            {
                "code": "LEAD_HAS_DEPENDENTS",
                "message": "This lead has already moved on in the pipeline, so it can't be deleted.",
                **plan,
            },
        )

    record_audit(db, module="leads", record_id=lead.lead_id, action="deleted", actor=actor)
    db.delete(lead)
    db.flush()

    removed: dict[str, list[str]] = {"contacts": [], "accounts": []}
    if with_linked:
        # Contacts before accounts: an account is only free once its leaving
        # contacts are gone.
        for collection, model in (("contacts", Contact), ("accounts", Account)):
            for entry in plan[collection]:
                if not entry["deletable"]:
                    continue
                record = db.get(model, entry["id"])
                if record is None:
                    continue
                record_audit(db, module=collection, record_id=entry["id"], action="deleted", actor=actor)
                db.delete(record)
                removed[collection].append(entry["id"])
            db.flush()

    db.commit()
    return removed
