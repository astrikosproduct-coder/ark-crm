"""
Release 1.2 — Segment -> Segment Category -> Subsegment on Leads and Accounts,
checked through the API (release_1_2_market_segments_metadata.py, run on this
register).

    python run_tests.py test_market_segments.py     (against the disposable copy)

  1  The register: one choice each on a Lead, shown From the Lead on an
     Opportunity and a Deal, several on an Account; the two maps per module.
  2  Accounts: Categories of every Segment held are accepted, one outside them
     is refused, and so is a Subsegment outside the Categories held.
  3  Leads: one choice each; a Category outside the Segment is refused; the
     list filters on it; an Opportunity shows its Lead's values.
  4  The dashboard slices by the Lead's Segment Category and Subsegment.
"""

import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from app.database import engine  # noqa: E402

engine.echo = False

from test_db import require_test_database  # noqa: E402

require_test_database()

from fastapi.testclient import TestClient  # noqa: E402

from app import requirements  # noqa: E402
from app.main import app  # noqa: E402
from test_support import sign_in_as_admin  # noqa: E402

# test_support switches the save checks off for the older scripts; the choice
# check is one of them, and this script is about what production does.
requirements.ENFORCED = True

client = TestClient(app)
admin = sign_in_as_admin(app)

failed: list[str] = []
created: dict[str, list[str]] = {"opportunities": [], "leads": [], "accounts": []}

DATA = json.loads((Path(__file__).parent / "data" / "market_segments.json").read_text(encoding="utf-8"))


def categories_of(segment: str) -> list[str]:
    return [c["key"] for c in DATA["categories"] if c["segment"] == segment]


def subsegments_of(category: str) -> list[str]:
    return [s["key"] for s in DATA["subsegments"] if s["category"] == category]


DC, CITY = "DATA_CENTERS", "SMART_CITIES"
DC_CAT, CITY_CAT = categories_of(DC)[0], categories_of(CITY)[0]
DC_SUB, CITY_SUB = subsegments_of(DC_CAT)[0], subsegments_of(CITY_CAT)[0]


def check(name: str, condition: bool, detail: str = "") -> None:
    if condition:
        print(f"  pass  {name}")
    else:
        failed.append(f"{name} — {detail}")
        print(f"  FAIL  {name} — {detail}")


def code_of(response) -> str | None:
    try:
        body = response.json().get("detail")
    except ValueError:
        return None
    return body.get("code") if isinstance(body, dict) else None


def rows_of(response) -> list[dict]:
    body = response.json()
    return body.get("rows", body) if isinstance(body, dict) else body


def section(title: str) -> None:
    print(f"\n{title}\n" + "-" * len(title))


ACCOUNT = {
    "account_type": ["END_CLIENT"],
    "account_owner": admin.user_id,
    "region": "EUROPE",
    "country": "FR",
    "segments": [CITY, DC],
    "customer_class": "A_STRATEGIC_>$2M",
}


def account(name: str, **extra):
    r = client.post("/api/accounts", json={**ACCOUNT, "account_name": f"Segments probe — {name}", **extra})
    if r.status_code == 201:
        created["accounts"].append(r.json()["account_id"])
    return r


