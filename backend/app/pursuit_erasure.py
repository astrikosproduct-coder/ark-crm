"""
DELETING A PURSUIT FOR GOOD — the whole chain, in one transaction.

Decided 21 Sep 2026 (asked for by the head of the business): an ordinary
delete refuses a record that has moved on — a Lead that became an Opportunity,
an Opportunity that became a Deal, anything in a pursuit group. This is the
other door: it erases the pursuit from wherever it was opened.

    plan(db, record_id)             what would go, and what would only be unlinked
    erase(db, record_id, actor)     does it, or nothing (one transaction)

WHAT GOES
---------
Every record of the chain (app/pursuits.py::chain): the Lead, the Opportunity
it became, the Deal(s) — a paid-pilot Deal included — with their child rows
(the foreign keys cascade), their stage history, their conversion records and
their audit entries.

WHAT STAYS, UNLINKED
--------------------
* Accounts and Contacts — other pursuits share them.
* Partner registrations — they belong to the partner; the link is cleared.
* Pursuit groups — the pursuit leaves through app/pursuits.py::remove_member,
  so the group's primary moves on and a group left with one member dissolves.
* Another pursuit opened off one of these Deals as an expansion — kept, its
  Parent Deal cleared.

ONE LINE OF HISTORY IS KEPT: who erased which records, and when — so a figure
that changes on the Dashboard can be explained.

WHO: every role (decided 21 Sep 2026) — the same as every other business
action in V1. The person must type the pursuit's name to confirm.
"""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import delete, or_, select, update
from sqlalchemy.orm import Session

from .audit import record_audit
from .messages import refusal
from .models import (
    AuditLog,
    Conversion,
    Deal,
    DealRegistration,
    Lead,
    Opportunity,
    PursuitGroup,
    StageTransition,
)
from .pursuits import chain, id_of, member_roots, record_by_id, remove_member, root_of

NAME = {"leads": "opportunity_name", "opportunities": "opportunity_name", "deals": "deal_name"}
NOUN = {"leads": "Lead", "opportunities": "Opportunity", "deals": "Deal"}


def _name(module: str, record: Any, db: Session) -> str:
    value = getattr(record, NAME[module], None)
    if not value and module == "opportunities" and record.parent_lead:
        lead = db.get(Lead, record.parent_lead)
        value = lead.opportunity_name if lead else None
    return value or id_of(module, record)


def _members(db: Session, record_id: str) -> tuple[str, list[tuple[str, Any]]]:
    module, record = record_by_id(db, record_id)
    root = root_of(db, module, record)
    records = chain(db, root)
    return root, records or [(module, record)]


def plan(db: Session, record_id: str) -> dict:
    root, records = _members(db, record_id)
    ids = [id_of(m, r) for m, r in records]
    root_module, root_record = records[0]

    groups = {r.pursuit_group for _, r in records if getattr(r, "pursuit_group", None)}
    registrations = list(
        db.scalars(
            select(DealRegistration.registration_id).where(
                or_(
                    DealRegistration.linked_lead.in_(ids),
                    DealRegistration.registration_id.in_(
                        [r.partner_deal_registration for m, r in records if m == "leads" and r.partner_deal_registration]
                    ),
                )
            )
        )
    )
    deal_ids = [i for i in ids if i.startswith("DEAL-")]
    expansions = (
        list(db.scalars(select(Lead.lead_id).where(Lead.parent_deal.in_(deal_ids), Lead.lead_id.notin_(ids))))
        if deal_ids
        else []
    )
    history = db.scalar(
        select(StageTransition.id).where(StageTransition.record_id.in_(ids)).limit(1)
    ) is not None
    return {
        "root": root,
        "name": _name(root_module, root_record, db),
        "records": [
            {"module": m, "noun": NOUN[m], "id": id_of(m, r), "name": _name(m, r, db), "stage": _stage(m, r)}
            for m, r in records
        ],
        "has_history": history,
        "groups": sorted(groups),
        "registrations": sorted(registrations),
        "expansion_leads": sorted(expansions),
    }


def _stage(module: str, record: Any) -> str | None:
    return getattr(record, "deal_stage" if module == "deals" else "project_stage", None)


def erase(db: Session, record_id: str, *, confirm: str | None, actor: str) -> dict:
    info = plan(db, record_id)
    if (confirm or "").strip().casefold() != info["name"].strip().casefold():
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            refusal(
                "CONFIRM_NAME_MISMATCH",
                "The name you typed doesn't match this pursuit.",
                [f"Type {info['name']} exactly to delete it."],
            ),
        )

    _, records = _members(db, record_id)
    ids = [id_of(m, r) for m, r in records]
    deal_ids = [i for i in ids if i.startswith("DEAL-")]
    opp_ids = [i for i in ids if i.startswith("OPP-")]
    lead_ids = [i for i in ids if i.startswith("LEAD-")]

    # Out of every group first, through the group's own rules.
    for group_id in info["groups"]:
        group = db.get(PursuitGroup, group_id)
        if group is None:
            continue
        member = info["root"]
        remaining = [r for r in member_roots(db, group_id) if r != info["root"]]
        remove_member(
            db, group, member, actor=actor, reason="Pursuit deleted for good.",
            new_primary=remaining[0] if remaining else None,
        )
    db.flush()

    # Unlink what stays.
    if lead_ids:
        db.execute(update(DealRegistration).where(DealRegistration.linked_lead.in_(lead_ids)).values(linked_lead=None))
        db.execute(update(Lead).where(Lead.parent_pursuit.in_(lead_ids), Lead.lead_id.notin_(lead_ids)).values(parent_pursuit=None))
    if deal_ids:
        db.execute(update(Lead).where(Lead.parent_deal.in_(deal_ids), Lead.lead_id.notin_(lead_ids)).values(parent_deal=None))

    # The history of these records, then the records — last to first, so no
    # foreign key is left pointing at a row already gone.
    db.execute(delete(StageTransition).where(StageTransition.record_id.in_(ids)))
    db.execute(delete(Conversion).where(or_(Conversion.source_id.in_(ids), Conversion.target_id.in_(ids))))
    db.execute(delete(AuditLog).where(AuditLog.record_id.in_(ids)))
    if deal_ids:
        db.execute(delete(Deal).where(Deal.deal_id.in_(deal_ids)))
    if opp_ids:
        db.execute(delete(Opportunity).where(Opportunity.opportunity_id.in_(opp_ids)))
    if lead_ids:
        db.execute(delete(Lead).where(Lead.lead_id.in_(lead_ids)))

    root_module = records[0][0]
    record_audit(
        db,
        module=root_module,
        record_id=info["root"],
        action="deleted",
        actor=actor,
        changed_fields=[f"pursuit deleted for good: {info['name']}", *ids],
    )
    db.commit()
    return info
