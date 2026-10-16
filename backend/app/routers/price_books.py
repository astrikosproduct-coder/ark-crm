"""
/api/price-books, /api/price-book-editions, /api/sizes — Products phase 3.

    price books   the Standard book and the regional ones (app/price_books.py)
    …/prices      one book's price of every product, in one edition: read as a
                  grid, written a handful of cells at a time
    editions      the price list as it stood: Draft, Current, Retired
    sizes         CPQ's Sizing Guide — the deployment sizes a price is set at

Anyone with a role reads. Every write is an admin's or a developer's
(app/auth.py::require_catalogue_editor), the same line Products drew: a price
is not a salesperson's edit.

Each record is saved the way an Account is — typed columns from its *_SCALARS,
Setup-made fields into custom_fields, the register's required fields checked,
one audit entry — so a field added to any of the three modules in Setup is
stored and demanded with no change here.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import price_books as rules
from ..audit import record_audit
from ..auth import current_user, require_catalogue_editor
from ..changes import custom_field_diff, diff, snapshot
from ..custom_fields import apply_write, extras_of, merge_into_row, resolve_write
from ..database import get_db
from ..list_query import run_list_query
from ..live_register import published
from ..messages import not_found, refusal
from ..models import DeploymentSize, PriceBook, PriceBookEdition, User
from ..register_defaults import apply_defaults
from ..requirements import check_save
from ..schemas import (
    EDITION_SCALARS,
    PRICE_BOOK_SCALARS,
    SIZE_SCALARS,
    ActiveFlag,
    EditionWrite,
    PriceBookWrite,
    PriceCells,
    SizeWrite,
)
from ..thresholds import check_thresholds

router = APIRouter(tags=["price books"])

EDITOR = [Depends(require_catalogue_editor)]


# ------------------------------------------------------------------ shared


def _plain(value: Any) -> Any:
    """Numeric comes back as Decimal, which is not JSON-serialisable."""
    return float(value) if isinstance(value, Decimal) else value


def _require(db: Session, module: str, record: Any, names: tuple[str, ...]) -> None:
    """The columns the table won't store empty, refused as the required fields they are."""
    blank = [n for n in names if getattr(record, n) in (None, "")]
    if not blank:
        return
    register = published(db)
    sections = {f["api_name"]: f.get("section") for f in (register.fields_of(module) if register else [])}
    count = "this required field" if len(blank) == 1 else f"these {len(blank)} required fields"
    raise HTTPException(
        status.HTTP_422_UNPROCESSABLE_ENTITY,
        refusal(
            "REQUIRED_FIELDS_MISSING",
            "Some required fields are empty.",
            [f"Fill in {count}. Each is marked with a red asterisk."],
            fields=[{"api_name": n, "label": rules.label_of(db, module, n), "section": sections.get(n)} for n in blank],
        ),
    )


def _apply(record: Any, payload: Any, names) -> None:
    for name in names:
        value = getattr(payload, name)
        if isinstance(value, str):
            value = value.strip()
        # `active` is NOT NULL with a default; an omitted or emptied one stays on.
        if value is None and name == "active":
            value = True
        setattr(record, name, value)


def _finish(
    db: Session,
    module: str,
    record: Any,
    record_id: str,
    payload: Any,
    user: User,
    *,
    action: str,
    scalars: tuple[str, ...],
    before: dict | None = None,
    before_custom: dict | None = None,
) -> None:
    """Custom fields, the audit entry, the required-field check, the commit."""
    apply_write(record, resolve_write(db, module, explicit=payload.custom_fields, extras=extras_of(payload)))
    sent = sorted(payload.model_dump(exclude_unset=True))
    if action == "created":
        apply_defaults(db, module, record)
        record_audit(db, module=module, record_id=record_id, action=action, actor=user.user_id, changed_fields=sent)
    else:
        tracked = [n for n in scalars if n in before]
        changed = diff(before, snapshot(record, tracked)) + custom_field_diff(before_custom, record.custom_fields)
        record_audit(
            db, module=module, record_id=record_id, action=action, actor=user.user_id, changed_fields=sent, changed=changed
        )
    check_save(db, module, record, record_id=record_id, creating=False)
    db.commit()
    db.refresh(record)


# ------------------------------------------------------------------ price books