try:
    print("=" * 74)
    print("  RELEASE 1.2 — Segment -> Segment Category -> Subsegment")
    print("=" * 74)

    section("1  The register")
    spec = client.get("/api/spec").json()
    fields = spec.get("fields", []) if isinstance(spec, dict) else []
    by = {(f.get("module"), f.get("api_name")): f for f in fields if isinstance(f, dict)}
    for api_name, picklist in (("segment_category", "segment_categories"), ("subsegment", "subsegments")):
        f = by.get(("leads", api_name), {})
        check(f"leads.{api_name}: one choice from '{picklist}'", (f.get("type"), f.get("picklist")) == ("picklist", picklist), str(f)[:200])
        for module in ("opportunities", "deals"):
            f = by.get((module, api_name), {})
            check(f"{module}.{api_name}: shown From the Lead", f.get("value_mode") == "read_through", str(f.get("value_mode")))
    for api_name, picklist in (("segment_categories", "segment_categories"), ("subsegments", "subsegments")):
        f = by.get(("accounts", api_name), {})
        check(f"accounts.{api_name}: several choices from '{picklist}'", (f.get("type"), f.get("picklist")) == ("multiselect", picklist), str(f)[:200])
    deps = spec.get("dependencies", {}) if isinstance(spec, dict) else {}
    check("leads: Segment -> Segment Category -> Subsegment",
          deps.get("leads", {}).get("segment_category", {}).get("parent") == "theme"
          and deps.get("leads", {}).get("subsegment", {}).get("parent") == "segment_category", str(deps.get("leads", {}).keys()))
    check("accounts: the same over several choices",
          deps.get("accounts", {}).get("segment_categories", {}).get("parent") == "segments"
          and deps.get("accounts", {}).get("subsegments", {}).get("parent") == "segment_categories", str(deps.get("accounts", {}).keys()))
    picklists = spec.get("picklists", {}) if isinstance(spec, dict) else {}
    check("41 Segment Categories and 132 Subsegments",
          (len(picklists.get("segment_categories", [])), len(picklists.get("subsegments", []))) == (41, 132))

    section("2  Accounts — several choices")
    r = account("two segments", segment_categories=[DC_CAT, CITY_CAT], subsegments=[DC_SUB, CITY_SUB])
    check("Categories from both Segments held, and their Subsegments, save", r.status_code == 201, r.text[:300])
    acc = r.json()["account_id"] if r.status_code == 201 else None
    if acc:
        got = client.get(f"/api/accounts/{acc}").json()
        check("…and are kept", (got.get("segment_categories"), got.get("subsegments")) == ([DC_CAT, CITY_CAT], [DC_SUB, CITY_SUB]),
              str((got.get("segment_categories"), got.get("subsegments"))))
        r = client.patch(f"/api/accounts/{acc}", json={"segments": [DC]})
        check("taking a Segment off while its Category is held is refused", r.status_code == 422 and code_of(r) == "DEPENDENT_CHOICE",
              f"{r.status_code} {r.text[:200]}")
        rows = rows_of(client.get("/api/accounts", params={"segment_categories": DC_CAT}))
        check("the Accounts list filters on one of the Categories", any(x.get("account_id") == acc for x in rows))
    r = account("category outside", segments=[DC], segment_categories=[CITY_CAT])
    check("a Category outside every Segment held is refused", r.status_code == 422 and code_of(r) == "DEPENDENT_CHOICE",
          f"{r.status_code} {r.text[:200]}")
    r = account("subsegment outside", segments=[DC], segment_categories=[DC_CAT], subsegments=[CITY_SUB])
    check("a Subsegment outside the Categories held is refused", r.status_code == 422 and code_of(r) == "DEPENDENT_CHOICE",
          f"{r.status_code} {r.text[:200]}")
    r = account("none", segments=[DC])
    check("both stay optional", r.status_code == 201, r.text[:300])

    section("3  Leads — one choice each, shown From the Lead")
    lead_body = {
        "opportunity_name": "Segments probe — lead", "end_client": acc, "bd_owner": admin.user_id, "currency": "USD",
        "project_stage": "3_PRESCRIPTION", "lead_status": "OPEN", "estimated_value": 100000,
        "theme": DC, "segment_category": DC_CAT, "subsegment": DC_SUB, "not_duplicate_reason": "A probe.",
    }
    r = client.post("/api/leads", json={**lead_body, "segment_category": CITY_CAT, "subsegment": None})
    check("a Category outside the Lead's Segment is refused", r.status_code == 422 and code_of(r) == "DEPENDENT_CHOICE",
          f"{r.status_code} {r.text[:200]}")
    r = client.post("/api/leads", json=lead_body)
    check("a Lead with a Segment, Category and Subsegment saves", r.status_code == 201, r.text[:300])
    lead = r.json().get("lead_id") if r.status_code == 201 else None
    if lead:
        created["leads"].append(lead)
        got = client.get(f"/api/leads/{lead}").json()
        check("…and keeps them", (got.get("segment_category"), got.get("subsegment")) == (DC_CAT, DC_SUB),
              str((got.get("segment_category"), got.get("subsegment"))))
        rows = rows_of(client.get("/api/leads", params={"subsegment": DC_SUB}))
        check("the Leads list filters on the Subsegment", any(x.get("lead_id") == lead or x.get("id") == lead for x in rows))
        check("nothing was copied to the Account", client.get(f"/api/accounts/{acc}").json().get("subsegments") == [DC_SUB, CITY_SUB])

        section("4  The dashboard")

        def pipeline(**params) -> int:
            return client.get("/api/dashboard", params=params).json()["kpis"]["pipeline"]["count"]

        city_before = pipeline(subsegment=CITY_SUB)
        check("the Segment Category filter counts the Lead", pipeline(segment_category=DC_CAT) >= 1)
        check("…the Subsegment filter too", pipeline(subsegment=DC_SUB) >= 1)
        with_lead = pipeline(subsegment=DC_SUB)

        # Converting asks for Stage 3's own fields — not this script's subject.
        requirements.ENFORCED = False
        r = client.post("/api/opportunities", json={
            "parent_lead": lead, "project_stage": "4_RFP_RFI", "lead_status": "OPEN",
            "one_time_revenue": 100000, "conversion_note": "Segments probe.",
        })
        requirements.ENFORCED = True
        check("the Lead converts to an Opportunity", r.status_code == 201, r.text[:300])
        opp = r.json().get("id") if r.status_code == 201 else None
        if opp:
            created["opportunities"].append(opp)
            rows = rows_of(client.get("/api/opportunities", params={"segment_category": DC_CAT}))
            row = next((x for x in rows if x.get("id") == opp or x.get("opportunity_id") == opp), None)
            check("the Opportunity's list row shows its Lead's Category and Subsegment",
                  row is not None and (row.get("segment_category"), row.get("subsegment")) == (DC_CAT, DC_SUB), str(row)[:300])
            check("the dashboard still counts it once, as the Opportunity", pipeline(subsegment=DC_SUB) == with_lead,
                  f"{pipeline(subsegment=DC_SUB)} vs {with_lead}")
        check("…and not under another Subsegment", pipeline(subsegment=CITY_SUB) == city_before)

finally:
    section("Cleanup")
    for collection in ("opportunities", "leads", "accounts"):
        for record_id in reversed(created[collection]):
            r = client.delete(f"/api/{collection}/{record_id}")
            if r.status_code not in (200, 204, 404):
                print(f"  could not delete {collection}/{record_id}: {r.status_code}")

print()
if failed:
    print(f"{len(failed)} FAILED")
    for line in failed:
        print(f"  - {line}")
    sys.exit(1)
print("all passed")
