"""
Required fields are enforced on save and on a stage move — app/requirements.py,
decided 21 Sep 2026 — against the published register, so a field made Optional
in Administration and published stops being demanded at once.

Run:  python run_tests.py test_required_fields.py     (against the disposable copy)

Everything it creates is removed in the teardown, and the register change it
publishes is put back and published again.
"""

import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from sqlalchemy import select, text  # noqa: E402

from app.database import SessionLocal, engine  # noqa: E402

engine.echo = False

from test_db import require_test_database  # noqa: E402

require_test_database()

from fastapi.testclient import TestClient  # noqa: E402

from app import requirements  # noqa: E402
from app.main import app  # noqa: E402
from app.models import FieldPlacement  # noqa: E402
from app.routers import metadata as metadata_router  # noqa: E402
from test_support import RegisterGuard, sign_in_as_admin  # noqa: E402

# test_support switches the check off for the older scripts; this one tests it.
requirements.ENFORCED = True
# Publishing here must not rewrite frontend/spec/*.json in the working tree.
metadata_router.write_spec_documents = lambda documents: []

client = TestClient(app)
admin = sign_in_as_admin(app)

passed: list[str] = []
failed: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    if condition:
        passed.append(name)
        print(f"  PASS  {name}")
    else:
        failed.append(f"{name} — {detail}")
        print(f"  FAIL  {name} — {detail}")


def missing_of(response) -> set[str]:
    body = response.json().get("detail") or {}
    return {f["api_name"] for f in body.get("fields", [])} if isinstance(body, dict) else set()


def refused(response) -> bool:
    body = response.json().get("detail") if response.status_code == 422 else None
    return isinstance(body, dict) and body.get("code") == "REQUIRED_FIELDS_MISSING"


created: dict[str, list[str]] = {"leads": [], "contacts": [], "accounts": []}

ACCOUNT = {
    "account_name": "Required Fields Test Client",
    "account_type": ["END_CLIENT"],
    "account_owner": admin.user_id,
    "region": "MEA",
    "segment": "INFRASTRUCTURE",
    "customer_class": "A_STRATEGIC_>$2M",
    "account_target_phase": "YEAR_1",
}

STAGE_1 = {
    "demo_completed": True,
    "demo_date": "2026-09-10",
    "suite_demonstrated": "SAP-CORE",
    "demo_attendees": [],  # filled with the test Contact below
    "interest_level": "HIGH",
    "agreed_next_step": "PRESCRIPTION",
    "client_feedback": "Liked it.",
    "demo_debrief_notes": "Went well.",
}


def new_client(name: str) -> str:
    """A fresh End Client, so the duplicate-pursuit check never steps in."""
    r = client.post("/api/accounts", json={**ACCOUNT, "account_name": name})
    assert r.status_code == 201, r.text
    created["accounts"].append(r.json()["account_id"])
    return r.json()["account_id"]


def transition(lead_id: str, frm: int, to: int) -> None:
    """What the Update Stage dialog posts after its PUT."""
    r = client.post(
        "/api/transitions",
        json={
            "module": "leads", "record_id": lead_id, "from": frm, "to": to,
            "reason": "test" if to > frm + 1 or to < frm else None,
            "is_skip": to > frm + 1, "is_reversal": to < frm, "attested": [],
        },
    )
    assert r.status_code in (200, 201), r.text