BOOK_SEARCH = ("price_book_name", "currency")


def _book(book: PriceBook) -> dict:
    row = {"id": book.price_book_id, "price_book_id": book.price_book_id, "is_standard": book.is_standard}
    for name in PRICE_BOOK_SCALARS:
        row[name] = _plain(getattr(book, name))
    # The register's formula for this field, Region Pricing % x FX Rate.
    row["effective_multiplier"] = float(rules.multiplier(book))
    return merge_into_row(row, book)


def _book_or_404(db: Session, book_id: str) -> PriceBook:
    book = db.get(PriceBook, book_id)
    if book is None:
        raise not_found("price book")
    return book


@router.get("/price-books")
def list_price_books(request: Request, response: Response, db: Session = Depends(get_db)):
    """Every price book, the Standard one first."""
    books = sorted(db.scalars(select(PriceBook)), key=lambda b: (not b.is_standard, b.price_book_id))
    rows, total = run_list_query([_book(b) for b in books], request.query_params, lookups=(), default_search=BOOK_SEARCH)
    response.headers["X-Total-Count"] = str(total)
    return rows


@router.get("/price-books/{book_id}")
def get_price_book(book_id: str, db: Session = Depends(get_db)):
    return _book(_book_or_404(db, book_id))


@router.post("/price-books", status_code=status.HTTP_201_CREATED, dependencies=EDITOR)
def create_price_book(payload: PriceBookWrite, db: Session = Depends(get_db), user: User = Depends(current_user)):
    """
    A new regional price book. (The very first book made is the Standard one.)
    It prices every product at once: the Standard price x its Region Pricing %
    x its FX Rate, until it is given a price of its own for a product.
    """
    check_thresholds(db, rules.MODULE, payload.model_dump())
    book = PriceBook(price_book_id=rules.next_book_id(db))
    _apply(book, payload, PRICE_BOOK_SCALARS)
    _require(db, rules.MODULE, book, ("price_book_name",))
    rules.guard_book_name(db, book)
    rules.settle_standard(db, book, creating=True)
    db.add(book)
    db.flush()
    _finish(db, rules.MODULE, book, book.price_book_id, payload, user, action="created", scalars=PRICE_BOOK_SCALARS)
    return _book(book)


def _write_book(db: Session, book_id: str, payload: PriceBookWrite, user: User) -> dict:
    book = _book_or_404(db, book_id)
    sent = set(payload.model_dump(exclude_unset=True))
    tracked = [n for n in PRICE_BOOK_SCALARS if n in sent]
    before, before_custom = snapshot(book, tracked), dict(book.custom_fields or {})
    check_thresholds(db, rules.MODULE, payload.model_dump(include=sent))
    _apply(book, payload, tracked)
    _require(db, rules.MODULE, book, ("price_book_name",))
    if "price_book_name" in sent:
        rules.guard_book_name(db, book)
    rules.settle_standard(db, book, creating=False)
    _finish(
        db, rules.MODULE, book, book_id, payload, user,
        action="updated", scalars=PRICE_BOOK_SCALARS, before=before, before_custom=before_custom,
    )
    return _book(book)


@router.patch("/price-books/{book_id}", dependencies=EDITOR)
def patch_price_book(book_id: str, payload: PriceBookWrite, db: Session = Depends(get_db), user: User = Depends(current_user)):
    """Applies only the fields present in the request body."""
    return _write_book(db, book_id, payload, user)


@router.put("/price-books/{book_id}", dependencies=EDITOR)
def put_price_book(book_id: str, payload: PriceBookWrite, db: Session = Depends(get_db), user: User = Depends(current_user)):
    """What the record editor sends. Still applies only what was sent."""
    return _write_book(db, book_id, payload, user)


@router.patch("/price-books/{book_id}/active", dependencies=EDITOR)
def set_price_book_active(book_id: str, payload: ActiveFlag, db: Session = Depends(get_db), user: User = Depends(current_user)):
    """Stop offering a regional book, or offer it again. Its prices stay."""
    book = _book_or_404(db, book_id)
    was = book.active
    book.active = payload.active
    rules.settle_standard(db, book, creating=False)
    record_audit(
        db, module=rules.MODULE, record_id=book_id, action="updated", actor=user.user_id,
        changed_fields=["active"], changed=diff({"active": was}, {"active": book.active}),
    )
    db.commit()
    db.refresh(book)
    return _book(book)


