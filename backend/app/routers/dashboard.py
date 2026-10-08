"""
The management dashboard — one read of the live pipeline, shaped for the CEO
and management. Five tabs since 28 Sep 2026: Performance, Pipeline, Partners,
Accounts, Win & loss.

GET /api/dashboard answers every tile of every tab in ONE response, so every
number on the screen comes from the same read and cannot disagree with the
number beside it. It writes nothing. GET /api/dashboard/records returns the
records behind one bar, slice or point, grouped by the same code, so the list
always adds up to what was clicked.

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
    won       counted Deals whose PO Received Date falls in the period
    weighted  each record's USD x its own Probability % — the stage's number
              unless someone overrode it with a justification
    live      pipeline + counted Deals, less Deals whose deal_stage is CLOSED

ON HOLD IS PIPELINE. The Phase 1 dashboard brief (28 Sep 2026) asked for open
pipeline to exclude On Hold, and in the same breath for the Open pipeline card
to stay exactly as it is. The card counts On Hold (CLAUDE.md: "Open and On Hold
primary pursuits"), and every tile that sums pipeline must add up to the card,
so On Hold stays in, everywhere.

WON: THE DAY THE PO IS RECEIVED
-------------------------------
Decided 15 Sep 2026: a Deal is won on the day its purchase order is received —
deals.po_received_date, and nothing else. Not Booking Date (the ERP booking,
which lags the PO), not a stage move.

The Performance tab's Booked series is `won_between` applied month by month,
so over the fiscal year it IS the Won card: with the Period on that fiscal year
(the default since 28 Sep 2026) the Booked line ends where the Won card reads.
It does NOT tie to Actual Revenue (Deals), and cannot: that card counts Deals
by Expected Close Month, Booked by PO Received Date. Both cards are kept as
they were.

THE DATE RANGE MEANS ONE THING PER TILE
---------------------------------------
    Expected Close Month   pipeline, weighted, actual, stage, and every
                           Pipeline / Partners / Accounts tile. Compared by
                           MONTH. A record with no close month cannot be placed
                           in a range and is left out (`range.left_out`) —
                           except on "Pipeline by expected close month", whose
                           job is to show them.
    Date lost              Closed Lost, Why we lose — from the audit trail.
    PO Received Date       Won, and the Booked series.
    Fiscal year            Performance: the fiscal year holding the range's
                           start (or today, with no range).

`period=current_fy` asks for this fiscal year without the browser knowing when
it starts — the page opens on it.

FILTERS
-------
Region (Booking Region), Segment, BD Owner, Opportunity Type, Theme and Deal
Source are Lead fields the Opportunity and Deal read through, so every record
is filtered on the Lead it descends from (revenue.root_lead_of): one pursuit,
one answer, whichever module it has reached — and never on an Account, whose
region can differ from the deal's. Partner is Customer (Partner / SI): the
Deal's own locked copy on a Deal, the Lead's elsewhere.

No row-level filtering: everyone with a role sees every pursuit until the
RBAC phase (CLAUDE.md).

QUARTERS AND THE FISCAL YEAR
----------------------------
app/fiscal.py, and nowhere else.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import fiscal
from ..clock import company_date_of, now_utc, today_company
from ..database import get_db
from ..fiscal import add_months, quarter_bounds, quarter_number, start_year_of
from ..live_register import Published, published
from ..models import Account, AuditLog, Deal, Lead, Opportunity, PipelineSnapshot, SalesTarget, Stage, User
from ..progression import CLOSED_LOST
from ..revenue import REVENUE_LABEL, revenue_context, revenue_of, root_lead_of
from ..stage_entry import stage_number

router = APIRouter(tags=["dashboard"])

#: Quarter presets offered either side of the current one.
PRESET_QUARTERS_BACK = 4
PRESET_QUARTERS_AHEAD = 4

#: The longest range the page will compute, one column per month.
MAX_RANGE_MONTHS = 36

#: "Pipeline by expected close month" draws this many months.
CLOSE_MONTHS = 6

#: Ranked bar tiles keep this many and fold the rest into Others.
TOP_N = 10

MODULES = ("leads", "opportunities", "deals")
PIPELINE = ("leads", "opportunities")

#: deals.deal_stage value for a finished project. It has no stage number.
DEAL_CLOSED = "CLOSED"

#: Stage-scoped 'sticky': stored as closed_lost_reason_code__s<stage> in custom_fields.
LOSS_REASON_FIELD = "closed_lost_reason_code"

#: Group keys that are not values. The browser draws both in the neutral grey.
NOT_SET = "__none__"
OTHERS = "__others__"
NO_PARTNER = "__no_partner__"

#: A quarter meter's bands, in whole per cent.
GOOD_FROM = 95
WARN_FROM = 70

SOURCES = (
    ("leads", "lead_id", "project_stage"),
    ("opportunities", "opportunity_id", "project_stage"),
    ("deals", "deal_id", "deal_stage"),
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

    @property
    def usd(self) -> float:
        return self.revenue["usd"] or 0.0

    @property
    def weighted(self) -> float:
        """
        Value x Probability %.

        NO DIVISION BY 100 HERE. A record's probability_pct is stored as a
        FRACTION -- 0.70 is 70% -- and app/progression.py is the authority that
        makes it so. This line used to divide by 100 a second time, so every
        weighted figure was a hundredth of the truth. Fixed 18 Sep 2026; see
        test_dashboard_weighted.py.
        """
        return self.usd * float(self.record.probability_pct or 0)

    @property
    def close_month(self) -> date | None:
        return _as_date(self.record.expected_close_month)

    @property
    def secondary(self) -> bool:
        return bool(getattr(self.record, "pursuit_group", None)) and not self.record.is_primary_pursuit

    def lead(self, name: str) -> Any:
        """A Lead field, read on the Lead this record descends from."""
        return getattr(self.root, name, None) if self.root is not None else None

    @property
    def customer(self) -> str | None:
        """Customer (Partner / SI): the Deal's own locked copy, else the Lead's."""
        if self.module == "deals":
            return self.record.customer_partner_si
        return self.lead("customer_partner_si")


# ---------------------------------------------------------------------------
# calendar
# ---------------------------------------------------------------------------


def _month_index(day: date) -> int:
    return day.year * 12 + day.month - 1


def quarter_of(day: date) -> tuple[date, date, str]:
    """(first day, last day, label) of the fiscal quarter holding `day` — app/fiscal.py's rule."""
    number = quarter_number(day)
    fiscal_year = start_year_of(day)
    start, end = quarter_bounds(day)
    if fiscal.FISCAL_YEAR_START_MONTH == 1:
        label = f"Q{number} {fiscal_year}"
    else:
        label = f"Q{number} FY{fiscal_year}-{(fiscal_year + 1) % 100:02d}"
    return start, end, label


