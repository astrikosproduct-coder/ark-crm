import re

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..audit import record_audit
from ..auth import current_user
from ..messages import already_exists, not_found, picked_record_missing, refusal
from ..changes import custom_field_diff, diff, snapshot
from ..clock import now_utc, today_company
from ..database import get_db
from ..list_query import run_list_query
from starlette.datastructures import QueryParams
from ..custom_fields import apply_write, extras_of, merge_into_row, resolve_write
from ..ids import next_reference_id
from ..models import Account, DealRegistration, Lead, User
from ..registration_matching import (
    WITHDRAWN,
    account_names,
    dependents_of,
    match_row,
    possible_matches,
    registration_name,
    resolve_possible_conflicts,
)
from ..registration_withdrawal import preview as withdrawal_preview
from ..registration_withdrawal import withdraw as withdraw_registration
from ..schemas import (
    REGISTRATION_LOOKUPS,
    REGISTRATION_SCALARS,
    DealRegistrationConflictCheck,
    DealRegistrationCreate,
    DealRegistrationOut,
    DealRegistrationUpdate,
    DealRegistrationWithdraw,
)

router = APIRouter(tags=["registrations"])

REGISTRATION_ID_PATTERN = re.compile(r"^REG-(\d+)$")


# extensions.json list_views.registrations. `partner`/`end_client` are
# lookups, so the search has to run against the account NAME a reviewer can
# actually see, not the ACC-004 stored underneath — see _text_of, same as
# contacts.py's own DEFAULT_SEARCH.
DEFAULT_SEARCH = ("project_name", "partner", "end_client")

# Server-stamped, same rule as leads.py SYSTEM_STAMPED: never read from a body.
# Submitted Date is the PARTNER's date and may be earlier than the day ARK
# entered the claim; created_date is the day ARK entered it. Before migration
# 0024 only the first existed, so a backdated registration could not be told
# from one entered on time.
SYSTEM_STAMPED = ("created_by", "created_date", "modified_by", "modified_date")

#: Set only by their own actions — the Withdraw action and the conflict check.
ACTION_STAMPED = ("withdrawn_date", "withdrawal_reason", "not_conflict_with", "not_conflict_reason")

#: Changing any of these can make — or unmake — a collision, so the conflict
#: check runs again. Anything else (a value, a timeline) cannot.
IDENTITY = ("partner", "end_client", "project_name")


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
    users = {u.user_id: u.name for u in db.scalars(select(User))}
    return {"accounts": accounts, "leads": leads, "users": users}


def _serialise(reg: DealRegistration, labels: dict[str, dict[str, str]]) -> dict:
    row: dict[str, object] = {"id": reg.registration_id, "registration_id": reg.registration_id}
    for name in REGISTRATION_SCALARS:
        value = getattr(reg, name)
        row[name] = float(value) if name == "estimated_value" and value is not None else value
    for name in SYSTEM_STAMPED + ACTION_STAMPED:
        row[name] = getattr(reg, name)
    row["not_conflict_with"] = list(reg.not_conflict_with or [])
    # What a person calls it. lib/spec displayNameOf reads `name`, so every
    # lookup to a registration shows this rather than a REG- id.
    row["name"] = registration_name(reg, labels["accounts"])

    joined = {}
    for field, collection in REGISTRATION_LOOKUPS.items():
        value = getattr(reg, field)
        if value and value in labels[collection]:
            joined[field] = labels[collection][value]
    for field in ("created_by", "modified_by"):
        value = getattr(reg, field)
        if value and value in labels["users"]:
            joined[field] = labels["users"][value]
    if joined:
        row["__labels"] = joined

    # Admin-created field values, read back flat so the form engine sees them
    # exactly like a register field. Never overwrites a typed column.
    return merge_into_row(row, reg)


def _get_or_404(db: Session, registration_id: str) -> DealRegistration:
    reg = db.get(DealRegistration, registration_id)
    if reg is None:
        raise not_found("registration")
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
            raise picked_record_missing(field.replace("_", " "))


def _check_submitted_date(payload, sent: set[str]) -> None:
    """
    A partner cannot have submitted a claim on a day that has not happened.

    Backdating stays legal — a partner emails on the 12th and BD enters it on
    the 14th, and the acknowledgement clock rightly runs from the 12th. A future
    date would instead push the acknowledgement deadline out and make an
    overdue registration read as on time. Judged on the company calendar, the
    same one every other date rule uses (app/clock.py).
    """
    if "submitted_date" not in sent or payload.submitted_date is None:
        return
    today = today_company()
    if payload.submitted_date > today:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            refusal(
                "SUBMITTED_DATE_IN_FUTURE",
                "Submitted Date can't be in the future.",
                [f"Use the day the partner sent it: {today:%d %b %Y} or earlier."],
            ),
        )


