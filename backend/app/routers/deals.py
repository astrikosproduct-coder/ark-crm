import re

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth import current_user
from ..list_query import run_list_query
from ..read_through_rows import attach_read_through, read_through_names
from ..messages import already_exists, not_found, picked_record_missing, refusal
from ..requirements import check_save
from ..changes import child_snapshot, custom_field_diff, diff, list_changes, snapshot
from ..clock import days_since, now_utc
from ..database import get_db
from ..audit import record_audit
from ..custom_fields import apply_write, extras_of, merge_into_row, resolve_write
from ..carry_forward import locked_violations, seed_values
from ..ids import next_reference_id
from ..stage_entry import stage_entry_dates
from ..thresholds import check_thresholds
from ..progression import after_write as pct_after_write, plan_write, serialise_pct
from ..conversion import begin_conversion, complete_conversion
from ..pursuits import PURSUIT_STAMPED, guard_close, guard_win, inherit_on_create
from ..revenue import guard_final_value_matches_tcv, revenue_context, revenue_of
from ..models import (
    Account,
    Deal,
    DealBidCommitment,
    DealExpansionUseCase,
    FieldDefinition,
    Lead,
    Opportunity,
    User,
)
from ..schemas import (
    LEAD_LOOKUPS,
    DEAL_LOOKUPS,
    DEAL_SCALARS,
    DealCreate,
    DealMilestoneDeliveryIn,
    DealOut,
    DealPaymentMilestoneOut,
    DealUpdate,
)

router = APIRouter(tags=["deals"])

DEAL_ID_PATTERN = re.compile(r"^DEAL-(\d+)$")


# extensions.json list_views.deals, once written; kept narrow and textual like
# leads' and opportunities' own defaults.
DEFAULT_SEARCH = ("deal_name", "deal_stage")

# Written by the server on every save and discarded from whatever a payload
# claims — the same four names and the same rule leads.py and opportunities.py
# apply. Deals had none of them until 0030: their timestamps were called
# created_by_date / modified_by_date and no actor was stored at all.
SYSTEM_STAMPED = frozenset({"created_by", "created_date", "modified_by", "modified_date"})

# Row column names of the two childlists, in register order — see
# models.DealBidCommitment/DealExpansionUseCase and extensions.json's
# child_spec entries.
BID_COMMITMENT_ROW_COLUMNS = (
    "guarantee_type",
    "guarantee_value",
    "guarantee_issue_date",
    "guarantee_expiry_date",
    "guarantee_issuing_bank",
    "guarantee_status",
)

EXPANSION_USE_CASE_ROW_COLUMNS = (
    "use_case_no",
    "use_case_description",
    "use_case_status",
    "estimated_value",
)


def _next_deal_id(db: Session) -> str:
    """From a stored high-water mark, never max(existing) — see app/ids.py."""
    highest = 0
    for existing in db.scalars(select(Deal.deal_id)):
        match = DEAL_ID_PATTERN.match(existing or "")
        if match:
            highest = max(highest, int(match.group(1)))
    return next_reference_id(db, "deals", "DEAL", 5, highest)


def _label_maps(db: Session) -> dict[str, dict[str, str]]:
    """id -> display name for each collection a Deal looks up.

    parent_lead resolves against leads, parent_opportunity against
    opportunities — either link may be empty depending which conversion path
    created a given Deal, same reasoning opportunities.py's own _label_maps
    gives for its (possibly empty) leads map.

    opportunities has no entries: models.Opportunity stores no name of its
    own (opportunity_name is read_through its parent Lead, see the class
    docstring) — there is nothing here to join. A __labels lookup that finds
    nothing falls back to showing the raw id, the same graceful degradation
    src/mocks/userDirectory.ts already documents for a directory that is
    empty or unavailable, so parent_opportunity is left to show DEAL-00031's
    OPP-00005 id rather than a fabricated name.
    """
    accounts = {a.account_id: a.account_name for a in db.scalars(select(Account))}
    users = {u.user_id: u.name for u in db.scalars(select(User))}
    leads = {l.lead_id: l.opportunity_name for l in db.scalars(select(Lead))}
    return {
        "accounts": accounts,
        "users": users,
        "leads": leads,
        "opportunities": {},
        # What each row contributes to its stage's total — see app/revenue.py.
        "revenue": revenue_context(db),
        # Not a lookup collection — no column points at it. Rides here for the
        # same reason opportunities.py's own _label_maps carries one: one join
        # per page rather than one per row.
        "stage_entered": stage_entry_dates(
            db,
            "deals",
            {d.deal_id: d.deal_stage for d in db.scalars(select(Deal))},
        ),
    }


