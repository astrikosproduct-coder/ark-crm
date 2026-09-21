"""
The management dashboard, as assertions.

    python run_tests.py test_dashboard.py

The test database is a copy of the live one and already holds pursuits, so
every check here is a DIFFERENCE: read the dashboard, add records whose effect
is known, read it again. Nothing asserts an absolute total.
"""

import os
import sys
from calendar import monthrange
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from fastapi.testclient import TestClient  # noqa: E402

import test_db  # noqa: E402

test_db.require_test_database()

from app.main import app  # noqa: E402
from app.routers import dashboard as dashboard_module  # noqa: E402
from test_support import sign_in_as_admin  # noqa: E402

client = TestClient(app)
USER = sign_in_as_admin(app)

failures: list[str] = []
created: dict[str, list[str]] = {"deals": [], "opportunities": [], "leads": []}


def check(label: str, condition: bool, detail: str = "") -> None:
    if condition:
        print(f"  pass  {label}")
    else:
        failures.append(f"{label}{' — ' + detail if detail else ''}")
        print(f"  FAIL  {label}{' — ' + detail if detail else ''}")


def close(a: float, b: float) -> bool:
    return abs(a - b) < 0.01


def post(path: str, body: dict, collection: str):
    r = client.post(f"/api{path}", json=body)
    if r.status_code == 201:
        created[collection].append(r.json()["id"])
    return r


def put(path: str, body: dict):
    return client.put(f"/api{path}", json=body)


def dash(**params) -> dict:
    params = {k: (v.isoformat() if isinstance(v, date) else v) for k, v in params.items()}
    r = client.get("/api/dashboard", params=params)
    r.raise_for_status()
    return r.json()


def code_of(response) -> str | None:
    detail = response.json().get("detail")
    return detail.get("code") if isinstance(detail, dict) else None


def funnel_usd(d: dict, stage: int) -> float:
    return next(s["usd"] for s in d["funnel"] if s["stage"] == stage)


def rag_usd(d: dict, key: str) -> float:
    return next((b["usd"] for b in d["rag"] if b["rag"] == key), 0.0)


def reason_count(d: dict, key: str) -> int:
    return next((b["count"] for b in d["loss_reasons"] if b["reason"] == key), 0)


def listed(d: dict, widget: str, record_id: str) -> bool:
    return any(i["record_id"] == record_id for i in d[widget]["items"])


def section(title: str) -> None:
    print(f"\n{title}\n" + "-" * len(title))


