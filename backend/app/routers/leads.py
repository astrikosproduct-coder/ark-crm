import re

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth import current_user
from ..list_query import run_list_query
from ..messages import already_exists, not_found, picked_record_missing
from ..requirements import check_save
from ..pursuits import group_names
from ..changes import child_snapshot, custom_field_diff, diff, list_changes, snapshot
from ..clock import days_since, now_utc
from ..database import get_db
from ..audit import record_audit
from ..custom_fields import apply_write, extras_of, merge_into_row, resolve_write
from ..ids import next_reference_id
from ..lead_deletion import delete_lead_and_linked, deletion_plan
from ..pursuits import (
    PURSUIT_STAMPED,
    guard_close,
    guard_end_client_change,
    guard_possible_duplicate,
)
from ..revenue import revenue_context, revenue_of
from ..stage_entry import stage_entry_dates
from ..progression import after_write as pct_after_write, plan_write, serialise_pct
from ..models import (
    Account,
    Contact,
    Lead,
    LeadDemoAttendee,
    LeadFeatureGap,
    Opportunity,
    User,
)
from ..schemas import (
    LEAD_LOOKUPS,
    LEAD_SCALARS,
    ActiveFlag,
    LeadCreate,
    LeadOut,
    LeadUpdate,
)

router = APIRouter(tags=["leads"])

LEAD_ID_PATTERN = re.compile(r"^LEAD-(\d+)$")


# extensions.json list_views.leads.search, once written; kept narrow and
# textual like accounts' and contacts' defaults.
DEFAULT_SEARCH = ("opportunity_name", "country", "lead_status")

# Row column names of the demo_attendees / feature_gaps_logged childlists, in
# register order — see models.LeadDemoAttendee/LeadFeatureGap and
# extensions.json's child_spec.
DEMO_ATTENDEE_ROW_COLUMNS = ("attendee", "job_title", "organisation", "attendee_role")
FEATURE_GAP_ROW_COLUMNS = ("gap_description", "suite_module", "impact", "raised_by")

# WHO AND WHEN ARE THE SERVER'S TO DECIDE — never the payload's.
#
# These four are ordinary LEAD_SCALARS, so the write loops below would happily
# set them from the request body; until Sep 2026 they did, and the browser sent
# them on every save. That made the two fields a manager most needs to trust —
# "when was this last modified, and by whom" — the two a BD could type anything
# into, and it put a wrong laptop clock into the database with no ill intent
# required. They are skipped on write and stamped from the Entra session and the
# server clock instead; the form renders them read-only to match (System fields
# in the register carry editable=false since Sep 2026).
SYSTEM_STAMPED = frozenset({"created_by", "created_date", "modified_by", "modified_date"})


def _next_lead_id(db: Session) -> str:
    """From a stored high-water mark, never max(existing) — see app/ids.py."""
    highest = 0
    for existing in db.scalars(select(Lead.lead_id)):
        match = LEAD_ID_PATTERN.match(existing or "")
        if match:
            highest = max(highest, int(match.group(1)))
    return next_reference_id(db, "leads", "LEAD", 5, highest)


def _label_maps(db: Session) -> dict[str, dict[str, str]]:
    """id -> display name for each collection a Lead looks up."""
    accounts = {a.account_id: a.account_name for a in db.scalars(select(Account))}
    users = {u.user_id: u.name for u in db.scalars(select(User))}
    contacts = {c.contact_id: c.full_name for c in db.scalars(select(Contact))}
    leads = {l.lead_id: l.opportunity_name for l in db.scalars(select(Lead))}
    # Not a lookup collection — no Lead column points at it. It rides here
    # because it is the same shape of join (an id resolved to a display name,
    # once per page rather than once per row) and the alternative was passing
    # the session into _serialise.
    return {
        "accounts": accounts,
        "users": users,
        "contacts": contacts,
        "leads": leads,
        # A pursuit group by name — "Al Waha … at Madinat Al Waha" — for the
        # list column and the record's lookup, never PG-0002.
        "pursuit_groups": group_names(db),
        # Not a display-name join either: what each row contributes to its
        # stage's pipeline total, read once per page. See app/revenue.py.
        "revenue": revenue_context(db),
        # Not a display-name join either, and here for the same reason: one
        # query for the page rather than one per row. See app/stage_entry.py.
        "stage_entered": stage_entry_dates(
            db,
            "leads",
            {l.lead_id: l.project_stage for l in db.scalars(select(Lead))},
        ),
    }


