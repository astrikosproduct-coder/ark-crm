"""
Price Books: what a product costs, in which book, in which edition.

Products phase 3 (13 Oct 2026). Zoho's Products -> Price Books, with three
things ARK needs that Zoho's do not have.

ONE STANDARD BOOK, AND REGIONAL BOOKS WORKED OUT FROM IT
    The Standard book (USA USD) is the master: its prices are entered. A
    regional book carries a Region Pricing % and an FX rate, and its price is

        Standard price x Region Pricing % x FX Rate

    worked out when it is read, never stored — change the FX rate and every
    price in that book follows. A regional book may hold a price OF ITS OWN for
    a product (an override, in its own currency), which then replaces the
    worked-out one. Taking the override away brings the worked-out price back.

A PRICE HAS ONE OF THREE SHAPES, READ OFF THE PRODUCT'S PRICING BASIS
    by size     one price per deployment size       modules, suites, add-ons
    single      one price, whatever the size        user packs, a day rate
    percent     a share of the licence value        support
    The two Pricing Basis choices that decide this (By T-shirt size, % of
    licence) are system values of their list: renamable in Setup, never
    retired. Nothing here names a product, a category or a size.

    A percentage is the same in every book — a share of the licence is not a
    currency amount — so it lives in the Standard book only.

EDITIONS: A QUOTE MUST BE ABLE TO KEEP THE PRICE IT WAS ISSUED AT
    Draft     edited freely.
    Current   what is sold from; one at a time. A price may be ADDED where a
              product has none (a product made after the edition was), but one
              that is there can't be changed or removed.
    Retired   never changed.
    To change a price: start a new edition (a Draft copy of the Current one),
    change it there, make it Current. The old one is Retired with the day it
    stopped. An edition covers every book.

    What an edition does NOT freeze is a regional book's FX rate, which is the
    book's and moves when it moves. A quote stamps the rate it used (phase 5).

SIZES ARE RECORDS (CPQ's Sizing Guide), not a dropdown: a price names its size
by id, and a size with prices can't be deleted — deactivate it.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .clock import now_utc
from .ids import next_reference_id
from .live_register import published
from .messages import refusal
from .models import DeploymentSize, PriceBook, PriceBookEdition, PriceBookEntry, Product

MODULE = "price_books"
EDITIONS_MODULE = "price_book_editions"
SIZES_MODULE = "deployment_sizes"
PRODUCTS_MODULE = "products"

DRAFT, CURRENT, RETIRED = "DRAFT", "CURRENT", "RETIRED"

#: Pricing Basis choices the server reads by key (picklist_values.is_system).
BY_SIZE = "BY_T_SHIRT_SIZE"
PERCENT = "PCT_OF_LICENCE"

SIZED, SINGLE, SHARE = "sized", "single", "percent"

CENT = Decimal("0.01")
PCT_STEP = Decimal("0.000001")


def _refuse(code: str, message: str, details: list[str] | None = None, *, http: int = 422, **extra: Any) -> HTTPException:
    return HTTPException(http, refusal(code, message, details, **extra))


def _same(a: Any, b: Any) -> bool:
    return str(a or "").strip().lower() == str(b or "").strip().lower()


def label_of(db: Session, module: str, api_name: str) -> str:
    register = published(db)
    for f in register.fields_of(module) if register else []:
        if f["api_name"] == api_name:
            return f.get("label") or api_name
    return api_name.replace("_", " ").title()


# ------------------------------------------------------------------ ids


def _next_id(db: Session, model, column: str, name: str, prefix: str) -> str:
    """The next never-used id — a stored high-water mark, as app/ids.py explains."""
    highest = 0
    for existing in db.scalars(select(getattr(model, column))):
        tail = str(existing or "").rpartition("-")[2]
        if tail.isdigit():
            highest = max(highest, int(tail))
    return next_reference_id(db, name, prefix, 4, highest)


def next_book_id(db: Session) -> str:
    return _next_id(db, PriceBook, "price_book_id", MODULE, "PB")


def next_edition_id(db: Session) -> str:
    return _next_id(db, PriceBookEdition, "edition_id", EDITIONS_MODULE, "PBE")


def next_size_id(db: Session) -> str:
    return _next_id(db, DeploymentSize, "size_id", SIZES_MODULE, "SZ")


# ------------------------------------------------------------------ books


def standard_book(db: Session) -> PriceBook | None:
    return db.scalar(select(PriceBook).where(PriceBook.is_standard.is_(True)))


def multiplier(book: PriceBook) -> Decimal:
    """Region Pricing % x FX Rate — what a Standard price is multiplied by in this book."""
    pct = book.region_pricing_pct if book.region_pricing_pct is not None else Decimal(1)
    fx = book.fx_rate_local_per_usd if book.fx_rate_local_per_usd is not None else Decimal(1)
    return Decimal(pct) * Decimal(fx)


def worked_out(standard_price: Decimal | None, book: PriceBook) -> Decimal | None:
    """A regional book's price for a Standard price, to the cent."""
    if standard_price is None:
        return None
    return (Decimal(standard_price) * multiplier(book)).quantize(CENT, rounding=ROUND_HALF_UP)


