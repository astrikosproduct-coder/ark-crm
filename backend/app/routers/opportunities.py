import re

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth import current_user
from ..list_query import run_list_query
from ..read_through_rows import attach_read_through
from ..messages import already_exists, not_found, picked_record_missing, refusal
from ..changes import child_snapshot, custom_field_diff, diff, list_changes, snapshot
from ..clock import days_since, now_utc
from ..database import get_db
from ..audit import record_audit
from ..custom_fields import apply_write, extras_of, merge_into_row, resolve_write
from ..ids import next_reference_id
from ..stage_entry import stage_entry_dates
from ..progression import after_write as pct_after_write, plan_write, serialise_pct
from ..models import Deal, Lead, Opportunity, OpportunityPaymentMilestone, User
from ..priority_flags import PRIORITY_FLAGS, PriorityFlagError, resolve_priority_flag_patch
from ..conversion import begin_conversion, complete_conversion
from ..pursuits import PURSUIT_STAMPED, group_names, guard_close, inherit_on_create
from ..revenue import revenue_context, revenue_of
from ..schemas import (
    LEAD_LOOKUPS,
    OPPORTUNITY_LOOKUPS,
    OPPORTUNITY_SCALARS,
    OpportunityCreate,
    OpportunityOut,
    OpportunityUpdate,
)

router = APIRouter(tags=["opportunities"])

OPPORTUNITY_ID_PATTERN = re.compile(r"^OPP-(\d+)$")


# extensions.json list_views.opportunities, once written; kept narrow and
# textual like leads' own default.
DEFAULT_SEARCH = ("project_stage", "lead_status")

# Never set through the generic scalar loop — see _apply_priority_flags.
PRIORITY_FIELD_NAMES = {pf.flag for pf in PRIORITY_FLAGS} | {pf.rank for pf in PRIORITY_FLAGS}

# Stamped from the Entra session and the server clock, never from the payload.
# See the same constant in routers/leads.py for the full account of why.
SYSTEM_STAMPED = frozenset({"created_by", "created_date", "modified_by", "modified_date"})

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
    # Not a lookup collection — no column points at it. It rides here because
    # it is the same shape of join (an id resolved to a display name, once per
    # page rather than once per row) and the alternative was passing the
    # session into _serialise.
    return {
        "users": users,
        "leads": leads,
        # A pursuit group by name, never PG-0002 — see routers/leads.py.
        "pursuit_groups": group_names(db),
        # What each row contributes to its stage's total — see app/revenue.py.
        "revenue": revenue_context(db),
        # Nor is this a display-name join, and it is here for the same reason:
        # one query for the page rather than one per row. See app/stage_entry.py.
        "stage_entered": stage_entry_dates(
            db,
            "opportunities",
            {
                o.opportunity_id: o.project_stage
                for o in db.scalars(select(Opportunity))
            },
        ),
    }


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

    # TCV is computed and never stored, so until now a list row simply had no
    # total_value_tcv and every Opportunities card showed "—". Served from the
    # same evaluation the pipeline total uses, so the card and the column
    # header cannot disagree. See app/revenue.py.
    revenue = revenue_of(labels["revenue"], "opportunities", opp)
    row["revenue"] = revenue
    row["total_value_tcv"] = revenue["value"]
    row["pursuit_primary"] = (
        labels["revenue"].primary_of_group.get(opp.pursuit_group) if opp.pursuit_group else None
    )

    # The two Aging fields. Served here for the first time — Opportunities
    # rendered "No formula in the field register for this field." in that
    # section because nothing anywhere produced them. See app/stage_entry.py.
    entered = labels["stage_entered"].get(opp.opportunity_id) or opp.created_date
    row["stage_entered_date"] = entered
    row["days_in_current_stage"] = days_since(entered)
    row["days_since_last_update"] = days_since(opp.modified_date or opp.created_date)

    # The stage pair and its override state — which overwrites the raw
    # Decimals the scalar loop just put in the row. See app/progression.py.
    row.update(serialise_pct(opp))

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
    # overridden_by is NOT in OPPORTUNITY_LOOKUPS — see leads.py's own note:
    # that dict also drives create-time validation over every key
    # unconditionally, and overridden_by is never a payload field.
    if opp.overridden_by and opp.overridden_by in labels["users"]:
        joined["overridden_by"] = labels["users"][opp.overridden_by]
    if opp.pursuit_group and opp.pursuit_group in labels["pursuit_groups"]:
        joined["pursuit_group"] = labels["pursuit_groups"][opp.pursuit_group]
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
        raise not_found("opportunity")
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
        # SYSTEM_STAMPED fields are never written from the payload, so
        # validating them would 422 a request over a discarded value. See the
        # same guard in routers/leads.py::_check_links.
        if field not in sent or field in SYSTEM_STAMPED:
            continue
        value = getattr(payload, field)
        if value and db.get(models_by_collection[collection], value) is None:
            raise picked_record_missing({"accounts": "account", "users": "person", "contacts": "contact", "leads": "lead", "opportunities": "opportunity"}.get(collection, "record"))


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