def _serialise(lead: Lead, labels: dict[str, dict[str, str]]) -> dict:
    row = {
        "id": lead.lead_id,
        "lead_id": lead.lead_id,
        "demo_attendees": [
            {name: getattr(a, name) for name in DEMO_ATTENDEE_ROW_COLUMNS}
            for a in lead.demo_attendees
        ],
        "feature_gaps_logged": [
            {name: getattr(g, name) for name in FEATURE_GAP_ROW_COLUMNS}
            for g in lead.feature_gaps
        ],
        "contracting_party": lead.contracting_party,
        # The FACT, not the count. The browser derives "12 days" from this with
        # lib/time.ts's company clock, which is the same clock app/clock.py
        # counts on — so the number on a card and the number from the API agree
        # by construction rather than by two implementations staying in step.
        "stage_entered_date": labels["stage_entered"].get(lead.lead_id)
        or lead.created_date,
        "days_in_current_stage": days_since(
            labels["stage_entered"].get(lead.lead_id) or lead.created_date
        ),
        "days_since_last_update": lead.days_since_last_update,
    }
    for name in LEAD_SCALARS:
        value = getattr(lead, name)
        row[name] = float(value) if name in _MONEY_LIKE and value is not None else value
    row["created_date"] = lead.created_date
    row["modified_date"] = lead.modified_date

    # The one number this row adds to its stage's total, and why not when it
    # adds nothing — the board header sums these rather than deciding itself.
    row["revenue"] = revenue_of(labels["revenue"], "leads", lead)
    row["pursuit_primary"] = (
        labels["revenue"].primary_of_group.get(lead.pursuit_group) if lead.pursuit_group else None
    )

    # The stage pair and its override state — which overwrites the raw
    # Decimals the scalar loop just put in the row. See app/progression.py.
    row.update(serialise_pct(lead))

    joined = {}
    for field, collection in LEAD_LOOKUPS.items():
        value = getattr(lead, field)
        if value and value in labels[collection]:
            joined[field] = labels[collection][value]
    # overridden_by is NOT in LEAD_LOOKUPS: that dict also drives
    # _check_links's create-time validation, which runs over every key
    # unconditionally (see its own note) rather than only the keys sent —
    # and overridden_by is never a payload field, only ever server-written,
    # so getattr(payload, "overridden_by") on create would raise. Joined
    # here instead, off the same labels["users"] map, for display only.
    if lead.overridden_by and lead.overridden_by in labels["users"]:
        joined["overridden_by"] = labels["users"][lead.overridden_by]
    # Server-stamped (PURSUIT_STAMPED), so not in LEAD_LOOKUPS for the same
    # reason as overridden_by.
    if lead.pursuit_group and lead.pursuit_group in labels["pursuit_groups"]:
        joined["pursuit_group"] = labels["pursuit_groups"][lead.pursuit_group]
    if joined:
        row["__labels"] = joined

    # Admin-created field values, read back flat so the form engine sees them
    # exactly like a register field. Never overwrites a typed column.
    return merge_into_row(row, lead)


# Numeric register fields that come back from SQLAlchemy as Decimal, which is
# not JSON-serialisable.
_MONEY_LIKE = {
    "fx_rate_at_entry",
    "estimated_value",
    "incremental_value",
    "pilot_fee",
    "budget_estimate",
    "total_project_value",
}


def _get_or_404(db: Session, lead_id: str) -> Lead:
    lead = db.get(Lead, lead_id)
    if lead is None:
        raise not_found("lead")
    return lead