def _serialise(deal: Deal, labels: dict[str, dict[str, str]]) -> dict:
    row: dict[str, object] = {
        "id": deal.deal_id,
        "deal_id": deal.deal_id,
    }
    for name in DEAL_SCALARS:
        value = getattr(deal, name)
        row[name] = float(value) if name in _MONEY_LIKE and value is not None else value
    row["created_date"] = deal.created_date
    row["modified_date"] = deal.modified_date

    row["revenue"] = revenue_of(labels["revenue"], "deals", deal)
    row["pursuit_primary"] = (
        labels["revenue"].primary_of_group.get(deal.pursuit_group) if deal.pursuit_group else None
    )

    # The two Aging fields, served here for the first time — Deals rendered
    # "No formula in the field register for this field." in that section
    # because nothing anywhere produced them. Counted off created_date /
    # modified_date, the same two every other module counts off since 0030.
    entered = labels["stage_entered"].get(deal.deal_id) or deal.created_date
    row["stage_entered_date"] = entered
    row["days_in_current_stage"] = days_since(entered)
    row["days_since_last_update"] = days_since(deal.modified_date or deal.created_date)

    # The stage pair and its override state — which overwrites the raw
    # Decimals the scalar loop just put in the row. See app/progression.py.
    row.update(serialise_pct(deal))

    row["bid_commitments_register"] = [
        {
            "guarantee_type": c.guarantee_type,
            "guarantee_value": float(c.guarantee_value) if c.guarantee_value is not None else None,
            "guarantee_issue_date": c.guarantee_issue_date,
            "guarantee_expiry_date": c.guarantee_expiry_date,
            "guarantee_issuing_bank": c.guarantee_issuing_bank,
            "guarantee_status": c.guarantee_status,
        }
        for c in deal.bid_commitments
    ]
    row["expansion_use_cases"] = [
        {
            "use_case_no": u.use_case_no,
            "use_case_description": u.use_case_description,
            "use_case_status": u.use_case_status,
            "estimated_value": float(u.estimated_value) if u.estimated_value is not None else None,
        }
        for u in deal.expansion_use_cases
    ]

    joined = {}
    for field, collection in DEAL_LOOKUPS.items():
        value = getattr(deal, field)
        if value and value in labels[collection]:
            joined[field] = labels[collection][value]
    # overridden_by is NOT in DEAL_LOOKUPS — see leads.py's own note: that
    # dict also drives create-time validation over every key unconditionally,
    # and overridden_by is never a payload field.
    if deal.overridden_by and deal.overridden_by in labels["users"]:
        joined["overridden_by"] = labels["users"][deal.overridden_by]
    if joined:
        row["__labels"] = joined

    # Admin-created field values, read back flat so the form engine sees them
    # exactly like a register field. Never overwrites a typed column.
    return merge_into_row(row, deal)


# Numeric register fields that come back from SQLAlchemy as Decimal, which is
# not JSON-serialisable — same convention as leads.py/opportunities.py's own
# _MONEY_LIKE.
_MONEY_LIKE = {
    "contract_value",
    "arr_annual_recurring",
    "one_time_revenue",
    "third_party_one_time",
    "third_party_recurring_per_year",
    "csat_score",
    "incremental_value",
}


def _get_or_404(db: Session, deal_id: str) -> Deal:
    deal = db.get(Deal, deal_id)
    if deal is None:
        raise not_found("deal")
    return deal


