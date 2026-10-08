"""
Sales targets and the fiscal year: the acceptance criteria of Dashboard Phase 1.

    python run_tests.py test_sales_targets.py

Migration 0040, app/sales_targets.py, app/fiscal.py, 28 Sep 2026. Checked over
HTTP as real users — a Viewer, an Admin, a Developer — because "only admins
and developers write" is a server rule, and at the database with raw SQL,
because "a locked target never changes" must hold whoever writes.
"""

import os
import subprocess
import sys
from datetime import date
from decimal import Decimal

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import delete, select, text  # noqa: E402
from sqlalchemy.exc import DBAPIError  # noqa: E402

import test_db  # noqa: E402

test_db.require_test_database()

from app import fiscal  # noqa: E402
from app.auth import current_user  # noqa: E402
from app.clock import now_utc  # noqa: E402
from app.database import SessionLocal  # noqa: E402
from app.main import app  # noqa: E402
from app.models import AuditLog, IdSequence, SalesTarget, User, UserRole  # noqa: E402
from app.routers import dashboard as dashboard_module  # noqa: E402
from app.sales_targets import seed_year  # noqa: E402

client = TestClient(app)
failures: list[str] = []

PEOPLE = {
    "viewer": ("USR-T-ST1", "Target Viewer", ["VIEWER"]),
    "admin": ("USR-T-ST2", "Target Admin", ["ADMIN"]),
    "developer": ("USR-T-ST3", "Target Developer", ["DEVELOPER"]),
    "bd1": ("USR-T-ST4", "Target BD One", ["BD_OWNER"]),
    "bd2": ("USR-T-ST5", "Target BD Two", ["BD_OWNER"]),
    "sales": ("USR-T-ST6", "Target Sales Owner", ["SALES_OWNER"]),
}
IDS = [p[0] for p in PEOPLE.values()]
BD1, BD2 = PEOPLE["bd1"][0], PEOPLE["bd2"][0]


def check(label: str, condition: bool, detail: str = "") -> None:
    if condition:
        print(f"  pass  {label}")
    else:
        failures.append(f"{label}{' — ' + detail if detail else ''}")
        print(f"  FAIL  {label}{' — ' + detail if detail else ''}")


def act_as(key: str) -> None:
    user_id = PEOPLE[key][0]

    def _current_user():
        with SessionLocal() as db:
            user = db.get(User, user_id)
            _ = user.roles
            db.expunge(user)
            return user

    app.dependency_overrides[current_user] = _current_user


def code_of(response) -> str | None:
    detail = response.json().get("detail")
    return detail.get("code") if isinstance(detail, dict) else None


def refused_by_database(sql: str, **params) -> tuple[bool, str]:
    """Run raw SQL; True if PostgreSQL refused it."""
    with SessionLocal() as db:
        try:
            db.execute(text(sql), params)
            db.commit()
            return False, "accepted"
        except DBAPIError as error:
            db.rollback()
            return True, str(error.orig).splitlines()[0]


def section(title: str) -> None:
    print(f"\n{title}\n" + "-" * len(title))


with SessionLocal() as db:
    for user_id, name, roles in PEOPLE.values():
        if db.get(User, user_id) is None:
            stamp = now_utc()
            db.add(User(user_id=user_id, name=name, email=f"{user_id.lower()}@example.test", active=True, created_at=stamp, updated_at=stamp))
            db.flush()
        for role_id in roles:
            if db.get(UserRole, (user_id, role_id)) is None:
                db.add(UserRole(user_id=user_id, role_id=role_id))
    db.commit()

