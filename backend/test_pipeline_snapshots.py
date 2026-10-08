"""
Pipeline snapshots: written once a day, never updated, and equal to the tile.

    python run_tests.py test_pipeline_snapshots.py

Migration 0041, app/pipeline_snapshots.py, 28 Sep 2026. The test database is a
copy of the live one and may already hold pursuits, so the pipeline checks
compare the snapshot with the dashboard read at the same moment, never with an
absolute total.
"""

import os
import sys
from datetime import date, datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import delete, func, select, text  # noqa: E402
from sqlalchemy.exc import DBAPIError  # noqa: E402

import test_db  # noqa: E402

test_db.require_test_database()

from app import pipeline_snapshots as snapshots  # noqa: E402
from app.auth import current_user  # noqa: E402
from app.clock import COMPANY_TZ, now_utc, today_company  # noqa: E402
from app.database import SessionLocal  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Account, PipelineSnapshot, User, UserRole  # noqa: E402
from test_support import sign_in_as_admin  # noqa: E402

client = TestClient(app)
ADMIN = sign_in_as_admin(app)
admin_override = app.dependency_overrides[current_user]
failures: list[str] = []
created_leads: list[str] = []
VIEWER = ("USR-T-PS1", "Snapshot Viewer")


def check(label: str, condition: bool, detail: str = "") -> None:
    if condition:
        print(f"  pass  {label}")
    else:
        failures.append(f"{label}{' — ' + detail if detail else ''}")
        print(f"  FAIL  {label}{' — ' + detail if detail else ''}")


def close(a: float, b: float) -> bool:
    return abs(a - b) < 0.01


def code_of(response) -> str | None:
    detail = response.json().get("detail")
    return detail.get("code") if isinstance(detail, dict) else None


def section(title: str) -> None:
    print(f"\n{title}\n" + "-" * len(title))


def at(y, m, d, hh, mm) -> datetime:
    return datetime(y, m, d, hh, mm, tzinfo=COMPANY_TZ)


today = today_company()