try:
    print("=" * 74)
    print("  DASHBOARD — every widget moves by exactly what was added")
    print("=" * 74)

    # ------------------------------------------------------------ quarters
    section("0  Quarters and the date range")
    check("the fiscal year starts in April (decided 15 Sep 2026)", dashboard_module.FISCAL_YEAR_START_MONTH == 4)
    check(
        "1 Apr 2027 opens Q1 FY2027-28",
        dashboard_module.quarter_of(date(2027, 4, 1)) == (date(2027, 4, 1), date(2027, 6, 30), "Q1 FY2027-28"),
    )
    saved = dashboard_module.FISCAL_YEAR_START_MONTH
    try:
        dashboard_module.FISCAL_YEAR_START_MONTH = 1
        check("on calendar quarters, 14 Sep 2026 is Q3 2026", dashboard_module.quarter_of(date(2026, 9, 14)) == (date(2026, 7, 1), date(2026, 9, 30), "Q3 2026"))
        check("and 31 Dec is the last day of Q4", dashboard_module.quarter_of(date(2026, 12, 31))[1] == date(2026, 12, 31))
        dashboard_module.FISCAL_YEAR_START_MONTH = 4
        check(
            "with an April year, Sep is Q2 FY2026-27",
            dashboard_module.quarter_of(date(2026, 9, 14)) == (date(2026, 7, 1), date(2026, 9, 30), "Q2 FY2026-27"),
        )
        check(
            "and February is Q4 of the same fiscal year",
            dashboard_module.quarter_of(date(2027, 2, 1)) == (date(2027, 1, 1), date(2027, 3, 31), "Q4 FY2026-27"),
        )
    finally:
        dashboard_module.FISCAL_YEAR_START_MONTH = saved
    check(
        "a Jan-Apr 2027 range draws four forecast months",
        [m.isoformat() for m in dashboard_module.forecast_months(date(2027, 1, 1), date(2027, 4, 30), date(2026, 9, 14))]
        == ["2027-01-01", "2027-02-01", "2027-03-01", "2027-04-01"],
    )
    check(
        "a range starting mid-month still holds that month's closes",
        dashboard_module.close_month_in(date(2027, 1, 1), date(2027, 1, 15), date(2027, 4, 30)),
    )

    before = dash()
    today = date.fromisoformat(before["as_of"])
    month0 = today.replace(day=1)
    month_end = today.replace(day=monthrange(today.year, today.month)[1])
    next_year = (date(today.year + 1, 1, 1), date(today.year + 1, 4, 30))
    check("the endpoint answers with every widget", all(k in before for k in ("kpis", "funnel", "forecast", "rag", "ageing", "loss_reasons", "due", "at_risk")))
    presets = before["quarters"]
    check(
        "nine quarter presets, one of them the current quarter",
        len(presets) == 9 and [p["label"] for p in presets if p["current"]] == [dashboard_module.quarter_of(today)[2]],
        str(presets),
    )
    check("revenue labels come from the revenue rule", before["revenue_labels"]["opportunities"] == "Opportunity Revenue" and before["revenue_labels"]["deals"] == "Actual Revenue")
    r = client.get("/api/dashboard", params={"date_from": "2027-05-01", "date_to": "2027-01-01"})
    check("an inverted range is refused", r.status_code == 422 and code_of(r) == "RANGE_INVERTED", r.text[:200])
    r = client.get("/api/dashboard", params={"date_from": "2020-01-01", "date_to": "2026-01-01"})
    check("a range over 36 months is refused", r.status_code == 422 and code_of(r) == "RANGE_TOO_LONG", r.text[:200])

    # ------------------------------------------------------ an open, red lead
    section("1  An open Stage 1 lead, Red, closing this month")
    r = post(
        "/leads",
        {
            "opportunity_name": "Dashboard probe — open red",
            "project_stage": "1_DEMO",
            "lead_status": "OPEN",
            "currency": "USD",
            "estimated_value": 1_000_000,
            "overall_rag": "RED",
            "bd_owner": USER.user_id,
            "expected_close_month": month0.isoformat(),
            "next_milestone": "Demo follow-up",
            "next_milestone_date": (today + timedelta(days=5)).isoformat(),
        },
        "leads",
    )
    check("the lead saves", r.status_code == 201, r.text[:300])
    lead_a = r.json()
    after = dash()
    p0, p1 = before["kpis"]["pipeline"], after["kpis"]["pipeline"]
    check("pipeline grows by one record and 1,000,000", p1["count"] == p0["count"] + 1 and close(p1["usd"] - p0["usd"], 1_000_000), f"{p0} -> {p1}")
    check(
        "the Leads share of it is Estimated Value",
        close(p1["by_module"]["leads"]["usd"] - p0["by_module"]["leads"]["usd"], 1_000_000),
    )
    # NO "/ 100" HERE. probability_pct is stored as a FRACTION -- 0.10 is 10%,
    # written that way by app/progression.py -- so the weighted figure is the
    # value times it, full stop.
    #
    # This line used to read `* probability_pct / 100`, which is precisely what
    # Row.weighted did, and so the assertion agreed with the implementation and
    # both were a hundredth of the truth: a $1,000,000 lead at Stage 1 was
    # expected to weigh $1,000 and did. A test written by reading the code it
    # tests cannot catch the code being wrong. Corrected 18 Sep 2026 together
    # with the property; test_dashboard_weighted.py now pins the convention
    # itself so neither can drift alone.
    expected_weighted = 1_000_000 * float(lead_a["probability_pct"] or 0)
    check(
        "weighted grows by the value x the lead's own Probability %",
        close(p1["weighted_usd"] - p0["weighted_usd"], expected_weighted),
        f"{p1['weighted_usd'] - p0['weighted_usd']} vs {expected_weighted}",
    )
    check("Stage 1 of the funnel grows by 1,000,000", close(funnel_usd(after, 1) - funnel_usd(before, 1), 1_000_000))
    m0, m1 = before["forecast"]["months"][0], after["forecast"]["months"][0]
    check("this month's forecast grows by 1,000,000", close(m1["usd"] - m0["usd"], 1_000_000), str(m1))
    check("and all of it is in the Leads series", close(m1["by_module"]["leads"]["usd"] - m0["by_module"]["leads"]["usd"], 1_000_000))
    check("Red grows by 1,000,000", close(rag_usd(after, "RED") - rag_usd(before, "RED"), 1_000_000))
    check("the 0-30 day ageing bucket holds it", after["ageing"][0]["count"] == before["ageing"][0]["count"] + 1)
    check("its next milestone is due", after["due"]["total"] == before["due"]["total"] + 1)
    check("it is on the at-risk list for being Red", after["at_risk"]["total"] == before["at_risk"]["total"] + 1)
    risk = next((i for i in after["at_risk"]["items"] if i["record_id"] == lead_a["id"]), None)
    check("named, with the reason and its owner", bool(risk) and risk["reasons"] == ["red"] and risk["owner"], str(risk))

    this_month = dash(date_from=month0, date_to=month_end)
    check("a range over this month includes it", listed(this_month, "at_risk", lead_a["id"]))
    check("a range has no before/after/undated notes", this_month["forecast"]["overdue"] is None and this_month["forecast"]["undated"] is None)
    check("and says how many records it left out for having no close month", isinstance(this_month["range"]["left_out"], int))
    later = dash(date_from=next_year[0], date_to=next_year[1])
    check("a Jan-Apr range next year leaves it out of the expected-close widgets", not listed(later, "at_risk", lead_a["id"]))
    check("and its milestone, due this month, out of the due list", not listed(later, "due", lead_a["id"]))
    check("that range's forecast is its four months", [m["month"][5:7] for m in later["forecast"]["months"]] == ["01", "02", "03", "04"])

    # ---------------------------------------------------------------- filters
    section("2  Filters follow the Lead")
    check("an owner nobody has returns an empty pipeline", dash(owner="USR-NOBODY-PROBE")["kpis"]["pipeline"]["count"] == 0)
    mine = dash(owner=USER.user_id)
    check("the probe's owner includes it", listed(mine, "at_risk", lead_a["id"]))
    check("the owner is offered as a filter option", any(o["id"] == USER.user_id for o in after["owners"]))

    # -------------------------------------------------------------- lost
    section("3  A lead lost at Stage 3 on price")
    base = dash()
    base_today = dash(date_from=today, date_to=today)
    base_old = dash(date_from=date(2020, 1, 1), date_to=date(2020, 12, 31))
    r = post(
        "/leads",
        {"opportunity_name": "Dashboard probe — lost", "project_stage": "3_PRESCRIPTION", "lead_status": "OPEN", "currency": "USD", "estimated_value": 500_000},
        "leads",
    )
    check("the lead saves", r.status_code == 201, r.text[:300])
    lead_b = r.json()
    r = put(f"/leads/{lead_b['id']}", {"lead_status": "CLOSED_LOST", "closed_lost_reason_code__s3": "PRICE"})
    check("it closes as lost with a reason", r.status_code == 200, r.text[:300])
    after = dash()
    check(
        "with no range, Closed Lost grows by one and 500,000",
        after["kpis"]["lost"]["count"] == base["kpis"]["lost"]["count"] + 1
        and close(after["kpis"]["lost"]["usd"] - base["kpis"]["lost"]["usd"], 500_000),
        f"{base['kpis']['lost']} -> {after['kpis']['lost']}",
    )
    check("and it left the pipeline", after["kpis"]["pipeline"]["count"] == base["kpis"]["pipeline"]["count"])
    check("Price gains one loss", reason_count(after, "PRICE") == reason_count(base, "PRICE") + 1)
    check(
        "a range holding today counts it, by the date it was lost",
        dash(date_from=today, date_to=today)["kpis"]["lost"]["count"] == base_today["kpis"]["lost"]["count"] + 1,
    )
    check(
        "a range in 2020 does not",
        dash(date_from=date(2020, 1, 1), date_to=date(2020, 12, 31))["kpis"]["lost"]["count"] == base_old["kpis"]["lost"]["count"],
    )

    # ------------------------------------------------------ converted pursuit
    section("4  Converted pursuits: Actual Revenue, and the schedule chased on the Deal")
    base = dash()
    r = post("/leads", {"opportunity_name": "Dashboard probe — converted", "project_stage": "3_PRESCRIPTION", "lead_status": "OPEN", "currency": "USD"}, "leads")
    check("the lead saves", r.status_code == 201, r.text[:300])
    lead_c = r.json()
    r = post(
        "/opportunities",
        {
            "parent_lead": lead_c["id"],
            "project_stage": "6_COMMERCIAL_EVAL",
            "lead_status": "OPEN",
            "arr_annual_recurring": 1_000_000,
            "contract_years": 1,
            "final_negotiated_value": 1_000_000,
            "payment_milestones": [
                {
                    "milestone": "CONTRACT_SIGNING",
                    "pct_of_contract": 20,
                    "milestone_planned_date": today.isoformat(),
                    "milestone_payment_received_date": today.isoformat(),
                    "milestone_status": "PAID",
                },
                {
                    "milestone": "DELIVERY",
                    "pct_of_contract": 80,
                    "milestone_planned_date": (today + timedelta(days=10)).isoformat(),
                    "milestone_status": "NOT_DUE",
                },
            ],
        },
        "opportunities",
    )
    check("the opportunity saves with its payment schedule", r.status_code == 201, r.text[:300])
    opp_c = r.json()
    put(f"/leads/{lead_c['id']}", {"lead_status": "CONVERTED"}).raise_for_status()
    r = post(
        "/deals",
        {"deal_name": "Dashboard probe — converted", "parent_opportunity": opp_c["id"], "deal_stage": "7_CLOSE", "contract_value": 1_000_000},
        "deals",
    )
    check("the deal saves", r.status_code == 201, r.text[:300])
    deal_c = r.json()
    put(f"/opportunities/{opp_c['id']}", {"lead_status": "CONVERTED"}).raise_for_status()

    r = post("/leads", {"opportunity_name": "Dashboard probe — no schedule", "project_stage": "3_PRESCRIPTION", "lead_status": "OPEN", "currency": "USD"}, "leads")
    lead_d = r.json()
    r = post("/deals", {"deal_name": "Dashboard probe — no schedule", "parent_lead": lead_d["id"], "deal_stage": "7_CLOSE", "contract_value": 50_000}, "deals")
    check("a deal converted straight from a lead saves", r.status_code == 201, r.text[:300])
    put(f"/leads/{lead_d['id']}", {"lead_status": "CONVERTED"}).raise_for_status()

    after = dash()
    a0, a1 = base["kpis"]["actual"], after["kpis"]["actual"]
    check("Actual Revenue grows by both deals' contract value", a1["count"] == a0["count"] + 2 and close(a1["usd"] - a0["usd"], 1_050_000), f"{a0} -> {a1}")
    check("no Won figure is served until the team defines a win", "won" not in after["kpis"])
    payment = [i for i in after["due"]["items"] if i["kind"] == "payment" and i["record_id"] == deal_c["id"]]
    check("the unpaid milestone is chased on the Deal, not the converted Opportunity", len(payment) == 1, str(payment))
    check("the converted opportunity and lead left the pipeline", after["kpis"]["pipeline"]["count"] == base["kpis"]["pipeline"]["count"])
    check("the deals are in Stage 7 of the funnel", after["funnel"][7]["count"] == base["funnel"][7]["count"] + 2)

finally:
    section("Cleanup")
    for collection in ("deals", "opportunities", "leads"):
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
