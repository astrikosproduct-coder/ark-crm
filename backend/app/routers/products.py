import re

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import Boolean, select
from sqlalchemy.orm import Session

from ..audit import record_audit
from ..auth import current_user, require_catalogue_editor
from ..changes import custom_field_diff, diff, snapshot
from ..custom_fields import apply_write, extras_of, merge_into_row, resolve_write
from ..database import get_db
from ..ids import next_reference_id
from ..list_query import run_list_query
from ..live_register import published
from ..messages import not_found, refusal
from ..models import Product, User
from ..price_books import product_prices
from ..products import MODULE, field_label, guard_dates, guard_sku, pursuits_naming, record_fields, records_naming
from ..register_defaults import apply_defaults
from ..requirements import check_save
from ..schemas import PRODUCT_SCALARS, ActiveFlag, ProductCreate, ProductUpdate
from ..thresholds import check_thresholds

router = APIRouter(tags=["products"])

# extensions.json list_views.products.search.
DEFAULT_SEARCH = ("item_name", "sku_code", "description")

PRODUCT_ID = re.compile(r"^PRD-(\d+)$")

#: Writing the catalogue is an admin's or a developer's — app/auth.py.
EDITOR = [Depends(require_catalogue_editor)]

_COLUMNS = Product.__table__.columns
#: Text a person types that is trimmed on the way in.
_TRIMMED = ("sku_code", "item_name")
#: Columns the table will not store empty. Read off the table, not listed.
_NOT_NULL = tuple(n for n in PRODUCT_SCALARS if not _COLUMNS[n].nullable and _COLUMNS[n].default is None)
#: The Yes / No columns that may be unanswered (NULL).
_OPTIONAL_FLAGS = tuple(n for n in PRODUCT_SCALARS if isinstance(_COLUMNS[n].type, Boolean) and _COLUMNS[n].nullable)


def _serialise(product: Product) -> dict:
    row = {"id": product.product_id, "product_id": product.product_id}
    for name in PRODUCT_SCALARS:
        row[name] = getattr(product, name)
    return merge_into_row(row, product)


def _record(db: Session, product: Product) -> dict:
    """
    One product, with its list price under `prices`: the Standard price book,
    the edition in use, a row per size in the Sizing Guide's order — or one row
    with no size for a product that costs the same at every size. The prices
    themselves are Price Books' (app/price_books.py); nothing here writes one.
    """
    row = _serialise(product)
    row["prices"] = product_prices(db, product)
    return row


def _get_or_404(db: Session, product_id: str) -> Product:
    product = db.get(Product, product_id)
    if product is None:
        raise not_found("product")
    return product


def _next_product_id(db: Session) -> str:
    """
    The register calls product_id an autonumber, so the server allocates it —
    from a stored high-water mark, never max(existing): an id must not be
    reused, or a new product inherits the Leads that named a deleted one. See
    app/ids.py. load_price_book.py draws from the same counter.
    """
    highest = 0
    for existing in db.scalars(select(Product.product_id)):
        match = PRODUCT_ID.match(existing or "")
        if match:
            highest = max(highest, int(match.group(1)))
    return next_reference_id(db, "products", "PRD", 4, highest)


def _apply(product: Product, payload: ProductCreate | ProductUpdate, names) -> None:
    for name in names:
        value = getattr(payload, name)
        if isinstance(value, str) and name in _TRIMMED:
            value = value.strip()
        # active is NOT NULL with a default; an omitted or emptied one stays on.
        if value is None and name == "active":
            value = True
        setattr(product, name, value)


def _require_columns(db: Session, product: Product) -> None:
    """
    SKU Code, Item Name and Catalogue Category can't be stored empty, whatever
    the register says about them — refused as the required fields they are, so
    the form marks each, before the database is asked.
    """
    blank = [n for n in _NOT_NULL if getattr(product, n) in (None, "")]
    if not blank:
        return
    register = published(db)
    sections = {f["api_name"]: f.get("section") for f in (register.fields_of(MODULE) if register else [])}
    count = "this required field" if len(blank) == 1 else f"these {len(blank)} required fields"
    raise HTTPException(
        status.HTTP_422_UNPROCESSABLE_ENTITY,
        refusal(
            "REQUIRED_FIELDS_MISSING",
            "Some required fields are empty.",
            [f"Fill in {count}. Each is marked with a red asterisk."],
            fields=[{"api_name": n, "label": field_label(db, n), "section": sections.get(n)} for n in blank],
        ),
    )


@router.get("/products")
def list_products(request: Request, response: Response, db: Session = Depends(get_db)):
    """
    The catalogue, with the list contract every live module serves
    (app/list_query.py). Read by the Products list and by every product picker
    on a Lead or a Deal, which filter it by the field's own rule.
    """
    rows = [_serialise(p) for p in db.scalars(select(Product).order_by(Product.product_id))]
    rows, total = run_list_query(rows, request.query_params, lookups=(), default_search=DEFAULT_SEARCH)
    response.headers["X-Total-Count"] = str(total)
    return rows


@router.get("/products/{product_id}")
def get_product(product_id: str, db: Session = Depends(get_db)):
    """One item, with its list price at each deployment size under `prices`."""
    return _record(db, _get_or_404(db, product_id))


