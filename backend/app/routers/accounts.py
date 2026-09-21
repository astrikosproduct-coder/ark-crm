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
from ..custom_fields import apply_write, extras_of, merge_into_row, resolve_write
from ..thresholds import check_thresholds
from ..ids import next_reference_id
from ..models import Account, AccountType, Contact, DealRegistration, User
from ..schemas import (
    ACCOUNT_SCALARS,
    AccountCreate,
    AccountOut,
    AccountUpdate,
    ActiveFlag,
)

router = APIRouter(tags=["accounts"])

ACCOUNT_ID_PATTERN = re.compile(r"^ACC-(\d+)$")


# Fields `q` searches when the caller names none. Kept narrow and textual;
# extensions.json list_views.accounts.search asks for exactly these three.
DEFAULT_SEARCH = ("account_name", "region", "segment")

MULTISELECTS = {"account_type"}

#: Lookups whose joined name search and sort read, not the id underneath.
ACCOUNT_LOOKUPS = ("account_owner",)


def _next_account_id(db: Session) -> str:
    """
    The register calls account_id an autonumber, so the server allocates it.

    From a stored high-water mark, NOT from max(existing) — an id must never be
    reused, or a new account inherits the references of a deleted one. See
    app/ids.py.
    """
    highest = 0
    for existing in db.scalars(select(Account.account_id)):
        match = ACCOUNT_ID_PATTERN.match(existing or "")
        if match:
            highest = max(highest, int(match.group(1)))
    return next_reference_id(db, "accounts", "ACC", 3, highest)


def _serialise(account: Account, owner_names: dict[str, str]) -> dict:
    """One account in the shape the frontend's spec layer expects."""
    row = {
        "id": account.account_id,
        "account_id": account.account_id,
        "account_type": sorted(t.account_type for t in account.types),
    }
    for name in ACCOUNT_SCALARS:
        value = getattr(account, name)
        # Numeric comes back as Decimal, which is not JSON-serialisable.
        row[name] = float(value) if name.endswith("_score") and value is not None else value

    # The lookup display name, joined here so a list of 25 is one request.
    if account.account_owner and account.account_owner in owner_names:
        row["__labels"] = {"account_owner": owner_names[account.account_owner]}

    # Admin-created field values, read back flat so the form engine sees them
    # exactly like a register field. Never overwrites a typed column.
    return merge_into_row(row, account)


def _owner_names(db: Session) -> dict[str, str]:
    return {u.user_id: u.name for u in db.scalars(select(User))}


def _apply_multiselects(db: Session, account: Account, payload: AccountUpdate | AccountCreate,
                        fields_sent: set[str]) -> None:
    """Replace a multiselect's junction rows when the caller sent that field."""
    if "account_type" in fields_sent:
        account.types.clear()
        db.flush()
        for value in dict.fromkeys(payload.account_type or []):
            account.types.append(AccountType(account_id=account.account_id, account_type=value))


def _get_or_404(db: Session, account_id: str) -> Account:
    account = db.get(Account, account_id)
    if account is None:
        raise not_found("account")
    return account


@router.get("/accounts", response_model=list[AccountOut])
def list_accounts(request: Request, response: Response, db: Session = Depends(get_db)):
    """
    Accounts, with the list semantics the prototype's list component expects:
    filtering, free-text search, sorting and paging as query parameters, and the
    row total on X-Total-Count.

    Partners is a VIEW over this endpoint — the same records filtered by
    account_type — not a collection of its own.
    """
    accounts = list(db.scalars(select(Account)))
    owner_names = _owner_names(db)
    rows = [_serialise(a, owner_names) for a in accounts]

    # Filters, search, sort and page — the one list contract every live module
    # shares (app/list_query.py), so the Filter panel works here as on Leads.
    rows, total = run_list_query(
        rows, request.query_params, lookups=ACCOUNT_LOOKUPS, default_search=DEFAULT_SEARCH
    )
    response.headers["X-Total-Count"] = str(total)
    return rows


@router.get("/accounts/{account_id}", response_model=AccountOut)
def get_account(account_id: str, db: Session = Depends(get_db)):
    return _serialise(_get_or_404(db, account_id), _owner_names(db))


