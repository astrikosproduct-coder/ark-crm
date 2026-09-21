"""
Global search: one box, every live module.

    GET /api/search?q=metro            grouped hits, a few per module
    GET /api/search?q=LEAD-00118       an id goes straight to its record

WHY IT LIVES HERE AND NOT IN EACH MODULE
----------------------------------------
Every list endpoint already searches its own collection through
app/list_query.py, and the header box needs the opposite shape: a little from
each module rather than everything from one. Routing the header through five
list calls would mean five round trips, five sets of pagination the caller has
to ignore, and five chances for one slow module to hold up the whole dropdown.
So this asks one question of the database and answers in the shape the dropdown
draws.

WHAT IT SEARCHES, AND WHAT IT DELIBERATELY DOES NOT
---------------------------------------------------
Names, references and the parties involved -- what a person actually types when
they are trying to reach a record they already know exists. Not notes, not
reasons, not free narrative: a header search that matches the middle of a
paragraph returns a record whose reason for appearing cannot be shown in one
line, and an unexplainable hit is worse than no hit.

AN OPPORTUNITY HAS NO NAME OF ITS OWN
-------------------------------------
It reads opportunity_name and end_client through its parent Lead
(spec/module_split.json read_through), so this joins to the Lead to search
them. Without that join the module would be unsearchable by the only two words
anyone would type for it, which is exactly the bug read_through_rows.py fixed
for the list screens.

A LOOKUP IS SEARCHED BY ITS NAME
--------------------------------
end_client stores ACC-0007; nobody types that. Accounts whose name matches are
resolved first and their ids folded into the same query, so typing "metro"
finds the Leads at Dubai Metro as well as the Account itself. Same rule the
list contract already follows -- the text operators read what a person sees.

PERMISSIONS
-----------
Mounted with PROTECTED like every other data router, so it is exactly as
readable as the modules it searches. When profiles arrive it needs a per-module
filter here too -- see the RBAC note in CLAUDE.md. Until then a signed-in user
with any role can search everything they could already open.
"""

from __future__ import annotations

from typing import Any, Iterable

from fastapi import APIRouter, Depends, Request
from sqlalchemy import String, cast, func, or_, select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Account, Contact, Deal, Lead, Opportunity

router = APIRouter(tags=["search"])

#: Hits returned per module. Small on purpose: the dropdown is a way to REACH a
#: record, not a way to review a list. A group that has more says so, and the
#: footer sends the reader to the module's own list with the same text.
DEFAULT_PER_MODULE = 5
MAX_PER_MODULE = 25

#: Below this, every record in the database would match and the dropdown would
#: be noise. Two characters is enough for an initials-style name.
MIN_QUERY = 2


def _like(text: str) -> str:
    """A contains-match, with the caller's own % and _ treated as literals."""
    escaped = text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def _matching_account_ids(db: Session, term: str) -> list[str]:
    """Accounts whose NAME matches — so a lookup can be searched by its label."""
    return list(
        db.scalars(
            select(Account.account_id).where(Account.account_name.ilike(_like(term), escape="\\"))
        )
    )


def _hit(
    *,
    module: str,
    record_id: Any,
    title: Any,
    subtitle: Any = None,
    meta: Any = None,
) -> dict:
    return {
        "module": module,
        "id": str(record_id),
        # A record with no name yet is still reachable — it shows its reference
        # rather than an empty row the reader cannot click with confidence.
        "title": str(title) if title else str(record_id),
        "subtitle": str(subtitle) if subtitle else None,
        "meta": str(meta) if meta else None,
    }


def _capped(db: Session, query, limit: int) -> tuple[list, int]:
    """One page of rows plus the true total, so a group can say it has more."""
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    return list(db.scalars(query.limit(limit))), total


def _stage_meta(stage: Any, status: Any) -> str | None:
    """"Stage 3 · Open" — the two words that tell a reader which hit is live."""
    parts = [str(p).replace("_", " ").title() for p in (stage, status) if p]
    return " · ".join(parts) or None


def _search_leads(db: Session, term: str, account_ids: Iterable[str], limit: int):
    query = (
        select(Lead)
        .where(
            or_(
                Lead.opportunity_name.ilike(_like(term), escape="\\"),
                cast(Lead.lead_id, String).ilike(_like(term), escape="\\"),
                Lead.end_client.in_(list(account_ids)) if account_ids else False,
            )
        )
        .order_by(Lead.opportunity_name)
    )
    rows, total = _capped(db, query, limit)
    return [
        _hit(
            module="leads",
            record_id=r.lead_id,
            title=r.opportunity_name,
            subtitle=r.end_client,
            meta=_stage_meta(r.project_stage, r.lead_status),
        )
        for r in rows
    ], total