def period_presets(today: date) -> list[dict[str, Any]]:
    """This fiscal year and the last, then the quarters either side of this one."""
    this_fy = fiscal.label_of(today)
    last_fy = fiscal.label_of(fiscal.first_day(this_fy) - timedelta(days=1))
    presets = [
        {
            "kind": "fiscal_year",
            "label": label,
            "start": fiscal.first_day(label),
            "end": fiscal.last_day(label),
            "current": label == this_fy,
        }
        for label in (this_fy, last_fy)
    ]
    current, _, _ = quarter_of(today)
    for step in range(-PRESET_QUARTERS_BACK, PRESET_QUARTERS_AHEAD + 1):
        start, end, label = quarter_of(add_months(current, 3 * step))
        presets.append({"kind": "quarter", "label": label, "start": start, "end": end, "current": step == 0})
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


def month_end(month: date) -> date:
    return add_months(month, 1) - timedelta(days=1)


def _as_date(value: Any) -> date | None:
    """A Date column's value, or a timestamp's company-calendar day."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return company_date_of(value)
    return value if isinstance(value, date) else None


def previous_period(
    date_from: date | None, date_to: date | None
) -> tuple[date | None, date | None, str | None]:
    """
    The period this one should be compared against, and what to call it.

    A WHOLE QUARTER COMPARES WITH THE QUARTER BEFORE IT, and a whole fiscal year
    with the year before it, by name. Anything else — a hand-typed range —
    steps back its own inclusive length and is labelled as a period. BOTH ENDS
    OR NOTHING: an open-ended range has no length, so no "previous" is invented.
    """
    if not date_from or not date_to:
        return None, None, None
    start, end, _ = quarter_of(date_from)
    if (start, end) == (date_from, date_to):
        return quarter_of(start - timedelta(days=1))
    label = fiscal.label_of(date_from)
    if (fiscal.first_day(label), fiscal.last_day(label)) == (date_from, date_to):
        previous = fiscal.label_of(date_from - timedelta(days=1))
        return fiscal.first_day(previous), fiscal.last_day(previous), previous
    length = (date_to - date_from).days
    previous_end = date_from - timedelta(days=1)
    return previous_end - timedelta(days=length), previous_end, None


# ---------------------------------------------------------------------------
# rows
# ---------------------------------------------------------------------------


def _rows(db: Session, leads: dict[str, Lead], opportunities: list[Opportunity], deals: list[Deal]) -> list[Row]:
    """
    Every record as a Row. Also the rule app/pipeline_snapshots.py writes down
    at month-end, so a snapshot and the Open pipeline card agree to the cent.
    """
    ctx = revenue_context(db)
    records = {"leads": list(leads.values()), "opportunities": opportunities, "deals": deals}
    rows: list[Row] = []
    for module, id_attr, stage_attr in SOURCES:
        for record in records[module]:
            root = leads.get(root_lead_of(ctx, module, record) or "")
            own_name = record.opportunity_name if module == "leads" else getattr(record, "deal_name", None)
            rows.append(
                Row(
                    module=module,
                    record=record,
                    record_id=getattr(record, id_attr),
                    name=own_name or (root.opportunity_name if root else None) or getattr(record, id_attr),
                    stage=stage_number(getattr(record, stage_attr)),
                    revenue=revenue_of(ctx, module, record),
                    root=root,
                )
            )
    return rows


#: Query parameter -> what it is compared with. Region is Booking Region: the
#: booking entity is where money is reported (28 Sep 2026).
FILTERS: dict[str, Callable[[Row], Any]] = {
    "region": lambda r: r.lead("booking_region"),
    # Segment is the Lead's `theme` field, labelled Segment since Release 1.1;
    # the old 4-choice Segment was deleted, and with it the separate Theme filter.
    "segment": lambda r: r.lead("theme"),
    "owner": lambda r: r.lead("bd_owner"),
    "opportunity_type": lambda r: r.lead("opportunity_type"),
    "deal_source": lambda r: r.lead("deal_source"),
    "partner": lambda r: r.customer,
}

#: Filters a monthly target cannot be split by — targets are owner x month only.
NOT_TARGETED = ("region", "segment", "opportunity_type", "deal_source", "partner")


def _in_slice(row: Row, filters: dict[str, str | None]) -> bool:
    for name, wanted in filters.items():
        if wanted and (row.root is None or FILTERS[name](row) != wanted):
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


# ---------------------------------------------------------------------------
# the scope — everything one request reads, once
# ---------------------------------------------------------------------------


@dataclass
class Scope:
    today: date
    date_from: date | None
    date_to: date | None
    filters: dict[str, str | None]
    register: Published | None
    stages: list[Stage]
    users: dict[str, str]
    accounts: dict[str, Account]
    everything: list[Row]
    rows: list[Row] = field(default_factory=list)
    counted: list[Row] = field(default_factory=list)
    pipeline: list[Row] = field(default_factory=list)
    actual: list[Row] = field(default_factory=list)
    live: list[Row] = field(default_factory=list)
    closed_lost: list[Row] = field(default_factory=list)
    lost_on: dict[tuple[str, str], date] = field(default_factory=dict)

    @property
    def ranged(self) -> bool:
        return self.date_from is not None or self.date_to is not None

    @property
    def fiscal_year(self) -> str:
        """The fiscal year the Performance tab draws: the one holding the range's start."""
        return fiscal.label_of(self.date_from or self.date_to or self.today)

    def won_between(self, start: date | None, end: date | None) -> list[Row]:
        """Counted Deals whose PO Received Date is in [start, end] — Won, and Booked."""
        return [r for r in self.counted if r.module == "deals" and day_in(_as_date(r.record.po_received_date), start, end)]

    def lost_between(self, start: date | None, end: date | None) -> list[Row]:
        rows = [r for r in self.rows if r.record.lead_status == CLOSED_LOST and not r.secondary]
        if start is None and end is None:
            return rows
        return [r for r in rows if day_in(self.lost_on.get((r.module, r.record_id)), start, end)]

    @property
    def open_records(self) -> list[Row]:
        """What the forecast weighs: pipeline, and counted Deals whose PO has not arrived."""
        return [
            r
            for r in self.counted
            if r.module in PIPELINE or (r.record.po_received_date is None and r.record.deal_stage != DEAL_CLOSED)
        ]