try:
    # ------------------------------------------------------------ accounts
    partial = {k: v for k, v in ACCOUNT.items() if k != "region"}
    r = client.post("/api/accounts", json=partial)
    check("an Account with Region empty is refused", refused(r), f"{r.status_code} {r.text[:200]}")
    check("…naming Region and nothing else", missing_of(r) == {"region"}, str(missing_of(r)))
    r = client.post("/api/accounts", json=ACCOUNT)
    check("a complete Account saves", r.status_code == 201, r.text[:200])
    account_id = r.json()["account_id"]
    created["accounts"].append(account_id)
    r = client.patch(f"/api/accounts/{account_id}", json={"segment": None})
    check("clearing a required Account field is refused", refused(r) and missing_of(r) == {"segment"}, r.text[:200])

    # ------------------------------------------------------------ contacts
    contact = {
        "full_name": "Required Fields Test Person",
        "job_title": "CIO",
        "account": account_id,
        "contact_role": "DECM_DECISION_MAKER",
    }
    r = client.post("/api/contacts", json=contact)
    check("a Contact with Engagement Owner empty is refused", refused(r) and "engagement_owner" in missing_of(r), r.text[:200])
    r = client.post("/api/contacts", json={**contact, "engagement_owner": admin.user_id})
    check("a complete Contact saves", r.status_code == 201, r.text[:200])
    if r.status_code == 201:
        created["contacts"].append(r.json()["contact_id"])
        STAGE_1["demo_attendees"] = [{"attendee": r.json()["contact_id"], "organisation": account_id}]

    # ----------------------------------------------------- lead at Stage 0
    r = client.post("/api/leads", json={"opportunity_name": "Required Fields Test", "project_stage": "0_CONNECT"})
    missing = missing_of(r)
    check("a Lead with only a name is refused", refused(r), f"{r.status_code} {r.text[:200]}")
    check("…asking for Stage 0's fields", {"end_client", "segment", "estimated_value"} <= missing, str(missing))
    check("…never the system's own (stage, status, percentages)",
          not missing & {"project_stage", "lead_status", "probability_pct", "progression_pct"}, str(missing))
    check("…nor a later stage's (Demo Date is Stage 1)", "demo_date" not in missing, str(missing))
    check("…nor a hidden one (Customer is Partner-sourced only)", "customer_partner_si" not in missing, str(missing))

    stage_0 = {
        "opportunity_name": "Required Fields Test",
        "project_stage": "0_CONNECT",
        "bd_owner": admin.user_id,
        "deal_source": "DIRECT",
        "end_client": account_id,
        "opportunity_type": "NEW_LOGO",
        "segment": "INFRASTRUCTURE",
        "theme": "SMART_CITIES",
        "sap_solution_suite": "SAP-CORE",
        "currency": "USD",
        "estimated_value": 100000,
        "remarks_notes": "Met at the expo.",
        "demo_agreed": True,
        "demo_scheduled_date": "2026-09-05",
        "expected_close_month": "2027-03-01",
    }
    r = client.post("/api/leads", json={**stage_0, "deal_source": "PARTNER_SOURCED"})
    check("Partner-sourced makes Customer (Partner / SI) required", "customer_partner_si" in missing_of(r), r.text[:200])

    r = client.post("/api/leads", json=stage_0)
    check("a complete Stage 0 Lead saves", r.status_code == 201, r.text[:300])
    lead_id = r.json()["lead_id"]
    created["leads"].append(lead_id)

    r = client.patch(f"/api/leads/{lead_id}", json={"remarks_notes": ""})
    check("clearing a Stage 0 field at Stage 0 is refused", refused(r), r.text[:200])

    # ------------------------------------------------------- moving on
    r = client.patch(f"/api/leads/{lead_id}", json={"project_stage": "1_DEMO"})
    check("0 -> 1 with Stage 0 complete moves (Stage 1's own fields not yet asked)", r.status_code == 200, r.text[:300])
    transition(lead_id, 0, 1)

    r = client.patch(f"/api/leads/{lead_id}", json={"overall_rag": "GREEN"})
    check("a save AT Stage 1 asks for Stage 1's fields", refused(r) and "demo_date" in missing_of(r), r.text[:300])

    r = client.patch(f"/api/leads/{lead_id}", json={"project_stage": "3_PRESCRIPTION"})
    check("skipping 1 -> 3 with Stage 1 empty is refused", refused(r) and "demo_date" in missing_of(r), r.text[:300])

    r = client.patch(f"/api/leads/{lead_id}", json={**STAGE_1, "project_stage": "3_PRESCRIPTION"})
    check("…and allowed once Stage 1 is filled, Stage 2 skipped", r.status_code == 200, r.text[:300])
    transition(lead_id, 1, 3)

    r = client.patch(f"/api/leads/{lead_id}", json={"overall_rag": "AMBER"})
    missing = missing_of(r)
    stage2 = {f["api_name"] for f in requirements.published(SessionLocal()).fields_of("leads")
              if requirements.due_stage(f) == 2 and f.get("requirement") == "Mandatory"}
    check("at Stage 3, the skipped Stage 2's fields are not asked for", not (missing & stage2), str(missing & stage2))

    # ------------------------------------------------ status and going back
    r = client.patch(f"/api/leads/{lead_id}", json={"lead_status": "ON_HOLD"})
    check("On Hold asks for its reason and nothing else",
          refused(r) and missing_of(r) == {"on_hold_reason"}, f"{r.status_code} {missing_of(r)}")
    r = client.patch(f"/api/leads/{lead_id}", json={"lead_status": "ON_HOLD", "on_hold_reason__s3": "Budget freeze"})
    check("On Hold with a reason saves, Stage 3 fields still empty", r.status_code == 200, r.text[:300])

    r = client.patch(f"/api/leads/{lead_id}", json={"lead_status": "OPEN", "project_stage": "1_DEMO", "stage_reversal_reason": "x"})
    check("moving back is never blocked by a stage's fields", r.status_code == 200, r.text[:300])

    # --------------------------------- a field made Optional and published
    with RegisterGuard() as guard, SessionLocal() as db:
        placement = db.scalar(
            select(FieldPlacement).where(
                FieldPlacement.module_key == "leads",
                FieldPlacement.api_name == "remarks_notes",
                FieldPlacement.status == "active",
            )
        )
        r = client.patch(f"/api/admin/metadata/placements/{placement.id}/required", json={"required": False})
        check("Administration can mark Remarks optional", r.status_code == 200, r.text[:200])

        body = {**stage_0, "opportunity_name": "Required Fields Test 2", "remarks_notes": None,
                "end_client": new_client("Required Fields Test Client 2")}
        r = client.post("/api/leads", json=body)
        check("…but until it is PUBLISHED, Remarks is still required", refused(r) and "remarks_notes" in missing_of(r), r.text[:200])

        r = client.post("/api/admin/metadata/publish", json={"note": "test: Remarks optional"})
        check("publish", r.status_code == 200, r.text[:200])
        r = client.post("/api/leads", json=body)
        check("once published, a Lead without Remarks saves", r.status_code == 201, r.text[:300])
        if r.status_code == 201:
            created["leads"].append(r.json()["lead_id"])
        spec = client.get("/api/spec").json()
        remarks = next(f for f in spec["fields"] if f["module"] == "leads" and f["api_name"] == "remarks_notes")
        check("…and /api/spec serves it as Optional to the browser", remarks["requirement"] == "Optional", remarks["requirement"])

        r = client.patch(f"/api/admin/metadata/placements/{placement.id}/required", json={"required": True})
        r2 = client.post("/api/admin/metadata/publish", json={"note": "test: Remarks required again"})
        check("put back and republished", r.status_code == 200 and r2.status_code == 200, r2.text[:200])
    guard.report()

    # ---------------------------------------------------- the paid pilot
    pilot_body = {**stage_0, "opportunity_name": "Required Fields Pilot",
                  "end_client": new_client("Required Fields Test Client 3")}
    r = client.post("/api/leads", json=pilot_body)
    pilot_id = r.json()["lead_id"]
    created["leads"].append(pilot_id)
    client.patch(f"/api/leads/{pilot_id}", json={"project_stage": "1_DEMO"})
    transition(pilot_id, 0, 1)
    paid = {**STAGE_1, "agreed_next_step": "POC_SCOPING", "pilot_commercial_model": "PAID", "pilot_fee": 25000,
            "data_site_access_confirmation_document": "https://example.com/site-access.pdf"}
    r = client.patch(f"/api/leads/{pilot_id}", json=paid)
    check("marking a pilot Paid asks for its PO Received Date",
          refused(r) and "pilot_po_received_date" in missing_of(r), f"{r.status_code} {missing_of(r)}")
    r = client.patch(f"/api/leads/{pilot_id}", json={**paid, "pilot_po_received_date": "2026-09-18"})
    check("…and with it, the Lead converts", r.status_code == 200 and r.json()["lead_status"] == "CONVERTED", r.text[:300])
    deal = client.get("/api/deals").json()
    pilot_deal = next((d for d in deal if d.get("parent_lead") == pilot_id), None)
    check("…into a Deal whose PO Received Date is that date (its Won date)",
          pilot_deal is not None and pilot_deal.get("po_received_date") == "2026-09-18", str(pilot_deal and pilot_deal.get("po_received_date")))
    if pilot_deal:
        r = client.patch(f"/api/deals/{pilot_deal['deal_id']}", json={"remarks": "pilot kicked off"})
        check("the POC/Pilot Deal saves at Stage 7 without Stage 7's fields", r.status_code == 200, r.text[:300])

