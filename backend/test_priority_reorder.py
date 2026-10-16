"""
Release 1.2 — re-ranking Low Hanging / Top 10 from their screen, checked
through the API (PUT /api/opportunities/priority/{flag}).

    python run_tests.py test_priority_reorder.py     (against the disposable copy)

  1  A pick moves to an open rank; two picks swap in one request.
  2  Refused: a rank shared, a rank out of range, a record not on the list,
     an unknown list. Nothing moves when refused.
  3  Each record that moved gets one History line naming the rank.
  4  Adding from an open slot takes a record off the OTHER list (mutually
     exclusive), as the record's own page does.
  5  The two screens' own view settings are accepted, and a page keeps the
     view it opens on (page:<module>) — no new table.
"""

import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from app.database import engine  # noqa: E402

engine.echo = False

from test_db import require_test_database  # noqa: E402

require_test_database()

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from test_support import sign_in_as_admin  # noqa: E402

client = TestClient(app)
admin = sign_in_as_admin(app)

failed: list[str] = []
created: dict[str, list[str]] = {"opportunities": [], "leads": []}


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


def section(title: str) -> None:
    print(f"\n{title}\n" + "-" * len(title))


def opportunity(name: str) -> str | None:
    r = client.post("/api/leads", json={
        "opportunity_name": f"Rank probe — {name}", "bd_owner": admin.user_id, "currency": "USD",
        "project_stage": "3_PRESCRIPTION", "lead_status": "OPEN",
    })
    if r.status_code != 201:
        print(f"  could not make a lead: {r.status_code} {r.text[:200]}")
        return None
    created["leads"].append(r.json()["lead_id"])
    r = client.post("/api/opportunities", json={
        "parent_lead": r.json()["lead_id"], "project_stage": "4_RFP_RFI", "lead_status": "OPEN", "conversion_note": "Rank probe.",
    })
    if r.status_code != 201:
        print(f"  could not make an opportunity: {r.status_code} {r.text[:200]}")
        return None
    created["opportunities"].append(r.json()["id"])
    return r.json()["id"]


def ranks(flag: str, rank_field: str) -> dict[str, int]:
    return {
        row["id"]: row[rank_field]
        for row in client.get("/api/opportunities").json()
        if row.get(flag) and row["id"] in created["opportunities"]
    }


try:
    print("=" * 74)
    print("  RELEASE 1.2 — re-ranking Low Hanging / Top 10")
    print("=" * 74)

    # Clear the test copy's own picks so the ranks used here are free.
    for row in client.get("/api/opportunities").json():
        for flag in ("is_top_10", "is_low_hanging"):
            if row.get(flag):
                client.put(f"/api/opportunities/{row['id']}", json={flag: False})

    a, b, c = opportunity("A"), opportunity("B"), opportunity("C")
    for opp, rank in ((a, 1), (b, 2)):
        r = client.put(f"/api/opportunities/{opp}", json={"is_top_10": True, "top_10_rank": rank})
        check(f"{opp} goes on Top 10 at #{rank}", r.status_code == 200, r.text[:200])

    section("1  Moves and swaps")
    r = client.put("/api/opportunities/priority/is_top_10", json={"ranks": {a: 5}})
    check("a pick moves to an open rank", r.status_code == 204 and ranks("is_top_10", "top_10_rank") == {a: 5, b: 2},
          f"{r.status_code} {ranks('is_top_10', 'top_10_rank')}")
    r = client.put("/api/opportunities/priority/is_top_10", json={"ranks": {a: 2, b: 5}})
    check("two picks swap in one request", r.status_code == 204 and ranks("is_top_10", "top_10_rank") == {a: 2, b: 5},
          f"{r.status_code} {ranks('is_top_10', 'top_10_rank')}")

    section("2  Refusals — and nothing moves")
    before = ranks("is_top_10", "top_10_rank")
    r = client.put("/api/opportunities/priority/is_top_10", json={"ranks": {a: 5}})
    check("a rank another pick holds is refused", r.status_code == 409 and code_of(r) == "PRIORITY_RANK", f"{r.status_code} {r.text[:200]}")
    r = client.put("/api/opportunities/priority/is_top_10", json={"ranks": {a: 11}})
    check("a rank past the cap is refused", r.status_code == 409, f"{r.status_code} {r.text[:200]}")
    r = client.put("/api/opportunities/priority/is_top_10", json={"ranks": {c: 3}})
    check("a record not on the list is refused (adding is the record's own save)", r.status_code == 409, f"{r.status_code} {r.text[:200]}")
    r = client.put("/api/opportunities/priority/is_nothing", json={"ranks": {a: 3}})
    check("an unknown list is refused", r.status_code == 409, f"{r.status_code} {r.text[:200]}")
    check("…and nothing moved", ranks("is_top_10", "top_10_rank") == before, str(ranks("is_top_10", "top_10_rank")))

    section("3  History")
    rows = client.get("/api/audit-log", params={"module": "opportunities", "record_id": a}).json()
    rows = rows.get("rows", rows) if isinstance(rows, dict) else rows
    moved = [x for x in rows if any(ch.get("field") == "top_10_rank" for ch in (x.get("changed") or []))]
    check("each move left a History line naming the rank", len(moved) >= 2, str(rows)[:300])

    section("4  Adding from an open slot")
    r = client.put(f"/api/opportunities/{c}", json={"is_low_hanging": True, "low_hanging_rank": 1})
    check("C goes on Low Hanging", r.status_code == 200, r.text[:200])
    r = client.put(f"/api/opportunities/{c}", json={"is_top_10": True, "top_10_rank": 3})
    got = client.get(f"/api/opportunities/{c}").json()
    check("added to Top 10's open #3, it leaves Low Hanging",
          r.status_code == 200 and got.get("top_10_rank") == 3 and not got.get("is_low_hanging"), str({k: got.get(k) for k in ("is_top_10", "top_10_rank", "is_low_hanging")}))

    section("5  Each screen's own view settings")
    for key in ("list:opportunities_low_hanging", "list:opportunities_top_ten"):
        r = client.put(f"/api/view-preferences/{key}", json={"settings": {"columns": ["opportunity_name", "theme"], "wrap": False}})
        check(f"{key} is kept", r.status_code == 200, f"{r.status_code} {r.text[:200]}")
        client.delete(f"/api/view-preferences/{key}")
    r = client.put("/api/view-preferences/page:opportunities", json={"settings": {"default_view": "top-10"}})
    check("a page keeps the view it opens on", r.status_code == 200 and client.get("/api/view-preferences/page:opportunities").json()["settings"] == {"default_view": "top-10"}, r.text[:200])
    r = client.put("/api/view-preferences/page:opportunities", json={"settings": {"columns": ["x"]}})
    check("…and nothing else", r.status_code == 422, f"{r.status_code} {r.text[:200]}")
    r = client.put("/api/view-preferences/page:opportunities", json={"settings": {"default_view": "<script>"}})
    check("…and only a view's name", r.status_code == 422, f"{r.status_code} {r.text[:200]}")
    client.delete("/api/view-preferences/page:opportunities")

finally:
    section("Cleanup")
    for opp in created["opportunities"]:
        for flag in ("is_top_10", "is_low_hanging"):
            client.put(f"/api/opportunities/{opp}", json={flag: False})

print()
if failed:
    print(f"{len(failed)} FAILED")
    for line in failed:
        print(f"  - {line}")
    sys.exit(1)
print("all passed")
