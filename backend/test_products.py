"""
Products, step 1 — the catalogue is served, and a pursuit can only name what it offers.

    python run_tests.py test_products.py

What is proved (12 Oct 2026):
  · /api/products lists the catalogue and serves one item with its price at
    each size, in the register's size order. (Changing the catalogue is
    test_products_editing.py's.)
  · S!aP Solution Suite, Suite Demonstrated and Secondary S!aP Suites on a Lead
    accept a Segment Library item and refuse anything else — a product of
    another category, a retired one, an id that is not a product.
  · What was TYPED into those fields before the catalogue existed is kept: the
    Lead stays savable, the text reads back as typed, and it is refused only
    when a save changes the field to something that is not a product.
  · A product's page lists the pursuits naming it, each once.

Needs the catalogue loaded (load_price_book.py --apply) in the database the
test copy is made from.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from fastapi.testclient import TestClient  # noqa: E402

import test_db  # noqa: E402

test_db.require_test_database()

from app.database import SessionLocal  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Lead, Product  # noqa: E402
from test_support import sign_in_as_admin  # noqa: E402

client = TestClient(app)
USER = sign_in_as_admin(app)

failures: list[str] = []
created: dict[str, list[str]] = {"leads": [], "accounts": []}
retired: list[str] = []


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


def type_into(lead_id: str, **columns) -> None:
    """Put text straight into a column — what the form did before the catalogue."""
    with SessionLocal() as db:
        lead = db.get(Lead, lead_id)
        for name, value in columns.items():
            setattr(lead, name, value)
        db.commit()


def new_account(name: str) -> str:
    account = client.post("/api/accounts", json={"account_name": name, "account_type": ["END_CLIENT"]}).json()["id"]
    created["accounts"].append(account)
    return account


def new_lead(name: str, **extra):
    r = client.post(
        "/api/leads",
        json={
            "opportunity_name": name,
            "project_stage": "0_CONNECT",
            "lead_status": "OPEN",
            "currency": "USD",
            "end_client": END_CLIENT,
            **extra,
        },
    )
    if r.status_code == 201:
        created["leads"].append(r.json()["id"])
    return r


try:
    print("=" * 74)
    print("  PRODUCTS — the catalogue, and what a pursuit may name from it")
    print("=" * 74)

    print("\n1  The catalogue")
    r = client.get("/api/products")
    catalogue = r.json() if r.status_code == 200 else []
    check("the catalogue is served", r.status_code == 200 and len(catalogue) > 0, f"{r.status_code} {r.text[:200]}")
    check("with the row total on X-Total-Count", r.headers.get("x-total-count") == str(len(catalogue)))
    suites = [p for p in catalogue if p["catalogue_category"] == "SEGMENT_LIBRARY"]
    modules = [p for p in catalogue if p["catalogue_category"] == "MODULE"]
    packs = [p for p in catalogue if p["catalogue_category"] == "USER_PACK"]
    check("it holds suites, modules and user packs", bool(suites and modules and packs), f"{len(suites)}/{len(modules)}/{len(packs)}")
    if not (suites and modules and packs and len(suites) >= 3):
        raise SystemExit("The catalogue is not loaded — run load_price_book.py --apply, then run_tests.py again.")

    r = client.get("/api/products", params={"catalogue_category": "SEGMENT_LIBRARY"})
    check("a filter narrows it", {p["id"] for p in r.json()} == {p["id"] for p in suites})
    r = client.get("/api/products", params={"q": suites[0]["sku_code"].lower()})
    check("search finds an item by its SKU", [p["id"] for p in r.json()] == [suites[0]["id"]], str([p["id"] for p in r.json()]))

    priced = next((p for p in modules), None)
    r = client.get(f"/api/products/{priced['id']}")
    sizes = [p["size"] for p in r.json().get("prices", [])]
    check("an item carries its price at each size", r.status_code == 200 and len(sizes) > 1, str(sizes))
    check("in the register's order, not the alphabet's", sizes[:3] == ["XS", "S", "M"], str(sizes))
    check("each price names the edition of the price list it is from", all(p["price_book_version"] for p in r.json()["prices"]), str(r.json()["prices"][:1]))
    r = client.get(f"/api/products/{packs[0]['id']}")
    check("a user pack has one price, at no size", [p["size"] for p in r.json()["prices"]] == [None], str(r.json()["prices"]))
    check("an unknown product is a 404", client.get("/api/products/PRD-9999").status_code == 404)

    END_CLIENT = new_account("Products probe — end client")

    print("\n2  A Lead picks a suite")
    a, b, c = (s["id"] for s in suites[:3])
    r = new_lead("Products probe — picks", sap_solution_suite=a, secondary_sap_suites=[b, c], estimated_value=1000)
    check("a suite is accepted", r.status_code == 201, r.text[:300])
    lead_id = r.json()["id"]
    row = r.json()
    check("the single pick reads back as its id", row["sap_solution_suite"] == a)
    check("…with the product's name beside it", (row.get("__labels") or {}).get("sap_solution_suite") == suites[0]["item_name"], str(row.get("__labels")))
    check("the several-pick reads back as a list", row["secondary_sap_suites"] == [b, c], str(row["secondary_sap_suites"]))
    check(
        "…with the names joined",
        (row.get("__labels") or {}).get("secondary_sap_suites") == f"{suites[1]['item_name']}, {suites[2]['item_name']}",
        str(row.get("__labels")),
    )
    with SessionLocal() as db:
        check("stored as ids joined by commas, in the column it always had", db.get(Lead, lead_id).secondary_sap_suites == f"{b},{c}")

    r = new_lead("Products probe — a module", sap_solution_suite=modules[0]["id"])
    check("a product of another category is refused", r.status_code == 422 and code_of(r) == "PRODUCT_NOT_ALLOWED", f"{r.status_code} {r.text[:200]}")
    r = new_lead("Products probe — no such product", sap_solution_suite="PRD-9999")
    check("an id that is no product is refused", r.status_code == 422 and code_of(r) == "PICKED_RECORD_MISSING", f"{r.status_code} {r.text[:200]}")
    r = client.patch(f"/api/leads/{lead_id}", json={"suite_demonstrated": packs[0]["id"]})
    check("Suite Demonstrated takes suites only", r.status_code == 422 and code_of(r) == "PRODUCT_NOT_ALLOWED", f"{r.status_code} {r.text[:200]}")
    r = client.patch(f"/api/leads/{lead_id}", json={"secondary_sap_suites": [b, modules[0]["id"]]})
    check("so does every pick of a several-pick", r.status_code == 422 and code_of(r) == "PRODUCT_NOT_ALLOWED", f"{r.status_code} {r.text[:200]}")

    with SessionLocal() as db:
        db.get(Product, c).active = False
        db.commit()
    retired.append(c)
    r = client.patch(f"/api/leads/{lead_id}", json={"suite_demonstrated": c})
    check("a product no longer sold is refused", r.status_code == 422 and code_of(r) == "PRODUCT_INACTIVE", f"{r.status_code} {r.text[:200]}")
    r = client.patch(f"/api/leads/{lead_id}", json={"remarks_notes": "still savable"})
    check("…but a Lead already naming it still saves", r.status_code == 200, r.text[:200])

    r = client.patch(f"/api/leads/{lead_id}", json={"secondary_sap_suites": []})
    check("a several-pick can be emptied", r.status_code == 200 and r.json()["secondary_sap_suites"] == [], r.text[:200])

    print("\n3  What was typed before the catalogue is kept")
    # Its own End Client: a second pursuit at the first one's would be asked
    # about as a possible duplicate, which is not what this is testing.
    r = new_lead("Typed before the catalogue", end_client=new_account("Products probe — another client"))
    check("a second Lead saves", r.status_code == 201, r.text[:300])
    typed_id = r.json()["id"]
    type_into(typed_id, sap_solution_suite="Customized", secondary_sap_suites="Omnific and Cognus")
    row = client.get(f"/api/leads/{typed_id}").json()
    check("a typed single value reads back as typed", row["sap_solution_suite"] == "Customized")
    check("a typed several-pick reads back whole, as one entry", row["secondary_sap_suites"] == ["Omnific and Cognus"], str(row["secondary_sap_suites"]))
    r = client.patch(f"/api/leads/{typed_id}", json={"remarks_notes": "edited something else"})
    check("the Lead still saves when the field is left alone", r.status_code == 200, r.text[:200])
    r = client.put(
        f"/api/leads/{typed_id}",
        json={"sap_solution_suite": "Customized", "secondary_sap_suites": ["Omnific and Cognus"], "remarks_notes": "whole form"},
    )
    check("…and when the form sends it back unchanged", r.status_code == 200, r.text[:200])
    r = client.patch(f"/api/leads/{typed_id}", json={"sap_solution_suite": "Something else typed"})
    check("typing a new value is refused", r.status_code == 422, f"{r.status_code} {r.text[:200]}")
    r = client.patch(f"/api/leads/{typed_id}", json={"secondary_sap_suites": ["Omnific and Cognus", a]})
    check("a pick beside the typed text is refused, saying why", r.status_code == 422 and code_of(r) == "TYPED_PRODUCT", f"{r.status_code} {r.text[:200]}")
    r = client.patch(f"/api/leads/{typed_id}", json={"sap_solution_suite": a, "secondary_sap_suites": [b]})
    check("picking from the list replaces it", r.status_code == 200 and r.json()["sap_solution_suite"] == a and r.json()["secondary_sap_suites"] == [b], r.text[:200])

    print("\n4  Lists read the product's name")
    name = suites[0]["item_name"]
    r = client.get("/api/leads", params={"sap_solution_suite": a})
    check("a list filters by the product", {lead_id, typed_id} <= {x["id"] for x in r.json()}, str([x["id"] for x in r.json()]))
    r = client.get("/api/leads", params={"sap_solution_suite_contains": name[-5:].lower()})
    check("…and by its name", lead_id in {x["id"] for x in r.json()}, str([x["id"] for x in r.json()]))

    print("\n5  A product's pursuits")
    r = client.get(f"/api/products/{a}/pursuits")
    mine = [x for x in r.json()["records"] if x["id"] in (lead_id, typed_id)]
    check("both Leads naming it are listed", {x["id"] for x in mine} == {lead_id, typed_id}, str(r.json())[:300])
    first = next(x for x in mine if x["id"] == lead_id)
    check("each once, under the field that names it", [f["api_name"] for f in first["fields"]] == ["sap_solution_suite"], str(first["fields"]))
    second = next(x for x in mine if x["id"] == typed_id)
    check("the page names the pursuit", first["name"] == "Products probe — picks" and second["module"] == "leads")
    check("its value is the pursuit's, by the revenue rule", first["revenue"]["usd"] == 1000.0, str(first["revenue"]))
    r2 = client.get(f"/api/products/{b}/pursuits")
    check(
        "a several-pick names its products too",
        [f["api_name"] for x in r2.json()["records"] if x["id"] == typed_id for f in x["fields"]] == ["secondary_sap_suites"],
        str(r2.json())[:300],
    )
    check("the totals count open pipeline", r.json()["total"]["pipeline_count"] >= 2 and r.json()["total"]["pipeline_usd"] >= 1000.0, str(r.json()["total"]))
    check("an unknown product has no pursuits page", client.get("/api/products/PRD-9999/pursuits").status_code == 404)

finally:
    for lead in created["leads"]:
        client.delete(f"/api/leads/{lead}")
    for account in created["accounts"]:
        client.delete(f"/api/accounts/{account}")
    with SessionLocal() as db:
        for product_id in retired:
            db.get(Product, product_id).active = True
        db.commit()

print()
if failures:
    print(f"FAILED — {len(failures)}:")
    for failure in failures:
        print(f"  · {failure}")
    sys.exit(1)
print("All product checks passed.")