@router.delete("/price-books/{book_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=EDITOR)
def delete_price_book(book_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    """
    Delete a regional book and the prices of its own, for good. Its worked-out
    prices were never stored, so nothing else goes. The Standard book is never
    deleted: every other book is worked out from it.
    """
    book = _book_or_404(db, book_id)
    if book.is_standard:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            refusal(
                "STANDARD_BOOK_FIXED",
                "The Standard price book can't be deleted.",
                ["Every other book is worked out from it."],
            ),
        )
    record_audit(db, module=rules.MODULE, record_id=book_id, action="deleted", actor=user.user_id)
    db.delete(book)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ------------------------------------------------------------------ prices


def _edition_for(db: Session, edition_id: str | None) -> PriceBookEdition:
    if edition_id:
        return _edition_or_404(db, edition_id)
    edition = rules.current_edition(db)
    if edition is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            refusal("NO_EDITION", "There is no price list in use yet.", ["Start an edition, enter its prices, then make it current."]),
        )
    return edition


@router.get("/price-books/{book_id}/prices")
def get_prices(book_id: str, edition: str | None = None, db: Session = Depends(get_db)):
    """
    Every product's price in this book — in the edition named, else the one in
    use. A regional book's prices are worked out here, from the Standard book's.
    """
    return rules.matrix(db, _book_or_404(db, book_id), _edition_for(db, edition))


@router.put("/price-books/{book_id}/prices", dependencies=EDITOR)
def put_prices(book_id: str, payload: PriceCells, db: Session = Depends(get_db), user: User = Depends(current_user)):
    """
    Set or take away prices in one book and one edition — all of the cells
    sent, or none. A Draft edition takes any change; the edition in use takes
    only a first price for a product that has none (app/price_books.py).
    """
    book = _book_or_404(db, book_id)
    edition = _edition_or_404(db, payload.edition)
    moved = rules.save_cells(db, book, edition, [cell.model_dump() for cell in payload.cells])
    if moved:
        record_audit(
            db, module=rules.MODULE, record_id=book_id, action="updated", actor=user.user_id,
            changed_fields=["prices"], changed=moved,
        )
    db.commit()
    return rules.matrix(db, book, edition)


# ------------------------------------------------------------------ editions

EDITION_SEARCH = ("price_book_version", "notes")
_STATUS_ORDER = {rules.CURRENT: 0, rules.DRAFT: 1, rules.RETIRED: 2}


def _edition(edition: PriceBookEdition) -> dict:
    row = {"id": edition.edition_id, "edition_id": edition.edition_id}
    for name in EDITION_SCALARS:
        row[name] = getattr(edition, name)
    row["status"] = edition.status
    row["effective_to"] = edition.effective_to
    return merge_into_row(row, edition)


def _edition_or_404(db: Session, edition_id: str) -> PriceBookEdition:
    edition = db.get(PriceBookEdition, edition_id)
    if edition is None:
        raise not_found("edition")
    return edition


@router.get("/price-book-editions")
def list_editions(request: Request, response: Response, db: Session = Depends(get_db)):
    """Every edition: the one in use first, then the drafts, then past ones, newest first."""
    editions = sorted(
        db.scalars(select(PriceBookEdition)),
        key=lambda e: (_STATUS_ORDER.get(e.status, 9), -int(e.edition_id.rpartition("-")[2] or 0)),
    )
    rows, total = run_list_query([_edition(e) for e in editions], request.query_params, lookups=(), default_search=EDITION_SEARCH)
    response.headers["X-Total-Count"] = str(total)
    return rows


@router.get("/price-book-editions/{edition_id}")
def get_edition(edition_id: str, db: Session = Depends(get_db)):
    return _edition(_edition_or_404(db, edition_id))


