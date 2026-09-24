"""
End-to-end acceptance test of Progression % / Probability %: one stage table,
one rule (app/progression.py), against the real database through the real API.

Run:  python run_tests.py test_progression.py     (against the disposable copy)
      python test_progression.py                    (refuses on the live DB)

Everything it creates is removed in the teardown.
"""

import sys

from sqlalchemy import text

from app.database import SessionLocal, engine

engine.echo = False

from test_db import require_test_database  # noqa: E402

# This test writes. Refuse to run against the database the prototype is
# demonstrated from — the copy is made by run_tests.py. See test_db.py.
require_test_database()

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from test_support import sign_in_as_admin  # noqa: E402

client = TestClient(app)
admin = sign_in_as_admin(app)

passed: list[str] = []
failed: list[str] = []

#: The decided table (13 Sep 2026): stage -> (progression %, probability %).
TABLE = {
    0: (5, 5), 1: (15, 10), 2: (25, 20), 3: (40, 30), 4: (50, 40),
    5: (70, 55), 6: (85, 70), 7: (95, 90), 8: (100, 100), 9: (100, 100),
}


def check(name: str, condition: bool, detail: str = "") -> None:
    if condition:
        passed.append(name)
        print(f"  PASS  {name}")
    else:
        failed.append(f"{name} — {detail}")
        print(f"  FAIL  {name} — {detail}")


def pair(row: dict) -> tuple[int, int]:
    return round(row["progression_pct"] * 100), round(row["probability_pct"] * 100)


created_leads: list[str] = []
created_opps: list[str] = []
created_deals: list[str] = []


def create_lead(**fields) -> dict:
    body = {"opportunity_name": "Stage Pair Test Pursuit", "project_stage": "0_CONNECT", **fields}
    r = client.post("/api/leads", json=body)
    assert r.status_code == 201, r.text
    row = r.json()
    created_leads.append(row["lead_id"])
    return row


def patch_lead(lead_id: str, **fields):
    return client.patch(f"/api/leads/{lead_id}", json=fields)


