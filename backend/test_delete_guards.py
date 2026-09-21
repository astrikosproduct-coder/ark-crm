"""
Deleting an Account or a Contact is refused while a pursuit still names it.

    python run_tests.py test_delete_guards.py

The foreign keys from Leads, Deals, demo attendees and pursuit groups onto
accounts and contacts are ON DELETE SET NULL. Without the server-side check in
app/record_references.py, deleting a named Account would silently blank the
End Client on every Lead that used it. Added 21 Sep 2026, when MSW was removed
and the browser's delete dialog stopped being the only guard worth trusting.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from fastapi.testclient import TestClient  # noqa: E402

import test_db  # noqa: E402

test_db.require_test_database()

from app.main import app  # noqa: E402
from test_support import sign_in_as_admin  # noqa: E402

client = TestClient(app)
USER = sign_in_as_admin(app)

failures: list[str] = []
created: dict[str, list[str]] = {"leads": [], "contacts": [], "accounts": []}


def check(label: str, condition: bool, detail: str = "") -> None:
    if condition:
        print(f"  pass  {label}")
    else:
        failures.append(f"{label}{' — ' + detail if detail else ''}")
        print(f"  FAIL  {label}{' — ' + detail if detail else ''}")


def detail_of(response) -> dict:
    try:
        detail = response.json().get("detail")
    except ValueError:
        return {}
    return detail if isinstance(detail, dict) else {}


def post(path: str, body: dict, collection: str):
    r = client.post(f"/api{path}", json=body)
    if r.status_code == 201:
        created[collection].append(r.json()["id"])
    return r


def delete(collection: str, record_id: str):
    r = client.delete(f"/api/{collection}/{record_id}")
    if r.status_code == 204 and record_id in created[collection]:
        created[collection].remove(record_id)
    return r


try:
    print("=" * 74)
    print("  DELETE GUARDS — an Account or Contact a pursuit names cannot be deleted")
    print("=" * 74)

    end_client = post("/accounts", {"account_name": "Guard probe — end client", "account_type": ["END_CLIENT"]}, "accounts").json()["id"]
    person = post("/contacts", {"full_name": "Guard probe — person"}, "contacts").json()["id"]
    lead = post(
        "/leads",
        {
            "opportunity_name": "Guard probe — pursuit",
            "project_stage": "0_CONNECT",
            "lead_status": "OPEN",
            "currency": "USD",
            "end_client": end_client,
            "primary_contact": person,
        },
        "leads",
    )
    check("a lead naming the account and the contact saves", lead.status_code == 201, lead.text[:300])
    lead_id = lead.json()["id"]

    print("\n1  While the lead names them")
    r = delete("accounts", end_client)
    check("deleting the account is refused", r.status_code == 409, f"{r.status_code} {r.text[:200]}")
    check("with a code the screen can branch on", detail_of(r).get("code") == "ACCOUNT_IN_USE", str(detail_of(r)))
    check("naming the lead that holds it", lead_id in (detail_of(r).get("records") or []), str(detail_of(r)))
    check("and the lead's End Client is untouched", client.get(f"/api/leads/{lead_id}").json().get("end_client") == end_client)

    r = delete("contacts", person)
    check("deleting the contact is refused", r.status_code == 409, f"{r.status_code} {r.text[:200]}")
    check("with its own code", detail_of(r).get("code") == "CONTACT_IN_USE", str(detail_of(r)))
    check("and the lead's Primary Contact is untouched", client.get(f"/api/leads/{lead_id}").json().get("primary_contact") == person)

    print("\n2  Once nothing names them")
    r = delete("leads", lead_id)
    check("the lead deletes", r.status_code == 204, f"{r.status_code} {r.text[:200]}")
    check("then the contact deletes", delete("contacts", person).status_code == 204)
    check("then the account deletes", delete("accounts", end_client).status_code == 204)

finally:
    print("\nCleanup")
    for collection in ("leads", "contacts", "accounts"):
        for record_id in reversed(created[collection]):
            r = client.delete(f"/api/{collection}/{record_id}")
            if r.status_code not in (204, 404):
                print(f"  ! could not delete {collection}/{record_id}: {r.status_code} {r.text[:120]}")

print()
if failures:
    print(f"{len(failures)} FAILED")
    for f in failures:
        print("   ", f)
    sys.exit(1)
print("all passed")