def guard_book_name(db: Session, book: PriceBook) -> None:
    """One book per name, however it is capitalised (409 PRICE_BOOK_EXISTS)."""
    for other in db.scalars(select(PriceBook).where(PriceBook.price_book_id != book.price_book_id)):
        if _same(other.price_book_name, book.price_book_name):
            label = label_of(db, MODULE, "price_book_name")
            raise _refuse(
                "PRICE_BOOK_EXISTS",
                f"There is already a price book called {other.price_book_name}.",
                [f"Give this one a {label} of its own, then save."],
                http=status.HTTP_409_CONFLICT,
                price_book=other.price_book_id,
                fields=[{"api_name": "price_book_name", "label": label}],
            )


def settle_standard(db: Session, book: PriceBook, *, creating: bool) -> None:
    """
    Keep the Standard book the master. The first book ever made IS the Standard
    one; after that a new book is regional. The Standard book prices at 100%
    with no exchange — its prices are the ones every other book multiplies — so
    a save that says otherwise is refused, not quietly corrected.
    """
    if creating:
        book.is_standard = standard_book(db) is None
    if not book.is_standard:
        return
    one = Decimal(1)
    pct = book.region_pricing_pct
    fx = book.fx_rate_local_per_usd
    if (pct is not None and Decimal(pct) != one) or (fx is not None and Decimal(fx) != one):
        raise _refuse(
            "STANDARD_BOOK_FIXED",
            "The Standard price book is the one every other book is worked out from.",
            [
                f"Its {label_of(db, MODULE, 'region_pricing_pct')} stays 100% and its "
                f"{label_of(db, MODULE, 'fx_rate_local_per_usd')} stays 1.",
                "To price a region differently, change that region's price book.",
            ],
        )
    book.region_pricing_pct, book.fx_rate_local_per_usd = one, one
    if not book.active:
        raise _refuse(
            "STANDARD_BOOK_FIXED",
            "The Standard price book can't be deactivated.",
            ["Every other book is worked out from it."],
        )


# ------------------------------------------------------------------ editions


def current_edition(db: Session) -> PriceBookEdition | None:
    return db.scalar(select(PriceBookEdition).where(PriceBookEdition.status == CURRENT))


def guard_edition_name(db: Session, edition: PriceBookEdition) -> None:
    for other in db.scalars(select(PriceBookEdition).where(PriceBookEdition.edition_id != edition.edition_id)):
        if _same(other.price_book_version, edition.price_book_version):
            label = label_of(db, EDITIONS_MODULE, "price_book_version")
            raise _refuse(
                "EDITION_EXISTS",
                f"There is already an edition called {other.price_book_version}.",
                [f"Give this one a {label} of its own, then save."],
                http=status.HTTP_409_CONFLICT,
                edition=other.edition_id,
                fields=[{"api_name": "price_book_version", "label": label}],
            )