try:
    # --------------------------------------------------------- the table
    stages = client.get("/api/admin/metadata/stages").json()
    got = {s["stage"]: (s["progression_pct"], s["probability_pct"]) for s in stages}
    check("the stages table holds the decided pair for all ten stages", got == TABLE, str(got))
    check(
        "every value is a multiple of 5",
        all(v % 5 == 0 for p in got.values() for v in p if v is not None),
        str(got),
    )

    # ------------------------------------------------------------ create
    lead = create_lead()
    check("a Stage-0 create takes 5 / 5", pair(lead) == TABLE[0], str(pair(lead)))
    check("…with matching defaults and no override",
          lead["progression_default_pct"] == lead["progression_pct"]
          and lead["probability_default_pct"] == lead["probability_pct"]
          and lead["is_overridden"] is False, str(lead))
    lead_id = lead["lead_id"]

    # -------------------------------------------------------- stage moves
    row = patch_lead(lead_id, project_stage="4_RFP_RFI").json()
    check("a skip forward takes the target stage's pair (50 / 40)", pair(row) == TABLE[4], str(pair(row)))
    row = patch_lead(lead_id, project_stage="1_DEMO").json()
    check("a reversal takes the lower stage's pair (15 / 10)", pair(row) == TABLE[1], str(pair(row)))
    row = patch_lead(lead_id, overall_rag="GREEN").json()
    check("an unrelated save leaves the pair alone", pair(row) == TABLE[1], str(pair(row)))

    # -------------------------------------------------------- overrides
    r = patch_lead(lead_id, probability_pct=0.25)
    check("changing Probability with no reason -> 422", r.status_code == 422, f"{r.status_code} {r.text}")
    r = patch_lead(lead_id, progression_pct=0.30)
    check("changing Progression with no reason -> 422 too", r.status_code == 422, f"{r.status_code} {r.text}")
    r = patch_lead(lead_id, probability_pct=0.23, probability_override_justification__s1="x")
    check("a value not in steps of 5 -> 422", r.status_code == 422, f"{r.status_code} {r.text}")
    r = patch_lead(lead_id, probability_pct__s1=0.25)
    check("a per-stage copy of the number is refused", r.status_code == 422, f"{r.status_code} {r.text}")

    r = patch_lead(
        lead_id,
        probability_pct=0.25,
        progression_pct=0.20,
        probability_override_justification__s1="Incumbent — only credible bidder",
    )
    check("an override WITH a reason succeeds", r.status_code == 200, r.text)
    row = r.json()
    check("…and holds 20 / 25, flagged, attributed",
          pair(row) == (20, 25) and row["is_overridden"] is True
          and bool(row["overridden_by"]) and bool(row["overridden_date"]), str(row))
    check("…while the defaults still say what the stage set",
          round(row["probability_default_pct"] * 100) == 10, str(row["probability_default_pct"]))
    check("…and the reason is on the record for Stage 1",
          (row.get("probability_override_justification__s1") or "").startswith("Incumbent"), str(row))

    row = patch_lead(lead_id, overall_rag="AMBER").json()
    check("an override survives an ordinary save", pair(row) == (20, 25) and row["is_overridden"], str(row))

    row = patch_lead(lead_id, probability_pct=0.10, progression_pct=0.15).json()
    check("typing the stage's own values back clears the override",
          pair(row) == TABLE[1] and row["is_overridden"] is False and row["overridden_by"] is None, str(row))

    patch_lead(lead_id, probability_pct=0.15, probability_override_justification__s1="again")
    row = patch_lead(lead_id, project_stage="2_POC_PILOT").json()
    check("a stage move ends an override and takes the new pair",
          pair(row) == TABLE[2] and row["is_overridden"] is False, str(row))

    # ------------------------------------------------------------ status
    row = patch_lead(lead_id, lead_status="CLOSED_LOST").json()
    check("Closed Lost sets Probability to 0 with no reason asked",
          pair(row) == (TABLE[2][0], 0) and row["is_overridden"] is False, str(row))
    row = patch_lead(lead_id, lead_status="OPEN").json()
    check("reopening restores the stage's Probability", pair(row) == TABLE[2], str(pair(row)))

    r = patch_lead(lead_id, lead_status="POC_PILOT_DEAL")
    check("POC/Pilot Deal is refused as a Lead status", r.status_code == 422, f"{r.status_code} {r.text}")

    # ---------------------------------------------------------- paid pilot
    pilot = create_lead(opportunity_name="Paid Pilot Pursuit", project_stage="2_POC_PILOT",
                        agreed_next_step="POC_SCOPING")
    r = patch_lead(pilot["lead_id"], pilot_commercial_model="PAID", pilot_fee=75000)
    check("marking the pilot Paid saves", r.status_code == 200, r.text)
    check("…and the Lead is Converted", r.json()["lead_status"] == "CONVERTED", r.json()["lead_status"])

    with SessionLocal() as db:
        deals = db.execute(
            text("select deal_id, deal_stage, lead_status, contract_value, progression_pct, probability_pct "
                 "from deals where parent_lead = :lid"),
            {"lid": pilot["lead_id"]},
        ).fetchall()
        conversions = db.execute(
            text("select target_id from conversions where source_id = :lid"), {"lid": pilot["lead_id"]}
        ).fetchall()
    created_deals += [d[0] for d in deals]
    check("exactly one Deal is created", len(deals) == 1, str(deals))
    if deals:
        deal_id, stage, status_, value, prog, prob = deals[0]
        check("…at Stage 7 Close with status POC/Pilot Deal",
              stage == "7_CLOSE" and status_ == "POC_PILOT_DEAL", f"{stage} {status_}")
        check("…valued at the pilot fee", float(value) == 75000, str(value))
        check("…at Progression 95 / Probability 100", (round(prog * 100), round(prob * 100)) == (95, 100),
              f"{prog} {prob}")
        check("…with the conversion recorded", [c[0] for c in conversions] == [deal_id], str(conversions))

        deal = client.get(f"/api/deals/{deal_id}").json()
        check("the pilot Deal counts as revenue", deal["revenue"]["excluded"] is None, str(deal["revenue"]))
        # Metadata v2: these come from the locked Lead -> Deal (paid pilot)
        # rows of Conversion Mapping, not from code (G2, 24 Sep 2026).
        check("…named from the Lead, with \" — Paid POC\"", deal["deal_name"] == "Paid Pilot Pursuit — Paid POC",
              deal["deal_name"])
        from app import carry_forward
        from app.models import Deal as _Deal, Lead as _Lead
        with SessionLocal() as db:
            # This Lead was made without an End Client; lend it one for the
            # read, then put it back — nothing is committed.
            lead_row = db.get(_Lead, pilot["lead_id"])
            lead_row.end_client = db.execute(text("select account_id from accounts limit 1")).scalar()
            db.flush()
            shown = carry_forward.effective_value(db, "deals", db.get(_Deal, deal_id), "end_client")
            lead_client = lead_row.end_client
            db.rollback()
        # G1: the Deal shows its Lead's End Client. A pilot Deal has no
        # Opportunity, so this is reached through parent_lead directly.
        check("…showing its Lead's End Client, with no Opportunity in between",
              deal["end_client"] is None and shown == lead_client and shown is not None,
              f"stored={deal['end_client']} shown={shown} lead={lead_client}")
        row = client.patch(f"/api/deals/{deal_id}", json={"erp_reference": "ERP-1"}).json()
        check("saving the pilot Deal keeps it at 95 / 100", pair(row) == (95, 100), str(pair(row)))

    client.patch(f"/api/leads/{pilot['lead_id']}", json={"overall_rag": "GREEN"})
    with SessionLocal() as db:
        again = db.execute(text("select count(*) from deals where parent_lead = :lid"),
                           {"lid": pilot["lead_id"]}).scalar()
    check("saving the Lead again never creates a second Deal", again == 1, str(again))

    # ------------------------------------------------ opportunities + deals
    r = client.post("/api/opportunities", json={"parent_lead": lead_id, "project_stage": "5_TECHNICAL_EVAL"})
    check("an Opportunity create succeeds", r.status_code == 201, r.text)
    opp = r.json()
    created_opps.append(opp["opportunity_id"])
    check("an Opportunity takes its stage's pair (70 / 55)", pair(opp) == TABLE[5], str(pair(opp)))
    r = client.patch(f"/api/opportunities/{opp['opportunity_id']}", json={"lead_status": "POC_PILOT_DEAL"})
    check("POC/Pilot Deal is refused as an Opportunity status", r.status_code == 422, f"{r.status_code}")

finally:
    with SessionLocal() as db:
        for deal_id in created_deals:
            db.execute(text("delete from deals where deal_id = :id"), {"id": deal_id})
        for opp_id in created_opps:
            db.execute(text("delete from opportunities where opportunity_id = :id"), {"id": opp_id})
        for lead_id in created_leads:
            db.execute(text("delete from conversions where source_id = :id"), {"id": lead_id})
            db.execute(text("delete from leads where lead_id = :id"), {"id": lead_id})
        db.commit()

print()
print(f"  {len(passed)} passed, {len(failed)} failed")
if failed:
    print("\nFAILURES:")
    for f in failed:
        print(f"  - {f}")
sys.exit(1 if failed else 0)
