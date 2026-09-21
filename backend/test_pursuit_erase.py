"""
Deleting a pursuit for good — app/pursuit_erasure.py, decided 21 Sep 2026.

Run:  python run_tests.py test_pursuit_erase.py     (against the disposable copy)

Builds Lead -> Opportunity -> Deal, a second pursuit grouped with it, and an
expansion lead opened off the Deal; erases the first from its Deal; checks
what went, what was only unlinked, and the one line of history kept.
"""

import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from sqlalchemy import text  # noqa: E402

from app.database import SessionLocal, engine  # noqa: E402

engine.echo = False

from test_db import require_test_database  # noqa: E402

require_test_database()

from fastapi.testclient import TestClient  # noqa: E402

from app.auth import current_user  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Role, User  # noqa: E402
from test_support import sign_in_as_admin  # noqa: E402

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


made: dict[str, list[str]] = {"leads": [], "opportunities": [], "deals": [], "accounts": []}


def post(path: str, body: dict, kind: str):
    r = client.post(f"/api{path}", json=body)
    if r.status_code == 201:
        made[kind].append(r.json()["id"])
    return r


def count(sql: str, **params) -> int:
    with SessionLocal() as db:
        return db.execute(text(sql), params).scalar()


try:
    r = post("/accounts", {"account_name": "Erase Test Client", "account_type": ["END_CLIENT"]}, "accounts")
    client_id = r.json()["id"]

    r = post("/leads", {"opportunity_name": "Erase Probe", "project_stage": "3_PRESCRIPTION", "end_client": client_id}, "leads")
    lead_id = r.json()["id"]
    client.post("/api/transitions", json={"module": "leads", "record_id": lead_id, "from": 2, "to": 3, "attested": []})
    r = post("/opportunities", {"parent_lead": lead_id, "project_stage": "4_RFP_RFI", "lead_status": "OPEN",
                                  "arr_annual_recurring": 500000, "contract_years": 1, "final_negotiated_value": 500000}, "opportunities")
    opp_id = r.json()["id"]
    r = post("/deals", {"deal_name": "Erase Probe", "parent_opportunity": opp_id, "deal_stage": "7_CLOSE", "contract_value": 500000}, "deals")
    deal_id = r.json()["id"]
    check("the chain exists: Lead -> Opportunity -> Deal", bool(lead_id and opp_id and deal_id), f"{lead_id} {opp_id} {deal_id}")

    # A second pursuit for the same End Client, joined into one group with it.
    r = post("/leads", {"opportunity_name": "Erase Neighbour", "project_stage": "0_CONNECT", "end_client": client_id,
                        "join_pursuit_of": lead_id}, "leads")
    neighbour = r.json()["id"] if r.status_code == 201 else None
    check("a neighbour pursuit joins its group", neighbour is not None and r.json().get("pursuit_group"), r.text[:300])
    group_id = r.json().get("pursuit_group") if neighbour else None

    # An expansion opened off the Deal — a separate pursuit that must survive.
    r = post("/leads", {"opportunity_name": "Erase Expansion", "project_stage": "0_CONNECT", "opportunity_type": "EXPANSION",
                        "parent_deal": deal_id, "end_client": client_id, "not_duplicate_reason": "An expansion, not the same project."}, "leads")
    expansion = r.json()["id"] if r.status_code == 201 else None
    check("an expansion lead is opened off the Deal", expansion is not None, r.text[:300])

    r = client.get(f"/api/pursuits/{deal_id}/erase")
    plan = r.json()
    check("the plan, asked from the Deal, names the whole chain",
          [x["id"] for x in plan.get("records", [])] == [lead_id, opp_id, deal_id], str(plan)[:300])
    check("…and what is only unlinked", plan.get("groups") == [group_id] and plan.get("expansion_leads") == [expansion], str(plan)[:300])

    r = client.post(f"/api/pursuits/{deal_id}/erase", json={"confirm": "wrong name"})
    check("a mistyped name is refused", r.status_code == 422 and r.json()["detail"]["code"] == "CONFIRM_NAME_MISMATCH", r.text[:200])
    check("…and nothing went", count("SELECT count(*) FROM leads WHERE lead_id = :i", i=lead_id) == 1)

    # Any role may do it (decided 21 Sep 2026) — a Viewer reads the plan too.
    with SessionLocal() as db:
        db.add(User(user_id="USR-ERASETEST", name="Erase Test Viewer", email="erase.test@example.invalid",
                    active=True, roles=[db.get(Role, "VIEWER")]))
        db.commit()

    def _as_viewer():
        with SessionLocal() as db:
            viewer = db.get(User, "USR-ERASETEST")
            _ = viewer.roles
            return viewer

    app.dependency_overrides[current_user] = _as_viewer
    r = client.get(f"/api/pursuits/{deal_id}/erase")
    check("a user who is not a developer can open the plan", r.status_code == 200, f"{r.status_code} {r.text[:200]}")
    sign_in_as_admin(app)

    app.dependency_overrides[current_user] = _as_viewer
    r = client.post(f"/api/pursuits/{deal_id}/erase", json={"confirm": "erase probe"})
    check("with the name typed (any case), a Viewer deletes it", r.status_code == 200, r.text[:300])
    sign_in_as_admin(app)
    for kind, table, col, rid in (("Lead", "leads", "lead_id", lead_id), ("Opportunity", "opportunities", "opportunity_id", opp_id),
                                  ("Deal", "deals", "deal_id", deal_id)):
        check(f"…the {kind} is gone", count(f"SELECT count(*) FROM {table} WHERE {col} = :i", i=rid) == 0)
    ids = [lead_id, opp_id, deal_id]
    check("…with its stage history", count("SELECT count(*) FROM stage_transitions WHERE record_id = ANY(:i)", i=ids) == 0)
    check("…and its conversions", count("SELECT count(*) FROM conversions WHERE source_id = ANY(:i) OR target_id = ANY(:i)", i=ids) == 0)
    check("…and all but ONE audit line, saying who deleted it",
          count("SELECT count(*) FROM audit_log WHERE record_id = ANY(:i)", i=ids) == 1
          and count("SELECT count(*) FROM audit_log WHERE record_id = :i AND action = 'deleted' AND actor = 'USR-ERASETEST'", i=lead_id) == 1)
    check("the End Client stays", count("SELECT count(*) FROM accounts WHERE account_id = :i", i=client_id) == 1)
    check("the expansion lead stays, its Parent Deal cleared",
          count("SELECT count(*) FROM leads WHERE lead_id = :i AND parent_deal IS NULL", i=expansion) == 1)
    check("the neighbour stays, and its group of one is dissolved",
          count("SELECT count(*) FROM leads WHERE lead_id = :i AND pursuit_group IS NULL", i=neighbour) == 1
          and count("SELECT count(*) FROM pursuit_groups WHERE group_id = :g", g=group_id) == 0)