def _check_links(db: Session, payload, sent: set[str]) -> None:
    """
    Every LEAD_LOOKUPS entry is a real foreign key. Rejecting an unknown id
    here turns a database integrity error into a message naming the field.

    created_by and modified_by are lookups too, but they are SYSTEM_STAMPED and
    so never written from the payload — validating them would reject a request
    over a value that is about to be discarded, which is how an older client
    sending a stale user id would get a 422 for a field it no longer controls.
    Never validate what you do not write.
    """
    models_by_collection = {"accounts": Account, "users": User, "contacts": Contact, "leads": Lead}
    for field, collection in LEAD_LOOKUPS.items():
        if field not in sent or field in SYSTEM_STAMPED:
            continue
        value = getattr(payload, field)
        if value and db.get(models_by_collection[collection], value) is None:
            raise picked_record_missing({"accounts": "account", "users": "person", "contacts": "contact", "leads": "lead", "opportunities": "opportunity"}.get(collection, "record"))


def _check_registration(
    db: Session, payload, sent: set[str], current: str | None, lead_id: str | None = None
) -> None:
    """
    A lead is linked to a deal registration only while that registration still
    confers exclusivity. Withdrawn, rejected, superseded or expired, it protects
    nothing — and linking to it would put the lead into that registration's
    conflict and pursuit group as if it did. Checked when the link is SET or
    CHANGED, never on a save that leaves an existing link alone.
    """
    if "partner_deal_registration" not in sent:
        return
    value = payload.partner_deal_registration
    if not value or value == current:
        return
    from ..models import DealRegistration
    from ..registration_matching import is_live_status

    registration = db.get(DealRegistration, value)
    if registration is None:
        raise picked_record_missing("registration")
    if not is_live_status(registration.registration_status):
        state = str(registration.registration_status).replace("_", " ").lower()  # e.g. "expired"
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            {
                "code": "REGISTRATION_NOT_LIVE",
                "message": f"That registration is {state}, so a lead can't be linked to it.",
                "details": ["Pick a registration that is still active."],
            },
        )

    # One lead per registration. A second Create lead — a double press, or a
    # retry after a response that never arrived — must not open a second
    # pursuit of the same registration.
    existing = db.scalar(
        select(Lead.lead_id).where(Lead.partner_deal_registration == value, Lead.lead_id != (lead_id or ""))
    )
    if existing is None and registration.linked_lead not in (None, lead_id) and db.get(Lead, registration.linked_lead):
        existing = registration.linked_lead
    if existing is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            {
                "code": "REGISTRATION_HAS_LEAD",
                "message": "That registration already has a lead. Nothing new was created.",
                "lead_id": existing,
            },
        )


def _children_of(lead: Lead) -> dict[str, list[dict]]:
    """Both child lists as comparable rows — the before/after of list_changes."""
    return {
        "demo_attendees": child_snapshot(lead.demo_attendees, DEMO_ATTENDEE_ROW_COLUMNS),
        "feature_gaps_logged": child_snapshot(lead.feature_gaps, FEATURE_GAP_ROW_COLUMNS),
    }


def _apply_demo_attendees(db: Session, lead: Lead, payload: LeadUpdate | LeadCreate) -> None:
    lead.demo_attendees.clear()
    db.flush()
    for order, row in enumerate(payload.demo_attendees or []):
        db.add(
            LeadDemoAttendee(
                lead_id=lead.lead_id,
                row_order=order,
                **{name: getattr(row, name) for name in DEMO_ATTENDEE_ROW_COLUMNS},
            )
        )


def _apply_feature_gaps(db: Session, lead: Lead, payload: LeadUpdate | LeadCreate) -> None:
    lead.feature_gaps.clear()
    db.flush()
    for order, row in enumerate(payload.feature_gaps_logged or []):
        db.add(
            LeadFeatureGap(
                lead_id=lead.lead_id,
                row_order=order,
                **{name: getattr(row, name) for name in FEATURE_GAP_ROW_COLUMNS},
            )
        )


