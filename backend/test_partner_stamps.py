"""
Deal registrations and conflict adjudications say who made them, and when.

    python run_tests.py test_partner_stamps.py

Before migration 0024 neither record carried a creator or a creation instant,
and neither router wrote audit_log. A registration entered on 14 Sep with a
partner Submitted Date of 12 Sep could not be told from one entered on the
12th — establishing when REG-00003 was created took reading database backups.
These are the assertions that keep it from regressing.
"""

import os
import sys
from datetime import timedelta

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
USER_ID = getattr(USER, "user_id", USER)

failures: list[str] = []
created: dict[str, list[str]] = {"conflicts": [], "registrations": [], "accounts": []}


def check(label: str, condition: bool, detail: str = "") -> None:
    if condition:
        print(f"  pass  {label}")
    else:
        failures.append(f"{label}{' — ' + detail if detail else ''}")
        print(f"  FAIL  {label}{' — ' + detail if detail else ''}")


def post(path: str, body: dict, collection: str | None = None):
    r = client.post(f"/api{path}", json=body)
    if collection and r.status_code == 201:
        created[collection].append(r.json()["id"])
    return r


def audit(module: str, record_id: str) -> list[dict]:
    r = client.get("/api/audit-log", params={"record_module": module, "record_id": record_id})
    r.raise_for_status()
    return r.json()


def section(title: str) -> None:
    print(f"\n{title}\n" + "-" * len(title))


today = today_company()

try:
    section("0  The cast")
    ec = post("/accounts", {"account_name": "Stamp probe — EC", "account_type": ["END_CLIENT"]}, "accounts").json()["id"]
    pa = post("/accounts", {"account_name": "Stamp probe — Partner-A", "account_type": ["PARTNER_SI"]}, "accounts").json()["id"]
    pb = post("/accounts", {"account_name": "Stamp probe — Partner-B", "account_type": ["PARTNER_SI"]}, "accounts").json()["id"]

    section("1  A registration is stamped by the server, not the body")
    r = post(
        "/registrations",
        {
            "partner": pa,
            "end_client": ec,
            "project_name": "Stamp probe project",
            "submitted_date": today.isoformat(),
            # Forgeries — must bind to nothing.
            "created_by": "USR-999",
            "created_date": "2020-01-01T00:00:00Z",
        },
        "registrations",
    )
    check("registration saves", r.status_code == 201, r.text[:300])
    reg = r.json()
    check("created_by is the signed-in user", reg.get("created_by") == USER_ID, str(reg.get("created_by")))
    check(
        "created_date is today's server time, not the forged 2020",
        bool(reg.get("created_date")) and not str(reg["created_date"]).startswith("2020"),
        str(reg.get("created_date")),
    )
    check("the creator's name is joined for the header", bool((reg.get("__labels") or {}).get("created_by")))
    rows = audit("registrations", reg["id"])
    check(
        "the create is on the audit trail, by the signed-in user",
        any(a["action"] == "created" and a["actor"] == USER_ID for a in rows),
        str(rows)[:300],
    )

    section("2  Submitted Date: backdated yes, future no")
    r = post(
        "/registrations",
        {"partner": pb, "end_client": ec, "project_name": "Stamp probe project", "submitted_date": (today + timedelta(days=1)).isoformat()},
        "registrations",
    )
    check("a future Submitted Date is refused", r.status_code == 422, f"{r.status_code} {r.text[:200]}")
    r = post(
        "/registrations",
        {
            "partner": pb,
            "end_client": ec,
            "project_name": "Stamp probe project",
            "submitted_date": (today - timedelta(days=2)).isoformat(),
            # The same project as the first: the conflict check asks, and this
            # is the answer — see test_partner_lifecycle.py for the check itself.
            "raise_conflict_with": [reg["id"]],
        },
        "registrations",
    )
    check("a backdated Submitted Date saves", r.status_code == 201, r.text[:200])
    reg_b = r.json()
    check(
        "…and created_date still says when it was ENTERED",
        str(reg_b.get("created_date", "")).startswith(str(today.year)) and reg_b.get("submitted_date") == (today - timedelta(days=2)).isoformat(),
        str(reg_b),
    )
    r = client.put(f"/api/registrations/{reg['id']}", json={"submitted_date": (today + timedelta(days=3)).isoformat()})
    check("an edit to a future Submitted Date is refused", r.status_code == 422, f"{r.status_code} {r.text[:200]}")

    section("3  An edit records what moved")
    r = client.put(f"/api/registrations/{reg['id']}", json={**reg, "estimated_value": 1_234_567})
    check("the edit saves, even carrying the record's own stamps and labels back", r.status_code == 200, r.text[:300])
    edited = r.json()
    check("created_by/created_date are untouched by an edit", edited.get("created_date") == reg.get("created_date"))
    check("modified_date moved", edited.get("modified_date") != reg.get("modified_date"))
    updates = [a for a in audit("registrations", reg["id"]) if a["action"] == "updated"]
    moved = [c for a in updates for c in (a.get("changed") or []) if c.get("field") == "estimated_value"]
    check("the audit row names estimated_value, from and to", bool(moved) and moved[-1].get("to") in (1234567, 1234567.0), str(updates)[:300])

    section("4  A conflict adjudication is stamped and audited too")
    raised = reg_b.get("raised_conflicts") or []
    check("saving the second registration raised the conflict", len(raised) == 1, str(reg_b)[:300])
    conflict = client.get(f"/api/conflicts/{raised[0]}").json() if raised else {}
    if raised:
        created["conflicts"].append(raised[0])
    check("it carries created_by and created_date", conflict.get("created_by") == USER_ID and bool(conflict.get("created_date")))
    r = client.put(f"/api/conflicts/{conflict['id']}", json={"evidence_link": "https://example.com/minutes"})
    check("an edit saves", r.status_code == 200, r.text[:200])
    actions = [a["action"] for a in audit("conflicts", conflict["id"])]
    check("created and updated are both on its trail", "created" in actions and "updated" in actions, str(actions))

    section("5  Deletes leave a trail")
    r = client.delete(f"/api/conflicts/{conflict['id']}")
    check("the conflict deletes", r.status_code == 204, r.text[:200])
    if r.status_code == 204:
        created["conflicts"].remove(conflict["id"])
    check("its delete is audited", "deleted" in [a["action"] for a in audit("conflicts", conflict["id"])])
    r = client.delete(f"/api/registrations/{reg_b['id']}")
    check("a registration deletes", r.status_code == 204, r.text[:200])
    if r.status_code == 204:
        created["registrations"].remove(reg_b["id"])
    check("its delete is audited", "deleted" in [a["action"] for a in audit("registrations", reg_b["id"])])

finally:
    # Children before parents: a conflict names registrations, a registration
    # names accounts.
    for collection in ("conflicts", "registrations", "accounts"):
        for record_id in reversed(created[collection]):
            client.delete(f"/api/{collection}/{record_id}")

print()
if failures:
    print(f"{len(failures)} failed")
    for f in failures:
        print(f"  - {f}")
    sys.exit(1)
print("all passed")
