"""
Pursuit Groups, end to end — the EC story, as assertions.

    python run_tests.py test_pursuit_groups.py

Partner-A and Partner-B both bring the same project at EC. Astrikos pursues
both. Only the primary pursuit's value may reach a pipeline total, whatever
stage either is in, and whichever of them converts first. Each block below is
one chapter of the walkthrough agreed on 13 Sep 2026, and the forgery checks
matter as much as the happy path: a rule a client can switch off by sending a
field is not a rule.
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
created: dict[str, list[str]] = {
    "deals": [],
    "opportunities": [],
    "leads": [],
    "conflicts": [],
    "registrations": [],
    "accounts": [],
}


def check(label: str, condition: bool, detail: str = "") -> None:
    if condition:
        print(f"  pass  {label}")
    else:
        failures.append(f"{label}{' — ' + detail if detail else ''}")
        print(f"  FAIL  {label}{' — ' + detail if detail else ''}")


def code_of(response) -> str | None:
    detail = response.json().get("detail") if response.headers.get("content-type", "").startswith("application/json") else None
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


def row(collection: str, record_id: str) -> dict:
    return get(f"/{collection}/{record_id}")


def section(title: str) -> None:
    print(f"\n{title}\n" + "-" * len(title))


try:
    print("=" * 74)
    print("  PURSUIT GROUPS — one project, two partners, one number")
    print("=" * 74)

    # ------------------------------------------------------------ the cast
    section("0  The cast")
    ec = post("/accounts", {"account_name": "PG probe — EC", "account_type": ["END_CLIENT"]}, "accounts").json()["id"]
    pa = post("/accounts", {"account_name": "PG probe — Partner-A", "account_type": ["PARTNER_SI"]}, "accounts").json()["id"]
    pb = post("/accounts", {"account_name": "PG probe — Partner-B", "account_type": ["PARTNER_SI"]}, "accounts").json()["id"]
    other = post("/accounts", {"account_name": "PG probe — Other client"}, "accounts").json()["id"]
    reg_a = post("/registrations", {"partner": pa, "end_client": ec, "project_name": "EC smart city"}, "registrations").json()["id"]
    # The same project from a second partner: saving it raises the conflict
    # record (app/registration_matching.py) — it is not posted by hand any more.
    r = post(
        "/registrations",
        {"partner": pb, "end_client": ec, "project_name": "EC smart city", "raise_conflict_with": [reg_a]},
        "registrations",
    )
    reg_b = r.json()["id"]
    raised = r.json().get("raised_conflicts") or []
    check("accounts and registrations exist", all([ec, pa, pb, reg_a, reg_b]))
    check("saving the second registration raised the conflict", len(raised) == 1, r.text[:300])
    conflict_id = raised[0] if raised else ""
    if conflict_id:
        created["conflicts"].append(conflict_id)

    # ---------------------------------------------------- chapter 2: conflict
    section("2  The conflict is decided: both pursued")
    rationale = "Both partners hold a credible relationship; pursue both until the RFP names one."
    r = client.put(f"/api/conflicts/{conflict_id}", json={"decision": "BOTH_PURSUED", "decision_rationale": rationale})
    check(
        "Both pursued without a primary registration is refused",
        r.status_code == 422 and code_of(r) == "PRIMARY_REGISTRATION_REQUIRED",
        f"{r.status_code} {r.text[:200]}",
    )
    r = client.put(
        f"/api/conflicts/{conflict_id}",
        json={"decision": "BOTH_PURSUED", "primary_registration": reg_a, "decision_rationale": rationale},
    )
    check("Both pursued with Registration A as primary saves", r.status_code == 200, r.text[:300])
    conflict = r.json()
    group_id = conflict.get("pursuit_group")
    check("saving it created a Pursuit Group", bool(group_id), str(conflict))
    group = get(f"/pursuit-groups/{group_id}")
    check("the group names EC and no primary pursuit yet", group["end_client"] == ec and group["primary_pursuit"] is None)

    # --------------------------------------------- chapter 3: leads are created
    section("3  Partner-B's lead arrives first, then Partner-A's")
    r = post(
        "/leads",
        {
            "opportunity_name": "EC via Partner-B",
            "end_client": ec,
            "customer_partner_si": pb,
            "partner_deal_registration": reg_b,
            "project_stage": "1_DEMO",
            "lead_status": "OPEN",
            "currency": "USD",
            "estimated_value": 3_000_000,
            # Forged — neither may survive.
            "is_primary_pursuit": True,
            "pursuit_group": None,
        },
        "leads",
    )
    check("Partner-B's lead saves", r.status_code == 201, r.text[:300])
    lead_b = r.json()
    check("it joined the conflict's group by its registration", lead_b["pursuit_group"] == group_id)
    check("it is not primary — the forged flag was ignored", lead_b["is_primary_pursuit"] is False)
    check(
        "with no primary created yet, it does not count",
        lead_b["revenue"]["counted"] is False and lead_b["revenue"]["excluded"] == "no_primary",
        str(lead_b["revenue"]),
    )
    alerts = [a["code"] for a in get(f"/pursuit-groups/{group_id}")["alerts"]]
    check("the group says the primary has not been created yet", "NO_PRIMARY" in alerts, str(alerts))

    r = post(
        "/leads",
        {
            "opportunity_name": "EC via Partner-A",
            "end_client": ec,
            "customer_partner_si": pa,
            "partner_deal_registration": reg_a,
            "project_stage": "3_PRESCRIPTION",
            "lead_status": "OPEN",
            "currency": "USD",
            "estimated_value": 2_000_000,
        },
        "leads",
    )
    check("Partner-A's lead saves", r.status_code == 201, r.text[:300])
    lead_a = r.json()
    check("it joined as the primary, as the conflict decided", lead_a["is_primary_pursuit"] is True)
    lead_b = row("leads", lead_b["id"])
    check("Partner-B's lead is now counted out as a secondary", lead_b["revenue"]["excluded"] == "secondary")

    # ------------------------------ chapter 5: different stages, one number
    section("5  Prescription (A) and Demo Presentation (B): only A counts")
    rows = {r["id"]: r for r in get("/leads") if r["id"] in (lead_a["id"], lead_b["id"])}
    counted = sum(r["revenue"]["usd"] or 0 for r in rows.values() if r["revenue"]["counted"])
    check("EC contributes 2,000,000 to the pipeline, not 5,000,000", counted == 2_000_000, str(counted))
    check(
        "the Stage 1 row is visible but contributes nothing",
        rows[lead_b["id"]]["revenue"]["counted"] is False and rows[lead_b["id"]]["revenue"]["value"] == 3_000_000,
    )

    # -------------------------------------------- the duplicate question
    section("3b  A third lead for EC with no registration")
    r = post("/leads", {"opportunity_name": "EC, typed in directly", "end_client": ec, "lead_status": "OPEN"})
    check(
        "is refused as a possible duplicate, naming the open pursuits",
        r.status_code == 422 and code_of(r) == "POSSIBLE_DUPLICATE" and len(r.json()["detail"]["matches"]) == 2,
        f"{r.status_code} {r.text[:300]}",
    )
    r = post(
        "/leads",
        {
            "opportunity_name": "EC datacentre — a different project",
            "end_client": ec,
            "lead_status": "OPEN",
            "not_duplicate_reason": "Separate datacentre tender, not the smart city programme.",
        },
        "leads",
    )
    check("saves when the reason says it is a different project", r.status_code == 201, r.text[:300])
    check("and stays out of the group", r.json()["pursuit_group"] is None and r.json()["is_primary_pursuit"] is True)

    r = post(
        "/leads",
        {"opportunity_name": "EC via a third SI", "end_client": ec, "lead_status": "OPEN", "join_pursuit_of": lead_a["id"]},
        "leads",
    )
    check("a lead can join the group in the same save", r.status_code == 201 and r.json()["pursuit_group"] == group_id, r.text[:300])
    lead_d = r.json()
    check("one primary, any number of secondaries", len(get(f"/pursuit-groups/{group_id}")["members"]) == 3)

    r = client.post(f"/api/pursuit-groups/{group_id}/members/{lead_d['id']}/remove", json={"reason": "no"})
    check("removing without a real reason is refused", r.status_code == 422, r.text[:200])
    r = client.post(
        f"/api/pursuit-groups/{group_id}/members/{lead_d['id']}/remove",
        json={"reason": "Joined by mistake — this SI is bidding a different package."},
    )
    check("Remove from group works with a reason", r.status_code == 200 and len(r.json()["members"]) == 2, r.text[:300])
    lead_d = row("leads", lead_d["id"])
    check(
        "the removed lead is its own pursuit again, and the reason is kept",
        lead_d["pursuit_group"] is None and lead_d["is_primary_pursuit"] and "mistake" in (lead_d["not_duplicate_reason"] or ""),
    )

    # ---------------------------- the secondary converts first (the question)
    section("6/7  Partner-B converts to an Opportunity first")
    r = post(
        "/opportunities",
        {
            "parent_lead": lead_b["id"],
            "project_stage": "4_RFP_RFI",
            "lead_status": "OPEN",
            "arr_annual_recurring": 1_000_000,
            "contract_years": 3,
            "one_time_revenue": 100_000,
            # Forged — the Opportunity must take the Lead's place, not claim primary.
            "is_primary_pursuit": True,
        },
        "opportunities",
    )
    check("the Opportunity saves", r.status_code == 201, r.text[:300])
    opp_b = r.json()
    client.put(f"/api/leads/{lead_b['id']}", json={"lead_status": "CONVERTED"}).raise_for_status()
    check("it inherited the group and stayed secondary", opp_b["pursuit_group"] == group_id and opp_b["is_primary_pursuit"] is False)
    check("TCV is served on the list row — (1,000,000 × 3) + 100,000", opp_b["total_value_tcv"] == 3_100_000, str(opp_b.get("total_value_tcv")))
    opp_b = row("opportunities", opp_b["id"])
    check("and it still does not count", opp_b["revenue"]["counted"] is False and opp_b["revenue"]["excluded"] == "secondary")
    check("the converted lead is not counted either", row("leads", lead_b["id"])["revenue"]["excluded"] == "converted")
    group = get(f"/pursuit-groups/{group_id}")
    member_b = next(m for m in group["members"] if m["pursuit"] == lead_b["id"])
    check("the group describes pursuit B by its live record, the Opportunity", member_b["record_id"] == opp_b["id"])
    check("the secondary-is-ahead notice appears", "SECONDARY_AHEAD" in [a["code"] for a in group["alerts"]])

    # ------------------------------------------------------ chapter 8: blocks
    section("8  The primary cannot close while the secondary is open; a secondary cannot win")
    r = client.put(f"/api/leads/{lead_a['id']}", json={"lead_status": "CLOSED_LOST"})
    check("closing the primary is refused", r.status_code == 409 and code_of(r) == "PRIMARY_HAS_OPEN_SECONDARIES", r.text[:300])
    check("and nothing was written", row("leads", lead_a["id"])["lead_status"] == "OPEN")

    r = post("/deals", {"deal_name": "EC via Partner-B", "parent_opportunity": opp_b["id"], "contract_value": 3_000_000})
    check("a Deal from the secondary is refused", r.status_code == 409 and code_of(r) == "SECONDARY_CANNOT_WIN", r.text[:300])

    # ------------------------------------------- chapter 6: change primary
    section("6  The primary is changed to Partner-B, after both records moved on")
    r = client.post(f"/api/pursuit-groups/{group_id}/primary", json={"record_id": opp_b["id"], "reason": "ok"})
    check("changing primary without a real reason is refused", r.status_code == 422)
    r = client.post(
        f"/api/pursuit-groups/{group_id}/primary",
        json={"record_id": opp_b["id"], "reason": "Partner-B reached RFP; Partner-A has stalled at Prescription."},
    )
    check("changing primary by the Opportunity's id works", r.status_code == 200 and r.json()["primary_pursuit"] == lead_b["id"], r.text[:300])
    check("Partner-B's Opportunity now counts", row("opportunities", opp_b["id"])["revenue"]["counted"] is True)
    check("Partner-A's lead no longer does", row("leads", lead_a["id"])["revenue"]["excluded"] == "secondary")
    check("the converted, read-only lead was restamped too", row("leads", lead_b["id"])["is_primary_pursuit"] is True)
    history = get("/audit-log", record_id=opp_b["id"])
    stamped = [h for h in history if h["action"] == "pursuit"]
    check(
        "the Opportunity's history records who changed it and why",
        any(c["field"] == "__reason" and "stalled" in c["to"] for h in stamped for c in h["changed"])
        and all(h["actor"] == USER.user_id for h in stamped),
    )

    r = client.put(f"/api/leads/{lead_a['id']}", json={"lead_status": "CLOSED_LOST"})
    check("the old primary, now secondary, closes without a prompt", r.status_code == 200, r.text[:300])

    # ------------------------------------------------------- chapter 9: win
    section("9  Partner-B wins")
    r = post("/deals", {"deal_name": "EC via Partner-B", "parent_opportunity": opp_b["id"], "contract_value": 2_550_000})
    check(
        "X6.1: no Deal until Final Negotiated Value is recorded and equals TCV",
        r.status_code == 422 and code_of(r) == "FINAL_VALUE_MISMATCH",
        r.text[:300],
    )
    client.put(f"/api/opportunities/{opp_b['id']}", json={"final_negotiated_value": 3_000_000}).raise_for_status()
    r = post("/deals", {"deal_name": "EC via Partner-B", "parent_opportunity": opp_b["id"], "contract_value": 2_550_000})
    check("X6.1: a negotiated value that differs from TCV is refused", code_of(r) == "FINAL_VALUE_MISMATCH", r.text[:300])
    client.put(
        f"/api/opportunities/{opp_b['id']}", json={"arr_annual_recurring": 850_000, "final_negotiated_value": 2_650_000}
    ).raise_for_status()
    r = post("/deals", {"deal_name": "EC via Partner-B", "parent_opportunity": opp_b["id"], "contract_value": 2_550_000}, "deals")
    check("the Deal saves once TCV is updated to the agreed terms", r.status_code == 201, r.text[:300])
    deal = r.json()
    check("it inherited the group as the primary", deal["pursuit_group"] == group_id and deal["is_primary_pursuit"] is True)
    check("Deal Status is born Open", deal["lead_status"] == "OPEN")
    check("Actual Revenue is the contract value", deal["revenue"]["counted"] and deal["revenue"]["usd"] == 2_550_000, str(deal["revenue"]))

    r = client.put(f"/api/deals/{deal['id']}", json={"lead_status": "ON_HOLD"})
    check("Deal Status saves and comes back (it used to vanish)", r.status_code == 200 and row("deals", deal["id"])["lead_status"] == "ON_HOLD")
    r = client.put(f"/api/deals/{deal['id']}", json={"end_client": other})
    check("a grouped Deal cannot change End Client", r.status_code == 409 and code_of(r) == "REMOVE_FROM_GROUP_FIRST", r.text[:200])

    r = client.put(f"/api/conflicts/{conflict['id']}", json={"decision": "AWARDED_TO_REGISTRATION_A"})
    check("the conflict cannot leave Both pursued while the group holds pursuits", r.status_code == 409, r.text[:200])

    # ----------------------------------------------------------------- USD
    section("USD — local per 1 USD")
    r = post(
        "/leads",
        {"opportunity_name": "AED probe", "end_client": other, "lead_status": "OPEN", "currency": "AED", "fx_rate_at_entry": 3.6725, "estimated_value": 367_250},
        "leads",
    )
    check("an AED lead with a rate saves", r.status_code == 201, r.text[:300])
    check("367,250 AED at 3.6725 is 100,000 USD", r.json()["revenue"]["usd"] == 100_000, str(r.json().get("revenue")))
    r = post(
        "/leads",
        {"opportunity_name": "AED probe, no rate", "end_client": other, "lead_status": "OPEN", "currency": "AED", "estimated_value": 1, "not_duplicate_reason": "Probe only."},
        "leads",
    )
    check("without a rate it counts but is flagged, never guessed", r.json()["revenue"]["flag"] == "no_fx_rate" and r.json()["revenue"]["usd"] is None)
    r = post("/leads", {"opportunity_name": "Zero rate", "fx_rate_at_entry": 0})
    check("a zero rate is refused", r.status_code == 422)

    # -------------------------------------------------------------- dissolve
    section("Dissolve — one pursuit left")
    r = client.post(
        f"/api/pursuit-groups/{group_id}/members/{lead_a['id']}/remove",
        json={"reason": "Partner-A's pursuit is closed; nothing left to de-duplicate."},
    )
    check("removing the last secondary dissolves the group", r.status_code == 200 and r.json().get("dissolved") is True, r.text[:200])
    deal = row("deals", deal["id"])
    check("the Deal is its own pursuit again and still counts", deal["pursuit_group"] is None and deal["is_primary_pursuit"] is True)

finally:
    section("Cleanup")
    for collection in ("deals", "opportunities", "leads"):
        for record_id in reversed(created[collection]):
            record = client.get(f"/api/{collection}/{record_id}")
            if record.status_code == 200 and record.json().get("pursuit_group"):
                gid = record.json()["pursuit_group"]
                client.post(f"/api/pursuit-groups/{gid}/members/{record_id}/remove", json={"reason": "test cleanup"})
    for collection in ("deals", "opportunities", "leads", "conflicts", "registrations", "accounts"):
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