@router.post("/accounts", response_model=AccountOut, status_code=status.HTTP_201_CREATED)
def create_account(
    payload: AccountCreate,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    account_id = payload.account_id or _next_account_id(db)

    if db.get(Account, account_id) is not None:
        raise already_exists()

    _check_owner(db, payload.account_owner)
    check_thresholds(db, "accounts", payload.model_dump())

    account = Account(account_id=account_id)
    for name in ACCOUNT_SCALARS:
        value = getattr(payload, name)
        # active is NOT NULL with a default; an omitted field must not write None.
        if value is None and name == "active":
            value = True
        setattr(account, name, value)
    db.add(account)
    db.flush()  # the junction tables have an FK to this row

    _apply_multiselects(db, account, payload, set(MULTISELECTS))

    # Values for Administration-created fields go to custom_fields JSONB,
    # never to a column of their own. Unknown keys are not stored — see
    # app/custom_fields.py::resolve_write.
    apply_write(
        account,
        resolve_write(
            db,
            "accounts",
            explicit=payload.custom_fields,
            extras=extras_of(payload),
        ),
    )
    record_audit(
        db,
        module="accounts",
        record_id=account_id,
        action="created",
        actor=user.user_id,
        changed_fields=sorted(payload.model_dump(exclude_unset=True)),
    )

    db.commit()
    db.refresh(account)
    return _serialise(account, _owner_names(db))


@router.patch("/accounts/{account_id}", response_model=AccountOut)
def patch_account(
    account_id: str,
    payload: AccountUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    """Applies only the fields present in the request body."""
    return _write(db, account_id, payload, set(payload.model_dump(exclude_unset=True)), user)


@router.put("/accounts/{account_id}", response_model=AccountOut)
def put_account(
    account_id: str,
    payload: AccountUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    """
    Full-record write, kept because the prototype's record editor and the Lead
    account sync both PUT — see LeadAccountFieldSync.tsx, which writes the
    account back when a Lead edits an inherited field.

    Still applies only what was sent: a caller that PUTs a partial body is
    editing a form it rendered from the register, not asserting that every
    absent field is now null.
    """
    return _write(db, account_id, payload, set(payload.model_dump(exclude_unset=True)), user)


def _write(db: Session, account_id: str, payload: AccountUpdate, sent: set[str], user: User) -> dict:
    account = _get_or_404(db, account_id)

    # The before half of the diff, read before anything is applied — see
    # routers/leads.py::_write.
    tracked = [name for name in ACCOUNT_SCALARS if name in sent]
    before = snapshot(account, tracked)
    before_custom = dict(account.custom_fields or {})

    if "account_owner" in sent:
        _check_owner(db, payload.account_owner)
    check_thresholds(db, "accounts", payload.model_dump(include=sent))

    for name in ACCOUNT_SCALARS:
        if name in sent:
            value = getattr(payload, name)
            if value is None and name == "active":
                value = True
            setattr(account, name, value)

    _apply_multiselects(db, account, payload, sent & MULTISELECTS)

    # Values for Administration-created fields go to custom_fields JSONB,
    # never to a column of their own. Unknown keys are not stored — see
    # app/custom_fields.py::resolve_write.
    apply_write(
        account,
        resolve_write(
            db,
            "accounts",
            explicit=payload.custom_fields,
            extras=extras_of(payload),
        ),
    )
    changed = diff(before, snapshot(account, tracked))
    changed += custom_field_diff(before_custom, account.custom_fields)

    record_audit(
        db,
        module="accounts",
        record_id=account_id,
        action="updated",
        actor=user.user_id,
        changed_fields=sorted(sent),
        changed=changed,
    )

    db.commit()
    db.refresh(account)
    return _serialise(account, _owner_names(db))


def _check_owner(db: Session, owner_id: str | None) -> None:
    """
    account_owner is a real foreign key to users. Rejecting an unknown id here
    turns a silent integrity error into a message naming the field.
    """
    if owner_id and db.get(User, owner_id) is None:
        raise picked_record_missing("person")


@router.patch("/accounts/{account_id}/active", response_model=AccountOut)
def set_account_active(
    account_id: str,
    payload: ActiveFlag,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    """
    Deactivate or reactivate. This is the SAFE way to retire an organisation:
    the account keeps its id, so every lead, quote and contact pointing at it
    still resolves to a name.
    """
    account = _get_or_404(db, account_id)
    was_active = account.active
    account.active = payload.active
    record_audit(
        db,
        module="accounts",
        record_id=account_id,
        action="updated",
        actor=user.user_id,
        changed_fields=["active"],
        changed=diff({"active": was_active}, {"active": account.active}),
    )
    db.commit()
    db.refresh(account)
    return _serialise(account, _owner_names(db))


@router.delete("/accounts/{account_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_account(
    account_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    """
    Hard delete, allowed ONLY when nothing in the database depends on this
    account. A dependent record is refused with 409 and the caller is told to
    deactivate instead.

    This guards what the database can see — contacts (a real foreign key) and,
    since Round 3, deal registrations naming this account as partner or end
    client. Leads, deals and quotes still live in the mock store, so the
    frontend checks those before it ever calls this; see
    src/components/record/DeleteRecordDialog.tsx.
    """
    account = _get_or_404(db, account_id)

    dependents = db.scalars(
        select(Contact.contact_id).where(Contact.account == account_id)
    ).all()
    if dependents:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            refusal(
                "ACCOUNT_HAS_CONTACTS",
                f"This account still has {len(dependents)} "
                f"{'contact' if len(dependents) == 1 else 'contacts'}, so it can't be deleted.",
                ["Deactivate it instead."],
                contacts=dependents,
            ),
        )

    registration_dependents = db.scalars(
        select(DealRegistration.registration_id).where(
            (DealRegistration.partner == account_id) | (DealRegistration.end_client == account_id)
        )
    ).all()
    if registration_dependents:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            refusal(
                "ACCOUNT_HAS_REGISTRATIONS",
                f"This account is on {len(registration_dependents)} deal "
                f"{'registration' if len(registration_dependents) == 1 else 'registrations'}, so it can't be deleted.",
                ["Deactivate it instead."],
                registrations=registration_dependents,
            ),
        )

    record_audit(
        db, module="accounts", record_id=account_id, action="deleted", actor=user.user_id
    )
    db.delete(account)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