def build_scope(db: Session, *, date_from: date | None, date_to: date | None, filters: dict[str, str | None]) -> Scope:
    leads = {lead.lead_id: lead for lead in db.scalars(select(Lead))}
    everything = _rows(db, leads, list(db.scalars(select(Opportunity))), list(db.scalars(select(Deal))))
    scope = Scope(
        today=today_company(),
        date_from=date_from,
        date_to=date_to,
        filters=filters,
        register=published(db),
        stages=list(db.scalars(select(Stage).order_by(Stage.stage))),
        users={u.user_id: u.name for u in db.scalars(select(User))},
        accounts={a.account_id: a for a in db.scalars(select(Account))},
        everything=everything,
    )
    scope.rows = [r for r in everything if _in_slice(r, filters)]
    scope.counted = [r for r in scope.rows if r.revenue["counted"]]
    in_range = [r for r in scope.counted if close_month_in(r.close_month, date_from, date_to)]
    scope.pipeline = [r for r in in_range if r.module in PIPELINE]
    scope.actual = [r for r in in_range if r.module == "deals"]
    scope.live = scope.pipeline + [r for r in scope.actual if r.record.deal_stage != DEAL_CLOSED]
    scope.lost_on = _lost_on(db)
    scope.closed_lost = scope.lost_between(date_from, date_to)
    return scope


# ---------------------------------------------------------------------------
# dimensions — what a tile groups by
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Dimension:
    """
    One way to split records. `value` reads a row; `field` names the register
    field whose picklist labels and orders the values, when there is one.
    """

    value: Callable[[Row, Scope], Any]
    field: tuple[str, str] | None = None
    #: 'picklist' (labelled and ordered by the register), 'account', 'user', 'stage', 'month'
    kind: str = "picklist"
    #: A second picklist value set, for values read off an Account.
    order_by_value: bool = False