finally:
    sign_in_as_admin(app)
    with SessionLocal() as db:
        for table, col in (("deals", "deal_id"), ("opportunities", "opportunity_id"), ("leads", "lead_id")):
            ids = made[table]
            if ids:
                db.execute(text("DELETE FROM stage_transitions WHERE record_id = ANY(:i)"), {"i": ids})
                db.execute(text("DELETE FROM conversions WHERE source_id = ANY(:i) OR target_id = ANY(:i)"), {"i": ids})
                db.execute(text(f"UPDATE leads SET pursuit_group = NULL WHERE {col} = ANY(:i)") if table == "leads" else text("SELECT 1"), {"i": ids})
                db.execute(text(f"DELETE FROM {table} WHERE {col} = ANY(:i)"), {"i": ids})
        db.execute(text("DELETE FROM pursuit_groups WHERE end_client = ANY(:i)"), {"i": made["accounts"]})
        db.execute(text("DELETE FROM account_types WHERE account_id = ANY(:i)"), {"i": made["accounts"]})
        db.execute(text("DELETE FROM accounts WHERE account_id = ANY(:i)"), {"i": made["accounts"]})
        db.execute(text("DELETE FROM audit_log WHERE actor = 'USR-ERASETEST'"))
        db.execute(text("DELETE FROM user_roles WHERE user_id = 'USR-ERASETEST'"))
        db.execute(text("DELETE FROM users WHERE user_id = 'USR-ERASETEST'"))
        db.commit()

print(f"\n{len(passed)} passed, {len(failed)} failed")
for line in failed:
    print(f"  FAIL  {line}")
sys.exit(1 if failed else 0)