finally:
    with SessionLocal() as db:
        ids = created["leads"]
        if ids:
            deals = [row[0] for row in db.execute(text("SELECT deal_id FROM deals WHERE parent_lead = ANY(:i)"), {"i": ids})]
            for table, col in (("deal_bid_commitments", "deal_id"), ("deal_expansion_use_cases", "deal_id")):
                db.execute(text(f"DELETE FROM {table} WHERE {col} = ANY(:d)"), {"d": deals})
            db.execute(text("DELETE FROM conversions WHERE source_id = ANY(:i)"), {"i": ids})
            db.execute(text("DELETE FROM deals WHERE deal_id = ANY(:d)"), {"d": deals})
            db.execute(text("DELETE FROM stage_transitions WHERE record_id = ANY(:i)"), {"i": ids})
            db.execute(text("DELETE FROM lead_demo_attendees WHERE lead_id = ANY(:i)"), {"i": ids})
            db.execute(text("DELETE FROM leads WHERE lead_id = ANY(:i)"), {"i": ids})
        if created["contacts"]:
            db.execute(text("DELETE FROM contacts WHERE contact_id = ANY(:i)"), {"i": created["contacts"]})
        if created["accounts"]:
            db.execute(text("DELETE FROM account_types WHERE account_id = ANY(:i)"), {"i": created["accounts"]})
            db.execute(text("DELETE FROM accounts WHERE account_id = ANY(:i)"), {"i": created["accounts"]})
        db.commit()

print(f"\n{len(passed)} passed, {len(failed)} failed")
for line in failed:
    print(f"  FAIL  {line}")
sys.exit(1 if failed else 0)
