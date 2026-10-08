"""
Pipeline snapshots — the open pipeline, written down on the day (migration 0041).

WHAT IS COUNTED
---------------
Exactly the dashboard's Pipeline tile with no range: Leads and Opportunities
whose revenue is counted (Open / On Hold, primary pursuit), in USD, by
app/revenue.py's one-field-per-module rule. Weighted is each record's USD x its
own Probability % — the stage's, unless someone overrode it with a
justification. Deals are sold work, not pipeline. The rows are built by the
dashboard's own `_rows`, so a snapshot taken today and the tile agree to the
cent, and a rule change in one is a rule change in both.

Dimensions are read from the Lead each record descends from (BD Owner, Booking
Region, Segment are Lead fields the later modules read through).

WHEN IT IS WRITTEN
------------------
1. At 23:55 company time (app/clock.py) on the last day of every month, by a
   timer inside the API. This is the ONE exception to CLAUDE.md hard rule 6,
   decided 28 Sep 2026: it writes aggregates and nothing else — no record is
   changed, nobody is emailed.
2. At start-up, when the table is empty — the chart's starting point, so a new
   deployment does not wait up to a month for its first point.
3. By hand, POST /api/pipeline-snapshots, ADMIN or DEVELOPER.

A DAY IS WRITTEN ONCE
---------------------
If any row exists for the day, nothing is written and the response says when
it was taken. The unique index (NULLS NOT DISTINCT) makes that hold under a
race too — two workers, two timers, a person and the timer.

A LATE SNAPSHOT IS STILL TODAY'S PIPELINE
-----------------------------------------
Only the present can be measured. A snapshot dated in the past records the
pipeline as it stands NOW under an earlier date, so it is allowed only for a
month-end missed by at most LATE_GRACE_DAYS (the server was down on the
night), and `created_at` shows how late it was. Anything older is refused
rather than invented.

NOT BEFORE ITS MIGRATION
------------------------
create_all can build this table before 0041 runs (it did, on 28 Sep 2026, when
the dev server reloaded). Nothing is written until the migration's
insert-only trigger exists, so the table the migration replaces is empty.
"""

from __future__ import annotations

import asyncio
import os
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import exists, func, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from .clock import COMPANY_TZ, now_utc, today_company
from .database import SessionLocal
from .fiscal import add_months
from .models import Lead, Opportunity, PipelineSnapshot

#: The migration's trigger. Its presence is how the writer knows 0041 has run.
INSERT_ONLY_TRIGGER = "trg_pipeline_snapshots_insert_only"

#: Company time on the month's last day.
RUN_AT = time(23, 55)

#: How late a missed month-end may still be taken by hand.
LATE_GRACE_DAYS = 7

#: The timer wakes at least this often to re-check the clock, so a suspended
#: VM or a clock correction delays the run by at most this much.
MAX_SLEEP_SECONDS = 3600


@dataclass
class SnapshotRefused(Exception):
    code: str
    message: str
    details: list[str]


def last_day_of_month(day: date) -> date:
    return add_months(day, 1) - timedelta(days=1)


def is_month_end(day: date) -> bool:
    return day == last_day_of_month(day)


def next_run(now: datetime) -> datetime:
    """The next month-end 23:55, company time, strictly after `now`."""
    local = now.astimezone(COMPANY_TZ)
    due = datetime.combine(last_day_of_month(local.date()), RUN_AT, tzinfo=COMPANY_TZ)
    if due <= local:
        due = datetime.combine(last_day_of_month(add_months(local.date(), 1)), RUN_AT, tzinfo=COMPANY_TZ)
    return due


def ready(db: Session) -> bool:
    """Whether migration 0041 has run — its trigger exists."""
    return bool(db.scalar(text("SELECT 1 FROM pg_trigger WHERE tgname = :name").bindparams(name=INSERT_ONLY_TRIGGER)))


def _money(value: float) -> Decimal:
    return Decimal(str(round(value, 2)))


