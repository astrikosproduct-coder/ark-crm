"""
The Partners module's lifecycle, end to end — conflicts raised on save, delete
rules, and withdrawal with every knock-on on the pursuit and its group.

    python run_tests.py test_partner_lifecycle.py

Each block is one decision of 14 Sep 2026. The knock-on blocks are the ones
that matter most: closing the PRIMARY pursuit of a group when a partner
withdraws must never leave the project with nothing that counts.
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

failures: list[str] = []
created: dict[str, list[str]] = {"leads": [], "conflicts": [], "registrations": [], "accounts": []}

TODAY = today_company()
RATIONALE = "Partner-A runs the incumbent O&M contract; minutes of 10 Sep attached."


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


def get(path: str) -> dict:
    r = client.get(f"/api{path}")
    r.raise_for_status()
    return r.json()


def account(name: str, types: list[str]) -> str:
    return post("/accounts", {"account_name": f"Lifecycle probe — {name}", "account_type": types}, "accounts").json()["id"]


def registration(partner: str, client_id: str, project: str, days_ago: int = 0, **extra):
    body = {
        "partner": partner,
        "end_client": client_id,
        "project_name": project,
        "submitted_date": (TODAY - timedelta(days=days_ago)).isoformat(),
        "registration_status": "SUBMITTED",
        **extra,
    }
    return post("/registrations", body, "registrations")


def lead_for(reg_id: str, partner: str, client_id: str, name: str):
    r = post(
        "/leads",
        {
            "opportunity_name": name,
            "end_client": client_id,
            "customer_partner_si": partner,
            "deal_source": "PARTNER_SOURCED",
            "partner_deal_registration": reg_id,
            "project_stage": "0_CONNECT",
            "lead_status": "OPEN",
        },
        "leads",
    )
    return r


def conflict_between(reg_a: str, reg_b: str) -> dict | None:
    for c in get("/conflicts"):
        if {c["registration_a"], c["registration_b"]} == {reg_a, reg_b}:
            return c
    return None


def section(title: str) -> None:
    print(f"\n{title}\n" + "-" * len(title))


try:
    print("=" * 74)
    print("  PARTNER LIFECYCLE — conflicts, delete, withdraw")
    print("=" * 74)

    ec = account("EC", ["END_CLIENT"])
    pa = account("Partner-A", ["PARTNER_SI"])
    pb = account("Partner-B", ["PARTNER_SI"])
    pc = account("Partner-C", ["PARTNER_SI"])

    # ---------------------------------------------------------------- Q3
    section("1  A similar project is caught on save")
    r = registration(pa, ec, "Lifecycle probe Integrated Command & Control Centre", days_ago=2)
    check("the first registration saves", r.status_code == 201, r.text[:300])
    reg_a = r.json()["id"]

    r = registration(pb, ec, "Lifecycle probe ICCC")
    check(
        "an acronym of the same project is refused with the match",
        r.status_code == 422 and code_of(r) == "POSSIBLE_CONFLICT",
        f"{r.status_code} {r.text[:300]}",
    )
    matches = r.json()["detail"].get("matches", []) if r.status_code == 422 else []
    check(
        "the match is described by name, not only by id",
        any(m["registration_id"] == reg_a and m["partner_name"] and not m["same_partner"] for m in matches),
        str(matches)[:300],
    )

    r = registration(pb, ec, "Lifecycle probe ICCC", raise_conflict_with=[reg_a])
    check("'Same project — raise conflict' saves the registration", r.status_code == 201, r.text[:300])
    reg_b = r.json()["id"]
    check("…and raises exactly one conflict", len(r.json().get("raised_conflicts") or []) == 1, r.text[:300])
    conflict = conflict_between(reg_a, reg_b)
    check("the conflict record exists, still open", conflict is not None and not conflict["decision"], str(conflict))
    created["conflicts"].append(conflict["id"])
    check("Registration A is the one submitted first", conflict["registration_a"] == reg_a, str(conflict))
    check("Who Registered First is derived: Registration A", conflict["who_registered_first"] == "REGISTRATION_A")
    check("it is named after the partners", conflict["name"].startswith("Conflict: ") and " vs " in conflict["name"])

    r = registration(pc, ec, "Lifecycle probe water network")
    check("a different project at the same client is not asked about", r.status_code == 201, r.text[:300])
    reg_c = r.json()["id"]

    r = registration(pc, ec, "Lifecycle probe command and control centre", not_conflict_reason="A separate control-room fit-out package.")
    check("'Different project' with a reason saves", r.status_code == 201, r.text[:300])
    reg_d = r.json()["id"]
    check("…and both sides remember the pair", reg_a in r.json()["not_conflict_with"] and reg_d in get(f"/registrations/{reg_a}")["not_conflict_with"])
    check("…so it is never offered again", get(f"/registrations/{reg_d}/possible-conflicts") == [])

    r = registration(pa, ec, "Lifecycle probe ICCC", raise_conflict_with=[reg_a])
    check(
        "the same partner twice cannot be raised as a conflict",
        r.status_code == 422 and code_of(r) == "SAME_PARTNER_NOT_A_CONFLICT",
        f"{r.status_code} {r.text[:200]}",
    )

    # ---------------------------------------------------------------- Q5
    section("2  Adjudication needs its evidence")
    cid = conflict["id"]
    r = client.put(f"/api/conflicts/{cid}", json={"decision": "AWARDED_TO_REGISTRATION_A"})
    check("a decision without a rationale is refused", r.status_code == 422 and code_of(r) == "DECISION_RATIONALE_REQUIRED", r.text[:200])
    r = post("/conflicts", {"registration_a": reg_a, "registration_b": reg_b})
    check("a second conflict for the same pair is refused", r.status_code == 409 and code_of(r) == "CONFLICT_EXISTS", r.text[:200])
    r = client.put(
        f"/api/conflicts/{cid}",
        json={
            "decision": "BOTH_PURSUED",
            "primary_registration": reg_a,
            "decision_rationale": RATIONALE,
            "stronger_client_relationship": "REGISTRATION_A",
            "better_delivery_capability": "REGISTRATION_B",
            "who_registered_first": "REGISTRATION_B",
        },
    )
    check("Both pursued with a rationale saves", r.status_code == 200, r.text[:300])
    check("a forged Who Registered First is ignored", r.json().get("who_registered_first") == "REGISTRATION_A")
    group_id = r.json().get("pursuit_group")
    check("the decision created a pursuit group", bool(group_id))
    group = get(f"/pursuit-groups/{group_id}")
    check("the group has a name, not only an id", bool(group.get("name")) and group["name"] != group_id, str(group.get("name")))

    # ---------------------------------------------------------------- Q1 delete
    section("3  Delete — only while nothing depends on it")
    r = lead_for(reg_a, pa, ec, "Lifecycle probe — Partner-A pursuit")
    check("a lead is created from Registration A", r.status_code == 201, r.text[:300])
    lead_a = r.json()["id"]
    check("…and joins the group as primary", r.json()["pursuit_group"] == group_id and r.json()["is_primary_pursuit"] is True)

    r = client.delete(f"/api/registrations/{reg_a}")
    check("a registration with a lead cannot be deleted", r.status_code == 409 and code_of(r) == "REGISTRATION_HAS_DEPENDENTS", r.text[:200])
    detail = r.json()["detail"] if r.status_code == 409 else {}
    check("the refusal names the lead", any(l["name"] == "Lifecycle probe — Partner-A pursuit" for l in detail.get("leads", [])), str(detail)[:300])
    check("…and the conflict", len(detail.get("conflicts", [])) == 1)

    deleted_number = int(reg_c.split("-")[1])
    r = client.delete(f"/api/registrations/{reg_c}")
    check("a registration nothing depends on deletes", r.status_code == 204, r.text[:200])
    if r.status_code == 204:
        created["registrations"].remove(reg_c)
    r = registration(pc, ec, "Lifecycle probe street lighting")
    check("the next registration saves", r.status_code == 201, r.text[:200])
    check("…with a new number — a deleted id is never reused", int(r.json()["id"].split("-")[1]) > deleted_number, r.json()["id"])

    # ------------------------------------------------ Q1 withdraw, knock-on 2
    section("4  Withdraw the primary with no other open pursuit")
    preview = get(f"/registrations/{reg_a}/withdrawal")
    check("the preview sees the primary pursuit", preview["pursuit"] and preview["pursuit"]["is_primary"] is True, str(preview)[:300])
    check("…with no other open pursuit", preview["pursuit"]["other_open"] == [])
    check("…and names who takes over as primary", (preview["primary_handover"] or {}).get("registration_id") == reg_b, str(preview)[:300])

    r = client.post(f"/api/registrations/{reg_a}/withdraw", json={"reason": "Partner-A lost its local licence."})
    check("withdrawing without saying what happens to the pursuit is refused", r.status_code == 422 and code_of(r) == "PURSUIT_ACTION_REQUIRED", r.text[:200])
    check("…and nothing changed", get(f"/registrations/{reg_a}")["registration_status"] == "SUBMITTED")

    r = client.put(f"/api/registrations/{reg_a}", json={"registration_status": "WITHDRAWN"})
    check("Withdrawn cannot be typed in", r.status_code == 422 and code_of(r) == "USE_WITHDRAW_ACTION", r.text[:200])

    r = client.post(
        f"/api/registrations/{reg_a}/withdraw",
        json={"reason": "Partner-A lost its local licence.", "pursuit_action": "close"},
    )
    check("withdraw + close as lost saves", r.status_code == 200, r.text[:300])
    reg = get(f"/registrations/{reg_a}")
    check("the registration is Withdrawn, dated, with its reason", reg["registration_status"] == "WITHDRAWN" and reg["withdrawn_date"] == TODAY.isoformat() and reg["withdrawal_reason"])
    lead = get(f"/leads/{lead_a}")
    check("the lead is Closed Lost", lead["lead_status"] == "CLOSED_LOST", str(lead.get("lead_status")))
    check("…with reason Partner withdrew at its stage", lead.get("closed_lost_reason_code__s0") == "PARTNER_WITHDRAWN", str({k: v for k, v in lead.items() if "closed_lost" in k}))
    conflict = get(f"/conflicts/{cid}")
    check("the conflict's primary registration moved to Registration B", conflict["primary_registration"] == reg_b, str(conflict.get("primary_registration")))
    group = get(f"/pursuit-groups/{group_id}")
    check("the group has no primary pursuit until B's lead exists", group["primary_pursuit"] is None and group["primary_registration"] == reg_b, str(group)[:300])

    r = client.put(f"/api/registrations/{reg_a}", json={"estimated_value": 1})
    check("a withdrawn registration is read-only", r.status_code == 409 and code_of(r) == "REGISTRATION_WITHDRAWN", r.text[:200])
    r = lead_for(reg_a, pa, ec, "Lifecycle probe — late lead")
    check("a lead cannot be linked to a withdrawn registration", r.status_code == 422 and code_of(r) == "REGISTRATION_NOT_LIVE", r.text[:200])

    r = lead_for(reg_b, pb, ec, "Lifecycle probe — Partner-B pursuit")
    check("Registration B's lead is created", r.status_code == 201, r.text[:300])
    lead_b = r.json()["id"]
    check("…and becomes the primary — its value counts", r.json()["is_primary_pursuit"] is True and r.json()["pursuit_group"] == group_id, str(r.json().get("is_primary_pursuit")))

    # ------------------------------------------------ Q1 withdraw, knock-on 1
    section("5  Withdraw the primary while another pursuit is open")
    ec2 = account("EC two", ["END_CLIENT"])
    rx = registration(pa, ec2, "Lifecycle probe district cooling platform", days_ago=3).json()["id"]
    ry = registration(pb, ec2, "Lifecycle probe district cooling platform", raise_conflict_with=[rx]).json()["id"]
    cxy = conflict_between(rx, ry)
    created["conflicts"].append(cxy["id"])
    r = client.put(
        f"/api/conflicts/{cxy['id']}",
        json={"decision": "BOTH_PURSUED", "primary_registration": rx, "decision_rationale": RATIONALE},
    )
    check("second group: both pursued, X primary", r.status_code == 200, r.text[:200])
    group2 = r.json()["pursuit_group"]
    lx = lead_for(rx, pa, ec2, "Lifecycle probe — X pursuit").json()["id"]
    ly = lead_for(ry, pb, ec2, "Lifecycle probe — Y pursuit").json()["id"]
    check("X is primary, Y secondary", get(f"/leads/{lx}")["is_primary_pursuit"] and not get(f"/leads/{ly}")["is_primary_pursuit"])

    preview = get(f"/registrations/{rx}/withdrawal")
    check("the preview lists the open secondary by name", any(m["name"] == "Lifecycle probe — Y pursuit" for m in preview["pursuit"]["other_open"]), str(preview)[:300])

    r = client.post(f"/api/registrations/{rx}/withdraw", json={"reason": "Partner-X exited the market.", "pursuit_action": "close"})
    check("closing the primary without naming a new one is refused", r.status_code == 409 and code_of(r) == "NEW_PRIMARY_REQUIRED", r.text[:200])
    check("…and nothing was written", get(f"/registrations/{rx}")["registration_status"] == "SUBMITTED" and get(f"/leads/{lx}")["lead_status"] == "OPEN")

    r = client.post(
        f"/api/registrations/{rx}/withdraw",
        json={"reason": "Partner-X exited the market.", "pursuit_action": "close", "new_primary": ly},
    )
    check("naming the new primary, it saves in one go", r.status_code == 200, r.text[:300])
    check("X's lead is Closed Lost", get(f"/leads/{lx}")["lead_status"] == "CLOSED_LOST")
    check("Y's lead is now primary", get(f"/leads/{ly}")["is_primary_pursuit"] is True)
    check("the group says so", get(f"/pursuit-groups/{group2}")["primary_pursuit"] == ly)
    check("the conflict's primary registration followed", get(f"/conflicts/{cxy['id']}")["primary_registration"] == ry)

    # ------------------------------------------------------ hold and keep
    section("6  On hold, and keep pursuing")
    ec3 = account("EC three", ["END_CLIENT"])
    rh = registration(pa, ec3, "Lifecycle probe metro signalling").json()["id"]
    lh = lead_for(rh, pa, ec3, "Lifecycle probe — hold pursuit").json()["id"]
    r = client.post(f"/api/registrations/{rh}/withdraw", json={"reason": "Partner paused its bid team.", "pursuit_action": "hold"})
    check("withdraw + hold saves", r.status_code == 200, r.text[:300])
    lead = get(f"/leads/{lh}")
    check("the lead is On Hold", lead["lead_status"] == "ON_HOLD")
    check("…with the reason recorded at its stage", "Partner withdrew" in str(lead.get("on_hold_reason__s0")), str(lead.get("on_hold_reason__s0")))

    ec4 = account("EC four", ["END_CLIENT"])
    rk = registration(pb, ec4, "Lifecycle probe port operations").json()["id"]
    lk = lead_for(rk, pb, ec4, "Lifecycle probe — keep pursuit").json()["id"]
    r = client.post(f"/api/registrations/{rk}/withdraw", json={"reason": "Partner withdrew; ARK bids direct.", "pursuit_action": "keep"})
    check("withdraw + keep saves", r.status_code == 200, r.text[:300])
    lead = get(f"/leads/{lk}")
    check("the lead stays open", lead["lead_status"] == "OPEN")
    check("…and no longer names the withdrawn partner", lead["customer_partner_si"] is None)
    check("…but still says how it arrived", lead["deal_source"] == "PARTNER_SOURCED")

    # ------------------------------------------------- Expected Timeline
    section("7  Expected Timeline is a date")
    ec5 = account("EC five", ["END_CLIENT"])
    due = (TODAY + timedelta(days=90)).isoformat()
    r = registration(pc, ec5, "Lifecycle probe expected timeline", expected_timeline=due)
    check("a date saves", r.status_code == 201, r.text[:300])
    check("…and reads back as that date", r.status_code == 201 and r.json().get("expected_timeline") == due, r.text[:200])
    r = registration(pc, ec5, "Lifecycle probe free-text timeline", expected_timeline="RFP Q1 2027")
    check("free text is refused", r.status_code == 422, r.text[:200])

    ec8, ec9 = account("EC eight", ["END_CLIENT"]), account("EC nine", ["END_CLIENT"])
    r = registration(pc, ec8, "Lifecycle probe harbour lighting")
    check("a registration sent without a currency is USD", r.status_code == 201 and r.json().get("currency") == "USD", r.text[:200])
    r = registration(pc, ec9, "Lifecycle probe metro ticketing", currency="AED")
    check("a currency the user picked is kept", r.status_code == 201 and r.json().get("currency") == "AED", r.text[:200])

    # ------------------------------------------------------- lead defaults
    section("8  A new lead starts Open, in USD, as its own primary pursuit")
    ec6 = account("EC six", ["END_CLIENT"])
    r = post("/leads", {"opportunity_name": "Lifecycle probe — defaults", "end_client": ec6, "project_stage": "0_CONNECT", "estimated_value": 250000}, "leads")
    check("a lead sent with no status or currency saves", r.status_code == 201, r.text[:300])
    body = r.json() if r.status_code == 201 else {}
    check("…its status is Open", body.get("lead_status") == "OPEN", str(body.get("lead_status")))
    check("…its currency is USD at rate 1", body.get("currency") == "USD" and float(body.get("fx_rate_at_entry") or 0) == 1, str(body)[:200])
    check("…it is primary", body.get("is_primary_pursuit") is True)
    revenue = body.get("revenue")
    check("…and its value counts toward pipeline", revenue is None or (revenue.get("counted") and revenue.get("usd") == 250000), str(revenue))

    ec7 = account("EC seven", ["END_CLIENT"])
    r = post("/leads", {"opportunity_name": "Lifecycle probe — AED", "end_client": ec7, "project_stage": "0_CONNECT", "currency": "AED", "fx_rate_at_entry": 3.6725}, "leads")
    check("a currency the user chose is kept", r.status_code == 201 and r.json().get("currency") == "AED", r.text[:200])

    rr = registration(pc, ec6, "Lifecycle probe registration-created lead").json()["id"]
    r = post("/leads", {"opportunity_name": "Lifecycle probe — from registration", "end_client": ec6, "customer_partner_si": pc, "deal_source": "PARTNER_SOURCED", "partner_deal_registration": rr, "project_stage": "0_CONNECT", "not_duplicate_reason": "Separate probe project."}, "leads")
    check("a lead created the way a registration creates one is Open and USD", r.status_code == 201 and r.json().get("lead_status") == "OPEN" and r.json().get("currency") == "USD", r.text[:300])

    # ------------------------------------- Partners' answer, and no further
    section("9  A registration's 'different project' answer reaches its lead — and only its lead")
    partners_reason = "A separate municipal tender, not the other partner's package."

    ec10 = account("EC ten", ["END_CLIENT"])
    r1 = registration(pa, ec10, "Lifecycle probe smart parking", days_ago=2).json()["id"]
    r = registration(pb, ec10, "Lifecycle probe smart parking", not_conflict_reason=partners_reason)
    check("a similar registration saves as a different project", r.status_code == 201 and r1 in (r.json().get("not_conflict_with") or []), r.text[:300])
    r2 = r.json()["id"]
    l1 = lead_for(r1, pa, ec10, "Lifecycle probe — parking A")
    check("the first registration's lead saves", l1.status_code == 201, l1.text[:300])
    l2 = lead_for(r2, pb, ec10, "Lifecycle probe — parking B")
    check("the second's lead is not asked about the pursuit Partners already ruled on", l2.status_code == 201, l2.text[:300])
    check("…and carries Partners' reason as its Not a Duplicate Reason", l2.status_code == 201 and l2.json().get("not_duplicate_reason") == partners_reason, l2.text[:300])

    ec11 = account("EC eleven", ["END_CLIENT"])
    r3 = registration(pa, ec11, "Lifecycle probe water metering", days_ago=2).json()["id"]
    r = registration(pb, ec11, "Lifecycle probe water metering", not_conflict_reason=partners_reason)
    check("a second pair saves as a different project", r.status_code == 201 and r3 in (r.json().get("not_conflict_with") or []), r.text[:300])
    r4 = r.json()["id"]
    l3 = lead_for(r3, pa, ec11, "Lifecycle probe — metering A")
    check("its first lead saves", l3.status_code == 201, l3.text[:300])
    direct = post("/leads", {"opportunity_name": "Lifecycle probe — metering direct", "end_client": ec11, "project_stage": "0_CONNECT", "not_duplicate_reason": "Direct bid for the billing system."}, "leads")
    check("a direct lead at the same End Client saves with its own reason", direct.status_code == 201, direct.text[:300])

    r = lead_for(r4, pb, ec11, "Lifecycle probe — metering B")
    detail = r.json().get("detail", {}) if r.status_code == 422 else {}
    check("a pursuit Partners never compared against is still asked about", r.status_code == 422 and code_of(r) == "POSSIBLE_DUPLICATE", f"{r.status_code} {r.text[:300]}")
    check("…listing only that pursuit, not the one Partners ruled on", [m["record_id"] for m in detail.get("matches", [])] == [direct.json().get("id")], str(detail.get("matches"))[:300])
    check("…with Partners' reason offered to pre-fill the answer", detail.get("suggested_reason") == partners_reason, str(detail.get("suggested_reason")))
    r = post("/leads", {"opportunity_name": "Lifecycle probe — metering B", "end_client": ec11, "customer_partner_si": pb, "deal_source": "PARTNER_SOURCED", "partner_deal_registration": r4, "project_stage": "0_CONNECT", "lead_status": "OPEN", "not_duplicate_reason": partners_reason}, "leads")
    check("confirming that reason saves the lead", r.status_code == 201, r.text[:300])

finally:
    section("Cleanup")
    for record_id in reversed(created["leads"]):
        record = client.get(f"/api/leads/{record_id}")
        if record.status_code == 200 and record.json().get("pursuit_group"):
            gid = record.json()["pursuit_group"]
            client.post(f"/api/pursuit-groups/{gid}/members/{record_id}/remove", json={"reason": "test cleanup"})
    for collection in ("leads", "conflicts", "registrations", "accounts"):
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
