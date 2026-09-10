import re

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..audit import record_audit
from ..custom_fields import apply_write, extras_of, merge_into_row, resolve_write
from ..ids import next_reference_id
from ..models import Deal, Lead, Opportunity, OpportunityPaymentMilestone, User
from ..priority_flags import PRIORITY_FLAGS, PriorityFlagError, resolve_priority_flag_patch
from ..schemas import (
    OPPORTUNITY_LOOKUPS,
    OPPORTUNITY_SCALARS,
    OpportunityCreate,
    OpportunityOut,
    OpportunityUpdate,
)

router = APIRouter(tags=["opportunities"])

OPPORTUNITY_ID_PATTERN = re.compile(r"^OPP-(\d+)$")

RESERVED = {"_page", "_limit", "_sort", "_order", "_search", "q"}

# extensions.json list_views.opportunities, once written; kept narrow and
# textual like leads' own default.
DEFAULT_SEARCH = ("project_stage", "lead_status")

# Never set through the generic scalar loop — see _apply_priority_flags.
PRIORITY_FIELD_NAMES = {pf.flag for pf in PRIORITY_FLAGS} | {pf.rank for pf in PRIORITY_FLAGS}

# Row column names of the payment_milestones childlist, in register order —
# see models.OpportunityPaymentMilestone and extensions.json's child_spec.
MILESTONE_ROW_COLUMNS = (
    "milestone",
    "pct_of_contract",
    "trigger",
    "milestone_planned_date",
    "milestone_actual_date",
    "milestone_invoice_date",
    "milestone_payment_received_date",
    "milestone_status",
)


def _next_opportunity_id(db: Session) -> str:
    """From a stored high-water mark, never max(existing) — see app/ids.py."""
    highest = 0
    for existing in db.scalars(select(Opportunity.opportunity_id)):
        match = OPPORTUNITY_ID_PATTERN.match(existing or "")
        if match:
            highest = max(highest, int(match.group(1)))
    return next_reference_id(db, "opportunities", "OPP", 5, highest)


def _label_maps(db: Session) -> dict[str, dict[str, str]]:
    """id -> display name for each collection an Opportunity looks up.

    parent_lead resolves against the SAME leads table Lead's own
    parent_pursuit resolves against — the Leads table may be empty right now,
    which just means this map comes back empty too; nothing here requires a
    row to exist.
    """
    users = {u.user_id: u.name for u in db.scalars(select(User))}
    leads = {l.lead_id: l.opportunity_name for l in db.scalars(select(Lead))}
    return {"users": users, "leads": leads}


def _serialise(opp: Opportunity, labels: dict[str, dict[str, str]]) -> dict:
    row: dict[str, object] = {
        "id": opp.opportunity_id,
        "opportunity_id": opp.opportunity_id,
    }
    for name in OPPORTUNITY_SCALARS:
        value = getattr(opp, name)
        row[name] = float(value) if name in _MONEY_LIKE and value is not None else value
    row["created_date"] = opp.created_date
    row["modified_date"] = opp.modified_date

    row["payment_milestones"] = [
        {
            "milestone": m.milestone,
            "pct_of_contract": float(m.pct_of_contract) if m.pct_of_contract is not None else None,
            "trigger": m.trigger,
            "milestone_planned_date": m.milestone_planned_date,
            "milestone_actual_date": m.milestone_actual_date,
            "milestone_invoice_date": m.milestone_invoice_date,
            "milestone_payment_received_date": m.milestone_payment_received_date,
            "milestone_status": m.milestone_status,
        }
        for m in opp.payment_milestones
    ]

    joined = {}
    for field, collection in OPPORTUNITY_LOOKUPS.items():
        value = getattr(opp, field)
        if value and value in labels[collection]:
            joined[field] = labels[collection][value]
    if joined:
        row["__labels"] = joined

    # Admin-created field values, read back flat so the form engine sees them
    # exactly like a register field. Never overwrites a typed column.
    return merge_into_row(row, opp)


# Numeric register fields that come back from SQLAlchemy as Decimal, which is
# not JSON-serialisable — same convention as leads.py's _MONEY_LIKE.
_MONEY_LIKE = {
    "fx_rate_at_entry",
    "arr_annual_recurring",
    "one_time_revenue",
    "third_party_one_time",
    "third_party_recurring_per_year",
    "platform_licence_list_price",
    "services_and_implementation_cost",
    "third_party_cost",
    "perpetual_licence_fee",
    "final_negotiated_value",
    "agreed_advance_pct",
    "agreed_liability_cap_pct",
    "agreed_ld_cap_pct",
}


def _get_or_404(db: Session, opportunity_id: str) -> Opportunity:
    opp = db.get(Opportunity, opportunity_id)
    if opp is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"No opportunity {opportunity_id}")
    return opp