@router.get("/leads", response_model=list[LeadOut])
def list_leads(request: Request, response: Response, db: Session = Depends(get_db)):
    """
    Leads, with the same list contract accounts and contacts provide: equality
    filters (repeated = OR), free-text search, sort, page, and the row total on
    X-Total-Count.
    """
    labels = _label_maps(db)
    records = list(db.scalars(select(Lead)))
    rows = [_serialise(l, labels) for l in records]

    rows, total = run_list_query(
        rows, request.query_params, lookups=LEAD_LOOKUPS, default_search=DEFAULT_SEARCH
    )
    response.headers["X-Total-Count"] = str(total)
    return rows


@router.get("/leads/{lead_id}", response_model=LeadOut)
def get_lead(lead_id: str, db: Session = Depends(get_db)):
    return _serialise(_get_or_404(db, lead_id), _label_maps(db))


@router.post("/leads", response_model=LeadOut, status_code=status.HTTP_201_CREATED)
def create_lead(
    payload: LeadCreate,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    lead = insert_lead(payload, db, user)
    db.refresh(lead)
    return _serialise(lead, _label_maps(db))


def insert_lead(payload: LeadCreate, db: Session, user: User) -> Lead:
    """
    Every rule of creating a Lead, committed — without building the response.

    The route above is this plus serialisation. The spreadsheet import calls
    this directly (app/spreadsheets/importer.py): serialising reloads every
    account, user, contact and pursuit group to join display names — about 80%
    of a create's cost, and useless to an import that never reads it back.
    One function, so an import can never skip a rule the form's save applies.
    """
    lead_id = payload.lead_id or _next_lead_id(db)

    if db.get(Lead, lead_id) is not None:
        raise already_exists()

    _check_links(db, payload, set(LEAD_LOOKUPS))
    _check_registration(db, payload, set(payload.model_dump(exclude_unset=True)), None)

    lead = Lead(lead_id=lead_id)
    # Before a value is applied: validates the two numbers and any override.
    pct_plan = plan_write(
        db, "leads", lead, payload, set(payload.model_dump(exclude_unset=True)), creating=True
    )
    _BOOL_DEFAULTS = {
        "is_primary_pursuit": True,
        "lighthouse_project": False,
        "gorilla_flag": False,
        "demo_agreed": False,
        "demo_completed": False,
        "project_team_access_confirmed": False,
        "budget_confirmed": False,
        "active": True,
    }
    for name in LEAD_SCALARS:
        if name in SYSTEM_STAMPED or name in PURSUIT_STAMPED:
            continue
        value = getattr(payload, name)
        if value is None and name in _BOOL_DEFAULTS:
            value = _BOOL_DEFAULTS[name]
        setattr(lead, name, value)
    # Starting values every new lead gets, however it was created — "+ New
    # Lead", a deal registration's Create lead, an expansion off a Deal — and
    # the user changes them afterwards (14 Sep 2026). Only a blank is filled.
    # A lead with no currency counted as $0 in every pipeline total
    # (app/revenue.py flags it no_currency): that is how leads created from a
    # registration went missing from the dashboard.
    if not lead.lead_status:
        lead.lead_status = "OPEN"
    if not lead.currency:
        lead.currency = "USD"
    if lead.currency == "USD" and lead.fx_rate_at_entry is None:
        lead.fx_rate_at_entry = 1

    # See app/pursuits.py — a new lead is its own pursuit until a rule below
    # puts it in a group.
    lead.pursuit_group = None
    lead.is_primary_pursuit = True

    # See SYSTEM_STAMPED. created_date/modified_date have model defaults that
    # would fire anyway; they are set explicitly so that the row's four system
    # values are visibly decided in one place rather than half here and half in
    # a column default three thousand lines away.
    stamped_at = now_utc()
    lead.created_by = user.user_id
    lead.created_date = stamped_at
    lead.modified_by = user.user_id
    lead.modified_date = stamped_at

    db.add(lead)
    db.flush()  # the child tables have an FK to this row

    # The registration names its lead in the same commit, so its Create lead
    # button is gone even when the browser's follow-up never arrives.
    if lead.partner_deal_registration:
        from ..models import DealRegistration

        registration = db.get(DealRegistration, lead.partner_deal_registration)
        if registration is not None and not registration.linked_lead:
            registration.linked_lead = lead_id
            record_audit(
                db,
                module="registrations",
                record_id=registration.registration_id,
                action="updated",
                actor=user.user_id,
                changed_fields=["linked_lead"],
                changed=diff({"linked_lead": None}, {"linked_lead": lead_id}),
            )

    _apply_demo_attendees(db, lead, payload)
    _apply_feature_gaps(db, lead, payload)

    # Values for Administration-created fields go to custom_fields JSONB,
    # never to a column of their own. Unknown keys are not stored — see
    # app/custom_fields.py::resolve_write.
    apply_write(
        lead,
        resolve_write(
            db,
            "leads",
            explicit=payload.custom_fields,
            extras=extras_of(payload),
        ),
    )

    # Another open pursuit for this End Client: join its group, or give the
    # reason this is a different project — 422 POSSIBLE_DUPLICATE otherwise.
    guard_possible_duplicate(
        db, lead, actor=user.user_id, join_pursuit_of=payload.join_pursuit_of, checking=True
    )

    # No `changed` on a create: there is no "from" value to name, and a diff
    # listing every field as "— → x" would bury the one entry that matters,
    # which is that the record came into existence. The timeline renders this
    # as a single "Lead created" event.
    record_audit(
        db,
        module="leads",
        record_id=lead_id,
        action="created",
        actor=user.user_id,
        changed_fields=sorted(payload.model_dump(exclude_unset=True)),
    )

    # The stage's Progression %/Probability % — and, for a Lead created with
    # its pilot already Paid, the POC/Pilot Deal. See app/progression.py.
    # Every due Mandatory field filled, or 422 — see app/requirements.py.
    check_save(db, "leads", lead, record_id=lead_id, creating=True)
    pct_after_write(db, "leads", lead, pct_plan, actor=user.user_id)

    db.commit()
    return lead


@router.patch("/leads/{lead_id}", response_model=LeadOut)
def patch_lead(
    lead_id: str,
    payload: LeadUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    """Applies only the fields present in the request body."""
    return _write(db, lead_id, payload, set(payload.model_dump(exclude_unset=True)), user)


@router.put("/leads/{lead_id}", response_model=LeadOut)
def put_lead(
    lead_id: str,
    payload: LeadUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    """
    Kept for the same reason accounts and contacts have one: the prototype's
    record editor PUTs when it saves. Still applies only what was sent.
    """
    return _write(db, lead_id, payload, set(payload.model_dump(exclude_unset=True)), user)


def _write(db: Session, lead_id: str, payload: LeadUpdate, sent: set[str], user: User) -> dict:
    lead = _get_or_404(db, lead_id)
    _check_links(db, payload, sent & set(LEAD_LOOKUPS))
    _check_registration(db, payload, sent, lead.partner_deal_registration, lead.lead_id)

    # The before half of the diff, read BEFORE a single value is applied —
    # this is the whole reason the timeline can say "from Amber to Green"
    # rather than only "Overall RAG was touched". Taken over `sent` alone, so
    # a twenty-field PUT that altered one field costs one comparison per field
    # sent and yields exactly one entry.
    tracked = [n for n in LEAD_SCALARS if n in sent and n not in SYSTEM_STAMPED]
    before = snapshot(lead, tracked)
    before_custom = dict(lead.custom_fields or {})
    before_children = _children_of(lead)

    # BEFORE anything is applied: a Progression %/Probability % that differs
    # from the stage's value is an override and needs Override Justification
    # for the stage — 422 otherwise. See app/progression.py.
    pct_plan = plan_write(db, "leads", lead, payload, sent)

    # Pursuit-group rules, before a value moves — see app/pursuits.py.
    if "lead_status" in sent:
        guard_close(db, "leads", lead, payload.lead_status)
    guard_end_client_change(db, lead, sent, payload.end_client)
    end_client_before = lead.end_client
    registration_before = lead.partner_deal_registration

    for name in LEAD_SCALARS:
        if name not in sent or name in SYSTEM_STAMPED or name in PURSUIT_STAMPED:
            continue
        setattr(lead, name, getattr(payload, name))

    if "demo_attendees" in sent:
        _apply_demo_attendees(db, lead, payload)
    if "feature_gaps_logged" in sent:
        _apply_feature_gaps(db, lead, payload)

    # Values for Administration-created fields go to custom_fields JSONB,
    # never to a column of their own. Unknown keys are not stored — see
    # app/custom_fields.py::resolve_write.
    apply_write(
        lead,
        resolve_write(
            db,
            "leads",
            explicit=payload.custom_fields,
            extras=extras_of(payload),
        ),
    )
    guard_possible_duplicate(
        db,
        lead,
        actor=user.user_id,
        join_pursuit_of=payload.join_pursuit_of,
        checking=lead.end_client != end_client_before
        or lead.partner_deal_registration != registration_before,
    )

    # See SYSTEM_STAMPED. Stamped on every save rather than left to the
    # column's onupdate=, which fires only when some OTHER attribute changed —
    # a save that altered nothing would otherwise leave modified_date reading
    # as if the record had not been opened.
    lead.modified_by = user.user_id
    lead.modified_date = now_utc()

    changed = diff(before, snapshot(lead, tracked))
    changed += custom_field_diff(before_custom, lead.custom_fields)
    # flush first: _apply_demo_attendees clears and re-adds rows, and the
    # collection only reflects that once the session has written it out.
    db.flush()
    # _apply_* inserts rows with db.add(lead_id=...) rather than appending to
    # the relationship, so the in-memory collection is STALE after a write and
    # reading it back would compare the old rows against themselves. Expired
    # here so the next access reloads what was actually written.
    db.expire(lead, ["demo_attendees", "feature_gaps"])
    changed += list_changes(before_children, _children_of(lead))

    record_audit(
        db,
        module="leads",
        record_id=lead_id,
        action="updated",
        actor=user.user_id,
        changed_fields=sorted(sent),
        changed=changed,
    )

    # A stage move takes the new stage's pair; a status or a typed override
    # settles here; a pilot marked Paid becomes its Deal. See app/progression.py.
    # Every due Mandatory field filled, or 422 — see app/requirements.py.
    check_save(db, "leads", lead, record_id=lead_id, creating=False, previous_stage=pct_plan.previous_stage)
    pct_after_write(db, "leads", lead, pct_plan, actor=user.user_id)

    db.commit()
    db.refresh(lead)
    return _serialise(lead, _label_maps(db))


@router.patch("/leads/{lead_id}/active", response_model=LeadOut)
def set_lead_active(
    lead_id: str,
    payload: ActiveFlag,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    lead = _get_or_404(db, lead_id)
    was_active = lead.active
    lead.active = payload.active
    lead.modified_by = user.user_id
    lead.modified_date = now_utc()
    record_audit(
        db,
        module="leads",
        record_id=lead_id,
        action="updated",
        actor=user.user_id,
        changed_fields=["active"],
        changed=diff({"active": was_active}, {"active": lead.active}),
    )
    db.commit()
    db.refresh(lead)
    return _serialise(lead, _label_maps(db))


@router.get("/leads/{lead_id}/deletion")
def get_deletion_plan(lead_id: str, db: Session = Depends(get_db)):
    """What stops this lead being deleted, and which linked Accounts and
    Contacts could go with it. See app/lead_deletion.py."""
    return deletion_plan(db, _get_or_404(db, lead_id))


@router.delete("/leads/{lead_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_lead(
    lead_id: str,
    with_linked: bool = False,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    """
    Hard delete, refused with 409 LEAD_HAS_DEPENDENTS while the lead is linked
    to anything other than Accounts and Contacts — an Opportunity or Deal, a
    deal registration, a pursuit group. The refusal carries the plan, so the
    screen can name what is in the way.

    Linked Accounts and Contacts are kept unless `with_linked=true`, and even
    then only the ones nothing else uses. See app/lead_deletion.py.
    """
    delete_lead_and_linked(db, _get_or_404(db, lead_id), actor=user.user_id, with_linked=with_linked)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