def _children_of(opp: Opportunity) -> dict[str, list[dict]]:
    """The child list as comparable rows — the before/after of list_changes."""
    return {"payment_milestones": child_snapshot(opp.payment_milestones, MILESTONE_ROW_COLUMNS)}


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
    records = list(db.scalars(select(Opportunity)))
    rows = [_serialise(o, labels) for o in records]
    # Identity is read through the root Lead — without it a filter or sort on
    # End Client or an owner matched nothing. See app/read_through_rows.py.
    attach_read_through(db, "opportunities", list(zip(records, rows)))

    rows, total = run_list_query(
        rows, request.query_params, lookups=set(OPPORTUNITY_LOOKUPS) | set(LEAD_LOOKUPS), default_search=DEFAULT_SEARCH
    )
    response.headers["X-Total-Count"] = str(total)
    return rows


@router.get("/opportunities/{opportunity_id}", response_model=OpportunityOut)
def get_opportunity(opportunity_id: str, db: Session = Depends(get_db)):
    return _serialise(_get_or_404(db, opportunity_id), _label_maps(db))


@router.post("/opportunities", response_model=OpportunityOut, status_code=status.HTTP_201_CREATED)
def create_opportunity(
    payload: OpportunityCreate,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    opportunity_id = payload.opportunity_id or _next_opportunity_id(db)

    if db.get(Opportunity, opportunity_id) is not None:
        raise already_exists()

    sent = set(payload.model_dump(exclude_unset=True))
    _check_links(db, payload, sent & set(OPPORTUNITY_LOOKUPS))
    # Lead -> Opportunity is one transaction, and never twice: the Lead is
    # locked here and refused if it already became something. See
    # app/conversion.py.
    converting = begin_conversion(db, "leads", payload.parent_lead)

    opp = Opportunity(opportunity_id=opportunity_id)
    # Before a value is applied: validates the two numbers and any override.
    pct_plan = plan_write(db, "opportunities", opp, payload, sent, creating=True)
    _BOOL_DEFAULTS = {
        "nomination_bid": False,
        "incumbent_only": False,
        "pay_when_paid": False,
        "active": True,
    }
    for name in OPPORTUNITY_SCALARS:
        if name in PRIORITY_FIELD_NAMES or name in SYSTEM_STAMPED or name in PURSUIT_STAMPED:
            continue
        value = getattr(payload, name)
        if value is None and name in _BOOL_DEFAULTS:
            value = _BOOL_DEFAULTS[name]
        setattr(opp, name, value)
    # Born open, like a Lead and a Deal — a blank status is not a state.
    if not opp.lead_status:
        opp.lead_status = "OPEN"

    # The pursuit carries on: a secondary Lead becomes a secondary Opportunity.
    # From the parent, never from the body — see app/pursuits.py.
    inherit_on_create(db, "opportunities", opp)

    # See SYSTEM_STAMPED.
    stamped_at = now_utc()
    opp.created_by = user.user_id
    opp.created_date = stamped_at
    opp.modified_by = user.user_id
    opp.modified_date = stamped_at

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
        actor=user.user_id,
        changed_fields=sorted(sent),
    )

    # The stage's Progression %/Probability %. See app/progression.py.
    pct_after_write(db, "opportunities", opp, pct_plan, actor=user.user_id)

    if converting is not None:
        complete_conversion(
            db,
            source_module="leads",
            source=converting,
            target_module="opportunities",
            target_id=opportunity_id,
            sent=sent,
            note=payload.conversion_note,
            actor=user.user_id,
        )

    db.commit()
    db.refresh(opp)
    return _serialise(opp, _label_maps(db))