@router.post("/price-book-editions", status_code=status.HTTP_201_CREATED, dependencies=EDITOR)
def create_edition(payload: EditionWrite, db: Session = Depends(get_db), user: User = Depends(current_user)):
    """
    Start a new edition: a DRAFT holding a copy of every price of the edition
    in use (or of `copy_from`), in every book. Nothing is sold from it until it
    is made current.
    """
    source = _edition_or_404(db, payload.copy_from) if payload.copy_from else rules.current_edition(db)
    edition = PriceBookEdition(edition_id=rules.next_edition_id(db), status=rules.DRAFT)
    _apply(edition, payload, EDITION_SCALARS)
    _require(db, rules.EDITIONS_MODULE, edition, ("price_book_version",))
    rules.guard_edition_name(db, edition)
    db.add(edition)
    db.flush()
    if source is not None:
        rules.copy_prices(db, source, edition)
    _finish(db, rules.EDITIONS_MODULE, edition, edition.edition_id, payload, user, action="created", scalars=EDITION_SCALARS)
    return _edition(edition)


def _write_edition(db: Session, edition_id: str, payload: EditionWrite, user: User) -> dict:
    edition = _edition_or_404(db, edition_id)
    sent = set(payload.model_dump(exclude_unset=True))
    tracked = [n for n in EDITION_SCALARS if n in sent]
    before, before_custom = snapshot(edition, tracked), dict(edition.custom_fields or {})
    # The day an edition came into use is a fact once it has: only a draft's
    # planned start can still move.
    if edition.status != rules.DRAFT and "effective_from" in sent and payload.effective_from != edition.effective_from:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            refusal(
                "EDITION_LOCKED",
                f"{edition.price_book_version} has been in use, so the day it started can't be changed.",
                ["Its name and notes can still be edited."],
            ),
        )
    _apply(edition, payload, tracked)
    _require(db, rules.EDITIONS_MODULE, edition, ("price_book_version",))
    if "price_book_version" in sent:
        rules.guard_edition_name(db, edition)
    _finish(
        db, rules.EDITIONS_MODULE, edition, edition_id, payload, user,
        action="updated", scalars=EDITION_SCALARS, before=before, before_custom=before_custom,
    )
    return _edition(edition)


@router.patch("/price-book-editions/{edition_id}", dependencies=EDITOR)
def patch_edition(edition_id: str, payload: EditionWrite, db: Session = Depends(get_db), user: User = Depends(current_user)):
    return _write_edition(db, edition_id, payload, user)


@router.put("/price-book-editions/{edition_id}", dependencies=EDITOR)
def put_edition(edition_id: str, payload: EditionWrite, db: Session = Depends(get_db), user: User = Depends(current_user)):
    return _write_edition(db, edition_id, payload, user)


