import re

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..audit import record_audit
from ..custom_fields import apply_write, extras_of, merge_into_row, resolve_write
from ..carry_forward import locked_violations, seed_values
from ..ids import next_reference_id
from ..models import (
    Account,
    Deal,
    DealBidCommitment,
    DealExpansionUseCase,
    Lead,
    Opportunity,
    User,
)
from ..schemas import (
    DEAL_LOOKUPS,
    DEAL_SCALARS,
    DealCreate,
    DealOut,
    DealUpdate,
)

router = APIRouter(tags=["deals"])

DEAL_ID_PATTERN = re.compile(r"^DEAL-(\d+)$")

RESERVED = {"_page", "_limit", "_sort", "_order", "_search", "q"}

# extensions.json list_views.deals, once written; kept narrow and textual like
# leads' and opportunities' own defaults.
DEFAULT_SEARCH = ("deal_name", "deal_stage")

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
    return {"accounts": accounts, "users": users, "leads": leads, "opportunities": {}}


def _serialise(deal: Deal, labels: dict[str, dict[str, str]]) -> dict:
    row: dict[str, object] = {
        "id": deal.deal_id,
        "deal_id": deal.deal_id,
    }
    for name in DEAL_SCALARS:
        value = getattr(deal, name)
        row[name] = float(value) if name in _MONEY_LIKE and value is not None else value
    row["created_by_date"] = deal.created_by_date
    row["modified_by_date"] = deal.modified_by_date

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
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"No deal {deal_id}")
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
        if field not in sent:
            continue
        value = getattr(payload, field)
        if value and db.get(models_by_collection[collection], value) is None:
            noun = singular.get(collection, collection[:-1])
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"No such {noun}: {value}")


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
    rows = [_serialise(d, labels) for d in db.scalars(select(Deal))]

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
    if field in DEAL_LOOKUPS:
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


@router.get("/deals/{deal_id}", response_model=DealOut)
def get_deal(deal_id: str, db: Session = Depends(get_db)):
    return _serialise(_get_or_404(db, deal_id), _label_maps(db))


@router.post("/deals", response_model=DealOut, status_code=status.HTTP_201_CREATED)
def create_deal(payload: DealCreate, db: Session = Depends(get_db)):
    deal_id = payload.deal_id or _next_deal_id(db)

    if db.get(Deal, deal_id) is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, f"{deal_id} already exists")

    sent = set(payload.model_dump(exclude_unset=True))
    _check_links(db, payload, sent & set(DEAL_LOOKUPS))

    deal = Deal(deal_id=deal_id)
    _BOOL_DEFAULTS = {
        "order_booked": False,
        "active": True,
    }
    for name in DEAL_SCALARS:
        value = getattr(payload, name)
        if value is None and name in _BOOL_DEFAULTS:
            value = _BOOL_DEFAULTS[name]
        setattr(deal, name, value)

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
    record_audit(db, module="deals", record_id=deal_id, action="created", changed_fields=sorted(sent))
    db.commit()
    db.refresh(deal)
    return _serialise(deal, _label_maps(db))


@router.patch("/deals/{deal_id}", response_model=DealOut)
def patch_deal(deal_id: str, payload: DealUpdate, db: Session = Depends(get_db)):
    """Applies only the fields present in the request body."""
    return _write(db, deal_id, payload, set(payload.model_dump(exclude_unset=True)))


@router.put("/deals/{deal_id}", response_model=DealOut)
def put_deal(deal_id: str, payload: DealUpdate, db: Session = Depends(get_db)):
    """
    Kept for the same reason leads and opportunities have one: the
    prototype's record editor PUTs when it saves. Still applies only what
    was sent.
    """
    return _write(db, deal_id, payload, set(payload.model_dump(exclude_unset=True)))


def _write(db: Session, deal_id: str, payload: DealUpdate, sent: set[str]) -> dict:
    deal = _get_or_404(db, deal_id)
    _check_links(db, payload, sent & set(DEAL_LOOKUPS))

    # A carried value the Deal is not allowed to move. No placement is locked
    # today — D1 and D3 both chose divergence — so this refuses nothing yet.
    # It exists so that turning value_locked on in Administration is the whole
    # change, rather than metadata that claims a rule nothing enforces.
    locked = locked_violations(db, "deals", sent)
    if locked:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            {
                "message": (
                    "These values were carried forward from the parent record "
                    "and are locked against divergence."
                ),
                "fields": sorted(p.api_name for p in locked),
            },
        )

    for name in DEAL_SCALARS:
        if name not in sent:
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
    record_audit(db, module="deals", record_id=deal_id, action="updated", changed_fields=sorted(sent))
    db.commit()
    db.refresh(deal)
    return _serialise(deal, _label_maps(db))


@router.delete("/deals/{deal_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_deal(deal_id: str, db: Session = Depends(get_db)):
    """Hard delete. bid_commitments_register and expansion_use_cases rows
    cascade; nothing else points at a Deal yet."""
    deal = _get_or_404(db, deal_id)
    record_audit(db, module="deals", record_id=deal_id, action="deleted")
    db.delete(deal)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
