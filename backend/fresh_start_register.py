"""
The field register as version 1 — no prototype history.

    python fresh_start_register.py            # dry run: says what would go
    python fresh_start_register.py --apply    # does it, and publishes Version 1

Decided 21 Sep 2026: V1 is handed over as a fresh application, with no older
versions or history. Run on the DEVELOPMENT database before
make_release_database.py, which then carries the result to production. Run
after `alembic upgrade head` (0036 retires the pre-Round-7 archive).

WHAT GOES
---------
* Every published version (116 at the time of writing). A single new
  "Version 1" is published from the register as it stands. The register
  cannot have NO version: the Publish screen counts pending changes against
  the last published one, and the live app reads its field list from it.
* Fields deleted in Administration — their placements, and every definition
  left with no placement at all (a field retired by deleting its placement
  keeps an "active" definition that renders nowhere). The business columns
  behind them are untouched.
* Picklist choices retired (inactive), which no record can name once the
  prototype data is gone.

Nothing here touches a business table. Irreversible, like the wipe it follows.
"""

from __future__ import annotations

import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from fastapi import HTTPException  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app.database import SessionLocal, engine  # noqa: E402

engine.echo = False

from app.routers.metadata import _publish, build_snapshot  # noqa: E402

NOTE = "Version 1 — the register at go-live. Prototype history removed (21 Sep 2026)."

COUNTS = {
    "published versions": "SELECT count(*) FROM metadata_versions",
    "deleted field placements": "SELECT count(*) FROM field_placements WHERE status = 'deleted'",
    "definitions left unplaced": """SELECT count(*) FROM field_definitions d WHERE d.status = 'deleted'
        OR NOT EXISTS (SELECT 1 FROM field_placements p WHERE p.definition_id = d.id AND p.status = 'active')""",
    "retired picklist choices": "SELECT count(*) FROM picklist_values WHERE NOT active",
}

STEPS = [
    "DELETE FROM field_placements WHERE status = 'deleted'",
    """DELETE FROM field_definitions d
       WHERE NOT EXISTS (SELECT 1 FROM field_placements p WHERE p.definition_id = d.id)""",
    "DELETE FROM picklist_values WHERE NOT active",
    # Raw SQL on purpose: the ORM refuses to delete a published version
    # (routers/metadata.py::_guard_immutable), which is right everywhere but here.
    "DELETE FROM metadata_versions",
]


def main() -> int:
    apply = "--apply" in sys.argv
    with SessionLocal() as db:
        print(f"Fresh start for the field register — {'apply' if apply else 'dry run'}")
        print("=" * 74)
        for label, sql in COUNTS.items():
            print(f"  {label:<28} {db.execute(text(sql)).scalar():>5}  -> removed")
        if not apply:
            print("\nDry run — nothing written. Re-run with --apply.")
            return 0
        for sql in STEPS:
            db.execute(text(sql))
        db.flush()
        try:
            result = _publish(db, build_snapshot(db), NOTE, None)
        except HTTPException as exc:
            db.rollback()
            print(f"\nNot published, nothing written: {exc.detail}")
            return 1
        db.commit()
        print(f"\nPublished metadata version {result.version.version_no}: {NOTE}")
        for path in result.written:
            print(f"  wrote {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