def _guard_status(payload, sent: set[str], reg: DealRegistration | None) -> None:
    """
    Withdrawn is reached only through the Withdraw action, which records the
    reason and settles the pursuit in the same transaction. A PUT that simply
    names the status would do neither. And a withdrawn registration is final.
    """
    if reg is not None and reg.registration_status == WITHDRAWN:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            {"code": "REGISTRATION_WITHDRAWN", "message": "This registration was withdrawn and is read-only."},
        )
    if "registration_status" in sent and payload.registration_status == WITHDRAWN:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            {
                "code": "USE_WITHDRAW_ACTION",
                "message": "Use the Withdraw button to withdraw a registration.",
                "details": ["It asks why, and what happens to the pursuit."],
            },
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
    if not params.get("_sort"):
        # Newest registrations are read by date submitted unless a column is chosen.
        params = QueryParams([*params.multi_items(), ("_sort", "submitted_date")])
    rows, total = run_list_query(
        rows, params, lookups=REGISTRATION_LOOKUPS, default_search=DEFAULT_SEARCH
    )
    response.headers["X-Total-Count"] = str(total)
    return rows


@router.get("/registrations/{registration_id}", response_model=DealRegistrationOut)
def get_registration(registration_id: str, db: Session = Depends(get_db)):
    return _serialise(_get_or_404(db, registration_id), _label_maps(db))


