"""
A payment milestone is agreed once and delivered against later.

    python run_tests.py test_deal_milestones.py

Decided 16 Sep 2026. The four milestone_—_* dates and Status were all asked for
on the Opportunity at Stage 6, where three of them cannot be known — and once
the Opportunity converts it is read-only, so Actual, Invoice and Payment
Received could never be filled in anywhere, ever. The schedule stays on the
Opportunity; delivery is recorded on the Deal at Stage 8, against the SAME rows
(app/routers/deals.py). What this proves is the boundary: a Deal may say when a
milestone happened and may not say what was agreed.
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
sign_in_as_admin(app)

failures: list[str] = []
created: dict[str, list[str]] = {"deals": [], "opportunities": [], "leads": []}

PLANNED = "milestone_—_planned_date"
ACTUAL = "milestone_—_actual_date"
INVOICE = "milestone_—_invoice_date"
RECEIVED = "milestone_—_payment_received_date"


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
    print("  PAYMENT MILESTONES — agreed on the Opportunity, delivered on the Deal")
    print("=" * 74)

    print("\n1  A schedule agreed at Stage 6")
    lead = post("/leads", {"opportunity_name": "Milestone probe", "project_stage": "3_PRESCRIPTION", "lead_status": "OPEN"}, "leads")
    check("the lead saves", lead.status_code == 201, lead.text[:300])
    lead_id = lead.json()["id"]

    r = post(
        "/opportunities",
        {
            "parent_lead": lead_id,
            "project_stage": "6_COMMERCIAL_EVAL",
            "lead_status": "OPEN",
            "arr_annual_recurring": 1_000_000,
            "contract_years": 1,
            "final_negotiated_value": 1_000_000,
            "conversion_note": "Milestone probe moved to Opportunities.",
            "payment_milestones": [
                {"milestone": "CONTRACT_SIGNING", "pct_of_contract": 10, "trigger": "Signed contract or LOI", PLANNED: "2026-10-01"},
                {"milestone": "DELIVERY", "pct_of_contract": 40, "trigger": "Delivery note at site", PLANNED: "2027-02-01"},
            ],
        },
        "opportunities",
    )
    check("the Opportunity saves with two milestones", r.status_code == 201, r.text[:300])
    opp_id = r.json()["id"]
    check("…and reads them back", len(get(f"/opportunities/{opp_id}")["payment_milestones"]) == 2)

    print("\n2  The Deal sees the same rows")
    deal = post(
        "/deals",
        {
            "deal_name": "Milestone probe",
            "parent_opportunity": opp_id,
            "deal_stage": "8_PROJECT_SUCCESS",
            "contract_value": 1_000_000,
            "conversion_note": "Milestone probe converted.",
        },
        "deals",
    )
    check("the Deal saves", deal.status_code == 201, deal.text[:300])
    deal_id = deal.json()["id"]

    rows = get(f"/deals/{deal_id}/payment-milestones")
    check("both milestones are on the Deal", len(rows) == 2, str(len(rows)))
    check(
        "…carrying the schedule agreed on the Opportunity",
        rows[0]["milestone"] == "CONTRACT_SIGNING" and rows[0]["pct_of_contract"] == 10 and rows[0][PLANNED] == "2026-10-01",
        str(rows[0])[:200],
    )
    check("…addressed by position", [r_["row_order"] for r_ in rows] == [0, 1], str([r_["row_order"] for r_ in rows]))
    check("…and delivery is empty until someone records it", rows[0][ACTUAL] is None and rows[0]["milestone_status"] is None)

    print("\n3  Delivery is recorded on the Deal")
    r = client.put(
        f"/api/deals/{deal_id}/payment-milestones",
        json=[
            {"row_order": 0, ACTUAL: "2026-10-03", INVOICE: "2026-10-05", RECEIVED: "2026-11-02", "milestone_status": "PAID"},
            {"row_order": 1},
        ],
    )
    check("the write is accepted", r.status_code == 200, r.text[:300])
    rows = get(f"/deals/{deal_id}/payment-milestones")
    check(
        "…and the dates are on the milestone",
        rows[0][ACTUAL] == "2026-10-03" and rows[0][INVOICE] == "2026-10-05" and rows[0][RECEIVED] == "2026-11-02" and rows[0]["milestone_status"] == "PAID",
        str(rows[0])[:240],
    )
    check(
        "…the agreed half is untouched",
        rows[0]["pct_of_contract"] == 10 and rows[0]["trigger"] == "Signed contract or LOI" and rows[0][PLANNED] == "2026-10-01",
        str(rows[0])[:240],
    )
    check("…and the other milestone stays undelivered", rows[1][ACTUAL] is None)
    check(
        "the Opportunity shows the same delivery — one set of rows, not a copy",
        get(f"/opportunities/{opp_id}")["payment_milestones"][0]["milestone_—_actual_date"] == "2026-10-03",
    )

    print("\n4  What the Deal may not do")
    r = client.put(
        f"/api/deals/{deal_id}/payment-milestones",
        json=[{"row_order": 0, "pct_of_contract": 90, "milestone": "HANDOVER", "trigger": "rewritten", PLANNED: "2030-01-01"}],
    )
    check("a write that tries to rewrite the schedule is accepted but ignores it", r.status_code == 200, r.text[:200])
    rows = get(f"/deals/{deal_id}/payment-milestones")
    check(
        "…the percentage, milestone, trigger and planned date all stand",
        rows[0]["pct_of_contract"] == 10
        and rows[0]["milestone"] == "CONTRACT_SIGNING"
        and rows[0]["trigger"] == "Signed contract or LOI"
        and rows[0][PLANNED] == "2026-10-01",
        str(rows[0])[:240],
    )
    check("…and clearing the delivery dates it DOES own works", rows[0][ACTUAL] is None)

    r = client.put(f"/api/deals/{deal_id}/payment-milestones", json=[{"row_order": 9, ACTUAL: "2026-10-03"}])
    check(
        "a milestone that does not exist is refused, not created",
        r.status_code == 422 and code_of(r) == "NO_SUCH_MILESTONE",
        f"{r.status_code} {r.text[:200]}",
    )
    check("…and no row was added", len(get(f"/deals/{deal_id}/payment-milestones")) == 2)

    print("\n5  A Deal converted straight from a Lead has no schedule")
    lead2 = post("/leads", {"opportunity_name": "Milestone probe — POC fast path", "project_stage": "3_PRESCRIPTION", "lead_status": "OPEN"}, "leads")
    check("the second lead saves", lead2.status_code == 201, lead2.text[:300])
    direct = post(
        "/deals",
        {
            "deal_name": "Milestone probe — POC fast path",
            "parent_lead": lead2.json()["id"],
            "deal_stage": "8_PROJECT_SUCCESS",
            "contract_value": 250_000,
            "conversion_note": "Paid POC, straight to a Deal.",
        },
        "deals",
    )
    check("the Deal saves without an Opportunity", direct.status_code == 201, direct.text[:300])
    if direct.status_code == 201:
        r = client.get(f"/api/deals/{direct.json()['id']}/payment-milestones")
        check(
            "…and says so rather than showing an empty table",
            r.status_code == 409 and code_of(r) == "NO_PARENT_OPPORTUNITY",
            f"{r.status_code} {r.text[:200]}",
        )

finally:
    print("\nCleanup (best effort — converted records guard each other by design)")
    for collection in ("deals", "opportunities", "leads"):
        for record_id in reversed(created[collection]):
            client.delete(f"/api/{collection}/{record_id}")

print()
if failures:
    print(f"{len(failures)} failed")
    for f in failures:
        print(f"  - {f}")
    sys.exit(1)
print("all passed")
