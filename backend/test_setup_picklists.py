"""
Setup, step 3 (25 Sep 2026): dropdown choices live in the field, shared lists
are Global Sets — the Zoho arrangement, which has no Picklists screen.

    python run_tests.py test_setup_picklists.py

What the server now does, each checked over the API:

  * GET /picklists says which fields use each list ("Used in"), by owning module.
  * POST /picklists creates a Global Set from a name and its choices; the key
    is made from the name, each choice's key from its label.
  * POST /picklist-values takes a label alone, and refuses a repeated choice.
  * POST /fields with `new_picklist` creates the field's own (local) list in
    the same transaction — a refused field leaves no list behind.
  * PATCH /fields/{id} with `new_picklist` gives a field on a global set its
    own list, and refuses a field that already has one.
  * The rules that were there stay: a local list serves one field, and a
    global list used by several cannot be made local.

Every field it adds is removed by RegisterGuard; every list it adds is
deleted in the teardown. It never publishes.
"""

import sys

from fastapi.testclient import TestClient
from sqlalchemy import text

from app.database import SessionLocal, engine

engine.echo = False

from test_db import require_test_database  # noqa: E402

require_test_database()

from app.main import app  # noqa: E402
from test_support import RegisterGuard, sign_in_as_admin  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE = "/api/admin/metadata"
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


def picklist(key: str) -> dict | None:
    return next((p for p in client.get(f"{BASE}/picklists").json() if p["picklist_key"] == key), None)


def list_exists(key: str) -> bool:
    with SessionLocal() as db:
        return db.execute(text("SELECT 1 FROM picklists WHERE picklist_key = :k"), {"k": key}).first() is not None


sign_in_as_admin(app)
section_id = next(
    s["id"] for s in client.get(f"{BASE}/sections", params={"module": "leads"}).json() if s["active"]
)


def new_field(api_name: str, **extra) -> object:
    return client.post(
        f"{BASE}/fields",
        json={
            "module_key": "leads",
            "section_id": section_id,
            "api_name": api_name,
            "label": api_name.replace("_", " ").title(),
            "field_type": extra.pop("field_type", "picklist"),
            **extra,
        },
    )


print("=" * 74)
print("  SETUP — choices in the field, shared lists as Global Sets")
print("=" * 74)