try:
    print("=" * 74)
    print("  SALES TARGETS — owner x month, locked means locked")
    print("=" * 74)

    # ------------------------------------------------------------------ fiscal
    section("1  The fiscal year comes from one setting")
    check("the setting defaults to April", fiscal.FISCAL_YEAR_START_MONTH == 4)
    check("01 Apr 2026 is month 1 of FY27", fiscal.label_of(date(2026, 4, 1)) == "FY27" and fiscal.month_number(date(2026, 4, 1)) == 1)
    check("31 Mar 2027 is month 12 of FY27", fiscal.label_of(date(2027, 3, 31)) == "FY27" and fiscal.month_number(date(2027, 3, 31)) == 12)
    check("31 Mar 2026 is still FY26", fiscal.label_of(date(2026, 3, 31)) == "FY26")
    check("FY27 runs 01 Apr 2026 to 31 Mar 2027", (fiscal.first_day("FY27"), fiscal.last_day("FY27")) == (date(2026, 4, 1), date(2027, 3, 31)))
    months = fiscal.months_of("FY27")
    check("its twelve months are Apr 2026 … Mar 2027", len(months) == 12 and months[0] == date(2026, 4, 1) and months[-1] == date(2027, 3, 1))
    quarters = {q: fiscal.quarter_bounds(date(2026 + (m < 4), m, 15)) for q, m in (("Q1", 5), ("Q2", 8), ("Q3", 11), ("Q4", 2))}
    check(
        "Q1 Apr-Jun, Q2 Jul-Sep, Q3 Oct-Dec, Q4 Jan-Mar",
        quarters
        == {
            "Q1": (date(2026, 4, 1), date(2026, 6, 30)),
            "Q2": (date(2026, 7, 1), date(2026, 9, 30)),
            "Q3": (date(2026, 10, 1), date(2026, 12, 31)),
            "Q4": (date(2027, 1, 1), date(2027, 3, 31)),
        },
        str(quarters),
    )
    check(
        "the dashboard's quarter presets use the same rule",
        dashboard_module.quarter_of(date(2026, 5, 15))[:2] == (date(2026, 4, 1), date(2026, 6, 30)),
    )
    probe = (
        "from datetime import date; from app import fiscal; "
        "print(fiscal.FISCAL_YEAR_START_MONTH, fiscal.label_of(date(2027,1,1)), fiscal.month_number(date(2027,1,1)), "
        "fiscal.quarter_bounds(date(2027,2,1))[0])"
    )
    out = subprocess.run(
        [sys.executable, "-c", probe], env={**os.environ, "FISCAL_YEAR_START_MONTH": "1"}, capture_output=True, text=True
    )
    check(
        "set to 1, January opens FY27 as month 1 and Q1 starts in January",
        out.stdout.split() == ["1", "FY27", "1", "2027-01-01"],
        out.stdout + out.stderr[-300:],
    )
    out = subprocess.run(
        [sys.executable, "-c", "import app.fiscal"], env={**os.environ, "FISCAL_YEAR_START_MONTH": "13"}, capture_output=True, text=True
    )
    check("a month that isn't 1-12 stops start-up", out.returncode != 0 and "FISCAL_YEAR_START_MONTH" in out.stderr, out.stderr[-200:])

    # ------------------------------------------------------------- permissions
    section("2  Anyone with a role reads; only Admin and Developer write")
    body = {"bd_owner_id": BD1, "period_month": "2026-05-01", "target_amount_usd": 250000}
    act_as("viewer")
    r = client.get("/api/sales-targets", params={"fiscal_year": "FY27"})
    check("a Viewer reads targets", r.status_code == 200, r.text[:200])
    r = client.post("/api/sales-targets", json=body)
    check("a Viewer cannot create one", r.status_code == 403 and code_of(r) == "TARGET_EDITOR_ONLY", r.text[:200])
    act_as("sales")
    check("nor can a Sales Owner", client.post("/api/sales-targets", json=body).status_code == 403)

    act_as("admin")
    r = client.post("/api/sales-targets", json={**body, "created_by": "USR-T-ST1", "fiscal_year": "FY99", "status": "LOCKED"})
    check("an Admin creates one", r.status_code == 201, r.text[:300])
    t1 = r.json() if r.status_code == 201 else {}
    check("…as a draft, in FY27, worked out from the month", t1.get("status") == "DRAFT" and t1.get("fiscal_year") == "FY27", str(t1))
    check("…stamped with the Admin, never the body's author", t1.get("created_by") == PEOPLE["admin"][0] and t1.get("updated_by") == PEOPLE["admin"][0])
    check("…in USD", t1.get("currency") == "USD" and t1.get("target_amount_usd") == 250000)

    # ------------------------------------------------------------- the grain
    section("3  One current target per owner and month")
    r = client.post("/api/sales-targets", json=body)
    check("a duplicate owner-month is refused by the API", r.status_code == 409 and code_of(r) == "TARGET_EXISTS", r.text[:200])
    refused, why = refused_by_database(
        "INSERT INTO sales_targets (target_id, fiscal_year, period_month, bd_owner_id, target_amount_usd, "
        "status, created_at, created_by, updated_at, updated_by) "
        "VALUES ('TGT-T-DUP', 'FY27', '2026-05-01', :owner, 1, 'DRAFT', now(), :owner, now(), :owner)",
        owner=BD1,
    )
    check("…and by the database, whoever writes it", refused and "uq_sales_targets_current" in why, why)
    r = client.post("/api/sales-targets", json={**body, "period_month": "2026-05-15"})
    check("a day that isn't the 1st is refused", r.status_code == 422 and code_of(r) == "TARGET_MONTH_NOT_FIRST", r.text[:200])
    refused, why = refused_by_database(
        "INSERT INTO sales_targets (target_id, fiscal_year, period_month, bd_owner_id, target_amount_usd, "
        "status, created_at, created_by, updated_at, updated_by) "
        "VALUES ('TGT-T-MID', 'FY27', '2026-06-15', :owner, 1, 'DRAFT', now(), :owner, now(), :owner)",
        owner=BD1,
    )
    check("…in the database too", refused and "ck_sales_targets_period_month_first" in why, why)
    r = client.post("/api/sales-targets", json={**body, "bd_owner_id": PEOPLE["sales"][0]})
    check("a person without the BD Owner role gets no target", r.status_code == 422 and code_of(r) == "TARGET_OWNER_NOT_BD", r.text[:200])
    r = client.post("/api/sales-targets", json={**body, "period_month": "2026-06-01", "target_amount_usd": -1})
    check("a negative amount is refused", r.status_code == 422, r.text[:200])

    act_as("developer")
    r = client.post("/api/sales-targets", json={"bd_owner_id": BD2, "period_month": "2026-05-01", "target_amount_usd": 100000})
    check("a Developer creates one too", r.status_code == 201, r.text[:200])
    t2 = r.json() if r.status_code == 201 else {}

    # -------------------------------------------------------------- editing
    section("4  A draft is edited; a locked target is not")
    act_as("admin")
    r = client.patch(f"/api/sales-targets/{t1.get('id')}", json={"target_amount_usd": 300000})
    check("a draft's amount changes in place", r.status_code == 200 and r.json()["target_amount_usd"] == 300000, r.text[:200])
    r = client.post(f"/api/sales-targets/{t1.get('id')}/revise", json={"target_amount_usd": 1, "revision_note": "x"})
    check("a draft is not revised", r.status_code == 409 and code_of(r) == "TARGET_NOT_LOCKED", r.text[:200])
    r = client.post(f"/api/sales-targets/{t1.get('id')}/lock")
    check("locking stamps who and when", r.status_code == 200 and r.json()["status"] == "LOCKED" and r.json()["locked_by"] == PEOPLE["admin"][0] and r.json()["locked_at"], r.text[:200])
    r = client.patch(f"/api/sales-targets/{t1.get('id')}", json={"target_amount_usd": 1})
    check("editing a locked target is refused", r.status_code == 409 and code_of(r) == "TARGET_LOCKED", r.text[:200])
    r = client.post(f"/api/sales-targets/{t1.get('id')}/lock")
    check("locking it twice is refused", r.status_code == 409 and code_of(r) == "TARGET_LOCKED", r.text[:200])

    refused, why = refused_by_database("UPDATE sales_targets SET target_amount_usd = 1 WHERE target_id = :id", id=t1.get("id"))
    check("the database refuses to change a locked amount", refused and "never changes" in why, why)
    refused, why = refused_by_database(
        "UPDATE sales_targets SET status = 'SUPERSEDED', target_amount_usd = 1 WHERE target_id = :id", id=t1.get("id")
    )
    check("…or to supersede it while changing its number", refused, why)
    refused, why = refused_by_database("UPDATE sales_targets SET status = 'DRAFT', locked_at = NULL, locked_by = NULL WHERE target_id = :id", id=t1.get("id"))
    check("…or to unlock it", refused, why)
    refused, why = refused_by_database("DELETE FROM sales_targets WHERE target_id = :id", id=t1.get("id"))
    check("…or to delete it", refused and "only a draft" in why, why)

    # ------------------------------------------------------------- revising
    section("5  Revising a locked target creates a linked row")
    r = client.post(f"/api/sales-targets/{t1.get('id')}/revise", json={"target_amount_usd": 350000, "revision_note": "   "})
    check("a revision needs a reason", r.status_code == 422 and code_of(r) == "TARGET_REVISION_NOTE_MISSING", r.text[:200])
    r = client.post(
        f"/api/sales-targets/{t1.get('id')}/revise",
        json={"target_amount_usd": 350000, "revision_note": "Territory widened to KSA in May."},
    )
    check("a locked target is revised", r.status_code == 201, r.text[:300])
    t1b = r.json() if r.status_code == 201 else {}
    check("…into a new row that points back at it", t1b.get("revision_of") == t1.get("id") and t1b.get("id") != t1.get("id"))
    check("…locked at once, with the note", t1b.get("status") == "LOCKED" and t1b.get("revision_note") == "Territory widened to KSA in May.")
    check("…for the same owner and month", (t1b.get("bd_owner_id"), t1b.get("period_month")) == (BD1, "2026-05-01"))
    with SessionLocal() as db:
        original = db.get(SalesTarget, t1.get("id"))
        check(
            "the original is superseded, its number untouched",
            original.status == "SUPERSEDED" and original.target_amount_usd == Decimal("300000.00"),
            f"{original.status} {original.target_amount_usd}",
        )
    r = client.post(f"/api/sales-targets/{t1.get('id')}/revise", json={"target_amount_usd": 1, "revision_note": "again"})
    check("a superseded target is not revised again", r.status_code == 409 and code_of(r) == "TARGET_SUPERSEDED", r.text[:200])
    refused, why = refused_by_database("UPDATE sales_targets SET revision_note = 'rewritten' WHERE target_id = :id", id=t1.get("id"))
    check("the database refuses to touch a superseded row", refused, why)
    refused, why = refused_by_database(
        "INSERT INTO sales_targets (target_id, fiscal_year, period_month, bd_owner_id, target_amount_usd, "
        "status, locked_at, locked_by, revision_of, created_at, created_by, updated_at, updated_by) "
        "VALUES ('TGT-T-NONOTE', 'FY27', '2026-07-01', :owner, 1, 'LOCKED', now(), :owner, :of, now(), :owner, now(), :owner)",
        owner=BD1,
        of=t2.get("id"),
    )
    check("a revision with no note is refused by the database", refused, why)

    # ------------------------------------------------------------ the total
    section("6  The company target is the sum of current rows, once")
    act_as("viewer")
    r = client.get("/api/sales-targets", params={"fiscal_year": "FY27"})
    mine = [i for i in r.json()["items"] if i["bd_owner_id"] in (BD1, BD2)] if r.status_code == 200 else []
    check("the list holds the current rows only", sorted(i["id"] for i in mine) == sorted([t1b.get("id"), t2.get("id")]), str([i["id"] for i in mine]))
    everyone = sum(i["target_amount_usd"] for i in r.json()["items"])
    check("total_usd is their sum", abs(r.json()["total_usd"] - everyone) < 0.01)
    with SessionLocal() as db:
        sql_total = db.scalar(
            text("SELECT coalesce(sum(target_amount_usd), 0) FROM sales_targets WHERE fiscal_year = 'FY27' AND status <> 'SUPERSEDED'")
        )
    check("…and the plain SQL sum agrees", abs(float(sql_total) - r.json()["total_usd"]) < 0.01, f"{sql_total} vs {r.json()['total_usd']}")
    check("the revised owner counts 350,000, not 650,000", sum(i["target_amount_usd"] for i in mine if i["bd_owner_id"] == BD1) == 350000)
    r2 = client.get("/api/sales-targets", params={"fiscal_year": "FY27", "history": "true"})
    check(
        "history shows the superseded row, and the total does not move",
        any(i["id"] == t1.get("id") for i in r2.json()["items"]) and abs(r2.json()["total_usd"] - r.json()["total_usd"]) < 0.01,
    )
    r = client.get("/api/sales-targets", params={"fiscal_year": "2027"})
    check("a fiscal year written wrong is refused", r.status_code == 422 and code_of(r) == "FISCAL_YEAR_UNKNOWN", r.text[:200])

    # ---------------------------------------------------------------- audit
    section("7  Every change is in the audit trail")
    with SessionLocal() as db:
        trail = db.scalars(
            select(AuditLog)
            .where(AuditLog.record_module == "sales_targets", AuditLog.record_id.in_([t1.get("id"), t1b.get("id")]))
            .order_by(AuditLog.id)
        ).all()
    actions = [a.action for a in trail]
    check("created, updated, locked, superseded, revised", actions == ["created", "updated", "locked", "superseded", "revised"], str(actions))
    edit = next((a for a in trail if a.action == "updated"), None)
    check(
        "the edit records from and to",
        edit is not None and edit.changed == [{"field": "target_amount_usd", "from": 250000.0, "to": 300000.0}],
        str(edit.changed if edit else None),
    )
    check("every entry names the Admin", {a.actor for a in trail} == {PEOPLE["admin"][0]}, str({a.actor for a in trail}))

    # ----------------------------------------------------------------- seed
    section("8  The FY27 seed: twelve drafts at 0 per active BD Owner")
    with SessionLocal() as db:
        created, skipped = seed_year(db, "FY27", actor=PEOPLE["admin"][0])
        per_owner = {}
        for row in created:
            per_owner.setdefault(row.bd_owner_id, []).append(row)
        check("BD Two gets eleven: May already has a target", len(per_owner.get(BD2, [])) == 11, str(len(per_owner.get(BD2, []))))
        check("BD One gets eleven too: May's current row is the revision", len(per_owner.get(BD1, [])) == 11)
        check("every seeded row is a draft at 0 in FY27", all(r.status == "DRAFT" and r.target_amount_usd == 0 and r.fiscal_year == "FY27" for r in created))
        check("nobody without the BD Owner role is seeded", not ({r.bd_owner_id for r in created} & {PEOPLE[k][0] for k in ("viewer", "admin", "developer", "sales")}))
        again, skipped_again = seed_year(db, "FY27", actor=PEOPLE["admin"][0])
        check("running it again adds nothing", again == [] and skipped_again == skipped + len(created), f"{len(again)} {skipped_again}")
        db.rollback()

