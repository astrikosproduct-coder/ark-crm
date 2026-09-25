"""
Delete two picklists no field uses: accounts__country and sub_segment.

    python delete_dead_picklists.py            # dry run: says what it would delete
    python delete_dead_picklists.py --apply    # delete them and publish a version

Decided 25 Sep 2026 (Setup rebuild, step 3). Setup no longer has a Picklists
screen — Zoho has none: a field's choices are edited in the field, shared lists
are Global Sets. A list that no field uses would have nowhere to be seen, so
the two dead ones go for good:

  * accounts__country — replaced long ago by Region (see spec/extensions.json).
  * sub_segment       — its field was replaced by Theme.

Both were emptied by fresh_start_register.py and neither is named by any field,
live or deleted. This REVERSES the old rule "a picklist is never deleted, only
deactivated" for these two alone, on the user's instruction. The two feedback
lists, which no field uses either, are KEPT: the Feedback screens and
routers/feedback.py read them by key.

It refuses to delete a list that a field names (any status) or that still has
values, and does nothing on a database where both are already gone.

DEPLOY ORDER: run on development now; on production with the Phase 2 batch,
after `alembic upgrade head`. NO DDL — two rows in `picklists`.
"""

from __future__ import annotations

import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from fastapi import HTTPException  # noqa: E402
from sqlalchemy import func, select  # noqa: E402

from app.database import SessionLocal, engine  # noqa: E402

engine.echo = False

from app.models import FieldDefinition, Picklist, PicklistValue  # noqa: E402
from app.metadata_spec import diff_snapshots  # noqa: E402
from app.routers.metadata import (  # noqa: E402
    _latest_version,
    _publish,
    _validation_out,
    build_snapshot,
)

DEAD = ("accounts__country", "sub_segment")
NOTE = "Deleted two lists no field uses: accounts__country and sub_segment"


def plan(db) -> tuple[list[str], list[str]]:
    """(lines to report, problems that stop the run)."""
    log: list[str] = []
    problems: list[str] = []
    for key in DEAD:
        picklist = db.get(Picklist, key)
        if picklist is None:
            log.append(f"{key}: already gone")
            continue
        fields = db.scalars(
            select(FieldDefinition.scope_key + "." + FieldDefinition.api_name).where(
                FieldDefinition.picklist_key == key
            )
        ).all()
        values = db.scalar(
            select(func.count()).select_from(PicklistValue).where(PicklistValue.picklist_key == key)
        )
        if fields:
            problems.append(f"{key}: named by {', '.join(fields)} — not deleted")
        elif values:
            problems.append(f"{key}: still has {values} value(s) — not deleted")
        else:
            db.delete(picklist)
            log.append(f"{key}: deleted (no field names it, no values)")
    return log, problems


def main() -> int:
    apply = "--apply" in sys.argv
    with SessionLocal() as db:
        # Publishing takes the WHOLE draft. Anything else waiting would go live
        # under this script's note, so it stops instead — publish or undo that
        # first, in Setup.
        latest = _latest_version(db)
        pending = diff_snapshots(latest.snapshot, build_snapshot(db)) if latest else ["never published"]
        if pending:
            print("Stopped: the draft has unpublished changes, and publishing would take them too.")
            for line in pending[:20]:
                print(f"  {line}")
            print("Publish or undo them in Setup first, then run this again.")
            return 1

        log, problems = plan(db)
        print(f"Delete dead picklists — {'apply' if apply else 'dry run'}")
        print("=" * 74)
        for line in log + problems:
            print(f"  {line}")
        if problems:
            db.rollback()
            print("\nStopped: nothing written. These were not expected — look before deleting.")
            return 1
        if not any(line.endswith("no values)") for line in log):
            db.rollback()
            print("\nNothing to do.")
            return 0
        db.flush()
        if not apply:
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