def _account_attr(scope: Scope, account_id: str | None, attr: str) -> Any:
    account = scope.accounts.get(account_id or "")
    return getattr(account, attr, None) if account is not None else None


def _partner_tier(row: Row, scope: Scope) -> str | None:
    if not row.customer:
        return NO_PARTNER
    return _account_attr(scope, row.customer, "partner_tier")


DIMENSIONS: dict[str, Dimension] = {
    "stage": Dimension(lambda r, s: r.stage, kind="stage"),
    "close_month": Dimension(lambda r, s: r.close_month.replace(day=1) if r.close_month else None, kind="month"),
    "segment": Dimension(lambda r, s: r.lead("theme"), ("leads", "theme")),
    "destination_region": Dimension(lambda r, s: r.lead("destination_region"), ("leads", "destination_region")),
    "booking_region": Dimension(lambda r, s: r.lead("booking_region"), ("leads", "booking_region")),
    "deal_source": Dimension(lambda r, s: r.lead("deal_source"), ("leads", "deal_source")),
    "partner": Dimension(lambda r, s: r.customer, kind="account", order_by_value=True),
    "end_client": Dimension(lambda r, s: r.lead("end_client"), kind="account", order_by_value=True),
    "customer_class": Dimension(
        lambda r, s: _account_attr(s, r.lead("end_client"), "customer_class"), ("accounts", "customer_class")
    ),
    "partner_tier": Dimension(_partner_tier, ("accounts", "partner_tier")),
    "loss_reason": Dimension(lambda r, s: _loss_reason(r), ("leads", LOSS_REASON_FIELD), order_by_value=True),
}


@dataclass(frozen=True)
class Tile:
    """
    One tile's question: which records, split how. The browser's chart config
    names the same id; a later widget builder can send these three fields
    instead of an id and nothing below changes.
    """

    population: str
    dimension: str
    #: Keep the N largest groups and fold the rest into Others.
    top: int | None = None
    #: Count distinct values of this dimension per group (partners per tier).
    distinct: str | None = None


POPULATIONS: dict[str, Callable[[Scope], list[Row]]] = {
    #: The Open pipeline card's records.
    "pipeline": lambda s: s.pipeline,
    #: Pipeline plus Deals not finished — the stage funnel.
    "live": lambda s: s.live,
    #: Pipeline records whatever their close month; the close-month tile places them.
    "pipeline_any_month": lambda s: [r for r in s.counted if r.module in PIPELINE],
    #: The Closed Lost card's records.
    "lost": lambda s: s.closed_lost,
}

TILES: dict[str, Tile] = {
    "pipeline.stage": Tile("live", "stage"),
    "pipeline.close_month": Tile("pipeline_any_month", "close_month"),
    "pipeline.segment": Tile("pipeline", "segment"),
    "pipeline.delivery_region": Tile("pipeline", "destination_region"),
    "partners.partner": Tile("pipeline", "partner", top=TOP_N),
    "partners.deal_source": Tile("pipeline", "deal_source"),
    "partners.tier": Tile("pipeline", "partner_tier", distinct="partner"),
    "accounts.end_client": Tile("pipeline", "end_client", top=TOP_N),
    "accounts.customer_class": Tile("pipeline", "customer_class", distinct="end_client"),
    "winloss.reason": Tile("lost", "loss_reason"),
}


def _picklist_of(scope: Scope, ref: tuple[str, str] | None) -> str | None:
    if ref is None or scope.register is None:
        return None
    module, api_name = ref
    return next((f.get("picklist") for f in scope.register.fields_of(module) if f["api_name"] == api_name), None)


def _order_and_label(scope: Scope, dim: Dimension, key: Any) -> tuple[int, str]:
    """Where a value sorts, and what it is called. Unset values sort last."""
    if key is None:
        return (10_000, "Not set")
    if key == NO_PARTNER:
        return (10_001, "No partner")
    if dim.kind == "stage":
        name = next((s.name for s in scope.stages if s.stage == key), "")
        return (int(key), f"{key} {name}".strip())
    if dim.kind == "month":
        return (_month_index(key), key.strftime("%b %Y"))
    if dim.kind == "account":
        account = scope.accounts.get(key)
        return (0, account.account_name if account else key)
    picklist = _picklist_of(scope, dim.field)
    options = (scope.register.picklists.get(picklist, []) if scope.register and picklist else []) or []
    position = next((i for i, o in enumerate(options) if o.get("key") == key), len(options))
    label = next((o.get("label") for o in options if o.get("key") == key), None) or str(key)
    return (position, label)