def _check_links(db: Session, payload, sent: set[str]) -> None:
    """
    Every OPPORTUNITY_LOOKUPS entry is a real foreign key. Rejecting an
    unknown id here turns a database integrity error into a message naming
    the field — same rule leads.py follows. parent_lead is included: the
    Leads table may be empty, so this simply rejects any parent_lead value
    that names a Lead which does not (yet) exist, rather than requiring one.
    """
    models_by_collection = {"leads": Lead, "users": User}
    for field, collection in OPPORTUNITY_LOOKUPS.items():
        if field not in sent:
            continue
        value = getattr(payload, field)
        if value and db.get(models_by_collection[collection], value) is None:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY, f"No such {collection[:-1]}: {value}"
            )


def _all_priority_rows(db: Session) -> list[dict[str, object]]:
    rows = db.execute(
        select(
            Opportunity.opportunity_id,
            Opportunity.is_low_hanging,
            Opportunity.low_hanging_rank,
            Opportunity.is_top_10,
            Opportunity.top_10_rank,
        )
    ).all()
    return [
        {
            "id": opportunity_id,
            "is_low_hanging": is_low_hanging,
            "low_hanging_rank": low_hanging_rank,
            "is_top_10": is_top_10,
            "top_10_rank": top_10_rank,
        }
        for opportunity_id, is_low_hanging, low_hanging_rank, is_top_10, top_10_rank in rows
    ]


def _apply_priority_flags(
    db: Session,
    opp: Opportunity,
    payload,
    sent: set[str],
    current_state: dict[str, object] | None,
) -> None:
    """
    Routes is_low_hanging/is_top_10 (and their ranks) through
    app.priority_flags instead of the generic scalar loop — the one pair of
    fields a write is not free to set directly. A rank sent without its flag
    in the same request is silently ignored, same as the frontend: the two
    are always written together, so there is nothing to validate a rank
    against on its own.

    Raises HTTPException(409) on a cap breach, an out-of-range rank, or a
    rank another Opportunity already holds.
    """
    touched = sent & {pf.flag for pf in PRIORITY_FLAGS}
    if not touched:
        return

    raw_patch: dict[str, object] = {}
    for pf in PRIORITY_FLAGS:
        if pf.flag in sent:
            raw_patch[pf.flag] = getattr(payload, pf.flag)
        if pf.rank in sent:
            raw_patch[pf.rank] = getattr(payload, pf.rank)

    try:
        resolved = resolve_priority_flag_patch(
            _all_priority_rows(db), opp.opportunity_id, current_state, raw_patch
        )
    except PriorityFlagError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc

    for key, value in resolved.items():
        setattr(opp, key, value)


def _apply_payment_milestones(db: Session, opp: Opportunity, payload) -> None:
    opp.payment_milestones.clear()
    db.flush()
    for order, row in enumerate(payload.payment_milestones or []):
        db.add(
            OpportunityPaymentMilestone(
                opportunity_id=opp.opportunity_id,
                row_order=order,
                **{name: getattr(row, name) for name in MILESTONE_ROW_COLUMNS},
            )
        )


@router.get("/opportunities", response_model=list[OpportunityOut])
def list_opportunities(request: Request, response: Response, db: Session = Depends(get_db)):
    """
    Opportunities, with the same list contract leads/accounts/contacts
    provide: equality filters (repeated = OR), free-text search, sort, page,
    and the row total on X-Total-Count.
    """
    labels = _label_maps(db)
    rows = [_serialise(o, labels) for o in db.scalars(select(Opportunity))]

    params = request.query_params

    for key in {k for k in params if k not in RESERVED}:
        wanted = set(params.getlist(key))
        rows = [r for r in rows if _matches(r.get(key), wanted)]

    q = (params.get("q") or "").strip().lower()
    if q:
        named = [f for f in (params.get("_search") or "").split(",") if f]
        fields = named or list(DEFAULT_SEARCH)
        rows = [r for r in rows if q in _text_of(r, fields).lower()]

    sort = params.get("_sort")
    if sort:
        rows.sort(key=lambda r: _sort_key(r, sort))
        if params.get("_order") == "desc":
            rows.reverse()

    total = len(rows)

    page = int(params.get("_page") or 0)
    limit = int(params.get("_limit") or 0)
    if page > 0 and limit > 0:
        rows = rows[(page - 1) * limit : page * limit]

    response.headers["X-Total-Count"] = str(total)
    return rows


def _matches(value, wanted: set[str]) -> bool:
    if isinstance(value, list):
        return any(str(v) in wanted for v in value)
    return str(value if value is not None else "") in wanted


def _display(row: dict, field: str) -> str:
    if field in OPPORTUNITY_LOOKUPS:
        label = (row.get("__labels") or {}).get(field)
        if label:
            return label
    value = row.get(field)
    return "" if value is None else str(value)


def _text_of(row: dict, fields: list[str]) -> str:
    return " ".join(_display(row, f) for f in fields)


def _sort_key(row: dict, field: str):
    text = _display(row, field)
    return (1, "") if text == "" else (0, text.lower())


@router.get("/opportunities/{opportunity_id}", response_model=OpportunityOut)
def get_opportunity(opportunity_id: str, db: Session = Depends(get_db)):
    return _serialise(_get_or_404(db, opportunity_id), _label_maps(db))


