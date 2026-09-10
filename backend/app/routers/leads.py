import re

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..audit import record_audit
from ..custom_fields import apply_write, extras_of, merge_into_row, resolve_write
from ..ids import next_reference_id
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

RESERVED = {"_page", "_limit", "_sort", "_order", "_search", "q"}

# extensions.json list_views.leads.search, once written; kept narrow and
# textual like accounts' and contacts' defaults.
DEFAULT_SEARCH = ("opportunity_name", "country", "lead_status")

# Row column names of the demo_attendees / feature_gaps_logged childlists, in
# register order — see models.LeadDemoAttendee/LeadFeatureGap and
# extensions.json's child_spec.
DEMO_ATTENDEE_ROW_COLUMNS = ("attendee", "job_title", "organisation", "attendee_role")
FEATURE_GAP_ROW_COLUMNS = ("gap_description", "suite_module", "impact", "raised_by")


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
    return {"accounts": accounts, "users": users, "contacts": contacts, "leads": leads}


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
        "days_in_current_stage": lead.days_in_current_stage,
        "days_since_last_update": lead.days_since_last_update,
    }
    for name in LEAD_SCALARS:
        value = getattr(lead, name)
        row[name] = float(value) if name in _MONEY_LIKE and value is not None else value
    row["created_date"] = lead.created_date
    row["modified_date"] = lead.modified_date

    joined = {}
    for field, collection in LEAD_LOOKUPS.items():
        value = getattr(lead, field)
        if value and value in labels[collection]:
            joined[field] = labels[collection][value]
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
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"No lead {lead_id}")
    return lead


def _check_links(db: Session, payload, sent: set[str]) -> None:
    """
    Every LEAD_LOOKUPS entry is a real foreign key. Rejecting an unknown id
    here turns a database integrity error into a message naming the field.
    """
    models_by_collection = {"accounts": Account, "users": User, "contacts": Contact, "leads": Lead}
    for field, collection in LEAD_LOOKUPS.items():
        if field not in sent:
            continue
        value = getattr(payload, field)
        if value and db.get(models_by_collection[collection], value) is None:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY, f"No such {collection[:-1]}: {value}"
            )


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
    rows = [_serialise(l, labels) for l in db.scalars(select(Lead))]

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
    if field in LEAD_LOOKUPS:
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


@router.get("/leads/{lead_id}", response_model=LeadOut)
def get_lead(lead_id: str, db: Session = Depends(get_db)):
    return _serialise(_get_or_404(db, lead_id), _label_maps(db))


@router.post("/leads", response_model=LeadOut, status_code=status.HTTP_201_CREATED)
def create_lead(payload: LeadCreate, db: Session = Depends(get_db)):
    lead_id = payload.lead_id or _next_lead_id(db)

    if db.get(Lead, lead_id) is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, f"{lead_id} already exists")

    _check_links(db, payload, set(LEAD_LOOKUPS))

    lead = Lead(lead_id=lead_id)
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
        value = getattr(payload, name)
        if value is None and name in _BOOL_DEFAULTS:
            value = _BOOL_DEFAULTS[name]
        setattr(lead, name, value)

    db.add(lead)
    db.flush()  # the child tables have an FK to this row

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
    record_audit(
        db,
        module="leads",
        record_id=lead_id,
        action="created",
        actor=lead.modified_by or lead.created_by,
        changed_fields=sorted(payload.model_dump(exclude_unset=True)),
    )
    db.commit()
    db.refresh(lead)
    return _serialise(lead, _label_maps(db))


@router.patch("/leads/{lead_id}", response_model=LeadOut)
def patch_lead(lead_id: str, payload: LeadUpdate, db: Session = Depends(get_db)):
    """Applies only the fields present in the request body."""
    return _write(db, lead_id, payload, set(payload.model_dump(exclude_unset=True)))


@router.put("/leads/{lead_id}", response_model=LeadOut)
def put_lead(lead_id: str, payload: LeadUpdate, db: Session = Depends(get_db)):
    """
    Kept for the same reason accounts and contacts have one: the prototype's
    record editor PUTs when it saves. Still applies only what was sent.
    """
    return _write(db, lead_id, payload, set(payload.model_dump(exclude_unset=True)))


def _write(db: Session, lead_id: str, payload: LeadUpdate, sent: set[str]) -> dict:
    lead = _get_or_404(db, lead_id)
    _check_links(db, payload, sent & set(LEAD_LOOKUPS))

    for name in LEAD_SCALARS:
        if name not in sent:
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
    record_audit(
        db,
        module="leads",
        record_id=lead_id,
        action="updated",
        actor=lead.modified_by or lead.created_by,
        changed_fields=sorted(sent),
    )
    db.commit()
    db.refresh(lead)
    return _serialise(lead, _label_maps(db))


@router.patch("/leads/{lead_id}/active", response_model=LeadOut)
def set_lead_active(lead_id: str, payload: ActiveFlag, db: Session = Depends(get_db)):
    lead = _get_or_404(db, lead_id)
    lead.active = payload.active
    record_audit(
        db,
        module="leads",
        record_id=lead_id,
        action="updated",
        actor=lead.modified_by or lead.created_by,
        changed_fields=["active"],
    )
    db.commit()
    db.refresh(lead)
    return _serialise(lead, _label_maps(db))


@router.delete("/leads/{lead_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_lead(lead_id: str, db: Session = Depends(get_db)):
    """
    Hard delete, refused with 409 while anything still points INTO this Lead
    under a RESTRICT constraint: another Lead naming it as parent_pursuit, or
    a converted Opportunity reading its identity through parent_lead.

    Deal.parent_lead is ON DELETE SET NULL and so needs no guard here — only
    the RESTRICT links can fail, and they must fail as a 409 the UI can show,
    not as the IntegrityError-driven 500 they raise if they reach COMMIT.
    """
    lead = _get_or_404(db, lead_id)

    dependents = db.scalars(
        select(Lead.lead_id).where(Lead.parent_pursuit == lead_id)
    ).all()
    if dependents:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"{lead_id} is still the parent pursuit of {len(dependents)} lead(s): "
            f"{', '.join(dependents[:5])}"
            f"{'…' if len(dependents) > 5 else ''}. Deactivate it instead.",
        )

    opportunities = db.scalars(
        select(Opportunity.opportunity_id).where(Opportunity.parent_lead == lead_id)
    ).all()
    if opportunities:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"{lead_id} was converted and is still the parent of "
            f"{len(opportunities)} opportunity(ies): {', '.join(opportunities[:5])}"
            f"{'…' if len(opportunities) > 5 else ''}. Deactivate it instead.",
        )

    record_audit(db, module="leads", record_id=lead_id, action="deleted")
    db.delete(lead)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