try:
    print("=" * 74)
    print("  PIPELINE SNAPSHOTS — once a day, never updated")
    print("=" * 74)

    # ------------------------------------------------------------- the clock
    section("1  The month-end timer")
    due = snapshots.next_run(at(2026, 9, 28, 10, 0))
    check("from 28 Sep it next runs 30 Sep 23:55 company time", due == at(2026, 9, 30, 23, 55), str(due))
    check("at 23:55 on the 30th, the next run is 31 Oct", snapshots.next_run(at(2026, 9, 30, 23, 55)) == at(2026, 10, 31, 23, 55))
    check("February's last day is found", snapshots.next_run(at(2027, 2, 3, 9, 0)) == at(2027, 2, 28, 23, 55))
    # 18:30 UTC on 30 Sep is already 1 Oct in company time: September's run has passed.
    check("a UTC instant is read in company time", snapshots.next_run(datetime(2026, 9, 30, 18, 30, tzinfo=timezone.utc)) == at(2026, 10, 31, 23, 55))

    section("2  Which days can be taken")
    ok = lambda day, now: snapshots._check_date(day, now)  # noqa: E731
    for label, day, now, allowed in (
        ("today", date(2026, 10, 5), date(2026, 10, 5), True),
        ("a missed month-end, 5 days late", date(2026, 9, 30), date(2026, 10, 5), True),
        ("a missed month-end, 8 days late", date(2026, 9, 30), date(2026, 10, 8), False),
        ("an ordinary past day", date(2026, 10, 3), date(2026, 10, 5), False),
        ("tomorrow", date(2026, 10, 6), date(2026, 10, 5), False),
    ):
        try:
            ok(day, now)
            check(f"{label}: {'allowed' if allowed else 'refused'}", allowed)
        except snapshots.SnapshotRefused as refused:
            check(f"{label}: {'allowed' if allowed else 'refused'}", not allowed, refused.code)

    with SessionLocal() as db:
        check("the migration has run here", snapshots.ready(db))
        already = db.scalar(select(func.count()).select_from(PipelineSnapshot).where(PipelineSnapshot.snapshot_date == today))
    if already:
        print(f"  (today already has {already} snapshot rows in this copy; removing them for the test)")
        with SessionLocal() as db:
            db.execute(delete(PipelineSnapshot).where(PipelineSnapshot.snapshot_date == today))
            db.commit()

    # ------------------------------------------------------- some pipeline
    section("3  A pipeline with a known shape")
    with SessionLocal() as db:
        account = db.scalar(select(Account.account_id).order_by(Account.account_id).limit(1))
    # Several probes share one End Client, so each says it is its own project —
    # otherwise the duplicate-pursuit guard rightly stops the second.
    base = {
        "lead_status": "OPEN",
        "currency": "USD",
        "bd_owner": ADMIN.user_id,
        "not_duplicate_reason": "Snapshot test probe, a separate project.",
        **({"end_client": account} if account else {}),
    }
    for name, extra in (
        ("Snapshot probe — MEA infra", {"estimated_value": 400000, "booking_region": "MEA", "theme": "SMART_CITIES"}),
        ("Snapshot probe — India, no segment", {"estimated_value": 100000, "booking_region": "INDIA"}),
        ("Snapshot probe — unpriced", {"booking_region": "MEA", "theme": "DATA_CENTERS"}),
    ):
        r = client.post("/api/leads", json={"opportunity_name": name, "project_stage": "0_CONNECT", **base, **extra})
        check(f"lead saves: {name}", r.status_code == 201, r.text[:300])
        if r.status_code == 201:
            created_leads.append(r.json()["id"])

    # ------------------------------------------------------------- permissions
    section("4  Taking one by hand")
    with SessionLocal() as db:
        if db.get(User, VIEWER[0]) is None:
            stamp = now_utc()
            db.add(User(user_id=VIEWER[0], name=VIEWER[1], email="usr-t-ps1@example.test", active=True, created_at=stamp, updated_at=stamp))
            db.flush()
            db.add(UserRole(user_id=VIEWER[0], role_id="VIEWER"))
        db.commit()

    def as_viewer():
        with SessionLocal() as db:
            user = db.get(User, VIEWER[0])
            _ = user.roles
            db.expunge(user)
            return user

    app.dependency_overrides[current_user] = as_viewer
    r = client.post("/api/pipeline-snapshots")
    check("a Viewer cannot take one", r.status_code == 403 and code_of(r) == "TARGET_EDITOR_ONLY", r.text[:200])
    check("…but can read them", client.get("/api/pipeline-snapshots").status_code == 200)
    app.dependency_overrides[current_user] = admin_override

    tile = client.get("/api/dashboard").json()["kpis"]["pipeline"]
    r = client.post("/api/pipeline-snapshots")
    check("an Admin takes today's", r.status_code == 200 and r.json()["written"] > 0, r.text[:300])
    rows = client.get("/api/pipeline-snapshots", params={"date_from": today.isoformat(), "date_to": today.isoformat()}).json()
    everything = [x for x in rows if x["dimension"] == "ALL"]
    check("one ALL row", len(everything) == 1, str(everything))
    top = everything[0] if everything else {}
    check("…equal to the dashboard's Pipeline tile", close(top.get("open_value_usd", -1), tile["usd"]) and top.get("deal_count") == tile["count"], f"{top} vs {tile}")
    check("…weighted equal too", close(top.get("weighted_value_usd", -1), tile["weighted_usd"]))
    check("…and the unpriced count", top.get("unpriced_count") == tile["unpriced"], f"{top.get('unpriced_count')} vs {tile['unpriced']}")
    check("stamped with who took it", top.get("created_by") == ADMIN.user_id)

    section("5  One dimension per row, and each adds up to the whole")
    for dimension, column in (("BD_OWNER", "bd_owner_id"), ("BOOKING_REGION", "booking_region"), ("SEGMENT", "segment")):
        members = [x for x in rows if x["dimension"] == dimension]
        others = {"bd_owner_id", "booking_region", "segment"} - {column}
        check(f"{dimension}: no row carries another dimension", all(x[o] is None for x in members for o in others))
        check(
            f"{dimension}: rows sum to the ALL row",
            close(sum(x["open_value_usd"] for x in members), top.get("open_value_usd", 0))
            and sum(x["deal_count"] for x in members) == top.get("deal_count"),
        )
    mea = next((x for x in rows if x["dimension"] == "BOOKING_REGION" and x["booking_region"] == "MEA"), {})
    check("MEA holds at least the 400,000 probe and the unpriced one", mea.get("open_value_usd", 0) >= 400000 and mea.get("unpriced_count", 0) >= 1, str(mea))
    no_segment = next((x for x in rows if x["dimension"] == "SEGMENT" and x["segment"] is None), None)
    check("a lead with no segment lands in the Segment row with none", no_segment is not None and no_segment["open_value_usd"] >= 100000, str(no_segment))

    section("6  A day is written once")
    count_before = len(rows)
    r = client.post("/api/pipeline-snapshots")
    check("a second run writes nothing and says when it was taken", r.status_code == 200 and r.json()["written"] == 0 and r.json()["already_taken_at"], r.text[:200])
    with SessionLocal() as db:
        outcome = snapshots.take(db, today, actor=None)
        check("so does the timer's path", outcome["written"] == 0)
        count_after = db.scalar(select(func.count()).select_from(PipelineSnapshot).where(PipelineSnapshot.snapshot_date == today))
    check("the row count has not moved", count_after == count_before, f"{count_before} -> {count_after}")

    def refused(sql: str) -> tuple[bool, str]:
        with SessionLocal() as db:
            try:
                db.execute(text(sql), {"day": today})
                db.commit()
                return False, "accepted"
            except DBAPIError as error:
                db.rollback()
                return True, str(error.orig).splitlines()[0]

    no, why = refused(
        "INSERT INTO pipeline_snapshots (snapshot_date, dimension, open_value_usd, weighted_value_usd, deal_count, created_at) "
        "VALUES (:day, 'ALL', 1, 1, 0, now())"
    )
    check("the database refuses a second ALL row, NULLs and all", no and "uq_pipeline_snapshots_slice" in why, why)
    no, why = refused("UPDATE pipeline_snapshots SET open_value_usd = 0 WHERE snapshot_date = :day")
    check("the database refuses to update a snapshot", no and "never updated" in why, why)
    no, why = refused(
        "INSERT INTO pipeline_snapshots (snapshot_date, dimension, segment, booking_region, open_value_usd, weighted_value_usd, deal_count, created_at) "
        "VALUES (:day, 'SEGMENT', 'POWER', 'MEA', 1, 1, 0, now())"
    )
    check("a row cut two ways at once is refused", no and "ck_pipeline_snapshots_one_dimension" in why, why)

    r = client.post("/api/pipeline-snapshots", params={"snapshot_date": (today + timedelta(days=1)).isoformat()})
    check("tomorrow is refused in words", r.status_code == 422 and code_of(r) == "SNAPSHOT_IN_FUTURE", r.text[:200])

    section("7  The first start-up writes the starting point")
    with SessionLocal() as db:
        others = db.scalar(select(func.count()).select_from(PipelineSnapshot).where(PipelineSnapshot.snapshot_date != today))
    if others:
        print(f"  (skipped: this copy holds {others} snapshot rows from other days, so it is not a first start)")
    else:
        with SessionLocal() as db:
            db.execute(delete(PipelineSnapshot).where(PipelineSnapshot.snapshot_date == today))
            db.commit()
        snapshots._run(None, only_if_empty=True)
        with SessionLocal() as db:
            first = db.scalars(select(PipelineSnapshot).where(PipelineSnapshot.dimension == "ALL")).all()
        check("an empty table gets today's snapshot, written by nobody", len(first) == 1 and first[0].snapshot_date == today and first[0].created_by is None)
        snapshots._run(None, only_if_empty=True)
        with SessionLocal() as db:
            again = db.scalar(select(func.count()).select_from(PipelineSnapshot))
        check("a restart adds nothing", again == count_before, f"{again} vs {count_before}")

finally:
    app.dependency_overrides[current_user] = admin_override
    for lead_id in reversed(created_leads):
        r = client.delete(f"/api/leads/{lead_id}")
        if r.status_code not in (204, 404):
            print(f"  ! could not delete lead {lead_id}: {r.status_code} {r.text[:120]}")
    with SessionLocal() as db:
        db.execute(delete(PipelineSnapshot).where(PipelineSnapshot.snapshot_date == today))
        db.execute(delete(UserRole).where(UserRole.user_id == VIEWER[0]))
        db.execute(delete(User).where(User.user_id == VIEWER[0]))
        db.commit()
    print("\nCleanup done")

print()
if failures:
    print(f"{len(failures)} failed")
    for f in failures:
        print(f"  - {f}")
    sys.exit(1)
print("all passed")
