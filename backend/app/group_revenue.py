"""
What each company of a group brings in, and the group's total (Release 1.1,
decided 7 Oct 2026). Shown on the Group companies tab of an Account and a
Partner; Phase 2's dashboard will roll up by group from the same rule.

A pursuit belongs to a company when the company is its END CLIENT (read from
the Lead, as everywhere) or its PARTNER (Customer — Partner / SI). Two figures,
in USD, by app/revenue.py's rule so they reconcile with the dashboard:

  pipeline   Open and On Hold primary Leads and Opportunities — the
             dashboard's Open pipeline.
  won        counted Deals whose PO has been received — the dashboard's Won,
             over all time.

The group's total counts each pursuit ONCE: a deal where one company of the
group is the End Client and another its Partner is one deal, not two.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Deal, Lead, Opportunity
from .revenue import revenue_context, revenue_of, root_lead_of


def _empty() -> dict[str, Any]:
    return {"pipeline_usd": 0.0, "pipeline_count": 0, "won_usd": 0.0, "won_count": 0}


def group_figures(db: Session, account_ids: list[str]) -> dict[str, Any]:
    wanted = set(account_ids)
    ctx = revenue_context(db)
    leads = {l.lead_id: l for l in db.scalars(select(Lead))}
    by_company = {a: _empty() for a in account_ids}
    total = _empty()

    sources = (
        ("leads", list(leads.values()), "lead_id"),
        ("opportunities", list(db.scalars(select(Opportunity))), "opportunity_id"),
        ("deals", list(db.scalars(select(Deal))), "deal_id"),
    )
    for module, records, _id in sources:
        for record in records:
            root = leads.get(root_lead_of(ctx, module, record) or "")
            end_client = root.end_client if root else None
            partner = getattr(record, "customer_partner_si", None) or (root.customer_partner_si if root else None)
            companies = {c for c in (end_client, partner) if c in wanted}
            if not companies:
                continue
            revenue = revenue_of(ctx, module, record)
            if not revenue["counted"]:
                continue
            if module == "deals":
                if getattr(record, "po_received_date", None) is None:
                    continue
                usd_key, count_key = "won_usd", "won_count"
            else:
                usd_key, count_key = "pipeline_usd", "pipeline_count"
            usd = revenue["usd"] or 0.0
            for company in companies:
                by_company[company][usd_key] += usd
                by_company[company][count_key] += 1
            total[usd_key] += usd
            total[count_key] += 1

    for figures in [*by_company.values(), total]:
        figures["pipeline_usd"] = round(figures["pipeline_usd"], 2)
        figures["won_usd"] = round(figures["won_usd"], 2)
    return {"by_company": by_company, "total": total}
