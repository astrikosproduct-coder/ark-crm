"""
Deleting a Lead — only while nothing but Accounts and Contacts is linked to it,
and never taking an Account or Contact with it unless asked.

    python run_tests.py test_lead_delete.py

Decided 15 Sep 2026. See app/lead_deletion.py.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from fastapi.testclient import TestClient  # noqa: E402

import test_db  # noqa: E402

test_db.require_test_database()

from app.clock import today_company  # noqa: E402
from app.main import app  # noqa: E402
from test_support import sign_in_as_admin  # noqa: E402

client = TestClient(app)
USER = sign_in_as_admin(app)

failures: list[str] = []
created: dict[str, list[str]] = {"leads": [], "registrations": [], "contacts": [], "accounts": []}


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


def post(path: str, body: dict, collection: str):
    r = client.post(f"/api{path}", json=body)
    if r.status_code == 201:
        created[collection].append(r.json()["id"])
    return r


def exists(path: str) -> bool:
    return client.get(f"/api/{path}").status_code == 200


def account(name: str, types: list[str]) -> str:
    return post("/accounts", {"account_name": f"Delete probe — {name}", "account_type": types}, "accounts").json()["id"]


def contact(name: str, account_id: str) -> str:
    return post("/contacts", {"full_name": f"Delete probe — {name}", "account": account_id}, "contacts").json()["id"]


try:
    print("=" * 74)
    print("  LEAD DELETE — nothing but accounts and contacts, and those only if asked")
    print("=" * 74)

    ec = account("End client", ["END_CLIENT"])
    shared = account("Shared partner", ["PARTNER_SI"])
    at_client = contact("At the end client", ec)
    at_partner = contact("At the shared partner", shared)

    r = post("/leads", {"opportunity_name": "Delete probe — another pursuit", "end_client": shared, "project_stage": "0_CONNECT"}, "leads")
    check("another lead naming the partner as its End Client saves", r.status_code == 201, r.text[:300])

    body = {
        "opportunity_name": "Delete probe — lead",
        "end_client": ec,
        "customer_partner_si": shared,
        "primary_contact": at_client,
        "project_stage": "0_CONNECT",
        "demo_attendees": [{"attendee": at_partner}],
    }
    r = post("/leads", body, "leads")
    check("the lead saves", r.status_code == 201, r.text[:300])
    lead_one = r.json()["id"]

    print("\n1  The plan")
    plan = client.get(f"/api/leads/{lead_one}/deletion").json()
    accounts = {a["id"]: a for a in plan.get("accounts", [])}
    contacts = {c["id"]: c for c in plan.get("contacts", [])}
    check("nothing but accounts and contacts is linked, so nothing blocks", plan.get("blockers") == [], str(plan)[:300])
    check("its End Client could go with it", accounts.get(ec, {}).get("deletable") is True and "end_client" in accounts[ec]["via"], str(accounts.get(ec)))
    check(
        "a partner another lead also names is kept, and the plan says why",
        accounts.get(shared, {}).get("deletable") is False and accounts[shared]["used_by"].get("leads") == 1,
        str(accounts.get(shared)),
    )
    check("the primary contact could go", contacts.get(at_client, {}).get("deletable") is True and "primary_contact" in contacts[at_client]["via"], str(contacts.get(at_client)))
    check("a demo attendee used nowhere else could go", contacts.get(at_partner, {}).get("deletable") is True and "demo_attendees" in contacts[at_partner]["via"], str(contacts.get(at_partner)))

    print("\n2  Deleting without being asked to take anything with it")
    r = client.delete(f"/api/leads/{lead_one}")
    check("the lead is deleted", r.status_code == 204 and not exists(f"leads/{lead_one}"), r.text[:200])
    check(
        "…and every account and contact is still there",
        all(exists(p) for p in (f"accounts/{ec}", f"accounts/{shared}", f"contacts/{at_client}", f"contacts/{at_partner}")),
    )

    print("\n3  Deleting with its accounts and contacts")
    r = post("/leads", {**body, "opportunity_name": "Delete probe — lead two"}, "leads")
    check("a second lead on the same records saves", r.status_code == 201, r.text[:300])
    lead_two = r.json()["id"]
    r = client.delete(f"/api/leads/{lead_two}", params={"with_linked": "true"})
    check("the lead is deleted", r.status_code == 204 and not exists(f"leads/{lead_two}"), r.text[:200])
    check("…its End Client is gone", not exists(f"accounts/{ec}"))
    check("…both contacts are gone", not exists(f"contacts/{at_client}") and not exists(f"contacts/{at_partner}"))
    check("…the partner another lead still uses is kept", exists(f"accounts/{shared}"))

    print("\n4  A lead linked to anything else cannot be deleted")
    ec3 = account("Registered end client", ["END_CLIENT"])
    reg = post(
        "/registrations",
        {
            "partner": shared,
            "end_client": ec3,
            "project_name": "Delete probe registered project",
            "submitted_date": today_company().isoformat(),
            "registration_status": "SUBMITTED",
        },
        "registrations",
    )
    check("a registration saves", reg.status_code == 201, reg.text[:300])
    reg_id = reg.json()["id"]
    r = post(
        "/leads",
        {
            "opportunity_name": "Delete probe — registered",
            "end_client": ec3,
            "customer_partner_si": shared,
            "deal_source": "PARTNER_SOURCED",
            "partner_deal_registration": reg_id,
            "project_stage": "0_CONNECT",
        },
        "leads",
    )
    check("a lead from it saves", r.status_code == 201, r.text[:300])
    lead_three = r.json()["id"]
    plan = client.get(f"/api/leads/{lead_three}/deletion").json()
    check("the plan names the registration as what is in the way", any(b["kind"] == "registration" and b["id"] == reg_id for b in plan.get("blockers", [])), str(plan.get("blockers")))
    r = client.delete(f"/api/leads/{lead_three}", params={"with_linked": "true"})
    check("the delete is refused", r.status_code == 409 and code_of(r) == "LEAD_HAS_DEPENDENTS", f"{r.status_code} {r.text[:200]}")
    check("…and nothing was deleted", exists(f"leads/{lead_three}") and exists(f"accounts/{ec3}"))

finally:
    print("\nCleanup")
    for lead_id in created["leads"]:
        if exists(f"leads/{lead_id}"):
            client.put(f"/api/leads/{lead_id}", json={"partner_deal_registration": None})
            client.delete(f"/api/leads/{lead_id}")
    for collection in ("registrations", "contacts", "accounts"):
        for record_id in reversed(created[collection]):
            r = client.delete(f"/api/{collection}/{record_id}")
            if r.status_code not in (204, 404):
                print(f"  could not delete {collection}/{record_id}: {r.status_code} {r.text[:160]}")

print()
if failures:
    print(f"{len(failures)} failed")
    for f in failures:
        print(f"  - {f}")
    sys.exit(1)
print("all passed")