def groups_of(scope: Scope, tile_id: str) -> dict[Any, list[Row]]:
    """key -> the rows behind it, for one tile. The ONE place a tile's grouping happens."""
    tile = TILES[tile_id]
    dim = DIMENSIONS[tile.dimension]
    out: dict[Any, list[Row]] = {}
    for row in POPULATIONS[tile.population](scope):
        out.setdefault(dim.value(row, scope), []).append(row)
    if tile.top is not None:
        ranked = sorted(out.items(), key=lambda kv: -sum(r.usd for r in kv[1]))
        kept = {k: v for k, v in ranked[: tile.top]}
        rest = [r for k, v in ranked[tile.top :] for r in v]
        if rest:
            kept[OTHERS] = rest
        out = kept
    return out


def _key_out(key: Any) -> str:
    if key is None:
        return NOT_SET
    if isinstance(key, date):
        return key.isoformat()
    return str(key)


def serialise_tile(scope: Scope, tile_id: str) -> list[dict[str, Any]]:
    """A tile's groups, labelled and ordered, each with its bucket."""
    tile = TILES[tile_id]
    dim = DIMENSIONS[tile.dimension]
    out = []
    for key, members in groups_of(scope, tile_id).items():
        if key == OTHERS:
            order, label = (9_999, f"Others ({len({DIMENSIONS[tile.dimension].value(r, scope) for r in members})})")
        else:
            order, label = _order_and_label(scope, dim, key)
        item = {"key": _key_out(key), "label": label, "order": order, **_bucket(members)}
        if tile.distinct:
            item["distinct"] = len({DIMENSIONS[tile.distinct].value(r, scope) for r in members} - {None})
        out.append(item)
    if dim.order_by_value:
        out.sort(key=lambda g: (g["key"] in (NOT_SET, OTHERS, NO_PARTNER), -g["usd"], g["label"]))
    else:
        out.sort(key=lambda g: (g["order"], g["label"]))
    return out


# ---------------------------------------------------------------------------
# tiles with their own shape
# ---------------------------------------------------------------------------


def funnel(scope: Scope) -> list[dict[str, Any]]:
    """Every stage, in order, even an empty one — the funnel's shape is the point."""
    groups = groups_of(scope, "pipeline.stage")
    return [
        {"key": str(s.stage), "stage": s.stage, "name": s.name, "module": s.owner_module, **_bucket(groups.get(s.stage, []))}
        for s in scope.stages
    ]


def close_month_columns(scope: Scope) -> dict[str, Any]:
    """
    The next six months from this month — or from the range's start, within the
    range — plus one column for records with no close month. A range wholly in
    the past shows its own months: pipeline whose close has slipped.
    """
    this_month = scope.today.replace(day=1)
    first = this_month
    if scope.date_from and scope.date_from.replace(day=1) > first:
        first = scope.date_from.replace(day=1)
    last = add_months(first, CLOSE_MONTHS - 1)
    if scope.date_to and scope.date_to.replace(day=1) < last:
        last = scope.date_to.replace(day=1)
    if last < first:  # the range is wholly past
        first = scope.date_from.replace(day=1) if scope.date_from else add_months(last, -(CLOSE_MONTHS - 1))
        last = scope.date_to.replace(day=1)
        if _month_index(last) - _month_index(first) >= MAX_RANGE_MONTHS:
            first = add_months(last, -(MAX_RANGE_MONTHS - 1))
    months = [add_months(first, i) for i in range(_month_index(last) - _month_index(first) + 1)]

    groups = groups_of(scope, "pipeline.close_month")
    columns = [{"key": m.isoformat(), "label": m.strftime("%b %Y"), **_bucket(groups.get(m, []))} for m in months]
    columns.append({"key": NOT_SET, "label": "No close month", **_bucket(groups.get(None, []))})
    earlier = [r for k, v in groups.items() if k is not None and k < months[0] for r in v]
    later = [r for k, v in groups.items() if k is not None and k > months[-1] for r in v]
    return {"columns": columns, "earlier": _bucket(earlier), "later": _bucket(later)}


def _targets_by_month(db: Session, scope: Scope, label: str) -> tuple[bool, dict[date, float]]:
    """(available, month -> target USD). Current rows only: never SUPERSEDED."""
    if any(scope.filters.get(name) for name in NOT_TARGETED):
        return False, {}
    query = (
        select(SalesTarget.period_month, func.sum(SalesTarget.target_amount_usd))
        .where(SalesTarget.fiscal_year == label, SalesTarget.status != "SUPERSEDED")
        .group_by(SalesTarget.period_month)
    )
    if scope.filters.get("owner"):
        query = query.where(SalesTarget.bd_owner_id == scope.filters["owner"])
    return True, {month: float(total or 0) for month, total in db.execute(query)}


def _cumulative(values: list[float]) -> list[float]:
    total, out = 0.0, []
    for v in values:
        total += v
        out.append(round(total, 2))
    return out


