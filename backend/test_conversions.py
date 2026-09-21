"""
A conversion happens in one transaction, and never twice.

    python run_tests.py test_conversions.py

Decided 15 Sep 2026, after a "Yes, move to Opportunities" pressed three times
made three Opportunities. See app/conversion.py.
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
created: dict[str, list[str]] = {"deals": [], "opportunities": [], "leads": [], "registrations": [], "accounts": []}


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


def post(path: str, body: dict, collection: str | None = None):
    r = client.post(f"/api{path}", json=body)
    if collection and r.status_code == 201:
        created[collection].append(r.json()["id"])
    return r


def get(path: str, **params):
    r = client.get(f"/api{path}", params=params)
    r.raise_for_status()
    return r.json()


try:
    print("=" * 74)
    print("  CONVERSIONS — one transaction, never twice")
    print("=" * 74)

    print("\n1  Lead -> Opportunity")
    r = post("/leads", {"opportunity_name": "Conversion probe", "project_stage": "3_PRESCRIPTION", "lead_status": "OPEN"}, "leads")
    check("the lead saves", r.status_code == 201, r.text[:300])
    lead_id = r.json()["id"]

    opp_body = {
        "parent_lead": lead_id,
        "project_stage": "4_RFP_RFI",
        "lead_status": "OPEN",
        "arr_annual_recurring": 1_000_000,
        "contract_years": 1,
        "final_negotiated_value": 1_000_000,
        "conversion_note": "Conversion probe moved to Opportunities from Stage 3.",
    }
    r = post("/opportunities", opp_body, "opportunities")
    check("creating the Opportunity is the one request a move needs", r.status_code == 201, r.text[:300])
    opp_id = r.json()["id"]
    check("…the lead is Converted in the same transaction", get(f"/leads/{lead_id}")["lead_status"] == "CONVERTED")
    rows = get("/conversions", source_id=lead_id)
    check(
        "…and the conversion is recorded once, with its note, who and when",
        len(rows) == 1
        and rows[0]["target_id"] == opp_id
        and rows[0]["note"] == opp_body["conversion_note"]
        and rows[0]["actor"] == USER.user_id
        and rows[0]["timestamp"],
        str(rows)[:300],
    )
    check("…and the note is not copied as a value", "conversion_note" not in (rows[0]["copied_fields"] if rows else []))

    r = post("/opportunities", opp_body, "opportunities")
    check("pressing it again is refused", r.status_code == 409 and code_of(r) == "ALREADY_CONVERTED", f"{r.status_code} {r.text[:200]}")
    detail = r.json().get("detail", {}) if r.status_code == 409 else {}
    check("…naming the Opportunity it already became", detail.get("target_module") == "opportunities" and detail.get("target_id") == opp_id, str(detail))
    check("…and no second Opportunity exists", [o["id"] for o in get("/opportunities", parent_lead=lead_id)] == [opp_id])
    check("…and no second conversion record", len(get("/conversions", source_id=lead_id)) == 1)

    print("\n2  Opportunity -> Deal")
    deal_body = {
        "deal_name": "Conversion probe",
        "parent_opportunity": opp_id,
        "deal_stage": "7_CLOSE",
        "contract_value": 1_000_000,
        "conversion_note": "Conversion probe moved to Deals from its Stage 6 detail page.",
    }
    r = post("/deals", deal_body, "deals")
    check("creating the Deal converts the Opportunity", r.status_code == 201, r.text[:300])
    deal_id = r.json()["id"]
    check("…which is Converted", get(f"/opportunities/{opp_id}")["lead_status"] == "CONVERTED")
    check("…with its conversion recorded", [c["target_id"] for c in get("/conversions", source_id=opp_id)] == [deal_id])
    r = post("/deals", deal_body, "deals")
    check("a second Deal from the same Opportunity is refused", r.status_code == 409 and code_of(r) == "ALREADY_CONVERTED", f"{r.status_code} {r.text[:200]}")
    check("…naming the Deal", (r.json().get("detail") or {}).get("target_id") == deal_id if r.status_code == 409 else False)

    print("\n3  A conversion record no longer needs a timestamp from the browser")
    r = client.post(
        "/api/conversions",
        json={"source_module": "leads", "source_id": lead_id, "target_module": "opportunities", "target_id": opp_id, "copied_fields": []},
    )
    check("POST /conversions without timestamp saves, stamped by the server", r.status_code == 201 and r.json().get("timestamp"), f"{r.status_code} {r.text[:200]}")

    print("\n4  One lead per deal registration")
    ec = post("/accounts", {"account_name": "Conversion probe — end client", "account_type": ["END_CLIENT"]}, "accounts").json()["id"]
    partner = post("/accounts", {"account_name": "Conversion probe — partner", "account_type": ["PARTNER_SI"]}, "accounts").json()["id"]
    reg = post(
        "/registrations",
        {
            "partner": partner,
            "end_client": ec,
            "project_name": "Conversion probe registered project",
            "submitted_date": today_company().isoformat(),
            "registration_status": "SUBMITTED",
        },
        "registrations",
    )
    check("the registration saves", reg.status_code == 201, reg.text[:300])
    reg_id = reg.json()["id"]
    lead_body = {
        "opportunity_name": "Conversion probe — registered",
        "end_client": ec,
        "customer_partner_si": partner,
        "deal_source": "PARTNER_SOURCED",
        "partner_deal_registration": reg_id,
        "project_stage": "0_CONNECT",
    }
    r = post("/leads", lead_body, "leads")
    check("its lead saves", r.status_code == 201, r.text[:300])
    reg_lead = r.json()["id"]
    check("…and the registration names it in the same commit", get(f"/registrations/{reg_id}")["linked_lead"] == reg_lead)
    r = post("/leads", lead_body, "leads")
    check("a second Create lead is refused", r.status_code == 409 and code_of(r) == "REGISTRATION_HAS_LEAD", f"{r.status_code} {r.text[:200]}")
    check("…naming the lead that exists", (r.json().get("detail") or {}).get("lead_id") == reg_lead if r.status_code == 409 else False)

finally:
    print("\nCleanup (best effort — converted and registered records guard each other by design)")
    for collection in ("deals", "opportunities", "leads", "registrations", "accounts"):
        for record_id in reversed(created[collection]):
            client.delete(f"/api/{collection}/{record_id}")

print()
if failures:
    print(f"{len(failures)} failed")
    for f in failures:
        print(f"  - {f}")
    sys.exit(1)
print("all passed")
