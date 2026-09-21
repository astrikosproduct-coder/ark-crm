"""
ONE REVENUE SOURCE PER MODULE — frozen 13 Sep 2026.

    Leads          (Stages 0-3)   Estimated Value      leads.estimated_value
    Opportunities  (Stages 4-6)   Opportunity Revenue  opportunities.total_value_tcv
    Deals          (Stages 7-9)   Actual Revenue       deals.contract_value

No fallbacks. A Lead's card used to show `total_value_tcv ?? estimated_value`
and that is exactly what this module exists to stop: a number that silently
changes which field it is reading is not a number anybody can reconcile. Real
CRMs keep ONE amount per record that the owner keeps current; the stage says
how firm it is.

Deliberately NEVER a revenue source:
    total_project_value      the whole engagement where Astrikos is a
                             subcontractor — the register says "deliberately
                             excluded from all pipeline totals"
    final_negotiated_value   Stage 6's concession check against the bid. X6.1
                             now requires it to EQUAL TCV, so it cannot diverge
    incremental_value        expansion pipeline, sized separately
    arr / one-time lines     components of TCV, not a total

WHAT COUNTS
-----------
A record is in a pipeline total when its status is Open or On Hold (blank is
Open) AND it is the primary pursuit of its group. Closed Lost and Converted
never count — a converted Lead is its Opportunity now, and counting both would
double every pursuit that crossed Stage 3.

A counted record with no value, no currency, or no FX rate contributes nothing
and is FLAGGED, never borrowed from another field. At Stage 4 that means the
pipeline dips until the Opportunity's TCV lines are filled in. That dip is the
honest consequence of one source; it is not a bug to paper over.

USD
---
Values are entered in the pursuit's currency. fx_rate_at_entry is LOCAL UNITS
PER 1 USD (AED 3.6725), so USD = local / rate. Both currency and the rate live
on the Lead and are read through by the Opportunity and Deal, so one pursuit has
one rate however many records it becomes. USD needs no rate.

TCV is COMPUTED, never stored (models.Opportunity). It is evaluated here from
the register's own computed_expr — not a second copy of the formula — with the
frontend engine's blank semantics (src/lib/spec/evaluate.ts::arithmetic): an
operation whose operands are both blank is blank; otherwise a blank is 0.
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Deal, FieldDefinition, Lead, Opportunity
from .progression import PILOT_STATUS

REVENUE_FIELD = {
    "leads": "estimated_value",
    "opportunities": "total_value_tcv",
    "deals": "contract_value",
}

REVENUE_LABEL = {
    "leads": "Estimated Value",
    "opportunities": "Opportunity Revenue",
    "deals": "Actual Revenue",
}

#: Blank is Open: a record nobody has given a status to is not closed. A
#: POC/Pilot Deal counts: it is sold work with a contract value.
COUNTED_STATUSES = frozenset({None, "", "OPEN", "ON_HOLD", PILOT_STATUS})

BASE_CURRENCY = "USD"

_IDENT = re.compile(r"[A-Za-z0-9_]*[A-Za-z_][A-Za-z0-9_]*")


def _attr_of(api_name: str) -> str:
    """Register name -> model attribute. Python forbids a leading digit."""
    return "third_party_" + api_name[len("3rd_party_"):] if api_name.startswith("3rd_party_") else api_name


def _num(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


class _Arithmetic:
    """+ - * / and parentheses over register names. Nothing else is accepted —
    a computed_expr that needs more is a register change, not a job for eval."""

    def __init__(self, expr: str):
        self.names: dict[str, str] = {}

        def swap(match: re.Match) -> str:
            token = match.group(0)
            if re.fullmatch(r"[0-9]+", token):
                return token
            placeholder = f"v{len(self.names)}"
            self.names.setdefault(token, placeholder)
            return self.names[token]

        self.tree = ast.parse(_IDENT.sub(swap, expr), mode="eval").body
        self.lookup = {v: k for k, v in self.names.items()}

    def evaluate(self, read) -> float | None:
        return self._eval(self.tree, read)

    def _eval(self, node, read) -> float | None:
        if isinstance(node, ast.BinOp):
            a, b = self._eval(node.left, read), self._eval(node.right, read)
            if a is None and b is None:
                return None
            x, y = a or 0.0, b or 0.0
            if isinstance(node.op, ast.Add):
                return x + y
            if isinstance(node.op, ast.Sub):
                return x - y
            if isinstance(node.op, ast.Mult):
                return x * y
            if isinstance(node.op, ast.Div):
                return None if y == 0 else x / y
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
            v = self._eval(node.operand, read)
            return None if v is None else -v
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return float(node.value)
        if isinstance(node, ast.Name):
            return _num(read(self.lookup[node.id]))
        raise ValueError(f"unsupported expression: {ast.dump(node)}")


@dataclass
class RevenueContext:
    """Everything one page of rows needs, read once rather than per row."""

    tcv: _Arithmetic | None
    lead_currency: dict[str, tuple[str | None, Decimal | None]] = field(default_factory=dict)
    opportunity_parent: dict[str, str | None] = field(default_factory=dict)
    primary_of_group: dict[str, str | None] = field(default_factory=dict)


def revenue_context(db: Session) -> RevenueContext:
    from .models import PursuitGroup  # local: models imports nothing from here

    definition = db.scalars(
        select(FieldDefinition)
        .where(FieldDefinition.api_name == "total_value_tcv")
        .where(FieldDefinition.status == "active")
        .where(FieldDefinition.computed_expr.is_not(None))
    ).first()
    return RevenueContext(
        tcv=_Arithmetic(definition.computed_expr) if definition else None,
        lead_currency={
            l.lead_id: (l.currency, l.fx_rate_at_entry) for l in db.scalars(select(Lead))
        },
        opportunity_parent={
            o.opportunity_id: o.parent_lead for o in db.scalars(select(Opportunity))
        },
        primary_of_group={g.group_id: g.primary_pursuit for g in db.scalars(select(PursuitGroup))},
    )


def root_lead_of(ctx: RevenueContext, module: str, record: Any) -> str | None:
    """The Lead a record's currency and FX rate are read through."""
    if module == "leads":
        return record.lead_id
    if module == "opportunities":
        return record.parent_lead
    return record.parent_lead or ctx.opportunity_parent.get(record.parent_opportunity or "")