def copy_prices(db: Session, source: PriceBookEdition, target: PriceBookEdition) -> int:
    """Every price of `source`, in every book, into `target`. Returns how many."""
    rows = list(db.scalars(select(PriceBookEntry).where(PriceBookEntry.edition_id == source.edition_id)))
    for row in rows:
        db.add(
            PriceBookEntry(
                price_book_id=row.price_book_id,
                edition_id=target.edition_id,
                product_id=row.product_id,
                size_id=row.size_id,
                list_price=row.list_price,
                pct_of_annual_licence=row.pct_of_annual_licence,
            )
        )
    db.flush()
    return len(rows)


def make_current(db: Session, edition: PriceBookEdition) -> PriceBookEdition | None:
    """
    Draft -> Current, and the edition that was Current -> Retired, on the same
    day. Returns the retired one. Refused for an edition with no Standard
    price: selling from an empty price list is a mistake, not a decision.
    """
    if edition.status != DRAFT:
        raise _refuse(
            "EDITION_NOT_DRAFT",
            "Only a draft edition can be made current.",
            ["Start a new edition to change prices."],
        )
    book = standard_book(db)
    held = db.scalar(
        select(func.count())
        .select_from(PriceBookEntry)
        .where(PriceBookEntry.edition_id == edition.edition_id)
        .where(PriceBookEntry.price_book_id == (book.price_book_id if book else ""))
    )
    if not held:
        raise _refuse(
            "EDITION_EMPTY",
            "This edition has no prices yet.",
            ["Enter its prices in the Standard price book, then make it current."],
        )
    today = now_utc().date()
    previous = current_edition(db)
    if previous is not None:
        previous.status = RETIRED
        previous.effective_to = today
        db.flush()  # one Current at a time is a unique index: retire first
    edition.status = CURRENT
    edition.effective_from = edition.effective_from or today
    edition.effective_to = None
    edition.made_current_at = now_utc()
    db.flush()
    return previous


# ------------------------------------------------------------------ sizes


def sizes_in_order(db: Session) -> list[DeploymentSize]:
    rows = list(db.scalars(select(DeploymentSize)))
    return sorted(rows, key=lambda s: (s.sort_order if s.sort_order is not None else 10**6, s.size_code.lower()))


def guard_size_code(db: Session, size: DeploymentSize) -> None:
    for other in db.scalars(select(DeploymentSize).where(DeploymentSize.size_id != size.size_id)):
        if _same(other.size_code, size.size_code):
            label = label_of(db, SIZES_MODULE, "size_code")
            raise _refuse(
                "SIZE_EXISTS",
                f"There is already a size called {other.size_code}.",
                [f"Give this one a {label} of its own, then save."],
                http=status.HTTP_409_CONFLICT,
                size=other.size_id,
                fields=[{"api_name": "size_code", "label": label}],
            )


def prices_at_size(db: Session, size_id: str) -> int:
    return db.scalar(select(func.count()).select_from(PriceBookEntry).where(PriceBookEntry.size_id == size_id)) or 0


# ------------------------------------------------------------------ prices


def shape_of(product: Product) -> str:
    """How this product is priced — read off its Pricing Basis."""
    if product.pricing_basis == BY_SIZE:
        return SIZED
    if product.pricing_basis == PERCENT:
        return SHARE
    return SINGLE


def _number(value: Decimal | None) -> float | None:
    return float(value) if value is not None else None


def _category_order(db: Session) -> dict[str, int]:
    """Catalogue Category's choices in the register's order, for grouping the grid."""
    register = published(db)
    if register is None:
        return {}
    field = next((f for f in register.fields_of(PRODUCTS_MODULE) if f["api_name"] == "catalogue_category"), None)
    values = register.picklists.get((field or {}).get("picklist") or "", [])
    return {str(v["key"]): index for index, v in enumerate(values)}


def _entries(db: Session, edition_id: str, book_ids: list[str]) -> dict[tuple[str, str, str | None], PriceBookEntry]:
    rows = db.scalars(
        select(PriceBookEntry)
        .where(PriceBookEntry.edition_id == edition_id)
        .where(PriceBookEntry.price_book_id.in_(book_ids))
    )
    return {(r.price_book_id, r.product_id, r.size_id): r for r in rows}


