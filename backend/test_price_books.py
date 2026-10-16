"""
Products, phase 3 — price books, editions, prices, and the Sizing Guide.

    python run_tests.py test_price_books.py

What is proved (13 Oct 2026):
  · There is one Standard price book, and it stays the master: 100%, no
    exchange, never deactivated or deleted. A regional book is made, edited,
    deactivated and deleted.
  · A regional price is the Standard price x Region Pricing % x FX Rate, worked
    out when read; a price of the book's own replaces it, and taking that away
    brings the worked-out price back.
  · A price has the shape its product's Pricing Basis gives it: per size, one
    price, or a percentage — and a percentage lives in the Standard book only.
  · Editions: a draft is a copy that is edited freely; the edition in use takes
    a first price and no change; a past edition takes nothing. Making a draft
    current retires the one before it, the same day.
  · A size is a record: a new one is a column of every book, and one with
    prices can't be deleted.
  · Only an admin or a developer writes any of it; anyone with a role reads.

Needs the price book loaded (load_price_book.py --apply --add-missing) and
products_phase3_metadata.py applied in the database the test copy is made from.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import delete, select  # noqa: E402

import test_db  # noqa: E402

test_db.require_test_database()

from app import requirements  # noqa: E402
from app.auth import current_user  # noqa: E402
from app.clock import now_utc  # noqa: E402
from app.database import SessionLocal  # noqa: E402
from app.main import app  # noqa: E402
from app.models import (  # noqa: E402
    AuditLog,
    DeploymentSize,
    PriceBook,
    PriceBookEdition,
    PriceBookEntry,
    Product,
    User,
    UserRole,
)
from test_support import sign_in_as_admin  # noqa: E402

client = TestClient(app)
USER = sign_in_as_admin(app)
# test_support switches required fields off for the older scripts; a price
# book's and a size's are part of what is proved here.
requirements.ENFORCED = True

failures: list[str] = []
VIEWER = "USR-T-PB1"
#: Everything this script makes carries this, so its cleanup can find it.
MARK = "TPROBE"


def check(label: str, condition: bool, detail: str = "") -> None:
    if condition:
        print(f"  pass  {label}")
    else:
        failures.append(f"{label}{' — ' + detail if detail else ''}")
        print(f"  FAIL  {label}{' — ' + detail if detail else ''}")


def code_of(response) -> str | None:
    try:
        detail = response.json().get("detail")
    except ValueError:
        return None
    return detail.get("code") if isinstance(detail, dict) else None


def missing_of(response) -> set[str]:
    try:
        detail = response.json().get("detail")
    except ValueError:
        return set()
    return {f["api_name"] for f in detail.get("fields", [])} if isinstance(detail, dict) else set()


def act_as_viewer() -> None:
    def _current_user():
        with SessionLocal() as db:
            user = db.get(User, VIEWER)
            _ = user.roles
            db.expunge(user)
            return user

    app.dependency_overrides[current_user] = _current_user


def grid(book: str, edition: str | None = None) -> dict:
    r = client.get(f"/api/price-books/{book}/prices", params={"edition": edition} if edition else {})
    return r.json() if r.status_code == 200 else {}


def cell(matrix: dict, product: str, size: str | None = None) -> dict:
    row = next((r for r in matrix.get("rows", []) if r["product"] == product), None)
    if row is None:
        return {}
    return next((c for c in row["cells"] if c["size"] == size), {})


def put(book: str, edition: str, *cells: tuple) -> object:
    body = {"edition": edition, "cells": [{"product": p, "size": s, "value": v} for p, s, v in cells]}
    return client.put(f"/api/price-books/{book}/prices", json=body)


with SessionLocal() as db:
    if db.get(User, VIEWER) is None:
        stamp = now_utc()
        db.add(User(user_id=VIEWER, name="Price Book Viewer", email="usr-t-pb1@example.test", active=True, created_at=stamp, updated_at=stamp))
        db.flush()
        db.add(UserRole(user_id=VIEWER, role_id="VIEWER"))
        db.commit()
    ORIGINAL = db.scalar(select(PriceBookEdition.edition_id).where(PriceBookEdition.status == "CURRENT"))

try:
    print("=" * 74)
    print("  PRICE BOOKS — books, editions, prices, and the Sizing Guide")
    print("=" * 74)

    books = client.get("/api/price-books").json()
    if not books or not ORIGINAL:
        raise SystemExit("The price book is not loaded — run load_price_book.py --apply --add-missing, then run_tests.py again.")

    print("\n1  The Standard book, and the regional ones")
    standard = books[0]
    STD = standard["id"]
    check("the Standard book is listed first", standard["is_standard"] is True and sum(b["is_standard"] for b in books) == 1)
    check("it prices at 100% with no exchange", (standard["region_pricing_pct"], standard["fx_rate_local_per_usd"], standard["effective_multiplier"]) == (1.0, 1.0, 1.0), str(standard))
    regional = next((b for b in books if not b["is_standard"] and b["effective_multiplier"] != 1.0), None)
    check("a regional book carries its currency and its multiplier", regional is not None and bool(regional["currency"]), str(regional)[:200])

    r = client.post("/api/price-books", json={"description": "no name"})
    check("a book with no name is refused, the field named", r.status_code == 422 and missing_of(r) == {"price_book_name"}, f"{r.status_code} {r.text[:200]}")
    r = client.post("/api/price-books", json={"price_book_name": f"{MARK} Egypt EGP"})
    check("its other required fields are asked for", r.status_code == 422 and {"currency", "region_pricing_pct", "fx_rate_local_per_usd"} <= missing_of(r), f"{r.status_code} {r.text[:300]}")
    body = {"price_book_name": f"{MARK} Egypt", "currency": "USD", "region_pricing_pct": 0.5, "fx_rate_local_per_usd": 4, "rate_effective_date": "2026-10-01"}
    r = client.post("/api/price-books", json=body)
    check("a regional book is created", r.status_code == 201 and r.json()["is_standard"] is False and r.json()["active"] is True, f"{r.status_code} {r.text[:300]}")
    if r.status_code != 201:
        raise SystemExit("A price book could not be created — nothing after this can be proved.")
    EGY = r.json()["id"]
    check("its multiplier is Region Pricing % x FX Rate", r.json()["effective_multiplier"] == 2.0, str(r.json()["effective_multiplier"]))
    r = client.post("/api/price-books", json={**body, "price_book_name": f"  {MARK.lower()} egypt "})
    check("the same name, in any case, is refused", r.status_code == 409 and code_of(r) == "PRICE_BOOK_EXISTS", f"{r.status_code} {r.text[:200]}")
    r = client.patch(f"/api/price-books/{EGY}", json={"fx_rate_local_per_usd": 0})
    check("an FX rate of zero is refused", r.status_code == 422, f"{r.status_code} {r.text[:200]}")
    r = client.put(f"/api/price-books/{EGY}", json={**client.get(f"/api/price-books/{EGY}").json(), "fx_rate_local_per_usd": 3})
    check("the form's whole record saves", r.status_code == 200 and r.json()["effective_multiplier"] == 1.5, f"{r.status_code} {r.text[:300]}")

    r = client.patch(f"/api/price-books/{STD}", json={"region_pricing_pct": 0.9})
    check("the Standard book's percentage can't move", r.status_code == 422 and code_of(r) == "STANDARD_BOOK_FIXED", f"{r.status_code} {r.text[:200]}")
    r = client.patch(f"/api/price-books/{STD}/active", json={"active": False})
    check("it can't be deactivated", r.status_code == 422 and code_of(r) == "STANDARD_BOOK_FIXED", f"{r.status_code} {r.text[:200]}")
    r = client.delete(f"/api/price-books/{STD}")
    check("it can't be deleted", r.status_code == 409 and code_of(r) == "STANDARD_BOOK_FIXED", f"{r.status_code} {r.text[:200]}")
    check("…and it is unchanged", client.get(f"/api/price-books/{STD}").json()["region_pricing_pct"] == 1.0)

    print("\n2  A price has the shape its product is priced in")
    matrix = grid(STD)
    by_shape: dict[str, dict] = {}
    for row in matrix.get("rows", []):
        if any(c["price"] is not None for c in row["cells"]):
            by_shape.setdefault(row["shape"], row)
    check("the grid is served for the edition in use", matrix.get("edition") == ORIGINAL and matrix.get("is_standard") is True, str(matrix)[:200])
    check("it holds all three shapes", set(by_shape) == {"sized", "single", "percent"}, str(sorted(by_shape)))
    if set(by_shape) != {"sized", "single", "percent"}:
        raise SystemExit("The price book holds no service or support products — run load_price_book.py --apply --add-missing.")
    sized, single, share = by_shape["sized"], by_shape["single"], by_shape["percent"]
    sizes = [s["id"] for s in matrix["sizes"]]
    check("a product priced by size has a cell per size, in the Sizing Guide's order", [c["size"] for c in sized["cells"]] == sizes and len(sizes) >= 7, str(sizes))
    check("the sizes read smallest first", [s["size_code"] for s in matrix["sizes"]][:3] == ["XS", "S", "M"], str(matrix["sizes"][:3]))
    check("a product with one price has one cell, at no size", [c["size"] for c in single["cells"]] == [None])
    check("a support product's price is a share of the licence", [c["size"] for c in share["cells"]] == [None] and 0 < share["cells"][0]["price"] < 1, str(share["cells"]))
    check("the edition in use can be added to, not changed", (matrix["can_change"], matrix["can_add"]) == (False, True))

    SIZED, SIZE0 = sized["product"], sizes[0]
    base = cell(matrix, SIZED, SIZE0)["price"]
    egypt = grid(EGY)
    worked = cell(egypt, SIZED, SIZE0)
    check("a regional price is the Standard price x the multiplier", worked["price"] == round(base * 1.5, 2) and worked["standard"] == base and worked["own"] is False, f"{base} -> {worked}")
    check("a percentage is the same in every book", cell(egypt, share["product"])["price"] == share["cells"][0]["price"])
    check("a regional book's edition in use takes nothing", (egypt["can_change"], egypt["can_add"]) == (False, False))
    client.patch(f"/api/price-books/{EGY}", json={"fx_rate_local_per_usd": 4})
    check("change the FX rate and every price follows", cell(grid(EGY), SIZED, SIZE0)["price"] == round(base * 2, 2))

    print("\n3  The edition in use takes a first price, and no change")
    r = put(STD, ORIGINAL, (SIZED, SIZE0, base + 1))
    check("a price that is there can't be changed", r.status_code == 422 and code_of(r) == "EDITION_CURRENT", f"{r.status_code} {r.text[:200]}")
    r = put(STD, ORIGINAL, (SIZED, SIZE0, None))
    check("…or taken away", r.status_code == 422 and code_of(r) == "EDITION_CURRENT", f"{r.status_code} {r.text[:200]}")
    r = put(EGY, ORIGINAL, (SIZED, SIZE0, 5))
    check("a regional price of its own waits for a draft too", r.status_code == 422 and code_of(r) == "EDITION_CURRENT", f"{r.status_code} {r.text[:200]}")
    requirements.ENFORCED = False
    r = client.post("/api/products", json={"sku_code": f"{MARK}-NEW", "item_name": "Price book probe", "catalogue_category": "ADD_ON", "pricing_basis": "FLAT"})
    requirements.ENFORCED = True
    NEW = r.json()["id"] if r.status_code == 201 else ""
    check("a new product appears in the grid at once, unpriced", cell(grid(STD), NEW) == {"size": None, "standard": None, "price": None, "own": False}, str(cell(grid(STD), NEW)))
    r = put(STD, ORIGINAL, (NEW, None, 1250))
    check("…and takes its first price in the edition in use", r.status_code == 200 and cell(r.json(), NEW)["price"] == 1250.0, f"{r.status_code} {r.text[:200]}")
    check("the product's own page shows it, and the edition", [(p["size"], p["list_price_usa_usd"]) for p in client.get(f"/api/products/{NEW}").json()["prices"]] == [(None, 1250.0)])
    check("…and the currency the figure is in", client.get(f"/api/products/{NEW}").json()["prices"][0]["currency"] == standard["currency"])
    r = put(STD, ORIGINAL, (NEW, None, 1300))
    check("once set, it too is fixed", r.status_code == 422 and code_of(r) == "EDITION_CURRENT", f"{r.status_code} {r.text[:200]}")
    r = put(STD, ORIGINAL, (NEW, SIZE0, 10))
    check("a product with one price can't be priced at a size", r.status_code == 422 and code_of(r) == "PRICE_HAS_NO_SIZE", f"{r.status_code} {r.text[:200]}")
    r = put(STD, ORIGINAL, (SIZED, None, 10))
    check("a product priced by size needs one", r.status_code == 422 and code_of(r) == "PRICE_NEEDS_SIZE", f"{r.status_code} {r.text[:200]}")
    with SessionLocal() as db:
        audit = db.scalars(select(AuditLog).where(AuditLog.record_module == "price_books", AuditLog.record_id == STD).order_by(AuditLog.id.desc())).first()
    check("a price change is recorded, with what moved", audit is not None and audit.actor == USER.user_id and (audit.changed or [{}])[0].get("to") == 1250.0, str(audit.changed if audit else None))

    print("\n4  A draft edition is a copy, edited freely")
    r = client.post("/api/price-book-editions", json={"notes": "no name"})
    check("an edition with no name is refused", r.status_code == 422 and missing_of(r) == {"price_book_version"}, f"{r.status_code} {r.text[:200]}")
    r = client.post("/api/price-book-editions", json={"price_book_version": f"{MARK} 2027", "notes": "Made by test_price_books.py."})
    check("a new edition starts as a draft", r.status_code == 201 and r.json()["status"] == "DRAFT", f"{r.status_code} {r.text[:300]}")
    if r.status_code != 201:
        raise SystemExit("An edition could not be created — nothing after this can be proved.")
    DRAFT = r.json()["id"]
    with SessionLocal() as db:
        count = lambda e: len(db.scalars(select(PriceBookEntry.id).where(PriceBookEntry.edition_id == e)).all())  # noqa: E731
        check("holding a copy of every price of the edition in use", count(DRAFT) == count(ORIGINAL) > 0, f"{count(DRAFT)} / {count(ORIGINAL)}")
    r = client.post("/api/price-book-editions", json={"price_book_version": f"{MARK.lower()} 2027"})
    check("the same edition name is refused", r.status_code == 409 and code_of(r) == "EDITION_EXISTS", f"{r.status_code} {r.text[:200]}")
    listed = client.get("/api/price-book-editions").json()
    check("editions list the one in use first", listed[0]["id"] == ORIGINAL and DRAFT in {e["id"] for e in listed}, str([e["id"] for e in listed]))

    draft = grid(STD, DRAFT)
    check("a draft can be changed", (draft["can_change"], draft["edition_status"]) == (True, "DRAFT"))
    r = put(STD, DRAFT, (SIZED, SIZE0, base + 100), (NEW, None, None), (share["product"], None, 0.4))
    after = r.json() if r.status_code == 200 else {}
    check("prices are changed, taken away and set as a percentage in one save", r.status_code == 200 and cell(after, SIZED, SIZE0)["price"] == base + 100 and cell(after, NEW)["price"] is None and cell(after, share["product"])["price"] == 0.4, f"{r.status_code} {r.text[:300]}")
    check("the edition in use is untouched", cell(grid(STD), SIZED, SIZE0)["price"] == base)
    r = put(STD, DRAFT, (SIZED, SIZE0, -1))
    check("a price below zero is refused", r.status_code == 422 and code_of(r) == "PRICE_NEGATIVE", f"{r.status_code} {r.text[:200]}")
    r = put(STD, DRAFT, (SIZED, SIZE0, base + 5), ("PRD-9999", None, 5))
    check("one bad cell stops the whole save", r.status_code == 422 and cell(grid(STD, DRAFT), SIZED, SIZE0)["price"] == base + 100, f"{r.status_code} {r.text[:200]}")

    r = put(EGY, DRAFT, (SIZED, SIZE0, 777))
    own = cell(r.json(), SIZED, SIZE0) if r.status_code == 200 else {}
    check("a regional book takes a price of its own", own.get("price") == 777.0 and own.get("own") is True and own.get("standard") == base + 100, f"{r.status_code} {r.text[:200]}")
    r = put(EGY, DRAFT, (SIZED, SIZE0, None))
    back = cell(r.json(), SIZED, SIZE0) if r.status_code == 200 else {}
    check("taking it away brings the worked-out price back", back.get("price") == round((base + 100) * 2, 2) and back.get("own") is False, str(back))
    r = put(EGY, DRAFT, (share["product"], None, 0.5))
    check("a percentage is changed in the Standard book only", r.status_code == 422 and code_of(r) == "PCT_IS_STANDARD", f"{r.status_code} {r.text[:200]}")

    print("\n5  Making a draft current retires the one before it")
    r = client.post("/api/price-book-editions", json={"price_book_version": f"{MARK} empty", "copy_from": DRAFT})
    EMPTY = r.json()["id"] if r.status_code == 201 else ""
    with SessionLocal() as db:
        db.execute(delete(PriceBookEntry).where(PriceBookEntry.edition_id == EMPTY))
        db.commit()
    r = client.post(f"/api/price-book-editions/{EMPTY}/make-current")
    check("an edition with no prices can't be made current", r.status_code == 422 and code_of(r) == "EDITION_EMPTY", f"{r.status_code} {r.text[:200]}")
    r = client.delete(f"/api/price-book-editions/{EMPTY}")
    check("a draft is deleted", r.status_code == 204 and client.get(f"/api/price-book-editions/{EMPTY}").status_code == 404, f"{r.status_code}")

    r = client.post(f"/api/price-book-editions/{DRAFT}/make-current")
    today = now_utc().date().isoformat()
    check("the draft becomes the edition in use, from today", r.status_code == 200 and r.json()["status"] == "CURRENT" and r.json()["effective_from"] == today, f"{r.status_code} {r.text[:300]}")
    old = client.get(f"/api/price-book-editions/{ORIGINAL}").json()
    check("the one before it is retired, today", (old["status"], old["effective_to"]) == ("RETIRED", today), str(old))
    check("the grid now opens on the new edition", grid(STD).get("edition") == DRAFT and cell(grid(STD), SIZED, SIZE0)["price"] == base + 100)
    product = client.get(f"/api/products/{SIZED}").json()
    check("a product's page shows the new price and names the edition", product["prices"][0]["list_price_usa_usd"] == base + 100 and product["prices"][0]["price_book_version"] == f"{MARK} 2027", str(product["prices"][:1]))
    check("the past edition still reads as it was", cell(grid(STD, ORIGINAL), SIZED, SIZE0)["price"] == base)
    r = put(STD, ORIGINAL, (NEW, None, 9))
    check("…and takes nothing more", r.status_code == 422 and code_of(r) == "EDITION_LOCKED", f"{r.status_code} {r.text[:200]}")
    r = client.post(f"/api/price-book-editions/{ORIGINAL}/make-current")
    check("a past edition can't be made current again", r.status_code == 422 and code_of(r) == "EDITION_NOT_DRAFT", f"{r.status_code} {r.text[:200]}")
    r = client.delete(f"/api/price-book-editions/{ORIGINAL}")
    check("…or deleted", r.status_code == 409 and code_of(r) == "EDITION_IN_USE", f"{r.status_code} {r.text[:200]}")
    r = client.patch(f"/api/price-book-editions/{ORIGINAL}", json={"effective_from": "2020-01-01"})
    check("…or re-dated", r.status_code == 422 and code_of(r) == "EDITION_LOCKED", f"{r.status_code} {r.text[:200]}")
    r = client.patch(f"/api/price-book-editions/{ORIGINAL}", json={"notes": "Renamed in a test."})
    check("its notes can still be edited", r.status_code == 200 and r.json()["notes"] == "Renamed in a test.", r.text[:200])

    print("\n6  The Sizing Guide")
    guide = client.get("/api/sizes").json()
    check("the sizes are listed smallest first, with what each covers", [s["size_code"] for s in guide][:3] == ["XS", "S", "M"] and guide[0]["base_users_included"] is not None, str(guide[:1]))
    r = client.post("/api/sizes", json={"size_code": f"{MARK}"})
    check("a size's required fields are asked for", r.status_code == 422 and "base_users_included" in missing_of(r), f"{r.status_code} {r.text[:300]}")
    size_body = {"size_code": MARK, "managed_assets_cap": "No cap", "typical_deployment": "A test", "subsystem_types": "50+", "base_users_included": 9, "sort_order": 99}
    r = client.post("/api/sizes", json=size_body)
    check("a size is created", r.status_code == 201 and r.json()["active"] is True, f"{r.status_code} {r.text[:300]}")
    SIZE = r.json()["id"] if r.status_code == 201 else ""
    r = client.post("/api/sizes", json={**size_body, "size_code": MARK.lower()})
    check("the same size code is refused", r.status_code == 409 and code_of(r) == "SIZE_EXISTS", f"{r.status_code} {r.text[:200]}")
    check("it is a column of every price book at once, last", [s["id"] for s in grid(EGY)["sizes"]][-1] == SIZE)
    r = client.post("/api/price-book-editions", json={"price_book_version": f"{MARK} 2028"})
    NEXT = r.json()["id"] if r.status_code == 201 else ""
    r = put(STD, NEXT, (SIZED, SIZE, 42))
    check("a price is set at the new size, in a draft", r.status_code == 200 and cell(r.json(), SIZED, SIZE)["price"] == 42.0, f"{r.status_code} {r.text[:200]}")
    r = client.delete(f"/api/sizes/{SIZE}")
    check("a size with a price can't be deleted", r.status_code == 409 and code_of(r) == "SIZE_IN_USE", f"{r.status_code} {r.text[:200]}")
    r = client.patch(f"/api/sizes/{SIZE}/active", json={"active": False})
    check("it is deactivated instead", r.status_code == 200 and r.json()["active"] is False)
    check("…keeping its column where it has a price", SIZE in [s["id"] for s in grid(STD, NEXT)["sizes"]] and SIZE not in [s["id"] for s in grid(STD)["sizes"]])
    put(STD, NEXT, (SIZED, SIZE, None))
    r = client.delete(f"/api/sizes/{SIZE}")
    check("with no price left, it is deleted", r.status_code == 204, f"{r.status_code} {r.text[:200]}")

    print("\n7  A regional book is retired, and deleted")
    r = client.patch(f"/api/price-books/{EGY}/active", json={"active": False})
    check("a regional book is deactivated", r.status_code == 200 and r.json()["active"] is False)
    put(EGY, NEXT, (SIZED, SIZE0, 555))
    r = client.delete(f"/api/price-books/{EGY}")
    check("…and deleted, its own prices with it", r.status_code == 204 and client.get(f"/api/price-books/{EGY}").status_code == 404, f"{r.status_code}")
    with SessionLocal() as db:
        check("nothing of it is left", not db.scalars(select(PriceBookEntry.id).where(PriceBookEntry.price_book_id == EGY)).all())
    check("the Standard prices are untouched", cell(grid(STD), SIZED, SIZE0)["price"] == base + 100)

    print("\n8  Only an admin or a developer changes any of it")
    act_as_viewer()
    check(
        "anyone with a role reads books, prices, editions and sizes",
        all(client.get(path).status_code == 200 for path in ("/api/price-books", f"/api/price-books/{STD}/prices", "/api/price-book-editions", "/api/sizes")),
    )
    for label, r in (
        ("make a price book", client.post("/api/price-books", json=body)),
        ("edit one", client.patch(f"/api/price-books/{STD}", json={"display_format": "x"})),
        ("delete one", client.delete(f"/api/price-books/{STD}")),
        ("set a price", put(STD, NEXT, (SIZED, SIZE0, 1))),
        ("start an edition", client.post("/api/price-book-editions", json={"price_book_version": f"{MARK} viewer"})),
        ("make one current", client.post(f"/api/price-book-editions/{NEXT}/make-current")),
        ("delete an edition", client.delete(f"/api/price-book-editions/{NEXT}")),
        ("make a size", client.post("/api/sizes", json=size_body)),
        ("edit a size", client.patch(f"/api/sizes/{sizes[0]}", json={"base_users_included": 1})),
        ("delete a size", client.delete(f"/api/sizes/{sizes[0]}")),
    ):
        check(f"a Viewer cannot {label}", r.status_code == 403 and code_of(r) == "CATALOGUE_EDITOR_ONLY", f"{r.status_code} {r.text[:200]}")
    USER = sign_in_as_admin(app)

finally:
    sign_in_as_admin(app)
    requirements.ENFORCED = False
    with SessionLocal() as db:
        # Put the price list back as it was found: the edition that was in use
        # is in use again, and everything this script made is gone.
        made = list(db.scalars(select(PriceBookEdition.edition_id).where(PriceBookEdition.price_book_version.like(f"{MARK}%"))))
        products = list(db.scalars(select(Product.product_id).where(Product.sku_code.like(f"{MARK}%"))))
        db.execute(delete(PriceBookEntry).where(PriceBookEntry.edition_id.in_(made)))
        db.execute(delete(PriceBookEdition).where(PriceBookEdition.edition_id.in_(made)))
        db.execute(delete(Product).where(Product.product_id.in_(products)))
        db.execute(delete(PriceBook).where(PriceBook.price_book_name.like(f"{MARK}%")))
        db.execute(delete(DeploymentSize).where(DeploymentSize.size_code.like(f"{MARK}%")))
        original = db.get(PriceBookEdition, ORIGINAL) if ORIGINAL else None
        if original is not None:
            original.status, original.effective_to, original.notes = "CURRENT", None, None
        db.execute(delete(UserRole).where(UserRole.user_id == VIEWER))
        db.execute(delete(User).where(User.user_id == VIEWER))
        db.commit()
        left = list(db.scalars(select(PriceBookEdition.price_book_version).where(PriceBookEdition.price_book_version.like(f"{MARK}%"))))
    app.dependency_overrides.pop(current_user, None)
    print("\nCleanup", "done" if not left else f"left {left}")

print()
if failures:
    print(f"FAILED — {len(failures)}:")
    for failure in failures:
        print(f"  · {failure}")
    sys.exit(1)
print("All price book checks passed.")