def _check_links(db: Session, payload, sent: set[str]) -> None:
    """
    Every DEAL_LOOKUPS entry is a real foreign key. Rejecting an unknown id
    here turns a database integrity error into a message naming the field —
    same rule leads.py and opportunities.py follow. Neither parent_lead nor
    parent_opportunity is required to be sent: a Deal converted from a Lead
    leaves parent_opportunity unset and vice versa, see models.Deal.
    """
    models_by_collection = {
        "leads": Lead,
        "opportunities": Opportunity,
        "accounts": Account,
        "users": User,
    }
    # collection[:-1] (leads.py's and opportunities.py's own singularisation)
    # mangles "opportunities" into "opportunitie" — Deal is the first module
    # to look that collection up, so the irregular plural needs a name here.
    singular = {"opportunities": "opportunity"}
    for field, collection in DEAL_LOOKUPS.items():
        # created_by / modified_by are lookups too, and are SYSTEM_STAMPED, so
        # they are never written from the payload. Never validate what you do
        # not write — leads.py's own words.
        if field not in sent or field in SYSTEM_STAMPED:
            continue
        value = getattr(payload, field)
        if value and db.get(models_by_collection[collection], value) is None:
            noun = singular.get(collection, collection[:-1])
            raise picked_record_missing(noun)


def _children_of(deal: Deal) -> dict[str, list[dict]]:
    """Both child lists as comparable rows — the before/after of list_changes."""
    return {
        "bid_commitments_register": child_snapshot(deal.bid_commitments, BID_COMMITMENT_ROW_COLUMNS),
        "expansion_use_cases": child_snapshot(deal.expansion_use_cases, EXPANSION_USE_CASE_ROW_COLUMNS),
    }


def _apply_bid_commitments(db: Session, deal: Deal, payload) -> None:
    deal.bid_commitments.clear()
    db.flush()
    for order, row in enumerate(payload.bid_commitments_register or []):
        db.add(
            DealBidCommitment(
                deal_id=deal.deal_id,
                row_order=order,
                **{name: getattr(row, name) for name in BID_COMMITMENT_ROW_COLUMNS},
            )
        )


def _apply_expansion_use_cases(db: Session, deal: Deal, payload) -> None:
    deal.expansion_use_cases.clear()
    db.flush()
    for order, row in enumerate(payload.expansion_use_cases or []):
        db.add(
            DealExpansionUseCase(
                deal_id=deal.deal_id,
                row_order=order,
                **{name: getattr(row, name) for name in EXPANSION_USE_CASE_ROW_COLUMNS},
            )
        )


@router.get("/deals", response_model=list[DealOut])
def list_deals(request: Request, response: Response, db: Session = Depends(get_db)):
    """
    Deals, with the same list contract leads/opportunities/accounts/contacts
    provide: equality filters (repeated = OR), free-text search, sort, page,
    and the row total on X-Total-Count.
    """
    labels = _label_maps(db)
    records = list(db.scalars(select(Deal)))
    rows = [_serialise(d, labels) for d in records]
    # Identity is read through the root Lead — without it a filter or sort on
    # End Client or an owner matched nothing. See app/read_through_rows.py.
    attach_read_through(db, "deals", list(zip(records, rows)))

    rows, total = run_list_query(
        rows, request.query_params, lookups=set(DEAL_LOOKUPS) | set(LEAD_LOOKUPS), default_search=DEFAULT_SEARCH
    )
    response.headers["X-Total-Count"] = str(total)
    return rows


@router.get("/deals/{deal_id}", response_model=DealOut)
def get_deal(deal_id: str, db: Session = Depends(get_db)):
    return _serialise(_get_or_404(db, deal_id), _label_maps(db))


