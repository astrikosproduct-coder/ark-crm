import re

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..audit import record_audit
from ..custom_fields import apply_write, extras_of, merge_into_row, resolve_write
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

# The five query parameters the list endpoint reserves. Anything else is an
# equality filter on that field — the contract src/mocks/query.ts defines and
# that PartnersPage relies on when it asks for two account types at once.
RESERVED = {"_page", "_limit", "_sort", "_order", "_search", "q"}

# Fields `q` searches when the caller names none. Kept narrow and textual;
# extensions.json list_views.accounts.search asks for exactly these three.
DEFAULT_SEARCH = ("account_name", "region", "segment")

MULTISELECTS = {"account_type"}


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
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"No account {account_id}")
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

    params = request.query_params

    # 1. equality filters. A repeated parameter is an OR over its values, so
    #    ?account_type=PARTNER_SI&account_type=OEM_TECHNOLOGY_PARTNER matches
    #    either — ANDing them could never match anything.
    for key in {k for k in params if k not in RESERVED}:
        wanted = set(params.getlist(key))
        rows = [r for r in rows if _matches(r.get(key), wanted)]

    # 2. free-text search over the named fields, or the default three.
    q = (params.get("q") or "").strip().lower()
    if q:
        named = [f for f in (params.get("_search") or "").split(",") if f]
        search_fields = named or list(DEFAULT_SEARCH)
        rows = [r for r in rows if _text_of(r, search_fields).lower().find(q) >= 0]

    # 3. sort. Picklist columns sort by their stored KEY rather than their
    #    label, which the mock sorted by. The keys are upper-cased forms of the
    #    same words, so the order matches for every current picklist; a label
    #    that diverges from its key would need the vocabulary server-side.
    sort = params.get("_sort")
    if sort:
        rows.sort(key=lambda r: _sort_key(r.get(sort)))
        if params.get("_order") == "desc":
            rows.reverse()

    total = len(rows)

    # 4. page
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


def _text_of(row: dict, fields: list[str]) -> str:
    parts = []
    for name in fields:
        value = row.get(name)
        if isinstance(value, list):
            parts.extend(str(v) for v in value)
        elif value is not None:
            parts.append(str(value))
    return " ".join(parts)


def _sort_key(value):
    """Nulls last, then case-insensitive text."""
    if value is None or value == "":
        return (1, "")
    if isinstance(value, list):
        return (0, ", ".join(sorted(str(v) for v in value)).lower())
    return (0, str(value).lower())


@router.get("/accounts/{account_id}", response_model=AccountOut)
def get_account(account_id: str, db: Session = Depends(get_db)):
    return _serialise(_get_or_404(db, account_id), _owner_names(db))


@router.post("/accounts", response_model=AccountOut, status_code=status.HTTP_201_CREATED)
def create_account(payload: AccountCreate, db: Session = Depends(get_db)):
    account_id = payload.account_id or _next_account_id(db)

    if db.get(Account, account_id) is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, f"{account_id} already exists")

    _check_owner(db, payload.account_owner)

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
        changed_fields=sorted(payload.model_dump(exclude_unset=True)),
    )

    db.commit()
    db.refresh(account)
    return _serialise(account, _owner_names(db))


@router.patch("/accounts/{account_id}", response_model=AccountOut)
def patch_account(account_id: str, payload: AccountUpdate, db: Session = Depends(get_db)):
    """Applies only the fields present in the request body."""
    return _write(db, account_id, payload, set(payload.model_dump(exclude_unset=True)))


@router.put("/accounts/{account_id}", response_model=AccountOut)
def put_account(account_id: str, payload: AccountUpdate, db: Session = Depends(get_db)):
    """
    Full-record write, kept because the prototype's record editor and the Lead
    account sync both PUT — see LeadAccountFieldSync.tsx, which writes the
    account back when a Lead edits an inherited field.

    Still applies only what was sent: a caller that PUTs a partial body is
    editing a form it rendered from the register, not asserting that every
    absent field is now null.
    """
    return _write(db, account_id, payload, set(payload.model_dump(exclude_unset=True)))


def _write(db: Session, account_id: str, payload: AccountUpdate, sent: set[str]) -> dict:
    account = _get_or_404(db, account_id)

    if "account_owner" in sent:
        _check_owner(db, payload.account_owner)

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
    record_audit(db, module="accounts", record_id=account_id, action="updated", changed_fields=sorted(sent))

    db.commit()
    db.refresh(account)
    return _serialise(account, _owner_names(db))


def _check_owner(db: Session, owner_id: str | None) -> None:
    """
    account_owner is a real foreign key to users. Rejecting an unknown id here
    turns a silent integrity error into a message naming the field.
    """
    if owner_id and db.get(User, owner_id) is None:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, f"No such user: {owner_id}"
        )


@router.patch("/accounts/{account_id}/active", response_model=AccountOut)
def set_account_active(account_id: str, payload: ActiveFlag, db: Session = Depends(get_db)):
    """
    Deactivate or reactivate. This is the SAFE way to retire an organisation:
    the account keeps its id, so every lead, quote and contact pointing at it
    still resolves to a name.
    """
    account = _get_or_404(db, account_id)
    account.active = payload.active
    record_audit(db, module="accounts", record_id=account_id, action="updated", changed_fields=["active"])
    db.commit()
    db.refresh(account)
    return _serialise(account, _owner_names(db))


@router.delete("/accounts/{account_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_account(account_id: str, db: Session = Depends(get_db)):
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
            f"{account_id} still has {len(dependents)} contact(s): "
            f"{', '.join(dependents[:5])}"
            f"{'…' if len(dependents) > 5 else ''}. Deactivate it instead.",
        )

    registration_dependents = db.scalars(
        select(DealRegistration.registration_id).where(
            (DealRegistration.partner == account_id) | (DealRegistration.end_client == account_id)
        )
    ).all()
    if registration_dependents:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"{account_id} is still named on {len(registration_dependents)} deal registration(s): "
            f"{', '.join(registration_dependents[:5])}"
            f"{'…' if len(registration_dependents) > 5 else ''}. Deactivate it instead.",
        )

    record_audit(db, module="accounts", record_id=account_id, action="deleted")
    db.delete(account)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
