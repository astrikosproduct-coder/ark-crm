"""
A CONVERSION HAPPENS IN ONE TRANSACTION, AND NEVER TWICE — decided 15 Sep 2026.

    Lead -> Opportunity     POST /opportunities with parent_lead
    Opportunity -> Deal     POST /deals with parent_opportunity
    Lead -> Deal            POST /deals with parent_lead alone (pre-split data)

The create of the new record IS the conversion. In the same commit the source
becomes CONVERTED and the Conversion row is written.

It used to be three requests from the browser — create the Opportunity, mark
the Lead converted, log the conversion — and the third failed on every move: it
demanded a `timestamp` the server stamps anyway. By then the Opportunity existed
and the Lead was already converted, but the dialog said "Nothing was changed",
so people pressed Confirm again and got a second Opportunity. In one
transaction a failure really does change nothing.

NEVER TWICE. A source that has already become an Opportunity or Deal, or is
already Converted, is refused with 409 ALREADY_CONVERTED naming what it became.
The source row is locked first (SELECT ... FOR UPDATE), so two presses that
reach the server together cannot both pass the check.
"""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from .audit import record_audit
from .changes import diff
from .clock import now_utc
from .models import Conversion, Deal, Lead, Opportunity
from .progression import CONVERTED, PILOT_STATUS

#: How a source row is found, per module.
SOURCES: dict[str, tuple[Any, str]] = {
    "leads": (Lead, "lead_id"),
    "opportunities": (Opportunity, "opportunity_id"),
}

NOUN = {"leads": "lead", "opportunities": "opportunity"}
BECAME = {"opportunities": "an Opportunity", "deals": "a Deal"}

#: Payload keys that ARE the conversion rather than a value carried across.
NOT_COPIED = frozenset(
    {"parent_lead", "parent_opportunity", "lead_status", "project_stage", "deal_stage", "conversion_note"}
)


def _became(db: Session, source_module: str, source_id: str) -> tuple[str, str] | None:
    """The record this source already turned into, if any."""
    if source_module == "leads":
        opp = db.scalar(select(Opportunity.opportunity_id).where(Opportunity.parent_lead == source_id))
        if opp:
            return "opportunities", opp
        # A paid-pilot Deal is its own revenue, not the pursuit's conversion.
        deal = db.scalar(
            select(Deal.deal_id).where(
                Deal.parent_lead == source_id,
                Deal.parent_opportunity.is_(None),
                Deal.lead_status != PILOT_STATUS,
            )
        )
        return ("deals", deal) if deal else None
    deal = db.scalar(select(Deal.deal_id).where(Deal.parent_opportunity == source_id))
    return ("deals", deal) if deal else None


def begin_conversion(db: Session, source_module: str, source_id: str | None) -> Any | None:
    """
    Lock the source and refuse a second conversion. Call BEFORE the new record
    is added. Returns the locked source, or None when there is no such record
    (the router's own link check reports that).
    """
    if not source_id:
        return None
    model, id_column = SOURCES[source_module]
    source = db.scalar(select(model).where(getattr(model, id_column) == source_id).with_for_update())
    if source is None:
        return None

    became = _became(db, source_module, source_id)
    if became is None and source.lead_status != CONVERTED:
        return source

    target_module, target_id = became if became else (None, None)
    what = f"a {BECAME[target_module]}" if became else "another record"
    raise HTTPException(
        status.HTTP_409_CONFLICT,
        {
            "code": "ALREADY_CONVERTED",
            "message": f"This {NOUN[source_module]} was already converted to {what}. Nothing new was created.",
            "target_module": target_module,
            "target_id": target_id,
        },
    )


def complete_conversion(
    db: Session,
    *,
    source_module: str,
    source: Any,
    target_module: str,
    target_id: str,
    sent: set[str],
    note: str | None,
    actor: str,
) -> None:
    """Mark the source converted and write the Conversion row. Before the router commits."""
    _, id_column = SOURCES[source_module]
    source_id = getattr(source, id_column)
    stamp = now_utc()

    was = source.lead_status
    source.lead_status = CONVERTED
    source.modified_by = actor
    source.modified_date = stamp
    record_audit(
        db,
        module=source_module,
        record_id=source_id,
        action="updated",
        actor=actor,
        changed_fields=["lead_status"],
        changed=diff({"lead_status": was}, {"lead_status": CONVERTED}),
    )

    from .routers.conversions import _next_conversion_id  # local: routers import this module

    db.add(
        Conversion(
            reference_id=_next_conversion_id(db),
            source_module=source_module,
            source_id=source_id,
            target_module=target_module,
            target_id=target_id,
            copied_fields=sorted(sent - NOT_COPIED),
            note=note or f"{source_id} converted to {BECAME[target_module]}, {target_id}.",
            actor=actor,
            timestamp=stamp,
        )
    )
