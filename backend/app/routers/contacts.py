import re

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth import current_user
from ..messages import already_exists, not_found, picked_record_missing, refusal
from ..changes import custom_field_diff, diff, snapshot
from ..database import get_db
from ..list_query import run_list_query
from ..audit import record_audit
from ..record_references import records_naming_contact
from ..custom_fields import apply_write, extras_of, merge_into_row, resolve_write
from ..thresholds import check_thresholds
from ..ids import next_reference_id
from ..models import Account, Contact, User
from ..schemas import (
    CONTACT_LOOKUPS,
    CONTACT_SCALARS,
    ActiveFlag,
    ContactCreate,
    ContactOut,
    ContactUpdate,
)

router = APIRouter(tags=["contacts"])

CONTACT_ID_PATTERN = re.compile(r"^CON-(\d+)$")


# extensions.json list_views.contacts.search. `account` is a LOOKUP, so the
# search has to run against the account NAME the reviewer can actually see, not
# the ACC-004 stored underneath — see _text_of.
DEFAULT_SEARCH = ("full_name", "job_title", "email", "account")


def _next_contact_id(db: Session) -> str:
    """From a stored high-water mark, never max(existing) — see app/ids.py."""
    highest = 0
    for existing in db.scalars(select(Contact.contact_id)):
        match = CONTACT_ID_PATTERN.match(existing or "")
        if match:
            highest = max(highest, int(match.group(1)))
    return next_reference_id(db, "contacts", "CON", 3, highest)


def _label_maps(db: Session) -> dict[str, dict[str, str]]:
    """id -> display name for each collection a contact looks up."""
    return {
        "accounts": {a.account_id: a.account_name for a in db.scalars(select(Account))},
        "users": {u.user_id: u.name for u in db.scalars(select(User))},
    }


def _serialise(contact: Contact, labels: dict[str, dict[str, str]]) -> dict:
    row = {"id": contact.contact_id, "contact_id": contact.contact_id}

    for name in CONTACT_SCALARS:
        value = getattr(contact, name)
        # Numeric comes back as Decimal, which is not JSON-serialisable.
        row[name] = float(value) if name == "relationship_score" and value is not None else value

    joined = {}
    for field, collection in CONTACT_LOOKUPS.items():
        value = getattr(contact, field)
        if value and value in labels[collection]:
            joined[field] = labels[collection][value]
    if joined:
        row["__labels"] = joined

    # Admin-created field values, read back flat so the form engine sees them
    # exactly like a register field. Never overwrites a typed column.
    return merge_into_row(row, contact)


def _get_or_404(db: Session, contact_id: str) -> Contact:
    contact = db.get(Contact, contact_id)
    if contact is None:
        raise not_found("contact")
    return contact


def _check_links(db: Session, payload, sent: set[str]) -> None:
    """
    Both lookups are real foreign keys. Rejecting an unknown id here turns a
    database integrity error into a message that names the field.
    """
    if "account" in sent and payload.account and db.get(Account, payload.account) is None:
        raise picked_record_missing("account")
    if (
        "engagement_owner" in sent
        and payload.engagement_owner
        and db.get(User, payload.engagement_owner) is None
    ):
        raise picked_record_missing("person")


@router.get("/contacts", response_model=list[ContactOut])
def list_contacts(request: Request, response: Response, db: Session = Depends(get_db)):
    """
    Contacts, with the same list contract accounts and the mock server provide:
    equality filters (repeated = OR), free-text search, sort, page, and the row
    total on X-Total-Count.

    The Account detail screen reads this with ?account=ACC-004 to show everybody
    at one organisation.
    """
    labels = _label_maps(db)
    rows = [_serialise(c, labels) for c in db.scalars(select(Contact))]

    rows, total = run_list_query(
        rows, request.query_params, lookups=CONTACT_LOOKUPS, default_search=DEFAULT_SEARCH
    )
    response.headers["X-Total-Count"] = str(total)
    return rows


@router.get("/contacts/{contact_id}", response_model=ContactOut)
def get_contact(contact_id: str, db: Session = Depends(get_db)):
    return _serialise(_get_or_404(db, contact_id), _label_maps(db))