@router.post("/deals", response_model=DealOut, status_code=status.HTTP_201_CREATED)
def create_deal(
    payload: DealCreate,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    deal_id = payload.deal_id or _next_deal_id(db)

    if db.get(Deal, deal_id) is not None:
        raise already_exists()

    sent = set(payload.model_dump(exclude_unset=True))
    _check_links(db, payload, sent & set(DEAL_LOOKUPS))
    # Min / Max value from the register, e.g. CSAT Score 1-10 — app/thresholds.py.
    check_thresholds(db, "deals", payload.model_dump(include=sent))
    # Opportunity -> Deal (or a pre-split Lead -> Deal) is one transaction,
    # and never twice. See app/conversion.py.
    source_module = "opportunities" if payload.parent_opportunity else "leads"
    converting = begin_conversion(db, source_module, payload.parent_opportunity or payload.parent_lead)

    deal = Deal(deal_id=deal_id)
    # Before a value is applied: validates the two numbers and any override.
    pct_plan = plan_write(db, "deals", deal, payload, sent, creating=True)
    _BOOL_DEFAULTS = {
        "order_booked": False,
        # NOT NULL since 0030, so a payload that omits it must still land a
        # value rather than a None the column refuses.
        "payment_schedule_confirmed": False,
        "active": True,
    }
    # A field the Deal shows live from its Lead stores nothing here (metadata
    # v2; End Client since G1, 24 Sep 2026). A value sent for one is not kept.
    shown_live = set(read_through_names(db, "deals"))
    for name in DEAL_SCALARS:
        if name in PURSUIT_STAMPED or name in SYSTEM_STAMPED or name in shown_live:
            continue
        value = getattr(payload, name)
        if value is None and name in _BOOL_DEFAULTS:
            value = _BOOL_DEFAULTS[name]
        setattr(deal, name, value)
    # A Deal is born open; nothing could ever have saved one otherwise.
    if not deal.lead_status:
        deal.lead_status = "OPEN"

    # See SYSTEM_STAMPED. created_date/modified_date have column defaults that
    # would fire anyway; all four are set here so the row's system values are
    # decided in one visible place — leads.py says the same.
    stamped_at = now_utc()
    deal.created_by = user.user_id
    deal.created_date = stamped_at
    deal.modified_by = user.user_id
    deal.modified_date = stamped_at

    # The pursuit carries on, and a secondary may not be the one that wins —
    # see app/pursuits.py. Both before the row exists, so a refusal writes
    # nothing and allocates no id that sticks.
    inherit_on_create(db, "deals", deal)
    guard_win(db, deal)
    guard_final_value_matches_tcv(db, deal)

    db.add(deal)
    db.flush()  # the childlists need the row to exist

    _apply_bid_commitments(db, deal, payload)
    _apply_expansion_use_cases(db, deal, payload)

    # D1 / D3. A Deal opens at the figures its pursuit reached: the money
    # fields and the two counterparties are seeded from the nearest ancestor
    # that holds them, and the Deal owns them from here on. Only fields the
    # caller did NOT send are filled — an explicit value is a decision.
    #
    # After the parent link is set (it is a DEAL_SCALAR, applied above) and
    # before the commit, because the walk needs parent_opportunity to be there.
    carried = seed_values(db, "deals", deal, supplied=sent)

    # Values for Administration-created fields go to custom_fields JSONB,
    # never to a column of their own. Unknown keys are not stored — see
    # app/custom_fields.py::resolve_write.
    apply_write(
        deal,
        resolve_write(
            db,
            "deals",
            explicit=payload.custom_fields,
            extras=extras_of(payload),
        ),
    )
    # created_date / modified_date are stamped above, not by the column defaults
    # (models._now, UTC). Deals genuinely has NO created_by/modified_by column
    # — the Deals sheet never named one — so the only record of WHO touched a
    # Deal is the audit row below, which is now the signed-in Entra user rather
    # than the None this router used to pass. See the DealRecord docstring.
    record_audit(
        db,
        module="deals",
        record_id=deal_id,
        action="created",
        actor=user.user_id,
        changed_fields=sorted(sent),
    )

    # Every due Mandatory field filled, or 422 — see app/requirements.py.
    check_save(db, "deals", deal, record_id=deal_id, creating=True, converting=converting is not None)
    # The stage's Progression %/Probability %. A paid-pilot Deal never comes
    # through here — progression.spin_off_pilot_deal inserts it directly.
    pct_after_write(db, "deals", deal, pct_plan, actor=user.user_id)

    if converting is not None:
        complete_conversion(
            db,
            source_module=source_module,
            source=converting,
            target_module="deals",
            target_id=deal_id,
            sent=sent,
            note=payload.conversion_note,
            actor=user.user_id,
        )

    db.commit()
    db.refresh(deal)
    return _serialise(deal, _label_maps(db))


@router.patch("/deals/{deal_id}", response_model=DealOut)
def patch_deal(
    deal_id: str,
    payload: DealUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    """Applies only the fields present in the request body."""
    return _write(db, deal_id, payload, set(payload.model_dump(exclude_unset=True)), user)


@router.put("/deals/{deal_id}", response_model=DealOut)
def put_deal(
    deal_id: str,
    payload: DealUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    """
    Kept for the same reason leads and opportunities have one: the
    prototype's record editor PUTs when it saves. Still applies only what
    was sent.
    """
    return _write(db, deal_id, payload, set(payload.model_dump(exclude_unset=True)), user)


def _write(db: Session, deal_id: str, payload: DealUpdate, sent: set[str], user: User) -> dict:
    deal = _get_or_404(db, deal_id)
    _check_links(db, payload, sent & set(DEAL_LOOKUPS))
    check_thresholds(db, "deals", payload.model_dump(include=sent))

    # The before half of the diff, read before anything is applied — see
    # routers/leads.py::_write.
    tracked = [n for n in DEAL_SCALARS if n in sent]
    before = snapshot(deal, tracked)
    before_custom = dict(deal.custom_fields or {})
    before_children = _children_of(deal)

    # Before anything is applied — see routers/leads.py::_write.
    pct_plan = plan_write(db, "deals", deal, payload, sent)

    if "lead_status" in sent:
        guard_close(db, "deals", deal, payload.lead_status)
    # No End Client guard here: a Deal's End Client is the Lead's, shown live
    # and never written on the Deal (G1, 24 Sep 2026), so it cannot change.
    shown_live = set(read_through_names(db, "deals"))

    for name in DEAL_SCALARS:
        if name not in sent or name in PURSUIT_STAMPED or name in SYSTEM_STAMPED or name in shown_live:
            continue
        setattr(deal, name, getattr(payload, name))

    if "bid_commitments_register" in sent:
        _apply_bid_commitments(db, deal, payload)
    if "expansion_use_cases" in sent:
        _apply_expansion_use_cases(db, deal, payload)

    # Values for Administration-created fields go to custom_fields JSONB,
    # never to a column of their own. Unknown keys are not stored — see
    # app/custom_fields.py::resolve_write.
    apply_write(
        deal,
        resolve_write(
            db,
            "deals",
            explicit=payload.custom_fields,
            extras=extras_of(payload),
        ),
    )

    # The commercial terms are fixed once won (decided 16 Sep 2026). Checked
    # here, AFTER the values are applied, because the rule is about a value
    # CHANGING — the form re-sends the whole section on every save, so a check
    # on what was merely sent refused saves that touched nothing locked. Nothing
    # is committed yet, so refusing here leaves the Deal exactly as it was.
    locked = locked_violations(db, "deals", deal, before)
    if locked:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            {
                "code": "VALUE_LOCKED",
                "message": "These were fixed when the deal was won and can't change here:",
                "details": sorted(p.label_override or db.get(FieldDefinition, p.definition_id).label for p in locked),
                "fields": sorted(p.api_name for p in locked),
            },
        )

    # See SYSTEM_STAMPED. Stamped on every save rather than left to the
    # column's onupdate=, which fires only when some OTHER attribute changed —
    # a save that altered nothing would otherwise read as if the record had
    # never been opened.
    deal.modified_by = user.user_id
    deal.modified_date = now_utc()

    changed = diff(before, snapshot(deal, tracked))
    changed += custom_field_diff(before_custom, deal.custom_fields)
    # A child list counts as changed only when its ROWS moved — never merely
    # because the editor's whole-section PUT carried it. See changes.list_changes.
    db.flush()
    # See routers/leads.py — the relationship is stale after a db.add() insert.
    db.expire(deal, ["bid_commitments", "expansion_use_cases"])
    changed += list_changes(before_children, _children_of(deal))

    record_audit(
        db,
        module="deals",
        record_id=deal_id,
        action="updated",
        actor=user.user_id,
        changed_fields=sorted(sent),
        changed=changed,
    )

    # Every due Mandatory field filled, or 422 — see app/requirements.py.
    check_save(db, "deals", deal, record_id=deal_id, creating=False, previous_stage=pct_plan.previous_stage)
    # See routers/leads.py::_write.
    pct_after_write(db, "deals", deal, pct_plan, actor=user.user_id)

    db.commit()
    db.refresh(deal)
    return _serialise(deal, _label_maps(db))


# --------------------------------------------------------------------------
# Payment milestones — the schedule belongs to the Opportunity, the delivery
# belongs here.
#
# The rows live on opportunity_payment_milestones and are NOT copied: one set
# of milestones, agreed at Stage 6 and delivered against at Stage 8, so a
# percentage can never disagree with itself in two places. What this module
# adds is the only half nobody could reach before — Actual, Invoice, Payment
# Received and Status, which are facts of delivery and arrive after the
# Opportunity has gone read-only.
# --------------------------------------------------------------------------

DELIVERY_ROW_COLUMNS = (
    "milestone_actual_date",
    "milestone_invoice_date",
    "milestone_payment_received_date",
    "milestone_status",
)

#: The whole row, for the audit before/after. Matches opportunities.py.
MILESTONE_ROW_COLUMNS = (
    "milestone",
    "pct_of_contract",
    "trigger",
    "milestone_planned_date",
    *DELIVERY_ROW_COLUMNS,
)


def _schedule_of(db: Session, deal: Deal) -> Opportunity:
    """The Opportunity holding this Deal's payment schedule, or 409."""
    if not deal.parent_opportunity:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "NO_PARENT_OPPORTUNITY",
                "message": "No payment schedule to show.",
                "details": [
                    "This Deal came straight from a Lead.",
                    "Payment milestones are agreed at Stage 6 – Commercial Evaluation.",
                ],
            },
        )
    opportunity = db.get(Opportunity, deal.parent_opportunity)
    if opportunity is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "PARENT_OPPORTUNITY_MISSING",
                "message": "The opportunity this Deal came from no longer exists, so its payment schedule is gone.",
            },
        )
    return opportunity


