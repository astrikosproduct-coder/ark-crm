"""
The pipeline list contract: filters, ranges, search, sort — and read-through
identity on Opportunity rows, so the shared filter bar works on every board.

    python run_tests.py test_list_query.py

Added 17 Sep 2026 with app/list_query.py and app/read_through_rows.py.
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
created: dict[str, list[str]] = {"opportunities": [], "leads": [], "accounts": []}
TAG = "List probe"


def check(label: str, condition: bool, detail: str = "") -> None:
    if condition:
        print(f"  pass  {label}")
    else:
        failures.append(f"{label}{' — ' + detail if detail else ''}")
        print(f"  FAIL  {label}{' — ' + detail if detail else ''}")


def post(path: str, body: dict, collection: str):
    r = client.post(f"/api{path}", json=body)
    if r.status_code == 201:
        created[collection].append(r.json()["id"])
    return r


def names(path: str, **params) -> list[str]:
    r = client.get(f"/api{path}", params={"q": TAG, "_search": "opportunity_name", **params})
    r.raise_for_status()
    return [row.get("opportunity_name") for row in r.json()]


try:
    print("=" * 74)
    print("  LIST QUERY — filters, ranges, sort, read-through")
    print("=" * 74)

    client_a = post("/accounts", {"account_name": f"{TAG} client A", "account_type": ["END_CLIENT"]}, "accounts").json()["id"]
    client_b = post("/accounts", {"account_name": f"{TAG} client B", "account_type": ["END_CLIENT"]}, "accounts").json()["id"]

    leads = [
        ("List probe 1", 20_000, "2026-10-01", client_a),
        ("List probe 2", 100_000, "2026-12-01", client_b),
        ("List probe 3", None, None, client_a),
        ("List probe 4", 5_000, "2027-02-01", client_b),
    ]
    for name, value, month, end_client in leads:
        body = {
            "opportunity_name": name,
            "project_stage": "1_DEMO_PRESENTATION",
            "lead_status": "OPEN",
            "end_client": end_client,
            "bd_owner": USER.user_id,
        }
        if value is not None:
            body["estimated_value"] = value
        if month is not None:
            body["expected_close_month"] = month
        r = post("/leads", body, "leads")
        detail = r.json().get("detail") if r.status_code == 422 else None
        if isinstance(detail, dict) and detail.get("code") == "POSSIBLE_DUPLICATE":
            body["not_duplicate_reason"] = "Separate probe rows for the list query test."
            r = post("/leads", body, "leads")
        check(f"{name} saves", r.status_code == 201, r.text[:300])

    print("\n1  Sort compares numbers as numbers, blanks last both ways")
    asc = names("/leads", _sort="estimated_value", _order="asc")
    check("ascending by value", asc == ["List probe 4", "List probe 1", "List probe 2", "List probe 3"], str(asc))
    desc = names("/leads", _sort="estimated_value", _order="desc")
    check("descending by value opens on the biggest", desc == ["List probe 2", "List probe 1", "List probe 4", "List probe 3"], str(desc))

    print("\n2  Ranges are inclusive, and a blank is outside every range")
    got = names("/leads", estimated_value_gte="20000")
    check("value >= 20,000", sorted(got) == ["List probe 1", "List probe 2"], str(got))
    got = names("/leads", estimated_value_gte="5000", estimated_value_lte="20000")
    check("5,000 <= value <= 20,000", sorted(got) == ["List probe 1", "List probe 4"], str(got))
    got = names("/leads", expected_close_month_gte="2026-11-01", expected_close_month_lte="2026-12-31")
    check("close month Nov–Dec 2026", got == ["List probe 2"], str(got))

    usd = names("/leads", **{"revenue.usd_gte": "20000", "_sort": "revenue.usd", "_order": "desc"})
    check("a range and a sort through one dot — revenue.usd", usd == ["List probe 2", "List probe 1"], str(usd))

    print("\n3  Equality filters repeat as OR, and combine with ranges")
    got = names("/leads", end_client=client_a)
    check("one End Client", sorted(got) == ["List probe 1", "List probe 3"], str(got))
    r = client.get("/api/leads", params=[("q", TAG), ("_search", "opportunity_name"), ("end_client", client_a), ("end_client", client_b), ("estimated_value_lte", "20000")])
    got = sorted(row["opportunity_name"] for row in r.json())
    check("either End Client, value <= 20,000", got == ["List probe 1", "List probe 4"], str(got))
    check("X-Total-Count is the filtered total", r.headers.get("x-total-count") == "2", r.headers.get("x-total-count"))

    print("\n4  The filter panel's operators")
    got = names("/leads", end_client_ne=client_a)
    check("isn't: End Client isn't A", sorted(got) == ["List probe 2", "List probe 4"], str(got))
    got = names("/leads", estimated_value_empty="1")
    check("is empty: no value", got == ["List probe 3"], str(got))
    got = names("/leads", estimated_value_empty="0")
    check("is not empty: has a value", sorted(got) == ["List probe 1", "List probe 2", "List probe 4"], str(got))
    got = names("/leads", estimated_value_gt="5000", estimated_value_lt="100000")
    check("strict > and <", got == ["List probe 1"], str(got))
    got = names("/leads", end_client_contains="CLIENT b")
    check("contains reads the lookup's name, any case", sorted(got) == ["List probe 2", "List probe 4"], str(got))
    got = names("/leads", end_client_ncontains="client b")
    check("doesn't contain", sorted(got) == ["List probe 1", "List probe 3"], str(got))
    got = names("/leads", opportunity_name_is="list probe 3")
    check("is (text), any case", got == ["List probe 3"], str(got))
    got = names("/leads", opportunity_name_isnt="list probe 3")
    check("isn't (text)", len(got) == 3 and "List probe 3" not in got, str(got))
    got = names("/leads", opportunity_name_starts="list probe 2")
    check("starts with", got == ["List probe 2"], str(got))
    got = names("/leads", is_primary_pursuit_is="true")
    check("checkbox is Yes", len(got) >= 1, str(got))
    everyone = names("/leads")
    got_yes = names("/leads", is_primary_pursuit_is="true")
    got_no = names("/leads", is_primary_pursuit_isnt="true")
    check("checkbox is No holds every row that isn't Yes", sorted(got_yes + got_no) == sorted(everyone), f"{got_yes} + {got_no}")

    print("\n5  Opportunity rows carry their read-through identity")
    lead_id = created["leads"][0]
    r = post(
        "/opportunities",
        {"parent_lead": lead_id, "project_stage": "4_RFP_RFI", "lead_status": "OPEN", "conversion_note": "List probe."},
        "opportunities",
    )
    check("the Opportunity saves", r.status_code == 201, r.text[:300])
    opp_id = r.json()["id"] if r.status_code == 201 else None
    record = client.get(f"/api/opportunities/{opp_id}").json() if opp_id else {}
    check("a RECORD read stays what the record stores — no End Client copied", not record.get("end_client"), str(record.get("end_client")))
    rows = client.get("/api/opportunities", params={"end_client": client_a, "bd_owner": USER.user_id}).json()
    row = next((x for x in rows if x["id"] == opp_id), None)
    check("filtering Opportunities by End Client and owner finds it", row is not None, str([x["id"] for x in rows]))
    check("…with the parent Lead's name", row is not None and row.get("opportunity_name") == "List probe 1", str(row and row.get("opportunity_name")))
    check("…and the End Client's label", row is not None and (row.get("__labels") or {}).get("end_client") == f"{TAG} client A", str(row and row.get("__labels")))
    rows = client.get("/api/opportunities", params={"end_client": client_b}).json()
    check("…and a different End Client does not match it", opp_id not in [x["id"] for x in rows])

finally:
    print("\nCleanup")
    for collection in ("opportunities", "leads", "accounts"):
        for record_id in reversed(created[collection]):
            client.delete(f"/api/{collection}/{record_id}")

print()
if failures:
    print(f"{len(failures)} failed")
    for f in failures:
        print(f"  - {f}")
    sys.exit(1)
print("all passed")
