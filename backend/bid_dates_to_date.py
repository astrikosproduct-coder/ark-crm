"""
Submission Deadline and Bid Submission Date become date fields in the register.

    python bid_dates_to_date.py            # dry run: shows the result, writes nothing
    python bid_dates_to_date.py --apply    # write, then publish a version

Run AFTER `alembic upgrade head` (0029_bid_dates_are_dates), which retypes the
two columns. This is the register half of the same decision (16 Sep 2026): a
bid deadline is a DAY, and the time of day was never read by anything.

It also fixes what looked like data loss. A datetime field reaches the form as
"2027-02-14T17:23:00+00:00"; a browser's datetime-local box only accepts
"2027-02-14T17:23" and renders an offset value as EMPTY, so both fields went
blank after every save. A date box takes "2027-02-14" unchanged.

WHAT DOES NOT CHANGE
--------------------
api_names, labels, sections, order, capture_stage (4), Mandatory, the 4 -> 5
block, and submitted_on_time's expression — comparing two ISO dates as text
orders them correctly, exactly as it did for two ISO timestamps.

The definitions are scope 'pipeline' and are placed on Opportunities only, so
no other module's layout moves.
"""

from __future__ import annotations

import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from fastapi import HTTPException  # noqa: E402
from sqlalchemy import select  # noqa: E402

from app.database import SessionLocal, engine  # noqa: E402

engine.echo = False

from app.models import FieldDefinition  # noqa: E402
from app.routers.metadata import _publish, _validation_out, build_snapshot  # noqa: E402

RETYPED = ("submission_deadline", "bid_submission_date")
NEW_TYPE = "date"

NOTE = "Submission Deadline and Bid Submission Date are date fields, not date-and-time"


def apply(db) -> tuple[list[str], list[str]]:
    log: list[str] = []
    problems: list[str] = []

    for api_name in RETYPED:
        definition = db.scalars(
            select(FieldDefinition).where(
                FieldDefinition.api_name == api_name,
                FieldDefinition.scope_key == "pipeline",
                FieldDefinition.status == "active",
            )
        ).first()
        if definition is None:
            problems.append(f"no active pipeline definition for {api_name}")
            continue
        if definition.field_type == NEW_TYPE:
            continue
        if definition.field_type != "datetime":
            problems.append(f"{api_name} is {definition.field_type!r}, not 'datetime' — check before retyping")
            continue
        log.append(f"{api_name}: type 'datetime' -> {NEW_TYPE!r}")
        definition.field_type = NEW_TYPE

    return log, problems


def show_result(db) -> None:
    rows = [r for r in build_snapshot(db)["fields"] if r.get("api_name") in RETYPED]
    for r in rows:
        print(
            f"    {r.get('module'):15} {r.get('api_name'):22} type={r.get('type'):9} "
            f"stage={r.get('capture_stage')} {r.get('requirement')}"
        )


def main() -> int:
    applying = "--apply" in sys.argv
    with SessionLocal() as db:
        log, problems = apply(db)
        print(f"Bid dates -> date — {'apply' if applying else 'dry run'}")
        print("=" * 74)
        for line in log or ["nothing to do"]:
            print(f"  {line}")
        if problems:
            print("\nProblems — nothing written:")
            for line in problems:
                print(f"  {line}")
            db.rollback()
            return 1
        if not log:
            db.rollback()
            return 0
        db.flush()
        if not applying:
            show_result(db)
            validation = _validation_out(build_snapshot(db))
            print(f"\nValidation: {'ok' if validation.ok else 'FAILED'}")
            for error in validation.errors:
                print(f"  error: {error}")
            db.rollback()
            print("Dry run — nothing written. Re-run with --apply.")
            return 0 if validation.ok else 1
        try:
            result = _publish(db, build_snapshot(db), NOTE, None)
        except HTTPException as exc:
            db.rollback()
            print(f"\nNot published, nothing written: {exc.detail}")
            return 1
        db.commit()
        print(f"\nPublished metadata version {result.version.version_no}.")
        for path in result.written:
            print(f"  wrote {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