def matrix(db: Session, book: PriceBook, edition: PriceBookEdition) -> dict[str, Any]:
    """
    Every product's price in one book and one edition — the grid the Prices
    tab draws. Each cell says the Standard price, the price in THIS book, and
    whether the book holds it itself (`own`) or it was worked out.
    """
    standard = standard_book(db)
    standard_id = standard.price_book_id if standard else book.price_book_id
    held = _entries(db, edition.edition_id, list({book.price_book_id, standard_id}))
    regional = not book.is_standard

    used = {size_id for (_, _, size_id) in held if size_id}
    sizes = [s for s in sizes_in_order(db) if s.active or s.size_id in used]
    order = _category_order(db)
    products = sorted(
        db.scalars(select(Product)),
        key=lambda p: (
            order.get(p.catalogue_category, 99),
            p.display_order if p.display_order is not None else 10**6,
            p.item_name.lower(),
        ),
    )

    def cell(product: Product, size_id: str | None, share: bool) -> dict[str, Any]:
        base = held.get((standard_id, product.product_id, size_id))
        own = held.get((book.price_book_id, product.product_id, size_id)) if regional else base
        if share:
            value = _number(base.pct_of_annual_licence) if base else None
            return {"size": size_id, "standard": value, "price": value, "own": bool(base) and not regional}
        base_price = base.list_price if base else None
        if not regional:
            return {"size": size_id, "standard": _number(base_price), "price": _number(base_price), "own": base is not None}
        if own is not None and own.list_price is not None:
            return {"size": size_id, "standard": _number(base_price), "price": _number(own.list_price), "own": True}
        return {"size": size_id, "standard": _number(base_price), "price": _number(worked_out(base_price, book)), "own": False}

    rows = []
    for product in products:
        shape = shape_of(product)
        cells = (
            [cell(product, s.size_id, False) for s in sizes]
            if shape == SIZED
            else [cell(product, None, shape == SHARE)]
        )
        rows.append(
            {
                "product": product.product_id,
                "item_name": product.item_name,
                "sku_code": product.sku_code,
                "catalogue_category": product.catalogue_category,
                "pricing_basis": product.pricing_basis,
                "unit_of_measure": product.unit_of_measure,
                "active": product.active,
                "shape": shape,
                "cells": cells,
            }
        )

    return {
        "price_book": book.price_book_id,
        "price_book_name": book.price_book_name,
        "is_standard": book.is_standard,
        "currency": book.currency,
        "multiplier": float(multiplier(book)),
        "edition": edition.edition_id,
        "edition_name": edition.price_book_version,
        "edition_status": edition.status,
        # What a save may do here — the same rules save_cells applies.
        "can_change": edition.status == DRAFT,
        "can_add": edition.status == CURRENT and book.is_standard,
        "sizes": [{"id": s.size_id, "size_code": s.size_code, "active": s.active} for s in sizes],
        "rows": rows,
    }


def _amount(raw: Any, step: Decimal) -> Decimal:
    try:
        value = Decimal(str(raw)).quantize(step, rounding=ROUND_HALF_UP)
    except (InvalidOperation, ValueError):
        raise _refuse("PRICE_NOT_A_NUMBER", "A price must be a number.", ["Correct it, then save."]) from None
    if value < 0:
        raise _refuse("PRICE_NEGATIVE", "A price can't be less than zero.", ["Correct it, then save."])
    return value