@router.post("/opportunities", response_model=OpportunityOut, status_code=status.HTTP_201_CREATED)
def create_opportunity(payload: OpportunityCreate, db: Session = Depends(get_db)):
    opportunity_id = payload.opportunity_id or _next_opportunity_id(db)

    if db.get(Opportunity, opportunity_id) is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, f"{opportunity_id} already exists")

    sent = set(payload.model_dump(exclude_unset=True))
    _check_links(db, payload, sent & set(OPPORTUNITY_LOOKUPS))

    opp = Opportunity(opportunity_id=opportunity_id)
    _BOOL_DEFAULTS = {
        "nomination_bid": False,
        "incumbent_only": False,
        "pay_when_paid": False,
        "active": True,
    }
    for name in OPPORTUNITY_SCALARS:
        if name in PRIORITY_FIELD_NAMES:
            continue
        value = getattr(payload, name)
        if value is None and name in _BOOL_DEFAULTS:
            value = _BOOL_DEFAULTS[name]
        setattr(opp, name, value)

    # Explicit defaults before validation: resolve_priority_flag_patch reads
    # `current_state` to know what was already on, and there is no row yet.
    opp.is_low_hanging = False
    opp.low_hanging_rank = None
    opp.is_top_10 = False
    opp.top_10_rank = None

    db.add(opp)
    db.flush()  # payment_milestones and the priority-flag self-exclusion both need the row to exist

    _apply_priority_flags(db, opp, payload, sent, current_state=None)
    _apply_payment_milestones(db, opp, payload)

    # Values for Administration-created fields go to custom_fields JSONB,
    # never to a column of their own. Unknown keys are not stored — see
    # app/custom_fields.py::resolve_write.
    apply_write(
        opp,
        resolve_write(
            db,
            "opportunities",
            explicit=payload.custom_fields,
            extras=extras_of(payload),
        ),
    )
    record_audit(
        db,
        module="opportunities",
        record_id=opportunity_id,
        action="created",
        actor=opp.modified_by or opp.created_by,
        changed_fields=sorted(sent),
    )
    db.commit()
    db.refresh(opp)
    return _serialise(opp, _label_maps(db))


@router.patch("/opportunities/{opportunity_id}", response_model=OpportunityOut)
def patch_opportunity(opportunity_id: str, payload: OpportunityUpdate, db: Session = Depends(get_db)):
    """Applies only the fields present in the request body."""
    return _write(db, opportunity_id, payload, set(payload.model_dump(exclude_unset=True)))


@router.put("/opportunities/{opportunity_id}", response_model=OpportunityOut)
def put_opportunity(opportunity_id: str, payload: OpportunityUpdate, db: Session = Depends(get_db)):
    """
    Kept for the same reason accounts, contacts and leads have one: the
    prototype's record editor and HeaderStrip both PUT when they save. Still
    applies only what was sent.
    """
    return _write(db, opportunity_id, payload, set(payload.model_dump(exclude_unset=True)))


def _write(db: Session, opportunity_id: str, payload: OpportunityUpdate, sent: set[str]) -> dict:
    opp = _get_or_404(db, opportunity_id)
    _check_links(db, payload, sent & set(OPPORTUNITY_LOOKUPS))

    current_state = {
        "is_low_hanging": opp.is_low_hanging,
        "low_hanging_rank": opp.low_hanging_rank,
        "is_top_10": opp.is_top_10,
        "top_10_rank": opp.top_10_rank,
    }
    _apply_priority_flags(db, opp, payload, sent, current_state)

    for name in OPPORTUNITY_SCALARS:
        if name not in sent or name in PRIORITY_FIELD_NAMES:
            continue
        setattr(opp, name, getattr(payload, name))

    if "payment_milestones" in sent:
        _apply_payment_milestones(db, opp, payload)

    # Values for Administration-created fields go to custom_fields JSONB,
    # never to a column of their own. Unknown keys are not stored — see
    # app/custom_fields.py::resolve_write.
    apply_write(
        opp,
        resolve_write(
            db,
            "opportunities",
            explicit=payload.custom_fields,
            extras=extras_of(payload),
        ),
    )
    record_audit(
        db,
        module="opportunities",
        record_id=opportunity_id,
        action="updated",
        actor=opp.modified_by or opp.created_by,
        changed_fields=sorted(sent),
    )
    db.commit()
    db.refresh(opp)
    return _serialise(opp, _label_maps(db))


@router.delete("/opportunities/{opportunity_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_opportunity(opportunity_id: str, db: Session = Depends(get_db)):
    """
    Hard delete. payment_milestones rows cascade, but a converted Deal reads
    its identity through parent_opportunity under a RESTRICT constraint, so
    that case is refused with a 409 rather than reaching COMMIT and surfacing
    as a 500.
    """
    opp = _get_or_404(db, opportunity_id)

    deals = db.scalars(select(Deal.deal_id).where(Deal.parent_opportunity == opportunity_id)).all()
    if deals:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"{opportunity_id} was converted and is still the parent of "
            f"{len(deals)} deal(s): {', '.join(deals[:5])}"
            f"{'…' if len(deals) > 5 else ''}. Deactivate it instead.",
        )
    record_audit(db, module="opportunities", record_id=opportunity_id, action="deleted")
    db.delete(opp)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