def _search_opportunities(db: Session, term: str, account_ids: Iterable[str], limit: int):
    # The join that makes the module searchable at all — see the module docstring.
    query = (
        select(Opportunity, Lead)
        .join(Lead, Lead.lead_id == Opportunity.parent_lead, isouter=True)
        .where(
            or_(
                Lead.opportunity_name.ilike(_like(term), escape="\\"),
                cast(Opportunity.opportunity_id, String).ilike(_like(term), escape="\\"),
                Opportunity.client_tender_reference.ilike(_like(term), escape="\\"),
                Lead.end_client.in_(list(account_ids)) if account_ids else False,
            )
        )
        .order_by(Lead.opportunity_name)
    )
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = list(db.execute(query.limit(limit)))
    return [
        _hit(
            module="opportunities",
            record_id=opportunity.opportunity_id,
            title=lead.opportunity_name if lead else None,
            subtitle=lead.end_client if lead else None,
            meta=_stage_meta(opportunity.project_stage, opportunity.lead_status),
        )
        for opportunity, lead in rows
    ], total


def _search_deals(db: Session, term: str, account_ids: Iterable[str], limit: int):
    query = (
        select(Deal)
        .where(
            or_(
                Deal.deal_name.ilike(_like(term), escape="\\"),
                Deal.project_code.ilike(_like(term), escape="\\"),
                cast(Deal.deal_id, String).ilike(_like(term), escape="\\"),
                Deal.end_client.in_(list(account_ids)) if account_ids else False,
            )
        )
        .order_by(Deal.deal_name)
    )
    rows, total = _capped(db, query, limit)
    return [
        _hit(
            module="deals",
            record_id=r.deal_id,
            title=r.deal_name,
            subtitle=r.end_client,
            meta=_stage_meta(r.deal_stage, r.lead_status),
        )
        for r in rows
    ], total


def _search_accounts(db: Session, term: str, limit: int):
    query = (
        select(Account)
        .where(
            or_(
                Account.account_name.ilike(_like(term), escape="\\"),
                cast(Account.account_id, String).ilike(_like(term), escape="\\"),
            )
        )
        .order_by(Account.account_name)
    )
    rows, total = _capped(db, query, limit)
    return [_hit(module="accounts", record_id=r.account_id, title=r.account_name) for r in rows], total


def _search_contacts(db: Session, term: str, account_ids: Iterable[str], limit: int):
    query = (
        select(Contact)
        # A confidential contact is left out of a global search on purpose: the
        # flag exists to keep the person off screens they were not sought on,
        # and a header dropdown is the definition of one. They are still found
        # on their own module's list, where the reader went looking for them.
        .where(Contact.confidential.is_not(True))
        .where(
            or_(
                Contact.full_name.ilike(_like(term), escape="\\"),
                Contact.email.ilike(_like(term), escape="\\"),
                Contact.job_title.ilike(_like(term), escape="\\"),
                cast(Contact.contact_id, String).ilike(_like(term), escape="\\"),
                Contact.account.in_(list(account_ids)) if account_ids else False,
            )
        )
        .order_by(Contact.full_name)
    )
    rows, total = _capped(db, query, limit)
    return [
        _hit(module="contacts", record_id=r.contact_id, title=r.full_name, subtitle=r.job_title, meta=r.account)
        for r in rows
    ], total


#: Group order is reading order, not alphabetical: the pipeline first, because
#: that is what people are looking for nine times in ten, then the parties.
GROUP_LABELS = [
    ("leads", "Leads"),
    ("opportunities", "Opportunities"),
    ("deals", "Deals"),
    ("accounts", "Accounts"),
    ("contacts", "Contacts"),
]


@router.get("/search")
def global_search(request: Request, db: Session = Depends(get_db)) -> dict:
    """
    Every live module, a few hits each, in one request.

    Returns `{q, groups: [{module, label, total, items: [...]}]}` with empty
    groups dropped — a dropdown listing five module headings and no results
    reads as broken rather than empty.
    """
    term = (request.query_params.get("q") or "").strip()
    try:
        limit = min(int(request.query_params.get("_limit") or DEFAULT_PER_MODULE), MAX_PER_MODULE)
    except ValueError:
        limit = DEFAULT_PER_MODULE

    if len(term) < MIN_QUERY:
        return {"q": term, "groups": []}

    # Resolved once and shared by every module that carries a lookup to it.
    account_ids = _matching_account_ids(db, term)

    results = {
        "leads": _search_leads(db, term, account_ids, limit),
        "opportunities": _search_opportunities(db, term, account_ids, limit),
        "deals": _search_deals(db, term, account_ids, limit),
        "accounts": _search_accounts(db, term, limit),
        "contacts": _search_contacts(db, term, account_ids, limit),
    }

    groups = []
    for key, label in GROUP_LABELS:
        items, total = results[key]
        if items:
            groups.append({"module": key, "label": label, "total": total, "items": items})
    return {"q": term, "groups": groups}