def performance(db: Session, scope: Scope) -> dict[str, Any]:
    """
    The fiscal year against plan: the S-curve and the four quarter meters.

    Booked is `won_between` per month — the Won card's own rule. Forecast adds,
    from this month on, the weighted value of open records by Expected Close
    Month: pipeline, plus counted Deals whose PO has not arrived. It joins the
    Booked line at this month; a record whose close month has passed, or who
    has none, is not in it and is counted in `forecast_left_out`.
    """
    label = scope.fiscal_year
    months = fiscal.months_of(label)
    this_month = scope.today.replace(day=1)
    # How far through the year we are: the index of this month, or before / after.
    if this_month < months[0]:
        now_at = -1
    elif this_month > months[-1]:
        now_at = 12
    else:
        now_at = months.index(this_month)

    booked = [sum(r.usd for r in scope.won_between(m, month_end(m))) for m in months]
    prior_label = fiscal.label_of(months[0] - timedelta(days=1))
    prior = [sum(r.usd for r in scope.won_between(m, month_end(m))) for m in fiscal.months_of(prior_label)]

    weighted_by_month = {m: 0.0 for m in months}
    left_out: list[Row] = []
    for r in scope.open_records:
        close = r.close_month.replace(day=1) if r.close_month else None
        if close in weighted_by_month and (now_at < 0 or months.index(close) >= now_at):
            weighted_by_month[close] += r.weighted
        elif close is None or close < this_month:
            left_out.append(r)
    weighted = [weighted_by_month[m] for m in months]

    available, target_map = _targets_by_month(db, scope, label)
    target_monthly = [target_map.get(m, 0.0) for m in months]
    target_set = available and any(v > 0 for v in target_monthly)

    booked_cum = _cumulative(booked)
    forecast: list[float | None] = [None] * 12
    if 0 <= now_at < 12:
        # Joins the Booked line at this month, at the same value. This month's
        # still-open records are added at the next point, with that month's own.
        running = booked_cum[now_at]
        forecast[now_at] = running
        pending = weighted[now_at]
        for i in range(now_at + 1, 12):
            running += pending + weighted[i]
            pending = 0.0
            forecast[i] = round(running, 2)
    elif now_at < 0:
        # A year not yet begun: nothing is booked, so it is the weighted pipeline alone.
        forecast = _cumulative(weighted)

    series = []
    target_cum = _cumulative(target_monthly)
    for i, month in enumerate(months):
        series.append(
            {
                "month": month.isoformat(),
                "target": target_cum[i] if target_set else None,
                "booked": booked_cum[i] if i <= now_at else None,
                "forecast": forecast[i],
                "prior": _cumulative(prior)[i],
            }
        )

    quarters = []
    for q in range(4):
        q_months = list(range(q * 3, q * 3 + 3))
        start, end = months[q_months[0]], month_end(months[q_months[-1]])
        ended = end < scope.today
        booked_q = sum(booked[i] for i in q_months)
        value = booked_q if ended else booked_q + sum(weighted[i] for i in q_months if i >= max(now_at, 0))
        target_q = sum(target_monthly[i] for i in q_months) if available else 0.0
        pct = round(value / target_q * 100) if target_q > 0 else None
        quarters.append(
            {
                "key": f"Q{q + 1}",
                "label": f"Q{q + 1}",
                "start": start,
                "end": end,
                "basis": "booked" if ended else "forecast",
                "value": round(value, 2),
                "booked": round(booked_q, 2),
                "target": round(target_q, 2) if target_q > 0 else None,
                "pct": pct,
                "band": None if pct is None else "good" if pct >= GOOD_FROM else "warning" if pct >= WARN_FROM else "critical",
            }
        )

    in_fy = scope.won_between(fiscal.first_day(label), fiscal.last_day(label))
    return {
        "fiscal_year": label,
        "prior_fiscal_year": prior_label,
        "start": fiscal.first_day(label),
        "end": fiscal.last_day(label),
        "months": series,
        "quarters": quarters,
        "targets": {
            "available": available,
            "set": target_set,
            #: The filters that stop a target being drawn, so the page can name them.
            "blocked_by": [name for name in NOT_TARGETED if scope.filters.get(name)],
        },
        "booked_in_year": {**_bucket(in_fy), "unpriced": sum(1 for r in in_fy if r.revenue["flag"])},
        #: Deals whose PO date is later this year than this month — in Won, not yet plotted.
        "booked_after_now": _bucket(
            [r for r in in_fy if now_at < 12 and _as_date(r.record.po_received_date) > month_end(this_month)]
        ),
        "forecast_left_out": _bucket(left_out),
    }


def _snapshot_dimension(scope: Scope) -> tuple[str | None, str | None, str | None]:
    """
    (dimension, column, value) the month-end history can answer these filters
    with, or (None, None, reason). Snapshots are cut one way at a time, never
    crossed: all, or one BD Owner, or one Booking Region, or one Segment.
    """
    cut = {"owner": ("BD_OWNER", "bd_owner_id"), "region": ("BOOKING_REGION", "booking_region"), "segment": ("SEGMENT", "segment")}
    active = [name for name, value in scope.filters.items() if value]
    if not active:
        return "ALL", None, None
    if len(active) == 1 and active[0] in cut:
        dimension, column = cut[active[0]]
        return dimension, column, scope.filters[active[0]]
    return None, None, "Month-end history is kept for one BD Owner, Booking Region or Segment at a time."