def position(db: Session) -> list[dict[str, Any]]:
    """
    The pipeline now, as rows ready to insert (without date or author): the ALL
    row, then one per BD Owner, Booking Region and Segment present. A record
    whose Lead has no value for a dimension lands in that dimension's NULL row.
    """
    # Imported here: the dashboard router is the owner of the row rule, and
    # importing it at module level would load every router with this module.
    from .routers.dashboard import PIPELINE, _rows

    leads = {lead.lead_id: lead for lead in db.scalars(select(Lead))}
    opportunities = list(db.scalars(select(Opportunity)))
    pipeline = [r for r in _rows(db, leads, opportunities, []) if r.revenue["counted"] and r.module in PIPELINE]

    groups: dict[tuple[str, str | None, str | None, str | None], list] = {("ALL", None, None, None): list(pipeline)}
    for r in pipeline:
        root = r.root
        owner = root.bd_owner if root else None
        region = root.booking_region if root else None
        # Segment is the Lead's `theme` field since Release 1.1 (the old Segment is deleted).
        segment = root.theme if root else None
        groups.setdefault(("BD_OWNER", owner, None, None), []).append(r)
        groups.setdefault(("BOOKING_REGION", None, region, None), []).append(r)
        groups.setdefault(("SEGMENT", None, None, segment), []).append(r)

    return [
        {
            "dimension": dimension,
            "bd_owner_id": owner,
            "booking_region": region,
            "segment": segment,
            "open_value_usd": _money(sum(r.usd for r in members)),
            "weighted_value_usd": _money(sum(r.weighted for r in members)),
            "deal_count": len(members),
            "unpriced_count": sum(1 for r in members if r.revenue["flag"]),
        }
        for (dimension, owner, region, segment), members in groups.items()
    ]


def _check_date(snapshot_date: date, today: date) -> None:
    if snapshot_date > today:
        raise SnapshotRefused(
            "SNAPSHOT_IN_FUTURE",
            "A snapshot can't be taken for a day that hasn't come yet.",
            ["Take it on the day, or leave it to the month-end run."],
        )
    if snapshot_date < today and not (is_month_end(snapshot_date) and (today - snapshot_date).days <= LATE_GRACE_DAYS):
        raise SnapshotRefused(
            "SNAPSHOT_TOO_LATE",
            "A past day's pipeline can't be rebuilt.",
            [
                "Only today's pipeline can be measured.",
                f"A missed month-end can still be taken within {LATE_GRACE_DAYS} days.",
            ],
        )


def take(db: Session, snapshot_date: date, *, actor: str | None) -> dict[str, Any]:
    """
    Write one day's snapshot, or nothing if the day already has one. Commits.
    `actor` is None for the timer, the signed-in user otherwise.
    """
    if not ready(db):
        raise SnapshotRefused(
            "SNAPSHOT_NOT_READY",
            "Pipeline snapshots aren't set up on this server yet.",
            ["Ask a developer to run the database upgrade."],
        )
    today = today_company()
    _check_date(snapshot_date, today)

    taken_at = db.scalar(
        select(func.min(PipelineSnapshot.created_at)).where(PipelineSnapshot.snapshot_date == snapshot_date)
    )
    if taken_at is not None:
        return {"snapshot_date": snapshot_date, "written": 0, "already_taken_at": taken_at, "late_by_days": None}

    stamp = now_utc()
    rows = [{**row, "snapshot_date": snapshot_date, "created_at": stamp, "created_by": actor} for row in position(db)]
    # RETURNING, not rowcount: a multi-row insert does not report its count.
    written = db.execute(
        insert(PipelineSnapshot).values(rows).on_conflict_do_nothing().returning(PipelineSnapshot.id)
    ).all()
    db.commit()
    return {
        "snapshot_date": snapshot_date,
        "written": len(written),
        "already_taken_at": None,
        "late_by_days": (today - snapshot_date).days or None,
    }


# ---------------------------------------------------------------------------
# the timer
# ---------------------------------------------------------------------------


def _timer_enabled() -> bool:
    """On unless PIPELINE_SNAPSHOT_TIMER=off — for a second instance on the same database."""
    return os.getenv("PIPELINE_SNAPSHOT_TIMER", "on").strip().lower() not in {"off", "false", "0", "no"}


def _run(snapshot_date: date | None, *, only_if_empty: bool) -> None:
    """One timer run, on its own session. Never raises: a failed run must not stop the next."""
    try:
        with SessionLocal() as db:
            if not ready(db):
                print("[pipeline snapshot] migration 0041 has not run here - nothing written")
                return
            if only_if_empty and db.scalar(select(exists().select_from(PipelineSnapshot))):
                return
            outcome = take(db, snapshot_date or today_company(), actor=None)
            if outcome["written"]:
                print(f"[pipeline snapshot] {outcome['snapshot_date']}: {outcome['written']} rows")
    except Exception as error:  # noqa: BLE001 — logged, and the loop goes on
        print(f"[pipeline snapshot] failed: {error!r}")


async def _timer() -> None:
    await asyncio.to_thread(_run, None, only_if_empty=True)
    while True:
        due = next_run(now_utc())
        while (wait := (due - now_utc()).total_seconds()) > 0:
            await asyncio.sleep(min(wait, MAX_SLEEP_SECONDS))
        await asyncio.to_thread(_run, due.date(), only_if_empty=False)


@asynccontextmanager
async def lifespan(_app):
    """Starts the month-end timer with the API and stops it with the API."""
    task = asyncio.create_task(_timer()) if _timer_enabled() else None
    try:
        yield
    finally:
        if task is not None:
            task.cancel()
