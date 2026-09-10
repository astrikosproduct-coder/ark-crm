import re

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..custom_fields import apply_write, extras_of, merge_into_row, resolve_write
from ..ids import next_reference_id
from ..models import DealRegistration, RegistrationConflict, User
from ..schemas import (
    CONFLICT_LOOKUPS,
    CONFLICT_SCALARS,
    RegistrationConflictCreate,
    RegistrationConflictOut,
    RegistrationConflictUpdate,
)

router = APIRouter(tags=["conflicts"])

# CLAUDE.md's Conventions list has no id shape for a conflict. CONF-0001 (four
# digits, following GATE-0091) is a prototype-only convention flagged in
# spec/extensions.json as unconfirmed against the register — which states
# CNF-00001 in its own values_note. Kept as CONF-0001 deliberately: it is what
# the browser store, useDataStore.ts and every existing conflict record
# already use.
CONFLICT_ID_PATTERN = re.compile(r"^CONF-(\d+)$")

RESERVED = {"_page", "_limit", "_sort", "_order", "_search", "q"}
DEFAULT_SEARCH = ("who_registered_first", "decision")


def _next_conflict_id(db: Session) -> str:
    """From a stored high-water mark, never max(existing) — see app/ids.py."""
    highest = 0
    for existing in db.scalars(select(RegistrationConflict.conflict_id)):
        match = CONFLICT_ID_PATTERN.match(existing or "")
        if match:
            highest = max(highest, int(match.group(1)))
    return next_reference_id(db, "conflicts", "CONF", 4, highest)


def _label_maps(db: Session) -> dict[str, dict[str, str]]:
    """id -> display name for each collection a conflict looks up.

    registrations resolves against project_name — the same field
    ConflictPanel.tsx and StageHistoryTab-style screens show beside a
    registration id, since a DealRegistration has no separate "name" field.
    """
    registrations = {
        r.registration_id: (r.project_name or r.registration_id)
        for r in db.scalars(select(DealRegistration))
    }
    users = {u.user_id: u.name for u in db.scalars(select(User))}
    return {"registrations": registrations, "users": users}


def _serialise(c: RegistrationConflict, labels: dict[str, dict[str, str]]) -> dict:
    row: dict[str, object] = {"id": c.conflict_id, "conflict_id": c.conflict_id}
    for name in CONFLICT_SCALARS:
        row[name] = getattr(c, name)

    joined = {}
    for field, collection in CONFLICT_LOOKUPS.items():
        value = getattr(c, field)
        if value and value in labels[collection]:
            joined[field] = labels[collection][value]
    if joined:
        row["__labels"] = joined

    # Admin-created field values, read back flat so the form engine sees them
    # exactly like a register field. Never overwrites a typed column.
    return merge_into_row(row, c)


def _get_or_404(db: Session, conflict_id: str) -> RegistrationConflict:
    conflict = db.get(RegistrationConflict, conflict_id)
    if conflict is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"No conflict {conflict_id}")
    return conflict


def _check_links(db: Session, payload, sent: set[str]) -> None:
    """Every CONFLICT_LOOKUPS entry is a real foreign key. Rejecting an
    unknown id here turns a database integrity error into a message naming
    the field — same rule every other router follows."""
    models_by_collection = {"registrations": DealRegistration, "users": User}
    for field, collection in CONFLICT_LOOKUPS.items():
        if field not in sent:
            continue
        value = getattr(payload, field)
        if value and db.get(models_by_collection[collection], value) is None:
            noun = "registration" if collection == "registrations" else collection[:-1]
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"No such {noun}: {value}")


@router.get("/conflicts", response_model=list[RegistrationConflictOut])
def list_conflicts(request: Request, response: Response, db: Session = Depends(get_db)):
    """
    Every recorded adjudication, with the same list contract every other
    module provides. ConflictPanel.tsx reads this unfiltered and matches pairs
    client-side via adjudicationFor() — registration_a/registration_b may name
    either side of a collision, so there is no single-field filter that would
    save it a round trip.
    """
    labels = _label_maps(db)
    rows = [_serialise(c, labels) for c in db.scalars(select(RegistrationConflict))]

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
    if field in CONFLICT_LOOKUPS:
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


@router.get("/conflicts/{conflict_id}", response_model=RegistrationConflictOut)
def get_conflict(conflict_id: str, db: Session = Depends(get_db)):
    return _serialise(_get_or_404(db, conflict_id), _label_maps(db))


@router.post("/conflicts", response_model=RegistrationConflictOut, status_code=status.HTTP_201_CREATED)
def create_conflict(payload: RegistrationConflictCreate, db: Session = Depends(get_db)):
    conflict_id = payload.conflict_id or _next_conflict_id(db)

    if db.get(RegistrationConflict, conflict_id) is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, f"{conflict_id} already exists")

    sent = set(payload.model_dump(exclude_unset=True))
    _check_links(db, payload, sent & set(CONFLICT_LOOKUPS))

    conflict = RegistrationConflict(conflict_id=conflict_id)
    _BOOL_DEFAULTS = {"both_partners_notified": False}
    for name in CONFLICT_SCALARS:
        value = getattr(payload, name)
        if value is None and name in _BOOL_DEFAULTS:
            value = _BOOL_DEFAULTS[name]
        setattr(conflict, name, value)

    db.add(conflict)
    apply_write(
        conflict,
        resolve_write(
            db,
            "partners",
            explicit=payload.custom_fields,
            extras=extras_of(payload),
        ),
    )
    db.commit()
    db.refresh(conflict)
    return _serialise(conflict, _label_maps(db))


@router.patch("/conflicts/{conflict_id}", response_model=RegistrationConflictOut)
def patch_conflict(conflict_id: str, payload: RegistrationConflictUpdate, db: Session = Depends(get_db)):
    """Applies only the fields present in the request body."""
    return _write(db, conflict_id, payload, set(payload.model_dump(exclude_unset=True)))


@router.put("/conflicts/{conflict_id}", response_model=RegistrationConflictOut)
def put_conflict(conflict_id: str, payload: RegistrationConflictUpdate, db: Session = Depends(get_db)):
    """Kept for the same reason every other module has one: the prototype's
    record editor PUTs when it saves. Still applies only what was sent."""
    return _write(db, conflict_id, payload, set(payload.model_dump(exclude_unset=True)))


def _write(db: Session, conflict_id: str, payload: RegistrationConflictUpdate, sent: set[str]) -> dict:
    conflict = _get_or_404(db, conflict_id)
    _check_links(db, payload, sent & set(CONFLICT_LOOKUPS))

    for name in CONFLICT_SCALARS:
        if name not in sent:
            continue
        setattr(conflict, name, getattr(payload, name))

    apply_write(
        conflict,
        resolve_write(
            db,
            "partners",
            explicit=payload.custom_fields,
            extras=extras_of(payload),
        ),
    )
    db.commit()
    db.refresh(conflict)
    return _serialise(conflict, _label_maps(db))


@router.delete("/conflicts/{conflict_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_conflict(conflict_id: str, db: Session = Depends(get_db)):
    """Hard delete. Nothing points at a conflict adjudication — it is the
    terminal record in this pair's story."""
    conflict = _get_or_404(db, conflict_id)
    db.delete(conflict)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
