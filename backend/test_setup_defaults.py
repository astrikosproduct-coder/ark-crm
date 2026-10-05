"""
Setup, step 4d (5 Oct 2026): default values, country codes, and the sections
a module does not use.

    python run_tests.py test_setup_defaults.py

  * A Pick List can have a default value — one of its active choices, stored
    by key (a label is accepted and turned into the key). Not a multiselect,
    not any other type, and not a field shown from an earlier module.
  * A default that stops naming a live choice is cleared: the choice switched
    off, or the field no longer a Pick List.
  * The published register carries Currency = USD on Leads and Deal
    Registrations (setup_step4d_metadata.py), and the server fills it on a new
    record whose Currency is blank — never over one that was given.
  * Every Phone field takes the country codes, whatever was sent. A code added
    to that list is keyed by the code in its label; a label without one, a
    repeated code, a changed code and switching the list off are refused.
  * Accounts' Phone is a Phone field now; Leads and Deals have no empty
    record-header strip and Leads no stage sections it does not own, while
    Opportunities keeps its Priority Flags.
  * A default travels with a publish and a rollback.

Placements are put back by RegisterGuard, new fields removed by it; the lists
and the test country code are removed by the teardown.
"""

import sys

from fastapi.testclient import TestClient
from sqlalchemy import select, text

from app.database import SessionLocal, engine

engine.echo = False

from test_db import require_test_database  # noqa: E402

require_test_database()

from app.main import app  # noqa: E402
from app.metadata_spec import build_snapshot, diff_snapshots  # noqa: E402
from app.models import DealRegistration, FieldPlacement, Lead  # noqa: E402
from app.register_defaults import apply_defaults  # noqa: E402
from app.routers.metadata import DIAL_CODE_SET  # noqa: E402
from test_support import RegisterGuard, sign_in_as_admin  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE = "/api/admin/metadata"
TEST_CODE = "+9999"
client = TestClient(app)
failures: list[str] = []


def check(label: str, condition: bool, detail: str = "") -> None:
    if condition:
        print(f"  pass  {label}")
    else:
        failures.append(f"{label}{' — ' + detail if detail else ''}")
        print(f"  FAIL  {label}{' — ' + detail if detail else ''}")


def code_of(response) -> str | None:
    detail = response.json().get("detail")
    return detail.get("code") if isinstance(detail, dict) else None


admin = sign_in_as_admin(app)


def section_id(module: str) -> int:
    return next(
        s["id"]
        for s in client.get(f"{BASE}/sections", params={"module": module}).json()
        if s["active"] and not s["label"].startswith("STAGE") and s["label"] != "__header"
    )


def new_field(module: str, api_name: str, field_type: str, **extra):
    return client.post(
        f"{BASE}/fields",
        json={
            "module_key": module,
            "section_id": section_id(module),
            "api_name": api_name,
            "label": api_name.replace("_", " ").title(),
            "field_type": field_type,
            **extra,
        },
    )


def placement_of(module: str, api_name: str):
    return next(
        (
            f
            for f in client.get(f"{BASE}/fields", params={"module": module, "status": "active"}).json()
            if f["api_name"] == api_name
        ),
        None,
    )


def dial_values():
    lists = client.get(f"{BASE}/picklists").json()
    return next(p for p in lists if p["picklist_key"] == DIAL_CODE_SET)["values"]