def value_of(ctx: RevenueContext, module: str, record: Any) -> float | None:
    if module == "opportunities":
        return ctx.tcv.evaluate(lambda name: getattr(record, _attr_of(name), None)) if ctx.tcv else None
    return _num(getattr(record, REVENUE_FIELD[module]))


def revenue_of(ctx: RevenueContext, module: str, record: Any) -> dict[str, Any]:
    """
    What this record contributes to its stage's pipeline total, and why not
    when it contributes nothing. Served on every pipeline list row as
    `revenue`, so the board header and the card read one server answer.

    excluded — the record is not in the total at all:
        closed_lost | converted | secondary | no_primary
    flag — the record IS counted but contributes 0 until someone fixes it:
        no_value | no_currency | no_fx_rate
    """
    value = value_of(ctx, module, record)
    root = root_lead_of(ctx, module, record)
    currency, rate = ctx.lead_currency.get(root or "", (None, None))

    status = getattr(record, "lead_status", None)
    excluded = None
    if status == "CLOSED_LOST":
        excluded = "closed_lost"
    elif status == "CONVERTED":
        excluded = "converted"
    elif status not in COUNTED_STATUSES:
        excluded = "closed_lost"
    elif getattr(record, "pursuit_group", None):
        if ctx.primary_of_group.get(record.pursuit_group) is None:
            excluded = "no_primary"
        elif not record.is_primary_pursuit:
            excluded = "secondary"

    usd = None
    flag = None
    if value is None:
        flag = "no_value"
    elif not currency:
        flag = "no_currency"
    elif currency == BASE_CURRENCY:
        usd = value
    elif rate is None or rate <= 0:
        flag = "no_fx_rate"
    else:
        usd = value / float(rate)

    return {
        "field": REVENUE_FIELD[module],
        "label": REVENUE_LABEL[module],
        "value": value,
        "currency": currency,
        "fx_rate": float(rate) if rate is not None else None,
        "usd": round(usd, 2) if usd is not None else None,
        "counted": excluded is None,
        "excluded": excluded,
        "flag": flag,
    }


def tcv_of(db: Session, opportunity: Opportunity) -> float | None:
    """One Opportunity's TCV, from the register's own computed_expr."""
    definition = db.scalars(
        select(FieldDefinition)
        .where(FieldDefinition.api_name == "total_value_tcv")
        .where(FieldDefinition.status == "active")
        .where(FieldDefinition.computed_expr.is_not(None))
    ).first()
    if definition is None:
        return None
    return _Arithmetic(definition.computed_expr).evaluate(
        lambda name: getattr(opportunity, _attr_of(name), None)
    )


def guard_final_value_matches_tcv(db: Session, deal: Deal) -> None:
    """
    X6.1, ENFORCED — decided 13 Sep 2026 as the most important of the revenue
    rules. An Opportunity leaves Stage 6 only by becoming a Deal, and it may
    not until its Final Negotiated Value is recorded and EQUALS its TCV: the
    Opportunity's one revenue source must be the negotiated number, not the bid.

    Enforced here, on the server, because exit criteria are advisory everywhere
    else in this build (src/lib/readiness.ts) — a rule the Advance button does
    not read is not a rule. Only a Deal converted FROM an Opportunity is
    checked; a paid-pilot Deal and a legacy Lead-to-Deal conversion have no
    Stage 6 to have exited.

    Compared to the cent: money is entered with no decimals (CLAUDE.md), so
    anything larger than a rounding difference is a real disagreement.
    """
    if not deal.parent_opportunity or deal.lead_status == PILOT_STATUS:
        return
    from fastapi import HTTPException, status  # local: this module is otherwise HTTP-free

    opportunity = db.get(Opportunity, deal.parent_opportunity)
    if opportunity is None:
        return
    tcv = tcv_of(db, opportunity)
    final = _num(opportunity.final_negotiated_value)
    if final is None or tcv is None or abs(final - tcv) >= 0.01:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            {
                "code": "FINAL_VALUE_MISMATCH",
                "message": "Final Negotiated Value must match the Total Contract Value before converting.",
                "details": (
                    [f"Final Negotiated Value: {final:,.0f}", f"Total Contract Value: {tcv:,.0f}"]
                    if final is not None and tcv is not None
                    else ["Fill in the Final Negotiated Value and the contract value lines first."]
                ),
                "criterion": "X6.1",
                "final_negotiated_value": final,
                "total_value_tcv": tcv,
            },
        )