try:
    with RegisterGuard() as guard:
        print("\n1  Used in")
        region = picklist("region")
        check("a global set lists the fields using it", bool(region and region["used_by"]), str(region)[:200])
        if region:
            check("…as many as its field count", len(region["used_by"]) == region["field_count"])
            first = region["used_by"][0]
            check(
                "…each with its owning module's label",
                first["module_label"] and first["module_key"] and first["label"],
                str(first),
            )

        print("\n2  A Global Set from a name and its choices")
        r = client.post(f"{BASE}/picklists", json={"label": "Zz Test Set", "is_global": True, "values": ["Alpha", "Beta One"]})
        check("created", r.status_code == 201, r.text[:300])
        body = r.json() if r.status_code == 201 else {}
        check("the key is made from the name", body.get("picklist_key") == "zz_test_set", str(body.get("picklist_key")))
        check("it is global", body.get("is_global") is True)
        check(
            "each choice's key is made from its label",
            [v["key"] for v in body.get("values", [])] == ["ALPHA", "BETA_ONE"],
            str([v["key"] for v in body.get("values", [])]),
        )
        r = client.post(f"{BASE}/picklists", json={"label": "Zz Test Set", "is_global": True, "values": ["x"]})
        check("the same name again gets a key of its own", r.status_code == 201 and r.json()["picklist_key"] == "zz_test_set_2", r.text[:200])
        r = client.post(f"{BASE}/picklists", json={"label": "Zz Repeat", "is_global": True, "values": ["Alpha", " alpha "]})
        check("a repeated choice is refused", r.status_code == 422 and code_of(r) == "PICKLIST_CHOICE_REPEATED", r.text[:200])
        check("…and no list is left behind", not list_exists("zz_repeat"))
        r = client.post(f"{BASE}/picklists", json={"label": "Zz Empty", "is_global": True, "values": ["  "]})
        check("a set with no choices is refused", r.status_code == 422 and code_of(r) == "PICKLIST_NO_CHOICES", r.text[:200])
        r = client.post(f"{BASE}/picklists", json={"is_global": True, "values": ["a"]})
        check("a set with no name is refused", r.status_code == 422 and code_of(r) == "PICKLIST_NAME_REQUIRED", r.text[:200])

        print("\n3  A choice from its label alone")
        r = client.post(f"{BASE}/picklist-values", json={"picklist_key": "zz_test_set", "label": "Gamma-ray"})
        check("added, keyed from the label", r.status_code == 201 and r.json()["key"] == "GAMMA_RAY", r.text[:200])
        r = client.post(f"{BASE}/picklist-values", json={"picklist_key": "zz_test_set", "label": "gamma-RAY"})
        check("the same choice again is refused", r.status_code == 409 and code_of(r) == "PICKLIST_CHOICE_REPEATED", r.text[:200])
        r = client.post(f"{BASE}/picklist-values", json={"picklist_key": "zz_test_set", "key": "DELTA", "label": "Delta"})
        check("a caller may still name the key", r.status_code == 201 and r.json()["key"] == "DELTA", r.text[:200])

        print("\n4  A field with its own choices")
        r = new_field("zz_colour", new_picklist=["Red", "Green"])
        check("created", r.status_code == 201, r.text[:300])
        colour = r.json() if r.status_code == 201 else {}
        check("its list is <module>__<field>", colour.get("picklist_key") == "leads__zz_colour", str(colour.get("picklist_key")))
        own = picklist("leads__zz_colour") or {}
        check("…local, with the two choices", own.get("is_global") is False and [v["label"] for v in own.get("values", [])] == ["Red", "Green"], str(own)[:200])
        check("…named after the module and the field", own.get("label") == "Leads · Zz Colour", str(own.get("label")))
        check("…and used by that field alone", [u["api_name"] for u in own.get("used_by", [])] == ["zz_colour"])

        r = new_field("zz_colour", new_picklist=["Blue"])
        check("a field refused as a duplicate is refused", r.status_code == 409, r.text[:200])
        check("…and leaves no list behind", not list_exists("leads__zz_colour_2"))
        r = new_field("zz_both", new_picklist=["A"], picklist_key="zz_test_set")
        check("own choices AND a global set is refused", r.status_code == 422 and code_of(r) == "PICKLIST_TWO_SOURCES", r.text[:200])
        r = new_field("zz_text", field_type="text", new_picklist=["A"])
        check("choices on a text field are refused", r.status_code == 422 and code_of(r) == "PICKLIST_NOT_A_DROPDOWN", r.text[:200])
        check("…and neither leaves a list behind", not list_exists("leads__zz_both") and not list_exists("leads__zz_text"))
        r = new_field("zz_blank", new_picklist=[])
        check("own choices with none in them are refused", r.status_code == 422 and code_of(r) == "PICKLIST_NO_CHOICES", r.text[:200])

        print("\n5  Moving between a global set and the field's own list")
        r = new_field("zz_shared_a", picklist_key="zz_test_set")
        a = r.json() if r.status_code == 201 else {}
        check("a field can use the global set", r.status_code == 201, r.text[:200])
        r = new_field("zz_shared_b", picklist_key="zz_test_set")
        check("…and so can a second", r.status_code == 201, r.text[:200])
        r = client.patch(f"{BASE}/picklists/zz_test_set", json={"is_global": False})
        check("a set two fields use cannot become local", r.status_code == 409 and code_of(r) == "PICKLIST_SHARED", r.text[:200])

        r = client.patch(f"{BASE}/fields/{a.get('definition_id')}", json={"new_picklist": ["Yes", "No"]})
        check("a field leaves the set for its own choices", r.status_code == 200 and r.json()["picklist_key"] == "leads__zz_shared_a", r.text[:200])
        users = [u["api_name"] for u in (picklist("zz_test_set") or {}).get("used_by", [])]
        check("…and the set no longer lists it", users == ["zz_shared_b"], str(users))
        r = client.patch(f"{BASE}/fields/{a.get('definition_id')}", json={"new_picklist": ["Maybe"]})
        check("a field already on its own list is refused a second", r.status_code == 409 and code_of(r) == "PICKLIST_ALREADY_OWN", r.text[:200])
        r = new_field("zz_borrower", picklist_key="leads__zz_colour")
        check("another field cannot borrow a local list", r.status_code == 409 and code_of(r) == "PICKLIST_IS_LOCAL", r.text[:200])

    print(f"\nRegisterGuard: {len(guard.repairs)} repair(s)")
    for line in guard.repairs:
        print(f"  {line}")

finally:
    with SessionLocal() as db:
        db.execute(text("DELETE FROM picklists WHERE picklist_key LIKE 'zz\\_%' OR picklist_key LIKE 'leads\\_\\_zz\\_%'"))
        db.commit()
        left = db.execute(
            text("SELECT picklist_key FROM picklists WHERE picklist_key LIKE 'zz\\_%' OR picklist_key LIKE 'leads\\_\\_zz\\_%'")
        ).scalars().all()
    print("Cleanup", "done" if not left else f"left {left}")

print()
if failures:
    print(f"{len(failures)} failed")
    for f in failures:
        print(f"  - {f}")
    sys.exit(1)
print("all passed")