@router.post("/contacts", response_model=ContactOut, status_code=status.HTTP_201_CREATED)
def create_contact(
    payload: ContactCreate,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    contact_id = payload.contact_id or _next_contact_id(db)

    if db.get(Contact, contact_id) is not None:
        raise already_exists()

    _check_links(db, payload, set(CONTACT_LOOKUPS))
    check_thresholds(db, "contacts", payload.model_dump())

    contact = Contact(contact_id=contact_id)
    for name in CONTACT_SCALARS:
        value = getattr(payload, name)
        # NOT NULL booleans: an omitted field must not write None. The two
        # checkboxes default false, active defaults true.
        if value is None and name in ("confidential", "is_client_poc_evaluator"):
            value = False
        if value is None and name == "active":
            value = True
        setattr(contact, name, value)

    db.add(contact)
    # Values for Administration-created fields go to custom_fields JSONB,
    # never to a column of their own. Unknown keys are not stored — see
    # app/custom_fields.py::resolve_write.
    apply_write(
        contact,
        resolve_write(
            db,
            "contacts",
            explicit=payload.custom_fields,
            extras=extras_of(payload),
        ),
    )
    record_audit(
        db,
        module="contacts",
        record_id=contact_id,
        action="created",
        actor=user.user_id,
        changed_fields=sorted(payload.model_dump(exclude_unset=True)),
    )
    db.commit()
    db.refresh(contact)
    return _serialise(contact, _label_maps(db))


@router.patch("/contacts/{contact_id}", response_model=ContactOut)
def patch_contact(
    contact_id: str,
    payload: ContactUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    """Applies only the fields present in the request body."""
    return _write(db, contact_id, payload, set(payload.model_dump(exclude_unset=True)), user)


@router.put("/contacts/{contact_id}", response_model=ContactOut)
def put_contact(
    contact_id: str,
    payload: ContactUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    """
    Kept for the same reason accounts has one: the prototype's record editor
    PUTs when it saves. Still applies only what was sent — a caller that omits a
    field is editing a form, not asserting the field is now null.
    """
    return _write(db, contact_id, payload, set(payload.model_dump(exclude_unset=True)), user)


def _write(db: Session, contact_id: str, payload: ContactUpdate, sent: set[str], user: User) -> dict:
    contact = _get_or_404(db, contact_id)

    # The before half of the diff, read before anything is applied — see
    # routers/leads.py::_write.
    tracked = [name for name in CONTACT_SCALARS if name in sent]
    before = snapshot(contact, tracked)
    before_custom = dict(contact.custom_fields or {})
    _check_links(db, payload, sent)
    check_thresholds(db, "contacts", payload.model_dump(include=sent))

    for name in CONTACT_SCALARS:
        if name not in sent:
            continue
        value = getattr(payload, name)
        if value is None and name in ("confidential", "is_client_poc_evaluator"):
            value = False
        if value is None and name == "active":
            value = True
        setattr(contact, name, value)

    # Values for Administration-created fields go to custom_fields JSONB,
    # never to a column of their own. Unknown keys are not stored — see
    # app/custom_fields.py::resolve_write.
    apply_write(
        contact,
        resolve_write(
            db,
            "contacts",
            explicit=payload.custom_fields,
            extras=extras_of(payload),
        ),
    )
    changed = diff(before, snapshot(contact, tracked))
    changed += custom_field_diff(before_custom, contact.custom_fields)

    record_audit(
        db,
        module="contacts",
        record_id=contact_id,
        action="updated",
        actor=user.user_id,
        changed_fields=sorted(sent),
        changed=changed,
    )
    db.commit()
    db.refresh(contact)
    return _serialise(contact, _label_maps(db))


@router.patch("/contacts/{contact_id}/active", response_model=ContactOut)
def set_contact_active(
    contact_id: str,
    payload: ActiveFlag,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    """
    Deactivate or reactivate. The safe way to retire someone who has left the
    client: the contact keeps its id, so a Lead naming them as Primary Contact
    still resolves to a name instead of showing a bare CON-004.
    """
    contact = _get_or_404(db, contact_id)
    was_active = contact.active
    contact.active = payload.active
    record_audit(
        db,
        module="contacts",
        record_id=contact_id,
        action="updated",
        actor=user.user_id,
        changed_fields=["active"],
        changed=diff({"active": was_active}, {"active": contact.active}),
    )
    db.commit()
    db.refresh(contact)
    return _serialise(contact, _label_maps(db))


@router.delete("/contacts/{contact_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_contact(
    contact_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    """
    Hard delete, refused while a Lead still names this contact — as Primary
    Contact or a demo attendee. Those foreign keys are ON DELETE SET NULL, so
    without this check the delete would silently blank them (21 Sep 2026; see
    app/record_references.py). The delete dialog shows the same references
    first, but this is the check that holds.
    """
    contact = _get_or_404(db, contact_id)
    dependents = records_naming_contact(db, contact_id)
    if dependents:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            refusal(
                "CONTACT_IN_USE",
                f"This contact is named on {len(dependents)} "
                f"{'pursuit' if len(dependents) == 1 else 'pursuits'}, so they can't be deleted.",
                ["Deactivate them instead.", "Or change those records to another contact first."],
                records=dependents,
            ),
        )
    record_audit(
        db, module="contacts", record_id=contact_id, action="deleted", actor=user.user_id
    )
    db.delete(contact)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