@router.get("/products/{product_id}/pursuits")
def get_product_pursuits(product_id: str, db: Session = Depends(get_db)):
    """
    The Leads, Opportunities and Deals naming this product, with the Open
    pipeline and Won they add up to — see app/products.py::pursuits_naming.
    """
    _get_or_404(db, product_id)
    return pursuits_naming(db, product_id)


@router.post("/products", status_code=status.HTTP_201_CREATED, dependencies=EDITOR)
def create_product(
    payload: ProductCreate,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    """
    A new product (phase 2, 13 Oct 2026). It has no list price yet: prices are
    set in Price Books, where it appears at once as a row with nothing in it.

    Also what an import row goes through (app/routers/spreadsheets.py), so a
    sheet and the form are held to the same rules.
    """
    check_thresholds(db, MODULE, payload.model_dump())
    only = record_fields(db)

    product = Product(product_id=_next_product_id(db))
    _apply(product, payload, PRODUCT_SCALARS)
    # A box a person left unticked on a new product is "No". (The first load
    # from the price book left these unanswered instead — it stated none.)
    for name in _OPTIONAL_FLAGS:
        if getattr(product, name) is None:
            setattr(product, name, False)
    _require_columns(db, product)
    guard_sku(db, product)
    guard_dates(db, product)
    db.add(product)
    db.flush()

    # Segment, Segment Category, Subsegment and anything else made in Setup:
    # custom_fields, never a column. Unknown keys are not stored.
    apply_write(product, resolve_write(db, MODULE, explicit=payload.custom_fields, extras=extras_of(payload)))
    apply_defaults(db, MODULE, product, only)

    record_audit(
        db,
        module=MODULE,
        record_id=product.product_id,
        action="created",
        actor=user.user_id,
        changed_fields=sorted(payload.model_dump(exclude_unset=True)),
    )

    # Every required field of a PRODUCT filled, and each dependent choice one
    # its parent offers, or 422 — app/requirements.py.
    check_save(db, MODULE, product, record_id=product.product_id, creating=False, only=only)
    db.commit()
    db.refresh(product)
    return _record(db, product)


@router.patch("/products/{product_id}", dependencies=EDITOR)
def patch_product(
    product_id: str,
    payload: ProductUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    """Applies only the fields present in the request body."""
    return _write(db, product_id, payload, user)


@router.put("/products/{product_id}", dependencies=EDITOR)
def put_product(
    product_id: str,
    payload: ProductUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    """
    What the record editor sends. Still applies only what was sent — the form
    PUTs what it rendered, it does not assert every absent field is now empty.
    """
    return _write(db, product_id, payload, user)


def _write(db: Session, product_id: str, payload: ProductUpdate, user: User) -> dict:
    product = _get_or_404(db, product_id)
    sent = set(payload.model_dump(exclude_unset=True))

    tracked = [name for name in PRODUCT_SCALARS if name in sent]
    before = snapshot(product, tracked)
    before_custom = dict(product.custom_fields or {})

    check_thresholds(db, MODULE, payload.model_dump(include=sent))
    _apply(product, payload, tracked)
    _require_columns(db, product)
    if "sku_code" in sent:
        guard_sku(db, product)
    if sent & {"effective_from", "effective_to"}:
        guard_dates(db, product)

    apply_write(product, resolve_write(db, MODULE, explicit=payload.custom_fields, extras=extras_of(payload)))

    changed = diff(before, snapshot(product, tracked))
    changed += custom_field_diff(before_custom, product.custom_fields)
    record_audit(
        db,
        module=MODULE,
        record_id=product_id,
        action="updated",
        actor=user.user_id,
        changed_fields=sorted(sent),
        changed=changed,
    )

    check_save(db, MODULE, product, record_id=product_id, creating=False, only=record_fields(db))
    db.commit()
    db.refresh(product)
    return _record(db, product)


@router.patch("/products/{product_id}/active", dependencies=EDITOR)
def set_product_active(
    product_id: str,
    payload: ActiveFlag,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    """
    Stop selling a product, or sell it again. The safe way to retire one: it
    keeps its id, so every Lead naming it still shows its name, and it stops
    being offered in new picks (app/products.py::check_picks).
    """
    product = _get_or_404(db, product_id)
    was_active = product.active
    product.active = payload.active
    record_audit(
        db,
        module=MODULE,
        record_id=product_id,
        action="updated",
        actor=user.user_id,
        changed_fields=["active"],
        changed=diff({"active": was_active}, {"active": product.active}),
    )
    db.commit()
    db.refresh(product)
    return _record(db, product)


@router.delete("/products/{product_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=EDITOR)
def delete_product(
    product_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    """
    Delete for good — the product and its list prices — allowed ONLY when no
    Lead or Deal names it. One that is named is refused with 409 and the way
    out: deactivate it, or take it off those records first.

    The pick columns have no foreign key (app/products.py), so this check is
    the only thing between a delete and a Lead showing a bare product number.
    The delete dialog lists the same records first; this is the check that
    holds.
    """
    product = _get_or_404(db, product_id)
    holders = records_naming(db, product_id)
    if holders:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            refusal(
                "PRODUCT_IN_USE",
                f"This product is named on {len(holders)} "
                f"{'record' if len(holders) == 1 else 'records'}, so it can't be deleted.",
                ["Deactivate it instead.", "Or take it off those records first."],
                records=holders,
            ),
        )
    record_audit(db, module=MODULE, record_id=product_id, action="deleted", actor=user.user_id)
    db.delete(product)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