finally:
    app.dependency_overrides.pop(current_user, None)
    with SessionLocal() as db:
        ids = db.scalars(select(SalesTarget.target_id).where(SalesTarget.bd_owner_id.in_(IDS))).all()
        # Locked rows are deletable only with the guard off — a test's cleanup, never the app's.
        db.execute(text("ALTER TABLE sales_targets DISABLE TRIGGER trg_sales_targets_guard"))
        db.execute(text("UPDATE sales_targets SET revision_of = NULL WHERE bd_owner_id = ANY(:ids)"), {"ids": IDS})
        db.execute(delete(SalesTarget).where(SalesTarget.bd_owner_id.in_(IDS)))
        db.execute(text("ALTER TABLE sales_targets ENABLE TRIGGER trg_sales_targets_guard"))
        db.execute(delete(AuditLog).where(AuditLog.record_module == "sales_targets", AuditLog.record_id.in_(ids)))
        if not db.scalar(select(SalesTarget.target_id).limit(1)):
            db.execute(delete(IdSequence).where(IdSequence.name == "sales_targets"))
        db.execute(delete(UserRole).where(UserRole.user_id.in_(IDS)))
        db.execute(delete(User).where(User.user_id.in_(IDS)))
        db.commit()
        leftover = db.scalars(select(User.user_id).where(User.user_id.like("USR-T-ST%"))).all()
    print("\nCleanup", "done" if not leftover else f"left {leftover}")

print()
if failures:
    print(f"{len(failures)} failed")
    for f in failures:
        print(f"  - {f}")
    sys.exit(1)
print("all passed")