def _milestone_row(m) -> dict:
    row = {name: getattr(m, name) for name in MILESTONE_ROW_COLUMNS}
    row["pct_of_contract"] = (
        float(m.pct_of_contract) if m.pct_of_contract is not None else None
    )
    row["row_order"] = m.row_order
    return row


@router.get(
    "/deals/{deal_id}/payment-milestones",
    response_model=list[DealPaymentMilestoneOut],
)
def list_deal_payment_milestones(deal_id: str, db: Session = Depends(get_db)):
    deal = _get_or_404(db, deal_id)
    opportunity = _schedule_of(db, deal)
    return [_milestone_row(m) for m in opportunity.payment_milestones]


@router.put(
    "/deals/{deal_id}/payment-milestones",
    response_model=list[DealPaymentMilestoneOut],
)
def set_deal_payment_milestone_delivery(
    deal_id: str,
    payload: list[DealMilestoneDeliveryIn],
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    """
    Record delivery against the agreed milestones. Rows are addressed by
    row_order and never created or removed here: the schedule is the
    Opportunity's, and a Deal that could add a milestone could invent a payment.
    """
    deal = _get_or_404(db, deal_id)
    opportunity = _schedule_of(db, deal)

    by_order = {m.row_order: m for m in opportunity.payment_milestones}
    unknown = sorted(row.row_order for row in payload if row.row_order not in by_order)
    if unknown:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "code": "NO_SUCH_MILESTONE",
                "message": "The payment schedule changed while you were editing it.",
                "details": ["Reload the page and try again."],
            },
        )

    before = {"payment_milestones": child_snapshot(opportunity.payment_milestones, MILESTONE_ROW_COLUMNS)}
    for row in payload:
        milestone = by_order[row.row_order]
        for name in DELIVERY_ROW_COLUMNS:
            setattr(milestone, name, getattr(row, name))

    db.flush()
    changed = list_changes(
        before,
        {"payment_milestones": child_snapshot(opportunity.payment_milestones, MILESTONE_ROW_COLUMNS)},
    )

    # Audited on the DEAL, because that is the record the person was on and the
    # History they will look in. The Opportunity is read-only and its own
    # timeline must not imply someone reopened it.
    record_audit(
        db,
        module="deals",
        record_id=deal_id,
        action="updated",
        actor=user.user_id,
        changed_fields=["payment_milestones"],
        changed=changed,
    )
    db.commit()
    db.refresh(opportunity)
    return [_milestone_row(m) for m in opportunity.payment_milestones]


@router.delete("/deals/{deal_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_deal(
    deal_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    """Hard delete. bid_commitments_register and expansion_use_cases rows
    cascade; nothing else points at a Deal yet."""
    deal = _get_or_404(db, deal_id)
    if deal.pursuit_group:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            refusal(
                "REMOVE_FROM_GROUP_FIRST",
                "This deal is in a pursuit group, so it can't be deleted.",
                ["Remove it from the group first."],
                group_id=deal.pursuit_group,
            ),
        )
    record_audit(db, module="deals", record_id=deal_id, action="deleted", actor=user.user_id)
    db.delete(deal)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
