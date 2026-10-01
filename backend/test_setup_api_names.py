"""
Setup, step 4a (1 Oct 2026): nobody types an API name or a module key.

    python run_tests.py test_setup_api_names.py

Zoho never asks a person for an API name, and Setup no longer does. The server
makes one from the label — once; a later rename leaves it alone, because it is
the key every stored value, condition and formula is written under:

  * "Zz Partner Tier"  -> zz_partner_tier, and zz_partner_tier_2 for the next.
  * never a name the module already has, deleted fields included.
  * never a real column of the module's table: "Status" on Leads is not `status`.
  * never starting with a digit, never with a double underscore (a per-stage key).
  * a module's key the same way, from its label.
  * a script may still name one, as before.

Fields are removed by RegisterGuard, modules in the teardown. Never publishes.
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


sign_in_as_admin(app)
section_id = next(
    s["id"] for s in client.get(f"{BASE}/sections", params={"module": "leads"}).json() if s["active"]
)


def add(label: str, **extra):
    r = client.post(
        f"{BASE}/fields",
        json={"module_key": "leads", "section_id": section_id, "label": label, "field_type": "text", **extra},
    )
    return r, (r.json() if r.status_code == 201 else {})


print("=" * 74)
print("  SETUP — API names and module keys are made, never typed")
print("=" * 74)

try:
    with RegisterGuard() as guard:
        print("\n1  A field's API name comes from its label")
        r, first = add("Zz Partner Tier")
        check("created without an API name", r.status_code == 201, r.text[:300])
        check("…named from the label", first.get("api_name") == "zz_partner_tier", str(first.get("api_name")))
        r, second = add("Zz Partner Tier")
        check("the same label again gets its own name", second.get("api_name") == "zz_partner_tier_2", str(second.get("api_name")))

        # `custom_fields` is a real column of leads — the JSONB every field
        # made in Setup is stored in. A field named after it would be a disaster.
        r, column_field = add("Custom Fields")
        name = column_field.get("api_name", "")
        check("a label matching a real column never takes the column's name", r.status_code == 201 and name == "custom_fields_2", name)

        r, digit = add("3rd Party Zz")
        check("a name never starts with a digit", digit.get("api_name") == "field_3rd_party_zz", str(digit.get("api_name")))
        r, punct = add("Zz  -- Reason (s3)!")
        check("punctuation collapses to single underscores", punct.get("api_name") == "zz_reason_s3", str(punct.get("api_name")))
        check("…so it can never look like a per-stage key", "__" not in punct.get("api_name", "__"))

        print("\n2  Deleted fields keep their names")
        r, gone = add("Zz Gone")
        d = client.delete(f"{BASE}/fields/{gone.get('definition_id')}")
        check("a field is deleted", d.status_code == 200, d.text[:200])
        r, again = add("Zz Gone")
        check("a new field with its label does not take its name", again.get("api_name") == "zz_gone_2", str(again.get("api_name")))

        print("\n3  Renaming never renames the API name")
        p = client.patch(f"{BASE}/fields/{first.get('definition_id')}", json={"label": "Zz Partner Level"})
        check("renamed", p.status_code == 200, p.text[:200])
        check("…and the API name stays", p.json().get("api_name") == "zz_partner_tier", str(p.json().get("api_name")))

        print("\n4  A script may still name one")
        r, named = add("Whatever", api_name="zz_named")
        check("a named API name is kept", named.get("api_name") == "zz_named", r.text[:200])
        r, clash = add("Whatever", api_name="zz_named")
        check("…and a named clash is still refused", r.status_code == 409, r.text[:200])

        print("\n5  A module's key comes from its label")
        m = client.post(f"{BASE}/modules", json={"label": "Zz Widgets"})
        check("a module is created without a key", m.status_code == 201 and m.json()["module_key"] == "zz_widgets", m.text[:200])
        m = client.post(f"{BASE}/modules", json={"label": "Zz Widgets"})
        check("…and the same label again gets its own key", m.status_code == 201 and m.json()["module_key"] == "zz_widgets_2", m.text[:200])

        print("\n6  Modules and layouts say when they last changed (4b)")
        leads = next((m for m in client.get(f"{BASE}/modules").json() if m["module_key"] == "leads"), {})
        check("a module carries its Last Modified", bool(leads.get("last_modified")), str(leads)[:200])
        layouts = client.get(f"{BASE}/layouts", params={"module": "leads"}).json()
        check(
            "Leads has one layout, Standard, the default",
            len(layouts) == 1 and layouts[0]["label"] == "Standard" and layouts[0]["is_default"],
            str(layouts)[:200],
        )
        check("…dated like its module", layouts and layouts[0]["last_modified"] == leads.get("last_modified"))
        before = leads.get("last_modified") or ""
        client.patch(f"{BASE}/fields/{first.get('definition_id')}", json={"label": "Zz Partner Grade"})
        after = next(m for m in client.get(f"{BASE}/modules").json() if m["module_key"] == "leads")["last_modified"]
        check("editing a field moves its module's Last Modified", after > before, f"{before} -> {after}")

    print(f"\nRegisterGuard: {len(guard.repairs)} repair(s)")
    for line in guard.repairs:
        print(f"  {line}")

finally:
    with SessionLocal() as db:
        # A new module gets its Standard layout; that goes first.
        db.execute(text("DELETE FROM layouts WHERE module_key LIKE 'zz\\_widgets%'"))
        db.execute(text("DELETE FROM modules WHERE module_key LIKE 'zz\\_widgets%'"))
        db.commit()
        left = db.execute(text("SELECT module_key FROM modules WHERE module_key LIKE 'zz\\_widgets%'")).scalars().all()
    print("Cleanup", "done" if not left else f"left {left}")

print()
if failures:
    print(f"{len(failures)} failed")
    for f in failures:
        print(f"  - {f}")
    sys.exit(1)
print("all passed")
