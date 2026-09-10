import re

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..custom_fields import apply_write, extras_of, merge_into_row, resolve_write
from ..ids import next_reference_id
from ..models import Account, DealRegistration, Lead, RegistrationConflict
from ..schemas import (
    REGISTRATION_LOOKUPS,
    REGISTRATION_SCALARS,
    DealRegistrationCreate,
    DealRegistrationOut,
    DealRegistrationUpdate,
)

router = APIRouter(tags=["registrations"])

REGISTRATION_ID_PATTERN = re.compile(r"^REG-(\d+)$")

RESERVED = {"_page", "_limit", "_sort", "_order", "_search", "q"}

# extensions.json list_views.registrations. `partner`/`end_client` are
# lookups, so the search has to run against the account NAME a reviewer can
# actually see, not the ACC-004 stored underneath — see _text_of, same as
# contacts.py's own DEFAULT_SEARCH.
DEFAULT_SEARCH = ("project_name", "partner", "end_client")


def _next_registration_id(db: Session) -> str:
    """From a stored high-water mark, never max(existing) — see app/ids.py."""
    highest = 0
    for existing in db.scalars(select(DealRegistration.registration_id)):
        match = REGISTRATION_ID_PATTERN.match(existing or "")
        if match:
            highest = max(highest, int(match.group(1)))
    return next_reference_id(db, "registrations", "REG", 5, highest)


def _label_maps(db: Session) -> dict[str, dict[str, str]]:
    """id -> display name for each collection a registration looks up."""
    accounts = {a.account_id: a.account_name for a in db.scalars(select(Account))}
    leads = {l.lead_id: l.opportunity_name for l in db.scalars(select(Lead))}
    return {"accounts": accounts, "leads": leads}


def _serialise(reg: DealRegistration, labels: dict[str, dict[str, str]]) -> dict:
    row: dict[str, object] = {"id": reg.registration_id, "registration_id": reg.registration_id}
    for name in REGISTRATION_SCALARS:
        value = getattr(reg, name)
        row[name] = float(value) if name == "estimated_value" and value is not None else value

    joined = {}
    for field, collection in REGISTRATION_LOOKUPS.items():
        value = getattr(reg, field)
        if value and value in labels[collection]:
            joined[field] = labels[collection][value]
    if joined:
        row["__labels"] = joined

    # Admin-created field values, read back flat so the form engine sees them
    # exactly like a register field. Never overwrites a typed column.
    return merge_into_row(row, reg)


def _get_or_404(db: Session, registration_id: str) -> DealRegistration:
    reg = db.get(DealRegistration, registration_id)
    if reg is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"No registration {registration_id}")
    return reg


def _check_links(db: Session, payload, sent: set[str]) -> None:
    """Every REGISTRATION_LOOKUPS entry is a real foreign key. Rejecting an
    unknown id here turns a database integrity error into a message naming
    the field — same rule leads.py and contacts.py follow."""
    models_by_collection = {"accounts": Account, "leads": Lead}
    for field, collection in REGISTRATION_LOOKUPS.items():
        if field not in sent:
            continue
        value = getattr(payload, field)
        if value and db.get(models_by_collection[collection], value) is None:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY, f"No such {collection[:-1]}: {value}"
            )


@router.get("/registrations", response_model=list[DealRegistrationOut])
def list_registrations(request: Request, response: Response, db: Session = Depends(get_db)):
    """
    Deal registrations, with the same list contract every other module
    provides: equality filters (repeated = OR), free-text search, sort, page,
    and the row total on X-Total-Count.

    ConvertToDealDialog.tsx reads this with ?linked_lead=<id> to supersede any
    active registration when a Lead becomes a Deal.
    """
    labels = _label_maps(db)
    rows = [_serialise(r, labels) for r in db.scalars(select(DealRegistration))]

    params = request.query_params

    for key in {k for k in params if k not in RESERVED}:
        wanted = set(params.getlist(key))
        rows = [r for r in rows if _matches(r.get(key), wanted)]

    q = (params.get("q") or "").strip().lower()
    if q:
        named = [f for f in (params.get("_search") or "").split(",") if f]
        fields = named or list(DEFAULT_SEARCH)
        rows = [r for r in rows if q in _text_of(r, fields).lower()]

    sort = params.get("_sort") or "submitted_date"
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
    if field in REGISTRATION_LOOKUPS:
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


@router.get("/registrations/{registration_id}", response_model=DealRegistrationOut)
def get_registration(registration_id: str, db: Session = Depends(get_db)):
    return _serialise(_get_or_404(db, registration_id), _label_maps(db))


@router.post("/registrations", response_model=DealRegistrationOut, status_code=status.HTTP_201_CREATED)
def create_registration(payload: DealRegistrationCreate, db: Session = Depends(get_db)):
    registration_id = payload.registration_id or _next_registration_id(db)

    if db.get(DealRegistration, registration_id) is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, f"{registration_id} already exists")

    sent = set(payload.model_dump(exclude_unset=True))
    _check_links(db, payload, sent & set(REGISTRATION_LOOKUPS))

    reg = DealRegistration(registration_id=registration_id)
    for name in REGISTRATION_SCALARS:
        setattr(reg, name, getattr(payload, name))

    db.add(reg)
    apply_write(
        reg,
        resolve_write(
            db,
            "partners",
            explicit=payload.custom_fields,
            extras=extras_of(payload),
        ),
    )
    db.commit()
    db.refresh(reg)
    return _serialise(reg, _label_maps(db))


@router.patch("/registrations/{registration_id}", response_model=DealRegistrationOut)
def patch_registration(registration_id: str, payload: DealRegistrationUpdate, db: Session = Depends(get_db)):
    """Applies only the fields present in the request body."""
    return _write(db, registration_id, payload, set(payload.model_dump(exclude_unset=True)))


@router.put("/registrations/{registration_id}", response_model=DealRegistrationOut)
def put_registration(registration_id: str, payload: DealRegistrationUpdate, db: Session = Depends(get_db)):
    """
    Kept for the same reason every other module has one: the prototype's
    record editor and the supersede/acknowledge actions all PUT. Still applies
    only what was sent.
    """
    return _write(db, registration_id, payload, set(payload.model_dump(exclude_unset=True)))


def _write(db: Session, registration_id: str, payload: DealRegistrationUpdate, sent: set[str]) -> dict:
    reg = _get_or_404(db, registration_id)
    _check_links(db, payload, sent & set(REGISTRATION_LOOKUPS))

    for name in REGISTRATION_SCALARS:
        if name not in sent:
            continue
        setattr(reg, name, getattr(payload, name))

    apply_write(
        reg,
        resolve_write(
            db,
            "partners",
            explicit=payload.custom_fields,
            extras=extras_of(payload),
        ),
    )
    db.commit()
    db.refresh(reg)
    return _serialise(reg, _label_maps(db))


@router.delete("/registrations/{registration_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_registration(registration_id: str, db: Session = Depends(get_db)):
    """
    Hard delete, refused with 409 while a conflict adjudication still names
    this registration as one of its two sides — the only real foreign key
    pointing INTO deal_registrations today.
    """
    reg = _get_or_404(db, registration_id)

    dependents = db.scalars(
        select(RegistrationConflict.conflict_id).where(
            (RegistrationConflict.registration_a == registration_id)
            | (RegistrationConflict.registration_b == registration_id)
        )
    ).all()
    if dependents:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"{registration_id} is still named by {len(dependents)} conflict adjudication(s): "
            f"{', '.join(dependents[:5])}"
            f"{'…' if len(dependents) > 5 else ''}.",
        )

    db.delete(reg)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