def month_end_history(db: Session, scope: Scope) -> dict[str, Any]:
    """
    The open pipeline at each month-end, from pipeline_snapshots. A month with
    no snapshot is null — a gap, never a zero. Months run through the range (or
    the last twelve), no later than this month.
    """
    this_month = scope.today.replace(day=1)
    last = min((scope.date_to or scope.today).replace(day=1), this_month)
    first = scope.date_from.replace(day=1) if scope.date_from else add_months(last, -11)
    if _month_index(last) - _month_index(first) >= MAX_RANGE_MONTHS:
        first = add_months(last, -(MAX_RANGE_MONTHS - 1))
    months = [add_months(first, i) for i in range(max(0, _month_index(last) - _month_index(first) + 1))]

    dimension, column, value = _snapshot_dimension(scope)
    if dimension is None:
        return {"available": False, "reason": value, "dimension": None, "months": []}

    by_month: dict[date, PipelineSnapshot] = {}
    if months:
        query = select(PipelineSnapshot).where(
            PipelineSnapshot.dimension == dimension,
            PipelineSnapshot.snapshot_date >= months[0],
            PipelineSnapshot.snapshot_date <= month_end(months[-1]),
        )
        if column:
            query = query.where(getattr(PipelineSnapshot, column) == value)
        for snap in db.scalars(query.order_by(PipelineSnapshot.snapshot_date)):
            by_month[snap.snapshot_date.replace(day=1)] = snap  # the latest in the month wins
    return {
        "available": True,
        "reason": None,
        "dimension": dimension,
        "months": [
            {
                "key": m.isoformat(),
                "label": m.strftime("%b %Y"),
                "snapshot_date": by_month[m].snapshot_date if m in by_month else None,
                "usd": float(by_month[m].open_value_usd) if m in by_month else None,
                "weighted_usd": float(by_month[m].weighted_value_usd) if m in by_month else None,
                "count": by_month[m].deal_count if m in by_month else None,
            }
            for m in months
        ],
    }


# ---------------------------------------------------------------------------
# the endpoints
# ---------------------------------------------------------------------------


def _refuse(code: str, message: str) -> HTTPException:
    return HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, {"code": code, "message": message})


def _resolve_range(period: str | None, date_from: date | None, date_to: date | None) -> tuple[date | None, date | None]:
    if period == "current_fy" and date_from is None and date_to is None:
        label = fiscal.label_of(today_company())
        return fiscal.first_day(label), fiscal.last_day(label)
    if date_from and date_to and date_from > date_to:
        raise _refuse("RANGE_INVERTED", "The From date must be on or before the To date.")
    if date_from and date_to and _month_index(date_to) - _month_index(date_from) >= MAX_RANGE_MONTHS:
        raise _refuse("RANGE_TOO_LONG", f"Choose a range of at most {MAX_RANGE_MONTHS} months.")
    return date_from, date_to


def _filters(request: Request) -> dict[str, str | None]:
    return {name: (request.query_params.get(name) or None) for name in FILTERS}