@router.patch("/opportunities/{opportunity_id}", response_model=OpportunityOut)
def patch_opportunity(
    opportunity_id: str,
    payload: OpportunityUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    """Applies only the fields present in the request body."""
    return _write(db, opportunity_id, payload, set(payload.model_dump(exclude_unset=True)), user)


@router.put("/opportunities/{opportunity_id}", response_model=OpportunityOut)
def put_opportunity(
    opportunity_id: str,
    payload: OpportunityUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    """
    Kept for the same reason accounts, contacts and leads have one: the
    prototype's record editor and HeaderStrip both PUT when they save. Still
    applies only what was sent.
    """
    return _write(db, opportunity_id, payload, set(payload.model_dump(exclude_unset=True)), user)


def _write(
    db: Session,
    opportunity_id: str,
    payload: OpportunityUpdate,
    sent: set[str],
    user: User,
) -> dict:
    opp = _get_or_404(db, opportunity_id)
    _check_links(db, payload, sent & set(OPPORTUNITY_LOOKUPS))

    # The before half of the diff, read before anything is applied — including
    # the priority flags, which _apply_priority_flags writes below and which a
    # reviewer very much wants to see move. See routers/leads.py::_write.
    tracked = [
        n for n in OPPORTUNITY_SCALARS if (n in sent or n in PRIORITY_FIELD_NAMES) and n not in SYSTEM_STAMPED
    ]
    before = snapshot(opp, tracked)
    before_custom = dict(opp.custom_fields or {})
    before_children = _children_of(opp)

    current_state = {
        "is_low_hanging": opp.is_low_hanging,
        "low_hanging_rank": opp.low_hanging_rank,
        "is_top_10": opp.is_top_10,
        "top_10_rank": opp.top_10_rank,
    }
    _apply_priority_flags(db, opp, payload, sent, current_state)

    # Before anything is applied — see routers/leads.py::_write.
    pct_plan = plan_write(db, "opportunities", opp, payload, sent)

    if "lead_status" in sent:
        guard_close(db, "opportunities", opp, payload.lead_status)

    for name in OPPORTUNITY_SCALARS:
        if name not in sent or name in PRIORITY_FIELD_NAMES or name in SYSTEM_STAMPED or name in PURSUIT_STAMPED:
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
    # See SYSTEM_STAMPED.
    opp.modified_by = user.user_id
    opp.modified_date = now_utc()

    changed = diff(before, snapshot(opp, tracked))
    changed += custom_field_diff(before_custom, opp.custom_fields)
    # A child list counts as changed only when its ROWS moved — never merely
    # because the editor's whole-section PUT carried it. See changes.list_changes.
    db.flush()
    # See routers/leads.py — the relationship is stale after a db.add() insert.
    db.expire(opp, ["payment_milestones"])
    changed += list_changes(before_children, _children_of(opp))

    record_audit(
        db,
        module="opportunities",
        record_id=opportunity_id,
        action="updated",
        actor=user.user_id,
        changed_fields=sorted(sent),
        changed=changed,
    )

    # See routers/leads.py::_write.
    pct_after_write(db, "opportunities", opp, pct_plan, actor=user.user_id)

    db.commit()
    db.refresh(opp)
    return _serialise(opp, _label_maps(db))


@router.delete("/opportunities/{opportunity_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_opportunity(
    opportunity_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    """
    Hard delete. payment_milestones rows cascade, but a converted Deal reads
    its identity through parent_opportunity under a RESTRICT constraint, so
    that case is refused with a 409 rather than reaching COMMIT and surfacing
    as a 500.
    """
    opp = _get_or_404(db, opportunity_id)

    if opp.pursuit_group:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            refusal(
                "REMOVE_FROM_GROUP_FIRST",
                "This opportunity is in a pursuit group, so it can't be deleted.",
                ["Remove it from the group first."],
                group_id=opp.pursuit_group,
            ),
        )

    deals = db.scalars(select(Deal.deal_id).where(Deal.parent_opportunity == opportunity_id)).all()
    if deals:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            refusal(
                "OPPORTUNITY_HAS_DEALS",
                "This opportunity already became a Deal, so it can't be deleted.",
                deals=deals,
            ),
        )
    record_audit(
        db, module="opportunities", record_id=opportunity_id, action="deleted", actor=user.user_id
    )
    db.delete(opp)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