@router.post("/registrations", response_model=DealRegistrationOut, status_code=status.HTTP_201_CREATED)
def create_registration(
    payload: DealRegistrationCreate,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    registration_id = payload.registration_id or _next_registration_id(db)

    if db.get(DealRegistration, registration_id) is not None:
        raise already_exists()

    sent = set(payload.model_dump(exclude_unset=True))
    _check_links(db, payload, sent & set(REGISTRATION_LOOKUPS))
    _check_submitted_date(payload, sent)
    _guard_status(payload, sent, None)

    reg = DealRegistration(registration_id=registration_id)
    for name in REGISTRATION_SCALARS:
        setattr(reg, name, getattr(payload, name))
    reg.not_conflict_with = []
    # USD unless the user picked another — the same starting value a Lead gets.
    if not reg.currency:
        reg.currency = "USD"

    stamped_at = now_utc()
    reg.created_by = user.user_id
    reg.created_date = stamped_at
    reg.modified_by = user.user_id
    reg.modified_date = stamped_at

    db.add(reg)
    apply_write(
        reg,
        resolve_write(
            db,
            "registrations",
            explicit=payload.custom_fields,
            extras=extras_of(payload),
        ),
    )
    db.flush()

    # A similar project already registered at this End Client: the save carries
    # the answer (raise a conflict / a different project), or it is refused with
    # the matches — see app/registration_matching.py.
    raised = resolve_possible_conflicts(
        db,
        reg,
        raise_with=payload.raise_conflict_with,
        dismiss_with=payload.not_conflict_with,
        reason=payload.not_conflict_reason,
        actor=user.user_id,
    )

    # No `changed` on a create — see the same call in leads.py.
    record_audit(
        db,
        module="registrations",
        record_id=registration_id,
        action="created",
        actor=user.user_id,
        changed_fields=sorted(sent),
    )
    db.commit()
    db.refresh(reg)
    row = _serialise(reg, _label_maps(db))
    row["raised_conflicts"] = raised
    return row


@router.patch("/registrations/{registration_id}", response_model=DealRegistrationOut)
def patch_registration(
    registration_id: str,
    payload: DealRegistrationUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    """Applies only the fields present in the request body."""
    return _write(db, registration_id, payload, set(payload.model_dump(exclude_unset=True)), user)


@router.put("/registrations/{registration_id}", response_model=DealRegistrationOut)
def put_registration(
    registration_id: str,
    payload: DealRegistrationUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    """
    Kept for the same reason every other module has one: the prototype's
    record editor and the supersede/acknowledge actions all PUT. Still applies
    only what was sent.
    """
    return _write(db, registration_id, payload, set(payload.model_dump(exclude_unset=True)), user)


def _write(
    db: Session, registration_id: str, payload: DealRegistrationUpdate, sent: set[str], user: User
) -> dict:
    reg = _get_or_404(db, registration_id)
    _guard_status(payload, sent, reg)
    _check_links(db, payload, sent & set(REGISTRATION_LOOKUPS))
    # Only when the value actually CHANGES: an old registration re-saved with
    # its existing Submitted Date must never be refused over a rule it predates.
    if "submitted_date" in sent and payload.submitted_date != reg.submitted_date:
        _check_submitted_date(payload, sent)

    identity_before = tuple(getattr(reg, n) for n in IDENTITY)
    tracked = [n for n in REGISTRATION_SCALARS if n in sent] + ["not_conflict_with", "not_conflict_reason"]
    before = snapshot(reg, tracked)
    before_custom = dict(reg.custom_fields or {})

    for name in REGISTRATION_SCALARS:
        if name not in sent:
            continue
        setattr(reg, name, getattr(payload, name))

    apply_write(
        reg,
        resolve_write(
            db,
            "registrations",
            explicit=payload.custom_fields,
            extras=extras_of(payload),
        ),
    )
    db.flush()

    raised: list[str] = []
    answered = bool(payload.raise_conflict_with or payload.not_conflict_with or payload.not_conflict_reason)
    if tuple(getattr(reg, n) for n in IDENTITY) != identity_before or answered:
        raised = resolve_possible_conflicts(
            db,
            reg,
            raise_with=payload.raise_conflict_with,
            dismiss_with=payload.not_conflict_with,
            reason=payload.not_conflict_reason,
            actor=user.user_id,
        )

    reg.modified_by = user.user_id
    reg.modified_date = now_utc()

    changed = diff(before, snapshot(reg, tracked))
    changed += custom_field_diff(before_custom, reg.custom_fields)
    record_audit(
        db,
        module="registrations",
        record_id=registration_id,
        action="updated",
        actor=user.user_id,
        changed_fields=sorted(sent),
        changed=changed,
    )
    db.commit()
    db.refresh(reg)
    row = _serialise(reg, _label_maps(db))
    row["raised_conflicts"] = raised
    return row


@router.get("/registrations/{registration_id}/dependents")
def get_dependents(registration_id: str, db: Session = Depends(get_db)):
    """The leads and conflicts that stop this registration being deleted, by name."""
    return dependents_of(db, _get_or_404(db, registration_id))


@router.get("/registrations/{registration_id}/possible-conflicts")
def get_possible_conflicts(registration_id: str, db: Session = Depends(get_db)):
    """
    Live registrations this one may collide with and nobody has answered for
    yet — for a registration saved before the check ran on save, or one whose
    counterpart changed since. The Conflict tab offers each as a card.
    """
    reg = _get_or_404(db, registration_id)
    accounts = account_names(db)
    return [match_row(m, reg, accounts) for m in possible_matches(db, reg)]


@router.post("/registrations/{registration_id}/conflict-check", response_model=DealRegistrationOut)
def post_conflict_check(
    registration_id: str,
    payload: DealRegistrationConflictCheck,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    """Answer one possible conflict: raise it, or record a different project."""
    reg = _get_or_404(db, registration_id)
    if reg.registration_status == WITHDRAWN:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            {"code": "REGISTRATION_WITHDRAWN", "message": "This registration was withdrawn and is read-only."},
        )
    tracked = ["not_conflict_with", "not_conflict_reason"]
    before = snapshot(reg, tracked)
    raised = resolve_possible_conflicts(
        db,
        reg,
        raise_with=payload.raise_conflict_with,
        dismiss_with=payload.not_conflict_with,
        reason=payload.not_conflict_reason,
        actor=user.user_id,
        partial=True,
    )
    changed = diff(before, snapshot(reg, tracked))
    if changed:
        reg.modified_by = user.user_id
        reg.modified_date = now_utc()
        record_audit(
            db,
            module="registrations",
            record_id=registration_id,
            action="updated",
            actor=user.user_id,
            changed_fields=tracked,
            changed=changed,
        )
    db.commit()
    db.refresh(reg)
    row = _serialise(reg, _label_maps(db))
    row["raised_conflicts"] = raised
    return row


@router.get("/registrations/{registration_id}/withdrawal")
def get_withdrawal(registration_id: str, db: Session = Depends(get_db)):
    """What withdrawing would touch — the pursuit, its group, the primary."""
    return withdrawal_preview(db, _get_or_404(db, registration_id))


@router.post("/registrations/{registration_id}/withdraw", response_model=DealRegistrationOut)
def post_withdraw(
    registration_id: str,
    payload: DealRegistrationWithdraw,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    """Withdraw, and settle the pursuit in the same transaction — see
    app/registration_withdrawal.py."""
    reg = _get_or_404(db, registration_id)
    withdraw_registration(
        db,
        reg,
        reason=payload.reason,
        action=payload.pursuit_action,
        new_primary=payload.new_primary,
        user=user,
    )
    db.refresh(reg)
    return _serialise(reg, _label_maps(db))


@router.delete("/registrations/{registration_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_registration(
    registration_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    """
    Hard delete, and only while nothing depends on the registration: no lead
    created from it and no conflict naming it. Deleting never takes a lead,
    account or contact with it — a registration whose partner pulled out is
    WITHDRAWN instead, which asks what happens to the pursuit. The database
    enforces the lead half too (leads.partner_deal_registration, ON DELETE
    RESTRICT, migration 0025).
    """
    reg = _get_or_404(db, registration_id)

    dependents = dependents_of(db, reg)
    if dependents["leads"] or dependents["conflicts"]:
        parts = []
        if dependents["leads"]:
            parts.append(f"{len(dependents['leads'])} {'lead' if len(dependents['leads']) == 1 else 'leads'}")
        if dependents["conflicts"]:
            parts.append(f"{len(dependents['conflicts'])} {'conflict' if len(dependents['conflicts']) == 1 else 'conflicts'}")
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            {
                "code": "REGISTRATION_HAS_DEPENDENTS",
                "message": f"This registration can't be deleted: {' and '.join(parts)} depend on it.",
                "details": ["Partner pulled out? Withdraw it instead."],
                **dependents,
            },
        )

    record_audit(
        db, module="registrations", record_id=registration_id, action="deleted", actor=user.user_id
    )
    db.delete(reg)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