@router.get("/dashboard")
def dashboard(
    request: Request,
    period: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    date_from, date_to = _resolve_range(period, date_from, date_to)
    scope = build_scope(db, date_from=date_from, date_to=date_to, filters=_filters(request))
    today = scope.today

    won = scope.won_between(date_from, date_to)

    comparison = None
    previous_from, previous_to, previous_label = previous_period(date_from, date_to)
    if previous_from and previous_to:
        previous_in_range = [r for r in scope.counted if close_month_in(r.close_month, previous_from, previous_to)]
        comparison = {
            "from": previous_from,
            "to": previous_to,
            #: "Q1 FY2026-27" or "FY26" when the period is named, else null.
            "label": previous_label,
            "kpis": {
                "pipeline": _bucket([r for r in previous_in_range if r.module in PIPELINE]),
                "actual": _bucket([r for r in previous_in_range if r.module == "deals"]),
                "won": _bucket(scope.won_between(previous_from, previous_to)),
                "lost": _bucket(scope.lost_between(previous_from, previous_to)),
            },
        }

    owner_ids = {r.lead("bd_owner") for r in scope.everything if r.lead("bd_owner")}
    partner_ids = {r.customer for r in scope.everything if r.customer}
    pipeline = scope.pipeline
    return {
        "as_of": today,
        #: The instant this answer was computed — the page header prints it.
        "generated_at": now_utc(),
        "range": {
            "from": date_from,
            "to": date_to,
            "left_out": sum(1 for r in scope.counted if r.close_month is None) if scope.ranged else 0,
        },
        "comparison": comparison,
        "periods": period_presets(today),
        "fiscal_year_start_month": fiscal.FISCAL_YEAR_START_MONTH,
        "revenue_labels": REVENUE_LABEL,
        "filters": scope.filters,
        "owners": sorted(({"id": uid, "name": scope.users.get(uid, uid)} for uid in owner_ids), key=lambda o: o["name"].lower()),
        "partners": sorted(
            ({"id": aid, "name": scope.accounts[aid].account_name if aid in scope.accounts else aid} for aid in partner_ids),
            key=lambda o: o["name"].lower(),
        ),
        "kpis": {
            "pipeline": {
                **_bucket(pipeline),
                "by_module": {m: _bucket([r for r in pipeline if r.module == m]) for m in PIPELINE},
                "unpriced": sum(1 for r in pipeline if r.revenue["flag"]),
            },
            "actual": {**_bucket(scope.actual), "unpriced": sum(1 for r in scope.actual if r.revenue["flag"])},
            "won": {**_bucket(won), "unpriced": sum(1 for r in won if r.revenue["flag"])},
            "lost": _bucket(scope.closed_lost),
        },
        "performance": performance(db, scope),
        "tiles": {
            "pipeline.stage": funnel(scope),
            "pipeline.close_month": close_month_columns(scope),
            "pipeline.segment": serialise_tile(scope, "pipeline.segment"),
            "pipeline.delivery_region": serialise_tile(scope, "pipeline.delivery_region"),
            "pipeline.month_end": month_end_history(db, scope),
            "partners.partner": serialise_tile(scope, "partners.partner"),
            "partners.deal_source": serialise_tile(scope, "partners.deal_source"),
            "partners.tier": serialise_tile(scope, "partners.tier"),
            "accounts.end_client": serialise_tile(scope, "accounts.end_client"),
            "accounts.customer_class": serialise_tile(scope, "accounts.customer_class"),
            "winloss.reason": serialise_tile(scope, "winloss.reason"),
        },
    }


# ---------------------------------------------------------------------------
# the records behind a mark
# ---------------------------------------------------------------------------

#: Performance marks: the tile id, then how a key picks its rows.
PERFORMANCE_TILES = ("performance.booked", "performance.forecast", "performance.quarter")


def _performance_members(scope: Scope, tile: str, key: str) -> list[Row]:
    label = scope.fiscal_year
    months = fiscal.months_of(label)
    this_month = scope.today.replace(day=1)
    if tile == "performance.quarter":
        if key not in ("Q1", "Q2", "Q3", "Q4"):
            return []
        q = int(key[1]) - 1
        first, last = months[q * 3], months[q * 3 + 2]
        ended = month_end(last) < scope.today
        booked = scope.won_between(first, month_end(last))
        if ended:
            return booked
        start = max(first, this_month)
        return booked + [r for r in scope.open_records if r.close_month and start <= r.close_month.replace(day=1) <= last]
    try:
        month = date.fromisoformat(key)
    except ValueError:
        return []
    if tile == "performance.booked":
        return scope.won_between(month, month_end(month))
    # performance.forecast: what the point adds — open records closing that month.
    return [r for r in scope.open_records if r.close_month and r.close_month.replace(day=1) == month]


def _members(scope: Scope, tile: str, keys: list[str]) -> list[Row]:
    if tile in PERFORMANCE_TILES:
        return [r for key in keys for r in _performance_members(scope, tile, key)]
    if tile == "kpi.won":
        return scope.won_between(scope.date_from, scope.date_to)
    if tile not in TILES:
        raise _refuse("TILE_UNKNOWN", "That chart can't list its records.")
    groups = {_key_out(k): v for k, v in groups_of(scope, tile).items()}
    return [r for key in keys for r in groups.get(key, [])]


@router.get("/dashboard/records")
def dashboard_records(
    request: Request,
    tile: str,
    key: list[str] = Query(default=[]),
    period: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """The records behind one bar, slice, point or meter, under the same filters."""
    date_from, date_to = _resolve_range(period, date_from, date_to)
    scope = build_scope(db, date_from=date_from, date_to=date_to, filters=_filters(request))
    members = _members(scope, tile, key)
    stage_names = {s.stage: s.name for s in scope.stages}
    items = sorted(
        (
            {
                "module": r.module,
                "record_id": r.record_id,
                "name": r.name,
                "stage": r.stage,
                "stage_name": stage_names.get(r.stage) if r.stage is not None else None,
                "status": r.record.lead_status,
                "owner": scope.users.get(r.lead("bd_owner") or ""),
                "usd": r.revenue["usd"],
                "weighted_usd": round(r.weighted, 2),
                "flag": r.revenue["flag"],
            }
            for r in members
        ),
        key=lambda i: (-(i["usd"] or 0), i["name"]),
    )
    return {"tile": tile, "keys": key, **_bucket(members), "items": items}
