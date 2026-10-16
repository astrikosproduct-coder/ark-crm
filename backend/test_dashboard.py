"""
The management dashboard, as assertions — five tabs since 28 Sep 2026.

    python run_tests.py test_dashboard.py

The test database is a copy of the live one and already holds pursuits, so
every check here is a DIFFERENCE: read the dashboard, add records whose effect
is known, read it again. Nothing asserts an absolute total. The exceptions are
the tie-outs — Booked against Won, a drill-down against its mark — which are
equalities within one read.
"""

import os
import sys
from calendar import monthrange
from datetime import date, timedelta
from decimal import Decimal

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import delete, text  # noqa: E402

import test_db  # noqa: E402

test_db.require_test_database()

from app import fiscal  # noqa: E402
from app import pipeline_snapshots as snapshots  # noqa: E402
from app.clock import now_utc, today_company  # noqa: E402
from app.database import SessionLocal  # noqa: E402
from app.main import app  # noqa: E402
from app.models import PipelineSnapshot, SalesTarget  # noqa: E402
from app.routers import dashboard as dashboard_module  # noqa: E402
from test_support import sign_in_as_admin  # noqa: E402

client = TestClient(app)
USER = sign_in_as_admin(app)

failures: list[str] = []
created: dict[str, list[str]] = {"deals": [], "opportunities": [], "leads": [], "accounts": []}
targets: list[str] = []
NOT_SET = "__none__"


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


def records(tile: str, *keys: str, **params) -> dict:
    params = {k: (v.isoformat() if isinstance(v, date) else v) for k, v in params.items()}
    r = client.get("/api/dashboard/records", params={"tile": tile, "key": list(keys), **params})
    r.raise_for_status()
    return r.json()


def code_of(response) -> str | None:
    detail = response.json().get("detail")
    return detail.get("code") if isinstance(detail, dict) else None


def group(d: dict, tile: str, key: str) -> dict:
    """One group of a grouped tile, or an empty bucket."""
    return next((g for g in d["tiles"][tile] if g["key"] == key), {"count": 0, "usd": 0.0, "weighted_usd": 0.0, "distinct": 0})


def stage_usd(d: dict, stage: int) -> float:
    return next(s["usd"] for s in d["tiles"]["pipeline.stage"] if s["stage"] == stage)


def column(d: dict, key: str) -> dict:
    return next(c for c in d["tiles"]["pipeline.close_month"]["columns"] if c["key"] == key)


def section(title: str) -> None:
    print(f"\n{title}\n" + "-" * len(title))


