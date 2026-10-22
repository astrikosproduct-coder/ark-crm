"""
v1.2.1 — "Converted" is the system's, never picked by hand.

    python run_tests.py test_converted_status.py     (against the disposable copy)

Found on production, 22 Oct 2026: an Opportunity whose Status was set to
Converted by hand became read-only and left the default list, with no Deal made.

  1  A Lead and an Opportunity refuse a hand-set Converted, on create and on
     save, naming what to do instead — and nothing changes.
  2  A real conversion still converts: creating the Opportunity converts its
     Lead; creating the Deal converts its Opportunity.
  3  Re-sending the status a converted record already has is not a change.
"""

import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from app.database import engine  # noqa: E402

engine.echo = False

from test_db import require_test_database  # noqa: E402

require_test_database()

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from test_support import sign_in_as_admin  # noqa: E402

client = TestClient(app)
admin = sign_in_as_admin(app)

failed: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    if condition:
        print(f"  pass  {name}")
    else:
        failed.append(f"{name} — {detail}")
        print(f"  FAIL  {name} — {detail}")


def detail_of(response) -> dict:
    try:
        body = response.json().get("detail")
    except ValueError:
        return {}
    return body if isinstance(body, dict) else {}


def section(title: str) -> None:
    print(f"\n{title}\n" + "-" * len(title))


def refused(r) -> bool:
    return r.status_code == 422 and detail_of(r).get("code") == "CONVERTED_NOT_PICKABLE"


LEAD = {"bd_owner": admin.user_id, "currency": "USD", "lead_status": "OPEN"}

print("=" * 74)
print('  v1.2.1 — "Converted" is never picked by hand')
print("=" * 74)

section("1  Refused by hand, on Leads and Opportunities")
r = client.post("/api/leads", json={**LEAD, "opportunity_name": "Converted probe — born converted", "project_stage": "0_CONNECT", "lead_status": "CONVERTED"})
check("a Lead can't be created Converted", refused(r), f"{r.status_code} {r.text[:200]}")

r = client.post("/api/leads", json={**LEAD, "opportunity_name": "Converted probe — lead", "project_stage": "3_PRESCRIPTION"})
check("an open Lead saves", r.status_code == 201, r.text[:200])
lead = r.json()["lead_id"]
for verb in ("put", "patch"):
    r = getattr(client, verb)(f"/api/leads/{lead}", json={"lead_status": "CONVERTED"})
    check(f"a Lead's {verb.upper()} to Converted is refused", refused(r), f"{r.status_code} {r.text[:200]}")
check("…saying how to move it on", "Update Stage" in " ".join(detail_of(r).get("details", [])), str(detail_of(r)))
check("…and the Lead is still Open", client.get(f"/api/leads/{lead}").json()["lead_status"] == "OPEN")

section("2  A real conversion still converts")
r = client.post("/api/opportunities", json={
    "parent_lead": lead, "project_stage": "6_COMMERCIAL_EVAL", "lead_status": "OPEN",
    "one_time_revenue": 50_000, "final_negotiated_value": 50_000, "conversion_note": "Converted probe.",
})
check("creating the Opportunity is allowed", r.status_code == 201, r.text[:300])
opp = r.json()["id"]
check("…and converts its Lead", client.get(f"/api/leads/{lead}").json()["lead_status"] == "CONVERTED")

r = client.patch(f"/api/opportunities/{opp}", json={"lead_status": "CONVERTED"})
check("an Opportunity's save to Converted is refused", refused(r), f"{r.status_code} {r.text[:200]}")
check("…saying Convert to Deal", "Convert to Deal" in " ".join(detail_of(r).get("details", [])), str(detail_of(r)))
check("…and it is still Open", client.get(f"/api/opportunities/{opp}").json()["lead_status"] == "OPEN")

r = client.post("/api/deals", json={
    "deal_name": "Converted probe — lead", "parent_opportunity": opp, "deal_stage": "7_CLOSE",
    "contract_value": 50_000, "conversion_note": "Converted probe.",
})
check("Convert to Deal creates the Deal", r.status_code == 201, r.text[:300])
deal = r.json().get("id") if r.status_code == 201 else None
check("…and converts the Opportunity", client.get(f"/api/opportunities/{opp}").json()["lead_status"] == "CONVERTED")
if deal:
    r = client.patch(f"/api/deals/{deal}", json={"lead_status": "CONVERTED"})
    check("a Deal can't be set Converted either", refused(r), f"{r.status_code} {r.text[:200]}")

section("3  Re-sending a status a record already has")
r = client.put(f"/api/leads/{lead}", json={"lead_status": "CONVERTED"})
check("a converted Lead re-sent as Converted is not refused for it", not refused(r), f"{r.status_code} {r.text[:200]}")

print()
if failed:
    print(f"{len(failed)} FAILED")
    for line in failed:
        print(f"  - {line}")
    sys.exit(1)
print("all passed")
