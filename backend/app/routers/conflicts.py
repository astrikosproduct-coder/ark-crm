import re

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..audit import record_audit
from ..auth import current_user
from ..messages import already_exists, not_found, picked_record_missing, refusal
from ..changes import custom_field_diff, diff, snapshot
from ..clock import now_utc
from ..database import get_db
from ..custom_fields import apply_write, extras_of, merge_into_row, resolve_write
from ..ids import next_reference_id
from ..models import DealRegistration, PursuitGroup, RegistrationConflict, User
from ..pursuits import apply_conflict_decision, dissolve_if_single
from ..registration_matching import (
    account_names,
    conflict_name,
    pair_conflict,
    partner_names_of_registrations,
    registration_name,
    who_registered_first_for,
)
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
    accounts = account_names(db)
    registrations = {r.registration_id: registration_name(r, accounts) for r in db.scalars(select(DealRegistration))}
    users = {u.user_id: u.name for u in db.scalars(select(User))}
    groups = {
        g.source_conflict: g.group_id
        for g in db.scalars(select(PursuitGroup).where(PursuitGroup.source_conflict.is_not(None)))
    }
    return {
        "registrations": registrations,
        "users": users,
        "groups": groups,
        "partner_of": partner_names_of_registrations(db, accounts),
    }


def _require_rationale(conflict: RegistrationConflict) -> None:
    """A decision both partners may contest has to be explainable afterwards."""
    if conflict.decision and not (conflict.decision_rationale or "").strip():
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            {
                "code": "DECISION_RATIONALE_REQUIRED",
                "message": "Record the Decision Rationale & Evidence before saving a decision.",
            },
        )


def _serialise(c: RegistrationConflict, labels: dict[str, dict[str, str]]) -> dict:
    row: dict[str, object] = {"id": c.conflict_id, "conflict_id": c.conflict_id}
    for name in CONFLICT_SCALARS:
        row[name] = getattr(c, name)

    # System stamps — read-only, never accepted from a body. See the create.
    for name in ("created_by", "created_date", "modified_by", "modified_date"):
        row[name] = getattr(c, name)

    joined = {}
    for field, collection in CONFLICT_LOOKUPS.items():
        value = getattr(c, field)
        if value and value in labels[collection]:
            joined[field] = labels[collection][value]
    for field in ("created_by", "modified_by"):
        value = getattr(c, field)
        if value and value in labels["users"]:
            joined[field] = labels["users"][value]
    if joined:
        row["__labels"] = joined

    # The Pursuit Group a "Both pursued" decision created, when there is one,
    # so ConflictPanel can link to it without a second query.
    row["pursuit_group"] = labels["groups"].get(c.conflict_id)
    row["name"] = conflict_name(c, labels["partner_of"])

    # Admin-created field values, read back flat so the form engine sees them
    # exactly like a register field. Never overwrites a typed column.
    return merge_into_row(row, c)


def _get_or_404(db: Session, conflict_id: str) -> RegistrationConflict:
    conflict = db.get(RegistrationConflict, conflict_id)
    if conflict is None:
        raise not_found("conflict")
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
            raise picked_record_missing(noun)


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
def create_conflict(
    payload: RegistrationConflictCreate,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    conflict_id = payload.conflict_id or _next_conflict_id(db)

    if db.get(RegistrationConflict, conflict_id) is not None:
        raise already_exists()

    sent = set(payload.model_dump(exclude_unset=True))
    _check_links(db, payload, sent & set(CONFLICT_LOOKUPS))

    # One adjudication per pair. Saving a registration raises the record itself
    # now (app/registration_matching.py), so a second one for the same two
    # registrations is always a mistake.
    existing_pair = pair_conflict(db, payload.registration_a, payload.registration_b)
    if existing_pair is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            {
                "code": "CONFLICT_EXISTS",
                "message": "These two registrations already have a conflict.",
                "details": ["Open that conflict and decide it there."],
            },
        )

    conflict = RegistrationConflict(conflict_id=conflict_id)
    _BOOL_DEFAULTS = {"both_partners_notified": False}
    for name in CONFLICT_SCALARS:
        value = getattr(payload, name)
        if value is None and name in _BOOL_DEFAULTS:
            value = _BOOL_DEFAULTS[name]
        setattr(conflict, name, value)
    # Criterion one is a fact about the two Submitted Dates, never an opinion.
    conflict.who_registered_first = who_registered_first_for(db, conflict)

    # Identity and time come from the Entra session and the server clock, never
    # from the request — the same rule as leads.py SYSTEM_STAMPED.
    stamped_at = now_utc()
    conflict.created_by = user.user_id
    conflict.created_date = stamped_at
    conflict.modified_by = user.user_id
    conflict.modified_date = stamped_at

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
    db.flush()
    # "Both pursued" creates the Pursuit Group — see app/pursuits.py.
    apply_conflict_decision(db, conflict, previous=None, actor=user.user_id)
    _require_rationale(conflict)
    record_audit(
        db,
        module="conflicts",
        record_id=conflict_id,
        action="created",
        actor=user.user_id,
        changed_fields=sorted(sent),
    )
    db.commit()
    db.refresh(conflict)
    return _serialise(conflict, _label_maps(db))