@router.post("/price-book-editions/{edition_id}/make-current", dependencies=EDITOR)
def make_edition_current(edition_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    """
    Sell from this edition from now on. The edition that was in use is retired
    today, and neither can be edited afterwards — which is the point.
    """
    edition = _edition_or_404(db, edition_id)
    previous = rules.make_current(db, edition)
    record_audit(
        db, module=rules.EDITIONS_MODULE, record_id=edition_id, action="updated", actor=user.user_id,
        changed_fields=["status"], changed=[{"field": "status", "from": rules.DRAFT, "to": rules.CURRENT}],
    )
    if previous is not None:
        record_audit(
            db, module=rules.EDITIONS_MODULE, record_id=previous.edition_id, action="updated", actor=user.user_id,
            changed_fields=["status"], changed=[{"field": "status", "from": rules.CURRENT, "to": rules.RETIRED}],
        )
    db.commit()
    db.refresh(edition)
    return _edition(edition)


@router.delete("/price-book-editions/{edition_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=EDITOR)
def delete_edition(edition_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    """A draft, and its prices, deleted for good. An edition that has been in use is kept."""
    edition = _edition_or_404(db, edition_id)
    if edition.status != rules.DRAFT:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            refusal(
                "EDITION_IN_USE",
                "Only a draft edition can be deleted.",
                ["An edition that has been in use is kept, so what was priced on it can still be read."],
            ),
        )
    record_audit(db, module=rules.EDITIONS_MODULE, record_id=edition_id, action="deleted", actor=user.user_id)
    db.delete(edition)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ------------------------------------------------------------------ sizes

SIZE_SEARCH = ("size_code", "typical_deployment", "managed_assets_cap")


def _size(size: DeploymentSize) -> dict:
    row = {"id": size.size_id, "size_id": size.size_id}
    for name in SIZE_SCALARS:
        row[name] = getattr(size, name)
    return merge_into_row(row, size)


def _size_or_404(db: Session, size_id: str) -> DeploymentSize:
    size = db.get(DeploymentSize, size_id)
    if size is None:
        raise not_found("size")
    return size


@router.get("/sizes")
def list_sizes(request: Request, response: Response, db: Session = Depends(get_db)):
    """The Sizing Guide, smallest first — its own Sort Order, not the alphabet's."""
    rows = [_size(s) for s in rules.sizes_in_order(db)]
    rows, total = run_list_query(rows, request.query_params, lookups=(), default_search=SIZE_SEARCH)
    response.headers["X-Total-Count"] = str(total)
    return rows


@router.get("/sizes/{size_id}")
def get_size(size_id: str, db: Session = Depends(get_db)):
    return _size(_size_or_404(db, size_id))


@router.post("/sizes", status_code=status.HTTP_201_CREATED, dependencies=EDITOR)
def create_size(payload: SizeWrite, db: Session = Depends(get_db), user: User = Depends(current_user)):
    """A new deployment size. It becomes a column of every price book at once."""
    check_thresholds(db, rules.SIZES_MODULE, payload.model_dump())
    size = DeploymentSize(size_id=rules.next_size_id(db))
    _apply(size, payload, SIZE_SCALARS)
    _require(db, rules.SIZES_MODULE, size, ("size_code",))
    rules.guard_size_code(db, size)
    db.add(size)
    db.flush()
    _finish(db, rules.SIZES_MODULE, size, size.size_id, payload, user, action="created", scalars=SIZE_SCALARS)
    return _size(size)


def _write_size(db: Session, size_id: str, payload: SizeWrite, user: User) -> dict:
    size = _size_or_404(db, size_id)
    sent = set(payload.model_dump(exclude_unset=True))
    tracked = [n for n in SIZE_SCALARS if n in sent]
    before, before_custom = snapshot(size, tracked), dict(size.custom_fields or {})
    check_thresholds(db, rules.SIZES_MODULE, payload.model_dump(include=sent))
    _apply(size, payload, tracked)
    _require(db, rules.SIZES_MODULE, size, ("size_code",))
    if "size_code" in sent:
        rules.guard_size_code(db, size)
    _finish(
        db, rules.SIZES_MODULE, size, size_id, payload, user,
        action="updated", scalars=SIZE_SCALARS, before=before, before_custom=before_custom,
    )
    return _size(size)


@router.patch("/sizes/{size_id}", dependencies=EDITOR)
def patch_size(size_id: str, payload: SizeWrite, db: Session = Depends(get_db), user: User = Depends(current_user)):
    return _write_size(db, size_id, payload, user)


@router.put("/sizes/{size_id}", dependencies=EDITOR)
def put_size(size_id: str, payload: SizeWrite, db: Session = Depends(get_db), user: User = Depends(current_user)):
    return _write_size(db, size_id, payload, user)


@router.patch("/sizes/{size_id}/active", dependencies=EDITOR)
def set_size_active(size_id: str, payload: ActiveFlag, db: Session = Depends(get_db), user: User = Depends(current_user)):
    """
    Stop pricing at a size, or price at it again. A size that already has
    prices keeps its column in the editions holding them.
    """
    size = _size_or_404(db, size_id)
    was = size.active
    size.active = payload.active
    record_audit(
        db, module=rules.SIZES_MODULE, record_id=size_id, action="updated", actor=user.user_id,
        changed_fields=["active"], changed=diff({"active": was}, {"active": size.active}),
    )
    db.commit()
    db.refresh(size)
    return _size(size)


@router.delete("/sizes/{size_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=EDITOR)
def delete_size(size_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    """Delete a size no price was ever set at. One with prices is deactivated instead."""
    size = _size_or_404(db, size_id)
    held = rules.prices_at_size(db, size_id)
    if held:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            refusal(
                "SIZE_IN_USE",
                f"{held} {'price is' if held == 1 else 'prices are'} set at this size, so it can't be deleted.",
                ["Deactivate it instead."],
            ),
        )
    record_audit(db, module=rules.SIZES_MODULE, record_id=size_id, action="deleted", actor=user.user_id)
    db.delete(size)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