try:
    print("=" * 74)
    print("  DASHBOARD — every tile moves by exactly what was added")
    print("=" * 74)

    # ------------------------------------------------------------ calendar
    section("0  Quarters, fiscal years and the period")
    check("the fiscal year starts in April (decided 15 Sep 2026)", fiscal.FISCAL_YEAR_START_MONTH == 4)
    check(
        "1 Apr 2027 opens Q1 FY2027-28",
        dashboard_module.quarter_of(date(2027, 4, 1)) == (date(2027, 4, 1), date(2027, 6, 30), "Q1 FY2027-28"),
    )
    # The setting lives in app/fiscal.py, and the dashboard reads it there.
    saved = fiscal.FISCAL_YEAR_START_MONTH
    try:
        fiscal.FISCAL_YEAR_START_MONTH = 1
        check("on calendar quarters, 14 Sep 2026 is Q3 2026", dashboard_module.quarter_of(date(2026, 9, 14)) == (date(2026, 7, 1), date(2026, 9, 30), "Q3 2026"))
        check("and 31 Dec is the last day of Q4", dashboard_module.quarter_of(date(2026, 12, 31))[1] == date(2026, 12, 31))
        fiscal.FISCAL_YEAR_START_MONTH = 4
        check("with an April year, Sep is Q2 FY2026-27", dashboard_module.quarter_of(date(2026, 9, 14)) == (date(2026, 7, 1), date(2026, 9, 30), "Q2 FY2026-27"))
        check("and February is Q4 of the same fiscal year", dashboard_module.quarter_of(date(2027, 2, 1)) == (date(2027, 1, 1), date(2027, 3, 31), "Q4 FY2026-27"))
    finally:
        fiscal.FISCAL_YEAR_START_MONTH = saved
    check("a range starting mid-month still holds that month's closes", dashboard_module.close_month_in(date(2027, 1, 1), date(2027, 1, 15), date(2027, 4, 30)))

    before = dash()
    today = date.fromisoformat(before["as_of"])
    month0 = today.replace(day=1)
    month_end = today.replace(day=monthrange(today.year, today.month)[1])
    fy = fiscal.label_of(today)
    next_year = (date(today.year + 1, 1, 1), date(today.year + 1, 4, 30))
    check("the endpoint answers every tab", all(k in before for k in ("kpis", "performance", "tiles")) and len(before["tiles"]) == 11, str(list(before["tiles"])))
    # 12 -> 11 with Release 1.1: Segment IS the Lead's theme field, so the Theme tile went.
    check("the removed widgets are gone", not any(k in before for k in ("forecast", "rag", "ageing", "due", "at_risk", "funnel", "loss_reasons", "quarters")))
    check("the answer carries the instant it was computed", bool(before["generated_at"]))
    presets = before["periods"]
    check(
        "this fiscal year and the last, then nine quarters",
        [p["kind"] for p in presets].count("fiscal_year") == 2 and [p["kind"] for p in presets].count("quarter") == 9,
        str([p["label"] for p in presets]),
    )
    check("the current fiscal year is offered as this year", [p["label"] for p in presets if p["kind"] == "fiscal_year" and p["current"]] == [fy])
    fy_view = dash(period="current_fy")
    check(
        "period=current_fy is the fiscal year's first to last day",
        (fy_view["range"]["from"], fy_view["range"]["to"]) == (fiscal.first_day(fy).isoformat(), fiscal.last_day(fy).isoformat()),
        str(fy_view["range"]),
    )
    check("a whole fiscal year compares with the one before it, by name", fy_view["comparison"]["label"] == fiscal.label_of(fiscal.first_day(fy) - timedelta(days=1)))
    r = client.get("/api/dashboard", params={"date_from": "2027-05-01", "date_to": "2027-01-01"})
    check("an inverted range is refused", r.status_code == 422 and code_of(r) == "RANGE_INVERTED", r.text[:200])
    r = client.get("/api/dashboard", params={"date_from": "2020-01-01", "date_to": "2026-01-01"})
    check("a range over 36 months is refused", r.status_code == 422 and code_of(r) == "RANGE_TOO_LONG", r.text[:200])

    # ------------------------------------------------------ accounts for the probe
    r = post("/accounts", {"account_name": "Dashboard probe — client", "account_type": ["END_CLIENT"], "region": "APAC", "customer_class": "A_STRATEGIC_>$2M"}, "accounts")
    check("an End Client account saves", r.status_code == 201, r.text[:300])
    client_acc = r.json()["id"]
    r = post("/accounts", {"account_name": "Dashboard probe — partner", "account_type": ["PARTNER_SI"], "region": "APAC", "partner_tier": "PLATINUM"}, "accounts")
    check("a partner account saves", r.status_code == 201, r.text[:300])
    partner_acc = r.json()["id"]

    # ------------------------------------------------------ an open lead
    section("1  An open Stage 1 lead booked in MEA, delivered in India, its accounts in APAC")
    r = post(
        "/leads",
        {
            "opportunity_name": "Dashboard probe — open",
            "project_stage": "1_DEMO",
            "lead_status": "OPEN",
            "currency": "USD",
            "estimated_value": 1_000_000,
            "bd_owner": USER.user_id,
            "expected_close_month": month0.isoformat(),
            "booking_region": "MEA",
            "destination_region": "INDIA",
            "theme": "SMART_CITIES",
            "deal_source": "PARTNER_SOURCED",
            "end_client": client_acc,
            "customer_partner_si": partner_acc,
            "not_duplicate_reason": "Dashboard test probe.",
        },
        "leads",
    )
    check("the lead saves", r.status_code == 201, r.text[:300])
    lead_a = r.json()
    after = dash()
    p0, p1 = before["kpis"]["pipeline"], after["kpis"]["pipeline"]
    check("pipeline grows by one record and 1,000,000", p1["count"] == p0["count"] + 1 and close(p1["usd"] - p0["usd"], 1_000_000), f"{p0} -> {p1}")
    check("the Leads share of it is Estimated Value", close(p1["by_module"]["leads"]["usd"] - p0["by_module"]["leads"]["usd"], 1_000_000))
    # NO "/ 100": probability_pct is stored as a FRACTION — see test_dashboard_weighted.py.
    expected_weighted = 1_000_000 * float(lead_a["probability_pct"] or 0)
    check("weighted grows by the value x the lead's own Probability %", close(p1["weighted_usd"] - p0["weighted_usd"], expected_weighted))
    check("Stage 1 of the funnel grows by 1,000,000", close(stage_usd(after, 1) - stage_usd(before, 1), 1_000_000))
    check("this month's close-month column grows by 1,000,000", close(column(after, month0.isoformat())["usd"] - column(before, month0.isoformat())["usd"], 1_000_000))
    for tile, key, name in (
        ("pipeline.segment", "SMART_CITIES", "Segment Smart Cities"),
        ("pipeline.delivery_region", "INDIA", "delivery region India — Destination Region"),
        ("partners.partner", partner_acc, "the partner"),
        ("partners.deal_source", "PARTNER_SOURCED", "Partner-sourced"),
        ("partners.tier", "PLATINUM", "Platinum"),
        ("accounts.end_client", client_acc, "the End Client"),
        ("accounts.customer_class", "A_STRATEGIC_>$2M", "Customer Class A"),
    ):
        check(f"{name} grows by 1,000,000", close(group(after, tile, key)["usd"] - group(before, tile, key)["usd"], 1_000_000), str(group(after, tile, key)))
    check("the tier counts its partner", group(after, "partners.tier", "PLATINUM")["distinct"] >= 1)
    check("the partner is offered as a filter", any(p["id"] == partner_acc for p in after["partners"]))
    check("every donut adds up to the Open pipeline card", all(close(sum(g["usd"] for g in after["tiles"][t]), p1["usd"]) for t in ("pipeline.segment", "pipeline.delivery_region", "partners.deal_source", "partners.tier", "accounts.customer_class")))

    section("2  Filters reach every tile, and Region is the deal's Booking Region")
    mea = dash(region="MEA")
    check("Booking Region MEA holds it", group(mea, "pipeline.segment", "SMART_CITIES")["count"] >= 1 and mea["kpis"]["pipeline"]["count"] >= 1)
    apac = dash(region="APAC")
    check("APAC — the region of both its accounts — does not", group(apac, "partners.partner", partner_acc)["count"] == 0 and group(apac, "accounts.end_client", client_acc)["count"] == 0)
    check("nor does India, where it is delivered", group(dash(region="INDIA"), "partners.partner", partner_acc)["count"] == 0)
    for name, value, wrong in (
        ("deal_source", "PARTNER_SOURCED", "DIRECT"),
        ("partner", partner_acc, client_acc),
        ("segment", "SMART_CITIES", "DATA_CENTERS"),
        ("owner", USER.user_id, "USR-NOBODY-PROBE"),
    ):
        hit, miss = dash(**{name: value}), dash(**{name: wrong})
        check(
            f"filter {name}: the probe is in every tile with it, and in none without",
            all(group(hit, t, k)["count"] >= 1 for t, k in (("partners.partner", partner_acc), ("accounts.end_client", client_acc), ("pipeline.segment", "SMART_CITIES")))
            and stage_usd(hit, 1) >= 1_000_000
            and group(miss, "partners.partner", partner_acc)["count"] == 0
            and group(miss, "accounts.end_client", client_acc)["count"] == 0
            and miss["filters"][name] == wrong,
        )

    section("3  A mark's records add up to the mark")
    drilled = records("pipeline.segment", "SMART_CITIES")
    check("the Smart Cities slice lists the probe", any(i["record_id"] == lead_a["id"] for i in drilled["items"]))
    check("…and its records sum to the slice", close(drilled["usd"], group(after, "pipeline.segment", "SMART_CITIES")["usd"]) and drilled["count"] == group(after, "pipeline.segment", "SMART_CITIES")["count"])
    drilled = records("pipeline.close_month", month0.isoformat())
    check("the close-month column's records sum to it", close(drilled["usd"], column(after, month0.isoformat())["usd"]))
    drilled = records("partners.partner", partner_acc, region="APAC")
    check("the drill-down honours the filters", drilled["count"] == 0)
    r = client.get("/api/dashboard/records", params={"tile": "nope", "key": "x"})
    check("an unknown tile is refused in words", r.status_code == 422 and code_of(r) == "TILE_UNKNOWN")

    section("4  No close month: shown on its own column, never hidden")
    base = dash()
    r = post("/leads", {"opportunity_name": "Dashboard probe — undated", "project_stage": "0_CONNECT", "lead_status": "OPEN", "currency": "USD", "estimated_value": 70_000}, "leads")
    check("the lead saves", r.status_code == 201, r.text[:300])
    after = dash()
    check("the No close month column grows by 70,000", close(column(after, NOT_SET)["usd"] - column(base, NOT_SET)["usd"], 70_000))
    check("its unset segment groups as Not set", close(group(after, "pipeline.segment", NOT_SET)["usd"] - group(base, "pipeline.segment", NOT_SET)["usd"], 70_000))
    check("a period leaves it out of the card, and says so", dash(period="current_fy")["range"]["left_out"] >= 1)

    # ------------------------------------------------------------- lost
    section("5  A lead lost at Stage 3 on price")
    base = dash()
    base_today = dash(date_from=today, date_to=today)
    base_old = dash(date_from=date(2020, 1, 1), date_to=date(2020, 12, 31))
    r = post("/leads", {"opportunity_name": "Dashboard probe — lost", "project_stage": "3_PRESCRIPTION", "lead_status": "OPEN", "currency": "USD", "estimated_value": 500_000}, "leads")
    check("the lead saves", r.status_code == 201, r.text[:300])
    lead_b = r.json()
    r = put(f"/leads/{lead_b['id']}", {"lead_status": "CLOSED_LOST", "closed_lost_reason_code__s3": "PRICE"})
    check("it closes as lost with a reason", r.status_code == 200, r.text[:300])
    after = dash()
    check(
        "with no range, Closed Lost grows by one and 500,000",
        after["kpis"]["lost"]["count"] == base["kpis"]["lost"]["count"] + 1 and close(after["kpis"]["lost"]["usd"] - base["kpis"]["lost"]["usd"], 500_000),
    )
    check("and it left the pipeline", after["kpis"]["pipeline"]["count"] == base["kpis"]["pipeline"]["count"])
    check("Why we lose: Price grows by 500,000 of lost value", close(group(after, "winloss.reason", "PRICE")["usd"] - group(base, "winloss.reason", "PRICE")["usd"], 500_000))
    check("a range holding today counts it, by the date it was lost", dash(date_from=today, date_to=today)["kpis"]["lost"]["count"] == base_today["kpis"]["lost"]["count"] + 1)
    check("a range in 2020 does not", dash(date_from=date(2020, 1, 1), date_to=date(2020, 12, 31))["kpis"]["lost"]["count"] == base_old["kpis"]["lost"]["count"])

    # ------------------------------------------------------ converted and won
    section("6  Converted pursuits: Actual Revenue, Won, and the Booked line")
    base = dash()
    r = post("/leads", {"opportunity_name": "Dashboard probe — converted", "project_stage": "3_PRESCRIPTION", "lead_status": "OPEN", "currency": "USD"}, "leads")
    lead_c = r.json()
    r = post(
        "/opportunities",
        {"parent_lead": lead_c["id"], "project_stage": "6_COMMERCIAL_EVAL", "lead_status": "OPEN", "arr_annual_recurring": 1_000_000, "contract_years": 1, "final_negotiated_value": 1_000_000},
        "opportunities",
    )
    check("the opportunity saves", r.status_code == 201, r.text[:300])
    opp_c = r.json()
    put(f"/leads/{lead_c['id']}", {"lead_status": "CONVERTED"}).raise_for_status()
    r = post("/deals", {"deal_name": "Dashboard probe — converted", "parent_opportunity": opp_c["id"], "deal_stage": "7_CLOSE", "contract_value": 1_000_000}, "deals")
    check("the deal saves", r.status_code == 201, r.text[:300])
    deal_c = r.json()
    put(f"/opportunities/{opp_c['id']}", {"lead_status": "CONVERTED"}).raise_for_status()
    r = post("/leads", {"opportunity_name": "Dashboard probe — pilot", "project_stage": "3_PRESCRIPTION", "lead_status": "OPEN", "currency": "USD"}, "leads")
    lead_d = r.json()
    r = post("/deals", {"deal_name": "Dashboard probe — pilot", "parent_lead": lead_d["id"], "deal_stage": "7_CLOSE", "contract_value": 50_000}, "deals")
    check("a deal converted straight from a lead saves", r.status_code == 201, r.text[:300])
    put(f"/leads/{lead_d['id']}", {"lead_status": "CONVERTED"}).raise_for_status()

    after = dash()
    a0, a1 = base["kpis"]["actual"], after["kpis"]["actual"]
    check("Actual Revenue grows by both deals' contract value", a1["count"] == a0["count"] + 2 and close(a1["usd"] - a0["usd"], 1_050_000), f"{a0} -> {a1}")
    w0, w1 = base["kpis"]["won"], after["kpis"]["won"]
    check("a Deal with no PO Received Date is not won, whatever its stage", w1["count"] == w0["count"] and close(w1["usd"], w0["usd"]))
    check("the converted opportunity and lead left the pipeline", after["kpis"]["pipeline"]["count"] == base["kpis"]["pipeline"]["count"])
    check("the deals are in Stage 7 of the funnel", after["tiles"]["pipeline.stage"][7]["count"] == base["tiles"]["pipeline.stage"][7]["count"] + 2)

    put(f"/deals/{deal_c['id']}", {"po_received_date": today.isoformat()}).raise_for_status()
    won_now = dash()["kpis"]["won"]
    check("recording the PO date wins the Deal, at its contract value", won_now["count"] == w0["count"] + 1 and close(won_now["usd"] - w0["usd"], 1_000_000))
    check("a period after the PO date does not count it", dash(date_from=next_year[0], date_to=next_year[1])["kpis"]["won"]["count"] == 0)

    fy_view = dash(period="current_fy")
    p = fy_view["performance"]
    months = [m["month"] for m in p["months"]]
    now_at = months.index(month0.isoformat())
    check("the curve is the fiscal year's twelve months, from its first", len(months) == 12 and months[0] == fiscal.first_day(fy).isoformat())
    check(
        "Booked at this month equals the Won card for the fiscal year",
        close(p["months"][now_at]["booked"], fy_view["kpis"]["won"]["usd"] - p["booked_after_now"]["usd"]),
        f"{p['months'][now_at]['booked']} vs {fy_view['kpis']['won']['usd']}",
    )
    check("…and the year's Booked total is the Won card itself", close(p["booked_in_year"]["usd"], fy_view["kpis"]["won"]["usd"]) and p["booked_in_year"]["count"] == fy_view["kpis"]["won"]["count"])
    check("Booked has no point after this month", all(m["booked"] is None for m in p["months"][now_at + 1 :]) and all(m["booked"] is not None for m in p["months"][: now_at + 1]))
    check("Forecast starts at this month, where Booked ends", p["months"][now_at]["forecast"] == p["months"][now_at]["booked"] and all(m["forecast"] is None for m in p["months"][:now_at]))
    check("Prior FY has all twelve months", all(m["prior"] is not None for m in p["months"]))
    drilled = records("performance.booked", month0.isoformat(), period="current_fy")
    check("this month's Booked point lists the won Deal", any(i["record_id"] == deal_c["id"] for i in drilled["items"]))

    section("7  Quarter attainment: bookings once ended, forecast while open")
    this_q = (now_at // 3)
    quarters = p["quarters"]
    check("the quarter holding today is measured on forecast", quarters[this_q]["basis"] == "forecast")
    check("an earlier quarter is measured on bookings", all(q["basis"] == "booked" for q in quarters[:this_q]))
    with SessionLocal() as db:
        had_targets = bool(db.scalar(text("SELECT 1 FROM sales_targets WHERE fiscal_year = :fy AND status <> 'SUPERSEDED' LIMIT 1"), {"fy": fy}))
    if had_targets:
        print("  (this copy already holds targets for the year; the no-target checks are skipped)")
    else:
        check("with no target, every quarter says so — no percentage", all(q["pct"] is None and q["target"] is None for q in quarters))
        check("and no target line is drawn", all(m["target"] is None for m in p["months"]) and p["targets"]["set"] is False)
    with SessionLocal() as db:
        stamp = now_utc()
        target = SalesTarget(
            target_id="TGT-T-DASH", fiscal_year=fy, period_month=month0, bd_owner_id=USER.user_id,
            target_amount_usd=Decimal("2000000"), currency="USD", status="DRAFT",
            created_at=stamp, created_by=USER.user_id, updated_at=stamp, updated_by=USER.user_id,
        )
        db.add(target)
        db.commit()
        targets.append("TGT-T-DASH")
    mine = dash(period="current_fy", owner=USER.user_id)["performance"]
    q_now = mine["quarters"][this_q]
    check("a target gives the open quarter a percentage on forecast", q_now["target"] is not None and q_now["pct"] is not None and q_now["basis"] == "forecast", str(q_now))
    check("the target line runs cumulatively from this month", mine["months"][now_at]["target"] is not None and mine["months"][-1]["target"] >= mine["months"][now_at]["target"])
    blocked = dash(period="current_fy", region="MEA")["performance"]
    check("a Region filter stops the target being drawn, and says which", blocked["targets"]["available"] is False and blocked["targets"]["blocked_by"] == ["region"] and all(q["pct"] is None for q in blocked["quarters"]))

    section("8  Month-end history: a gap is a gap")
    with SessionLocal() as db:
        # Every snapshot of this month, not only today's: one taken on an earlier
        # day of the month (the copied database may hold one) is still this month's.
        db.execute(delete(PipelineSnapshot).where(PipelineSnapshot.snapshot_date >= month0))
        db.commit()
    history = dash(period="current_fy")["tiles"]["pipeline.month_end"]
    check("with no snapshot this month, this month is null — not zero", next(m for m in history["months"] if m["key"] == month0.isoformat())["usd"] is None)
    with SessionLocal() as db:
        snapshots.take(db, today, actor=None)
    history = dash(period="current_fy")["tiles"]["pipeline.month_end"]
    this = next(m for m in history["months"] if m["key"] == month0.isoformat())
    check("once taken, this month shows the snapshot", this["usd"] is not None and this["snapshot_date"] == today.isoformat())
    check("the ALL row is read with no filters", history["dimension"] == "ALL")
    check("a BD Owner filter reads that owner's rows", dash(period="current_fy", owner=USER.user_id)["tiles"]["pipeline.month_end"]["dimension"] == "BD_OWNER")
    check("a Deal Source filter cannot be answered, and says why", dash(deal_source="PARTNER_SOURCED")["tiles"]["pipeline.month_end"]["available"] is False)

finally:
    section("Cleanup")
    with SessionLocal() as db:
        db.execute(delete(SalesTarget).where(SalesTarget.target_id.in_(targets or ["-"])))
        db.execute(delete(PipelineSnapshot).where(PipelineSnapshot.snapshot_date == today_company()))
        db.commit()
    for collection in ("deals", "opportunities", "leads", "accounts"):
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