@router.patch("/conflicts/{conflict_id}", response_model=RegistrationConflictOut)
def patch_conflict(
    conflict_id: str,
    payload: RegistrationConflictUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    """Applies only the fields present in the request body."""
    return _write(db, conflict_id, payload, set(payload.model_dump(exclude_unset=True)), user)


@router.put("/conflicts/{conflict_id}", response_model=RegistrationConflictOut)
def put_conflict(
    conflict_id: str,
    payload: RegistrationConflictUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    """Kept for the same reason every other module has one: the prototype's
    record editor PUTs when it saves. Still applies only what was sent."""
    return _write(db, conflict_id, payload, set(payload.model_dump(exclude_unset=True)), user)


def _write(
    db: Session, conflict_id: str, payload: RegistrationConflictUpdate, sent: set[str], user: User
) -> dict:
    conflict = _get_or_404(db, conflict_id)
    _check_links(db, payload, sent & set(CONFLICT_LOOKUPS))
    previous_decision = conflict.decision

    tracked = [n for n in CONFLICT_SCALARS if n in sent or n == "who_registered_first"]
    before = snapshot(conflict, tracked)
    before_custom = dict(conflict.custom_fields or {})

    for name in CONFLICT_SCALARS:
        if name not in sent:
            continue
        setattr(conflict, name, getattr(payload, name))
    conflict.who_registered_first = who_registered_first_for(db, conflict)

    apply_write(
        conflict,
        resolve_write(
            db,
            "partners",
            explicit=payload.custom_fields,
            extras=extras_of(payload),
        ),
    )
    if sent & {"decision", "primary_registration", "registration_a", "registration_b"}:
        apply_conflict_decision(db, conflict, previous=previous_decision, actor=user.user_id)
    _require_rationale(conflict)

    conflict.modified_by = user.user_id
    conflict.modified_date = now_utc()

    changed = diff(before, snapshot(conflict, tracked))
    changed += custom_field_diff(before_custom, conflict.custom_fields)
    record_audit(
        db,
        module="conflicts",
        record_id=conflict_id,
        action="updated",
        actor=user.user_id,
        changed_fields=sorted(sent),
        changed=changed,
    )
    db.commit()
    db.refresh(conflict)
    return _serialise(conflict, _label_maps(db))


@router.delete("/conflicts/{conflict_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_conflict(
    conflict_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    """Hard delete. The one thing that points at a conflict is the Pursuit Group
    a "Both pursued" decision created: refused while it still groups two or more
    pursuits, dissolved with the conflict when it does not."""
    conflict = _get_or_404(db, conflict_id)
    group = db.scalars(select(PursuitGroup).where(PursuitGroup.source_conflict == conflict_id)).first()
    if group is not None and not dissolve_if_single(db, group, actor=user.user_id):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            refusal(
                "GROUP_STILL_HAS_PURSUITS",
                "This conflict's pursuit group still holds its pursuits.",
                ["Remove them from the group first, then delete the conflict."],
            ),
        )
    record_audit(db, module="conflicts", record_id=conflict_id, action="deleted", actor=user.user_id)
    db.delete(conflict)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