try:
    with RegisterGuard() as guard:
        print("\n1  A Pick List's default value")
        r = new_field("leads", "zz_default_colour", "picklist", new_picklist=["Alpha", "Beta"], default_value="Beta")
        colour = r.json() if r.status_code == 201 else {}
        check("a new Pick List takes a default by its label", r.status_code == 201 and colour.get("default_value") == "BETA", r.text[:200])

        r = client.patch(f"{BASE}/placements/{colour.get('placement_id')}", json={"default_value": "Gamma"})
        check("a default that is not a choice is refused", r.status_code == 422 and code_of(r) == "DEFAULT_NOT_A_CHOICE", r.text[:200])

        r = client.patch(f"{BASE}/placements/{colour.get('placement_id')}", json={"default_value": "alpha"})
        check("…a choice's label in any case is stored as its key", r.status_code == 200 and r.json()["default_value"] == "ALPHA", r.text[:200])

        r = client.patch(f"{BASE}/placements/{colour.get('placement_id')}", json={"default_value": None})
        check("…and null clears it", r.status_code == 200 and r.json()["default_value"] is None, r.text[:200])

        r = new_field("leads", "zz_default_text", "text", default_value="hello")
        check("a text field cannot have a default", r.status_code == 422 and code_of(r) == "DEFAULT_PICK_LIST_ONLY", r.text[:200])
        r = new_field("leads", "zz_default_multi", "multiselect", new_picklist=["One", "Two"], default_value="One")
        check("nor a multiselect", r.status_code == 422 and code_of(r) == "DEFAULT_PICK_LIST_ONLY", r.text[:200])

        with SessionLocal() as db:
            shown = db.scalar(
                select(FieldPlacement).where(
                    FieldPlacement.module_key == "opportunities",
                    FieldPlacement.value_mode == "read_through",
                    FieldPlacement.status == "active",
                )
            )
        r = client.patch(f"{BASE}/placements/{shown.id}", json={"default_value": "X"})
        check("a field shown from an earlier module gets its default there", r.status_code == 422 and code_of(r) == "DEFAULT_NOT_HERE", r.text[:200])

        print("\n2  A default that stops naming a live choice is cleared")
        client.patch(f"{BASE}/placements/{colour.get('placement_id')}", json={"default_value": "BETA"})
        beta = next(
            v for p in client.get(f"{BASE}/picklists").json() if p["picklist_key"] == "leads__zz_default_colour"
            for v in p["values"] if v["key"] == "BETA"
        )
        client.patch(f"{BASE}/picklist-values/{beta['id']}", json={"active": False})
        check("switching the choice off clears the default", placement_of("leads", "zz_default_colour")["default_value"] is None)

        client.patch(f"{BASE}/placements/{colour.get('placement_id')}", json={"default_value": "ALPHA"})
        r = client.patch(f"{BASE}/fields/{colour.get('definition_id')}", json={"field_type": "text", "picklist_key": None})
        check("making the field text clears the default", r.status_code == 200 and placement_of("leads", "zz_default_colour")["default_value"] is None, r.text[:200])

        print("\n3  Currency starts as USD — from the register, not from code")
        spec = client.get("/api/spec").json()
        currency = {
            f["module"]: f.get("default_value")
            for f in spec["fields"]
            if f["api_name"] == "currency" and f["module"] in ("leads", "registrations")
        }
        check("the published register has USD on Leads and Deal Registrations", currency == {"leads": "USD", "registrations": "USD"}, str(currency))

        with SessionLocal() as db:
            lead = Lead()
            apply_defaults(db, "leads", lead)
            given = Lead(currency="AED")
            apply_defaults(db, "leads", given)
            reg = DealRegistration()
            apply_defaults(db, "registrations", reg)
        check("a new Lead with no currency gets USD", lead.currency == "USD", str(lead.currency))
        check("…a currency that was given is kept", given.currency == "AED", str(given.currency))
        check("…and a Deal Registration gets USD too", reg.currency == "USD", str(reg.currency))

        print("\n4  Every Phone field has the country codes")
        r = new_field("contacts", "zz_phone_plain", "phone")
        check("a new Phone field gets the country codes", r.status_code == 201 and r.json()["picklist_key"] == DIAL_CODE_SET, r.text[:200])
        r = new_field("contacts", "zz_phone_other", "phone", picklist_key="leads__currency")
        check("…whatever list was sent with it", r.status_code == 201 and r.json()["picklist_key"] == DIAL_CODE_SET, r.text[:200])
        r = new_field("contacts", "zz_phone_later", "text")
        later = r.json() if r.status_code == 201 else {}
        r = client.patch(f"{BASE}/fields/{later.get('definition_id')}", json={"field_type": "phone", "picklist_key": None})
        check("a text field made a Phone field gets them too", r.status_code == 200 and r.json()["picklist_key"] == DIAL_CODE_SET, r.text[:200])

        accounts_phone = placement_of("accounts", "phone")
        check(
            "Accounts' Phone is a Phone field with the country codes",
            accounts_phone is not None and accounts_phone["field_type"] == "phone" and accounts_phone["picklist_key"] == DIAL_CODE_SET,
            str(accounts_phone and (accounts_phone["field_type"], accounts_phone["picklist_key"])),
        )

        print("\n5  Adding a country code")
        r = client.post(f"{BASE}/picklist-values", json={"picklist_key": DIAL_CODE_SET, "label": f"Testland ({TEST_CODE})"})
        check("a code is keyed by the code in its label", r.status_code == 201 and r.json()["key"] == TEST_CODE, r.text[:200])
        added = r.json() if r.status_code == 201 else {}
        r = client.post(f"{BASE}/picklist-values", json={"picklist_key": DIAL_CODE_SET, "label": "Nowhere"})
        check("a label without a code is refused", r.status_code == 422 and code_of(r) == "DIAL_CODE_MISSING", r.text[:200])
        r = client.post(f"{BASE}/picklist-values", json={"picklist_key": DIAL_CODE_SET, "label": f"Elsewhere ({TEST_CODE})"})
        check("a code already in the list is refused", r.status_code == 409 and code_of(r) == "DIAL_CODE_REPEATED", r.text[:200])
        r = client.patch(f"{BASE}/picklist-values/{added.get('id')}", json={"label": f"Republic of Testland ({TEST_CODE})"})
        check("a code can be renamed while it keeps its code", r.status_code == 200, r.text[:200])
        r = client.patch(f"{BASE}/picklist-values/{added.get('id')}", json={"label": "Testland (+9998)"})
        check("…but its code cannot change", r.status_code == 422 and code_of(r) == "DIAL_CODE_FIXED", r.text[:200])
        r = client.patch(f"{BASE}/picklists/{DIAL_CODE_SET}", json={"active": False})
        check("the country codes cannot be switched off", r.status_code == 409 and code_of(r) == "DIAL_CODE_SET_NEEDED", r.text[:200])
        r = client.post(f"{BASE}/picklist-values", json={"picklist_key": "leads__currency", "label": "Zz Dollars (+1)"})
        check("other lists still make a key from the label", r.status_code == 201 and r.json()["key"] == "ZZ_DOLLARS_1", r.text[:200])

        print("\n6  Sections a module does not use are gone")
        labels = {
            m: {s["label"] for s in client.get(f"{BASE}/sections", params={"module": m}).json()}
            for m in ("leads", "opportunities", "deals")
        }
        check("Leads has no record-header strip", "__header" not in labels["leads"])
        check("Deals has no record-header strip", "__header" not in labels["deals"])
        check("Opportunities keeps its Priority Flags", "__header" in labels["opportunities"])
        stray = sorted(l for l in labels["leads"] if l.startswith(("STAGE 4", "STAGE 5", "STAGE 6", "STAGE 7")))
        check("Leads has no stage sections it does not own", not stray, str(stray))

        print("\n7  A default travels with a publish and a rollback")
        with SessionLocal() as db:
            before = build_snapshot(db)
            row = db.scalar(
                select(FieldPlacement).where(
                    FieldPlacement.module_key == "leads", FieldPlacement.api_name == "currency"
                )
            )
            row.default_value = "AED"
            db.flush()
            after = build_snapshot(db)
            db.rollback()
        changes = [c for c in diff_snapshots(before, after) if "default_value" in c]
        check("a changed default is a change to publish", len(changes) == 1 and "'USD' -> 'AED'" in changes[0], str(changes))
        rows = [f for f in before["fields"] if f["module"] == "leads" and f["api_name"] == "currency"]
        check("…and the snapshot carries it for a rollback", rows and rows[0].get("default_value") == "USD", str(rows[:1]))
        plain = [f for f in before["fields"] if f["module"] == "leads" and f["api_name"] == "opportunity_name"]
        check("a field with no default carries no key for it", plain and "default_value" not in plain[0], str(plain[:1]))

    print(f"\nRegisterGuard: {len(guard.repairs)} repair(s)")
    for line in guard.repairs:
        print(f"  {line}")

finally:
    with SessionLocal() as db:
        db.execute(text("DELETE FROM picklists WHERE picklist_key LIKE '%\\_\\_zz\\_%'"))
        db.execute(
            text("DELETE FROM picklist_values WHERE (picklist_key = :d AND key = :k) OR (picklist_key = 'leads__currency' AND key = 'ZZ_DOLLARS_1')"),
            {"d": DIAL_CODE_SET, "k": TEST_CODE},
        )
        db.commit()
    print("Cleanup done")

print()
if failures:
    print(f"{len(failures)} failed")
    for f in failures:
        print(f"  - {f}")
    sys.exit(1)
print("all passed")