def save_cells(db: Session, book: PriceBook, edition: PriceBookEdition, cells: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Write prices into one book and one edition. Each cell is {product, size,
    value}: a number sets the price, null takes it away (in a regional book,
    back to the worked-out price). All of them, or none.

    Returns what moved, as {field, from, to}, for the audit entry.
    """
    if edition.status == RETIRED:
        raise _refuse(
            "EDITION_LOCKED",
            f"{edition.price_book_version} is a past edition, so its prices can't be changed.",
            ["Start a new edition, change the price there, then make it current."],
        )
    current = edition.status == CURRENT
    regional = not book.is_standard
    sizes = {s.size_id: s for s in db.scalars(select(DeploymentSize))}
    moved: list[dict[str, Any]] = []

    for raw in cells:
        product = db.get(Product, str(raw.get("product") or ""))
        if product is None:
            raise _refuse("PRICED_PRODUCT_MISSING", "A product on this page no longer exists.", ["Reload the page and try again."])
        shape = shape_of(product)
        size_id = raw.get("size") or None
        if shape == SIZED:
            if size_id not in sizes:
                raise _refuse(
                    "PRICE_NEEDS_SIZE",
                    f"{product.item_name} is priced by size.",
                    ["Reload the page and enter its price under a size."],
                )
        elif size_id is not None:
            raise _refuse(
                "PRICE_HAS_NO_SIZE",
                f"{product.item_name} has one price, whatever the size.",
                ["Reload the page and try again."],
            )
        if shape == SHARE and regional:
            raise _refuse(
                "PCT_IS_STANDARD",
                f"{product.item_name} is priced as a percentage, which is the same in every price book.",
                ["Change it in the Standard price book."],
            )

        entry = db.scalar(
            select(PriceBookEntry)
            .where(PriceBookEntry.price_book_id == book.price_book_id)
            .where(PriceBookEntry.edition_id == edition.edition_id)
            .where(PriceBookEntry.product_id == product.product_id)
            .where(PriceBookEntry.size_id.is_(None) if size_id is None else PriceBookEntry.size_id == size_id)
        )
        before = None if entry is None else (entry.pct_of_annual_licence if shape == SHARE else entry.list_price)
        value = raw.get("value")
        after = None if value in (None, "") else _amount(value, PCT_STEP if shape == SHARE else CENT)
        if before == after:
            continue
        # The edition being sold from: a price may be added where there is
        # none; one that is there stays. A regional price of its own always
        # changes what the book charged, so it waits for a draft too.
        if current and (regional or before is not None):
            raise _refuse(
                "EDITION_CURRENT",
                f"{edition.price_book_version} is the edition in use, so its prices can't be changed.",
                ["Start a new edition, change the price there, then make it current."],
            )

        if after is None:
            db.delete(entry)
        elif entry is None:
            db.add(
                PriceBookEntry(
                    price_book_id=book.price_book_id,
                    edition_id=edition.edition_id,
                    product_id=product.product_id,
                    size_id=size_id,
                    list_price=None if shape == SHARE else after,
                    pct_of_annual_licence=after if shape == SHARE else None,
                )
            )
        elif shape == SHARE:
            entry.list_price, entry.pct_of_annual_licence = None, after
        else:
            entry.list_price, entry.pct_of_annual_licence = after, None
        where = sizes[size_id].size_code if size_id else None
        moved.append(
            {
                "field": " · ".join(part for part in (product.sku_code, where, edition.price_book_version) if part),
                "from": _number(before),
                "to": _number(after),
            }
        )
    db.flush()
    return moved


def product_prices(db: Session, product: Product) -> list[dict[str, Any]]:
    """
    A product's list price as its own page shows it: the Standard book, the
    edition in use, one row per size in the Sizing Guide's order. Empty when it
    has none — it can be picked, not quoted.
    """
    book, edition = standard_book(db), current_edition(db)
    if book is None or edition is None:
        return []
    rows = list(
        db.scalars(
            select(PriceBookEntry)
            .where(PriceBookEntry.product_id == product.product_id)
            .where(PriceBookEntry.price_book_id == book.price_book_id)
            .where(PriceBookEntry.edition_id == edition.edition_id)
        )
    )
    order = {s.size_id: (index, s.size_code) for index, s in enumerate(sizes_in_order(db))}
    rows.sort(key=lambda r: order.get(r.size_id, (-1, ""))[0])
    return [
        {
            "product": product.product_id,
            "size": order.get(row.size_id, (0, None))[1] if row.size_id else None,
            "list_price_usa_usd": _number(row.list_price),
            "pct_of_annual_licence": _number(row.pct_of_annual_licence),
            "price_book_version": edition.price_book_version,
            # The Standard book's, so the page can say what the figures are in.
            "currency": book.currency,
        }
        for row in rows
    ]
