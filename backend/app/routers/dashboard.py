"""
The management dashboard — one read of the live pipeline, shaped for the CEO
and management.

GET /api/dashboard answers every widget of the Phase-1 skeleton in ONE
response, so every number on the screen comes from the same snapshot and cannot
disagree with the number beside it. It writes nothing.

NOTHING HERE HAS ITS OWN MONEY RULE
-----------------------------------
Every amount is app/revenue.py::revenue_of — the rule the Kanban headers and
list rows already use, one field per module:

    Leads          Estimated Value      estimated_value
    Opportunities  Opportunity Revenue  total_value_tcv
    Deals          Actual Revenue       contract_value

    pipeline  Leads + Opportunities whose revenue is counted (Open / On Hold,
              primary pursuit), in USD. Deals are sold work, not pipeline.
    actual    Deals whose revenue is counted
    weighted  each record's USD x its own Probability %
    live      pipeline + counted Deals, less Deals whose deal_stage is CLOSED

WON: THE DAY THE PO IS RECEIVED — NOT YET MEASURABLE
----------------------------------------------------
Decided 15 Sep 2026: a Deal is won on the day its purchase order is received.
No field records that day. Booking Date is a different moment — when the order
was booked in CRM and ERP, and both convert dialogs stamp it with the day of
conversion — and PO Number carries no date. So nothing here computes Won until
the day is captured; the Won tile says so rather than showing a stand-in.

THE DATE RANGE MEANS ONE THING PER WIDGET
-----------------------------------------
A range with BOTH ends also returns `comparison`: the same pipeline, deals and
lost figures over the period of equal length immediately before it, so the tiles
can say "up or down" rather than only "how much". Null when either end is open —
see previous_period().

`date_from` / `date_to` (either may be left out) filter each widget by the date
that widget is about, never by one it is not:

    Expected Close Month   pipeline, weighted, actual, stage, forecast, RAG,
                           time in stage, red and stuck, stale.
                           Compared by MONTH, because the field is a month: a
                           range starting 15 Jan still holds a January close.
                           A record with no close month cannot be placed in a
                           range and is left out; how many is `range.left_out`.
    Date lost              closed lost, why we lose — read from the audit trail.
    Due date               the due list, over every live record.

With no range: every open record, the forecast's next six months, losses of
all time, and what is overdue or due in the next 30 days.

QUARTERS
--------
Offered only as range presets, on the fiscal year: April to March (decided
15 Sep 2026), so Q1 FY2026-27 is Apr-Jun 2026.

FILTERS
-------
Region, Segment, BD Owner and Opportunity Type are Lead fields that the
Opportunity and Deal read through, so every record is filtered on the Lead it
descends from (revenue.root_lead_of) — one pursuit, one answer, whichever
module it has reached.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ..clock import company_date_of, days_since, today_company
from ..database import get_db
from ..models import AuditLog, Deal, DealBidCommitment, Lead, Opportunity, Stage, User
from ..progression import CLOSED_LOST
from ..revenue import REVENUE_LABEL, revenue_context, revenue_of, root_lead_of
from ..stage_entry import stage_entry_dates, stage_number

router = APIRouter(tags=["dashboard"])

#: The fiscal year runs April to March — decided 15 Sep 2026.
FISCAL_YEAR_START_MONTH = 4

#: Quarter presets offered either side of the current one.
PRESET_QUARTERS_BACK = 4
PRESET_QUARTERS_AHEAD = 4

#: Mirrors STALE_AFTER_DAYS in src/components/leads/leadListCell.tsx — change both.
STALE_AFTER_DAYS = 30

#: A stay in one stage longer than this puts a record on the at-risk list.
STUCK_AFTER_DAYS = 90

#: How far ahead the "due" list looks with no range. Overdue items are included.
DUE_WINDOW_DAYS = 30

#: The forecast's width with no range, or with only one end of it given.
FORECAST_MONTHS = 6

#: The longest range the forecast will draw, one column per month.
MAX_RANGE_MONTHS = 36

#: Rows served per action list; the full count rides beside them.
LIST_LIMIT = 25

AGEING_BUCKETS = (("0-30", 0, 30), ("31-60", 31, 60), ("61-90", 61, 90), ("90+", 91, None))

MODULES = ("leads", "opportunities", "deals")
PIPELINE = ("leads", "opportunities")

#: The one RAG value that puts a record on the at-risk list.
RED = "RED"

#: A guarantee in either state can no longer lapse unnoticed.
SETTLED_GUARANTEES = {"RELEASED", "CALLED"}

#: deals.deal_stage value for a finished project. It has no stage number.
DEAL_CLOSED = "CLOSED"

#: Stage-scoped 'sticky': stored as closed_lost_reason_code__s<stage> in custom_fields.
LOSS_REASON_FIELD = "closed_lost_reason_code"

#: (module, id attribute, stage attribute, created attribute, modified attribute).
#: All three name them the same way since 0030 — Deals used to call theirs
#: created_by_date / modified_by_date and carried no actor at all.
SOURCES = (
    ("leads", "lead_id", "project_stage", "created_date", "modified_date"),
    ("opportunities", "opportunity_id", "project_stage", "created_date", "modified_date"),
    ("deals", "deal_id", "deal_stage", "created_date", "modified_date"),
)


@dataclass
class Row:
    module: str
    record: Any
    record_id: str
    name: str
    stage: int | None
    revenue: dict[str, Any]
    root: Lead | None
    days_in_stage: int
    days_since_update: int

    @property
    def usd(self) -> float:
        return self.revenue["usd"] or 0.0

    @property
    def weighted(self) -> float:
        """
        Value x Probability %.

        NO DIVISION BY 100 HERE. A record's probability_pct is stored as a
        FRACTION -- 0.70 is 70% -- and app/progression.py is the authority that
        makes it so: it divides by 100 on the way in (``frac``), normalises a
        whole number a caller sends (``_as_fraction``), validates the range as
        0..1, and multiplies by 100 again only to print. The stages table is the
        one place that holds whole numbers, because that is the register's own
        wording of the ladder.

        This line used to divide by 100 a second time, so every weighted figure
        on the dashboard -- the tile, the forecast, the funnel tooltip -- was a
        hundredth of the truth. An $8.4M weighted pipeline read $84,000 and
        nothing anywhere said otherwise. Fixed 18 Sep 2026; see test_dashboard_weighted.py.
        """
        return self.usd * float(self.record.probability_pct or 0)

    @property
    def close_month(self) -> date | None:
        return _as_date(self.record.expected_close_month)

    def own(self, name: str) -> Any:
        """
        A register field the record owns — never read through a parent, which
        would be a different judgement about a different record.

        The custom_fields fall-through is for Administration-created fields,
        which have no column by design. It used to carry Deals' overall_rag and
        next_milestone_date as well, and always found nothing: those are
        storage='column' placements, so nothing ever wrote them to JSONB
        either. 0030 gave them their columns.
        """
        if hasattr(self.record, name):
            return getattr(self.record, name)
        return (self.record.custom_fields or {}).get(name)

    @property
    def rag(self) -> str | None:
        value = self.own("overall_rag")
        return value.upper() if isinstance(value, str) and value else None

    @property
    def secondary(self) -> bool:
        return bool(getattr(self.record, "pursuit_group", None)) and not self.record.is_primary_pursuit


# ---------------------------------------------------------------------------
# calendar
# ---------------------------------------------------------------------------


def _add_months(day: date, months: int) -> date:
    """The first of the month `months` after `day`'s month (negative goes back)."""
    index = day.month - 1 + months
    return date(day.year + index // 12, index % 12 + 1, 1)


def _month_index(day: date) -> int:
    return day.year * 12 + day.month - 1


def quarter_of(day: date) -> tuple[date, date, str]:
    """(first day, last day, label) of the fiscal quarter holding `day`."""
    offset = (day.month - FISCAL_YEAR_START_MONTH) % 12
    number = offset // 3 + 1
    fiscal_year = day.year if day.month >= FISCAL_YEAR_START_MONTH else day.year - 1
    start = _add_months(date(fiscal_year, FISCAL_YEAR_START_MONTH, 1), (number - 1) * 3)
    end = _add_months(start, 3) - timedelta(days=1)
    if FISCAL_YEAR_START_MONTH == 1:
        label = f"Q{number} {fiscal_year}"
    else:
        label = f"Q{number} FY{fiscal_year}-{(fiscal_year + 1) % 100:02d}"
    return start, end, label


def quarter_presets(today: date) -> list[dict[str, Any]]:
    """The quarters the range control offers, oldest first."""
    current, _, _ = quarter_of(today)
    presets = []
    for step in range(-PRESET_QUARTERS_BACK, PRESET_QUARTERS_AHEAD + 1):
        start, end, label = quarter_of(_add_months(current, 3 * step))
        presets.append({"label": label, "start": start, "end": end, "current": step == 0})
    return presets


def close_month_in(close: date | None, start: date | None, end: date | None) -> bool:
    """Whether a close MONTH falls in the range, compared month to month."""
    if start is None and end is None:
        return True
    if close is None:
        return False
    month = _month_index(close)
    return (start is None or month >= _month_index(start)) and (end is None or month <= _month_index(end))


def day_in(day: date | None, start: date | None, end: date | None) -> bool:
    if day is None:
        return False
    return (start is None or day >= start) and (end is None or day <= end)


def forecast_months(start: date | None, end: date | None, today: date) -> list[date]:
    """The forecast's columns: the range's months, or six from whichever end is known."""
    if start is None and end is None:
        first = today.replace(day=1)
        last = _add_months(first, FORECAST_MONTHS - 1)
    elif end is None:
        first = start.replace(day=1)
        last = _add_months(first, FORECAST_MONTHS - 1)
    elif start is None:
        last = end.replace(day=1)
        first = _add_months(last, -(FORECAST_MONTHS - 1))
    else:
        first, last = start.replace(day=1), end.replace(day=1)
    return [_add_months(first, i) for i in range(_month_index(last) - _month_index(first) + 1)]


def _as_date(value: Any) -> date | None:
    """A Date column's value, or a timestamp's company-calendar day."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return company_date_of(value)
    return value if isinstance(value, date) else None


# ---------------------------------------------------------------------------
# rows
# ---------------------------------------------------------------------------


def _rows(db: Session, leads: dict[str, Lead], opportunities: list[Opportunity], deals: list[Deal]) -> list[Row]:
    ctx = revenue_context(db)
    records = {"leads": list(leads.values()), "opportunities": opportunities, "deals": deals}
    rows: list[Row] = []
    for module, id_attr, stage_attr, created_attr, modified_attr in SOURCES:
        entered = stage_entry_dates(
            db, module, {getattr(r, id_attr): getattr(r, stage_attr) for r in records[module]}
        )
        for record in records[module]:
            record_id = getattr(record, id_attr)
            root = leads.get(root_lead_of(ctx, module, record) or "")
            own_name = record.opportunity_name if module == "leads" else getattr(record, "deal_name", None)
            rows.append(
                Row(
                    module=module,
                    record=record,
                    record_id=record_id,
                    name=own_name or (root.opportunity_name if root else None) or record_id,
                    stage=stage_number(getattr(record, stage_attr)),
                    revenue=revenue_of(ctx, module, record),
                    root=root,
                    days_in_stage=days_since(entered.get(record_id) or getattr(record, created_attr)) or 0,
                    days_since_update=days_since(getattr(record, modified_attr)) or 0,
                )
            )
    return rows


def _in_slice(row: Row, filters: dict[str, str | None]) -> bool:
    for attr, wanted in filters.items():
        if wanted and (row.root is None or getattr(row.root, attr) != wanted):
            return False
    return True


def _bucket(rows: list[Row]) -> dict[str, Any]:
    return {
        "count": len(rows),
        "usd": round(sum(r.usd for r in rows), 2),
        "weighted_usd": round(sum(r.weighted for r in rows), 2),
    }


def _loss_reason(row: Row) -> str | None:
    """
    The reason recorded at the stage the record was lost in. Sticky per stage,
    so a reason given at an earlier loss is not borrowed. A Deal in CLOSED has
    no stage number; it takes the latest stage that recorded one.
    """
    extras = row.record.custom_fields or {}
    if row.stage is not None:
        return extras.get(f"{LOSS_REASON_FIELD}__s{row.stage}") or None
    prefix = f"{LOSS_REASON_FIELD}__s"
    scoped = sorted(
        (int(key[len(prefix):]), value)
        for key, value in extras.items()
        if key.startswith(prefix) and key[len(prefix):].isdigit() and value
    )
    return scoped[-1][1] if scoped else None


def _lost_on(db: Session) -> dict[tuple[str, str], date]:
    """
    (module, record id) -> the company day its status last became Closed Lost.
    Read from the audit trail, the only place the moment is kept. A record
    CREATED as Closed Lost has no status change to find, so it has no date and
    falls outside every range — it still counts when no range is set.
    """
    found: dict[tuple[str, str], date] = {}
    entries = db.scalars(
        select(AuditLog).where(AuditLog.record_module.in_(MODULES)).order_by(AuditLog.timestamp)
    )
    for entry in entries:
        for change in entry.changed or []:
            if isinstance(change, dict) and change.get("field") == "lead_status" and change.get("to") == CLOSED_LOST:
                found[(entry.record_module, entry.record_id)] = company_date_of(entry.timestamp)
    return found


def _item(row: Row, users: dict[str, str], stage_names: dict[int, str], **extra: Any) -> dict[str, Any]:
    owner = row.root.bd_owner if row.root else None
    return {
        "module": row.module,
        "record_id": row.record_id,
        "name": row.name,
        "stage": row.stage,
        "stage_name": stage_names.get(row.stage) if row.stage is not None else None,
        "usd": row.revenue["usd"],
        "flag": row.revenue["flag"],
        "owner": users.get(owner) if owner else None,
        "rag": row.rag,
        "days_in_stage": row.days_in_stage,
        "days_since_update": row.days_since_update,
        **extra,
    }


def previous_period(
    date_from: date | None, date_to: date | None
) -> tuple[date | None, date | None, str | None]:
    """
    The period this one should be compared against, and what to call it.

    A WHOLE QUARTER COMPARES WITH THE QUARTER BEFORE IT, by name. Quarters are
    not the same length -- Q1 Apr-Jun is 91 days, Q2 Jul-Sep is 92 -- so
    stepping back "the same number of days" from Q2 lands on 31 March and
    quietly drags one day of the previous fiscal year into the comparison. It
    would be arithmetically defensible and useless to a reader: nobody asks how
    this quarter compares with the 92 days before it. They ask about Q1.

    Anything else -- a hand-typed range -- steps back its own inclusive length,
    and is labelled as a period rather than given a name it does not have.

    BOTH ENDS OR NOTHING. An open-ended range has no length, so there is no
    "previous" of the same size, and inventing one would be a comparison the
    reader never asked for, labelled as if they had. The dashboard then shows no
    delta at all, which is the honest answer to "compared with what?".
    """
    if not date_from or not date_to:
        return None, None, None
    # Exactly one fiscal quarter? Then it is that quarter, and its predecessor
    # is a named thing rather than a window.
    start, end, _ = quarter_of(date_from)
    if (start, end) == (date_from, date_to):
        previous_start, previous_end, label = quarter_of(start - timedelta(days=1))
        return previous_start, previous_end, label
    length = (date_to - date_from).days
    previous_end = date_from - timedelta(days=1)
    return previous_end - timedelta(days=length), previous_end, None


def _refuse(code: str, message: str) -> HTTPException:
    return HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, {"code": code, "message": message})


# ---------------------------------------------------------------------------
# the endpoint
# ---------------------------------------------------------------------------


@router.get("/dashboard")
def dashboard(
    region: str | None = None,
    segment: str | None = None,
    owner: str | None = None,
    opportunity_type: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    if date_from and date_to and date_from > date_to:
        raise _refuse("RANGE_INVERTED", "The From date must be on or before the To date.")
    today = today_company()
    months = forecast_months(date_from, date_to, today)
    if len(months) > MAX_RANGE_MONTHS:
        raise _refuse("RANGE_TOO_LONG", f"Choose a range of at most {MAX_RANGE_MONTHS} months.")
    ranged = date_from is not None or date_to is not None

    stages = list(db.scalars(select(Stage).order_by(Stage.stage)))
    stage_names = {s.stage: s.name for s in stages}
    users = {u.user_id: u.name for u in db.scalars(select(User))}
    leads = {l.lead_id: l for l in db.scalars(select(Lead))}
    opportunities = list(
        db.scalars(select(Opportunity).options(selectinload(Opportunity.payment_milestones)))
    )
    deals = list(db.scalars(select(Deal)))

    filters = {
        "destination_region": region,
        "segment": segment,
        "bd_owner": owner,
        "opportunity_type": opportunity_type,
    }
    rows = [r for r in _rows(db, leads, opportunities, deals) if _in_slice(r, filters)]
    counted = [r for r in rows if r.revenue["counted"]]

    # ---- expected-close widgets
    in_range = [r for r in counted if close_month_in(r.close_month, date_from, date_to)]
    left_out = sum(1 for r in counted if r.close_month is None) if ranged else 0
    pipeline = [r for r in in_range if r.module in PIPELINE]
    actual = [r for r in in_range if r.module == "deals"]
    live = pipeline + [r for r in actual if r.record.deal_stage != DEAL_CLOSED]

    # ---- lost, by the date it was lost
    lost_on = _lost_on(db)
    closed_lost = [r for r in rows if r.record.lead_status == CLOSED_LOST and not r.secondary]
    if ranged:
        closed_lost = [r for r in closed_lost if day_in(lost_on.get((r.module, r.record_id)), date_from, date_to)]
    reasons: dict[str | None, list[Row]] = {}
    for r in closed_lost:
        reasons.setdefault(_loss_reason(r), []).append(r)
    loss_reasons = sorted(
        (
            {
                "reason": reason,
                **_bucket(members),
                "stages": {
                    str(stage): sum(1 for m in members if m.stage == stage)
                    for stage in sorted({m.stage for m in members if m.stage is not None})
                },
            }
            for reason, members in reasons.items()
        ),
        key=lambda b: (-b["count"], -b["usd"]),
    )

    # ---- forecast: revenue by expected close month, split by module
    expected = pipeline + actual

    def month_bucket(month: date) -> dict[str, Any]:
        members = [r for r in expected if r.close_month and _month_index(r.close_month) == _month_index(month)]
        return {
            "month": month.isoformat(),
            **_bucket(members),
            "by_module": {m: _bucket([r for r in members if r.module == m]) for m in MODULES},
        }

    forecast: dict[str, Any] = {"months": [month_bucket(m) for m in months]}
    if ranged:
        # Every record is already inside the range; there is no before or after.
        forecast.update(overdue=None, later=None, undated=None)
    else:
        forecast.update(
            overdue=_bucket([r for r in expected if r.close_month and r.close_month < months[0]]),
            later=_bucket([r for r in expected if r.close_month and _month_index(r.close_month) > _month_index(months[-1])]),
            undated=_bucket([r for r in expected if r.close_month is None]),
        )

    # ---- RAG and stage ageing, over the pipeline
    rag: dict[str | None, list[Row]] = {}
    for r in pipeline:
        rag.setdefault(r.rag, []).append(r)

    ageing = [
        {
            "bucket": label,
            **_bucket([r for r in pipeline if r.days_in_stage >= low and (high is None or r.days_in_stage <= high)]),
        }
        for label, low, high in AGEING_BUCKETS
    ]

    # ---- due, by due date, over every live record whatever its close month
    due_from, due_to = (date_from, date_to) if ranged else (None, today + timedelta(days=DUE_WINDOW_DAYS))
    live_any = [r for r in counted if r.module in PIPELINE or r.record.deal_stage != DEAL_CLOSED]
    live_by_id = {(r.module, r.record_id): r for r in live_any}
    due: list[dict[str, Any]] = []
    for r in live_any:
        milestone_day = _as_date(r.own("next_milestone_date"))
        if day_in(milestone_day, due_from, due_to):
            due.append(_item(r, users, stage_names, kind="milestone", date=milestone_day, detail=r.own("next_milestone")))
        if r.module == "opportunities" and not r.record.bid_submission_date:
            deadline = _as_date(r.record.submission_deadline)
            if day_in(deadline, due_from, due_to):
                due.append(_item(r, users, stage_names, kind="submission", date=deadline, detail=r.record.rfp_type))

    # A payment schedule belongs to the Opportunity but is chased on whichever
    # record is live: the Opportunity itself, or the Deal it became.
    for deal in deals:
        r = live_by_id.get(("deals", deal.deal_id))
        if r and deal.parent_opportunity:
            live_by_id.setdefault(("schedule", deal.parent_opportunity), r)
    for opp in opportunities:
        r = live_by_id.get(("opportunities", opp.opportunity_id)) or live_by_id.get(("schedule", opp.opportunity_id))
        if not r:
            continue
        for m in opp.payment_milestones:
            if not m.milestone_payment_received_date and day_in(m.milestone_planned_date, due_from, due_to):
                due.append(_item(r, users, stage_names, kind="payment", date=m.milestone_planned_date, detail=m.milestone))

    live_deals = [r.record_id for r in live_any if r.module == "deals"]
    if live_deals:
        for g in db.scalars(select(DealBidCommitment).where(DealBidCommitment.deal_id.in_(live_deals))):
            if g.guarantee_status not in SETTLED_GUARANTEES and day_in(g.guarantee_expiry_date, due_from, due_to):
                r = live_by_id[("deals", g.deal_id)]
                due.append(_item(r, users, stage_names, kind="guarantee", date=g.guarantee_expiry_date, detail=g.guarantee_type))

    due.sort(key=lambda i: (i["date"], i["name"]))
    for item in due:
        item["overdue"] = item["date"] < today

    # ---- red and stuck, and stale
    at_risk = [
        _item(
            r,
            users,
            stage_names,
            reasons=[reason for reason, hit in (("red", r.rag == RED), ("stuck", r.days_in_stage > STUCK_AFTER_DAYS)) if hit],
        )
        for r in live
        if r.rag == RED or r.days_in_stage > STUCK_AFTER_DAYS
    ]
    at_risk.sort(key=lambda i: (-(i["usd"] or 0), i["name"]))

    stale = [r for r in live if r.days_since_update > STALE_AFTER_DAYS]

    # ---- the same four numbers over the period before this one
    #
    # Re-filters the rows already in hand rather than asking the database
    # again: every widget's slice is a date test over `counted` / `rows`, so
    # the previous period costs a second pass in Python and no round trip.
    comparison = None
    previous_from, previous_to, previous_label = previous_period(date_from, date_to)
    if previous_from and previous_to:
        previous_in_range = [r for r in counted if close_month_in(r.close_month, previous_from, previous_to)]
        previous_pipeline = [r for r in previous_in_range if r.module in PIPELINE]
        previous_actual = [r for r in previous_in_range if r.module == "deals"]
        previous_lost = [
            r
            for r in rows
            if r.record.lead_status == CLOSED_LOST
            and not r.secondary
            and day_in(lost_on.get((r.module, r.record_id)), previous_from, previous_to)
        ]
        comparison = {
            "from": previous_from,
            "to": previous_to,
            #: "Q1 FY2026-27" when the period is a named quarter, else null and
            #: the frontend says "the previous period".
            "label": previous_label,
            "kpis": {
                "pipeline": _bucket(previous_pipeline),
                "actual": _bucket(previous_actual),
                "lost": _bucket(previous_lost),
            },
        }

    owner_ids = {l.bd_owner for l in leads.values() if l.bd_owner}
    return {
        "as_of": today,
        "range": {"from": date_from, "to": date_to, "left_out": left_out},
        #: The same period, one length earlier — or null when the range has no
        #: length to step back by. See previous_period().
        "comparison": comparison,
        "quarters": quarter_presets(today),
        "fiscal_year_start_month": FISCAL_YEAR_START_MONTH,
        "revenue_labels": REVENUE_LABEL,
        "thresholds": {
            "stale_after_days": STALE_AFTER_DAYS,
            "stuck_after_days": STUCK_AFTER_DAYS,
            "due_window_days": DUE_WINDOW_DAYS,
        },
        "filters": {"region": region, "segment": segment, "owner": owner, "opportunity_type": opportunity_type},
        "owners": sorted(
            ({"id": uid, "name": users.get(uid, uid)} for uid in owner_ids), key=lambda o: o["name"].lower()
        ),
        "kpis": {
            "pipeline": {
                **_bucket(pipeline),
                "by_module": {m: _bucket([r for r in pipeline if r.module == m]) for m in PIPELINE},
                "unpriced": sum(1 for r in pipeline if r.revenue["flag"]),
            },
            "actual": {**_bucket(actual), "unpriced": sum(1 for r in actual if r.revenue["flag"])},
            "lost": _bucket(closed_lost),
            "stale": _bucket(stale),
        },
        "funnel": [
            {"stage": s.stage, "name": s.name, "module": s.owner_module, **_bucket([r for r in live if r.stage == s.stage])}
            for s in stages
        ],
        "forecast": forecast,
        "rag": [{"rag": key, **_bucket(members)} for key, members in rag.items()],
        "ageing": ageing,
        "loss_reasons": loss_reasons,
        "due": {"total": len(due), "items": due[:LIST_LIMIT]},
        "at_risk": {"total": len(at_risk), "items": at_risk[:LIST_LIMIT]},
    }
