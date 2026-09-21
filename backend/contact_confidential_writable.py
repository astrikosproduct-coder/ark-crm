"""
Contacts — Confidential becomes a checkbox a person can tick again.

    python contact_confidential_writable.py             dry run: report, write nothing
    python contact_confidential_writable.py --apply     write, then publish

WHY IT STOPPED WORKING
----------------------
The register marks contacts.confidential `System`. Since the server began
stamping Created / Modified By from the Entra session, the form renders every
System field read-only (FieldControl.tsx, isSystemField) — correctly, for the
fields the application writes. Nothing writes Confidential: it is a judgement a
person makes about a contact, so `System` was a mislabel that the read-only rule
made visible. The contacts API already accepts the value; only the register
was wrong.

The fix is the register's, not a special case in the form: requirement
System -> Optional.
"""

from __future__ import annotations

import argparse
import sys

from sqlalchemy import select

from app.database import SessionLocal
from app.models import FieldPlacement

MODULE = "contacts"
API_NAME = "confidential"
REQUIREMENT = "Optional"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="write the change and publish")
    parser.add_argument("--user", default=None, help="acting user_id for the published version")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        placement = db.scalar(
            select(FieldPlacement).where(
                FieldPlacement.module_key == MODULE,
                FieldPlacement.api_name == API_NAME,
            )
        )
        if placement is None:
            print(f"{MODULE}.{API_NAME}: no placement on this module")
            return 1

        print(
            f"{MODULE}.{API_NAME}: requirement {placement.requirement!r} -> {REQUIREMENT!r}, "
            f"editable {placement.editable!r}"
        )
        if placement.requirement == REQUIREMENT and placement.editable is not False:
            print("Already writable — nothing to do.")
            return 0

        placement.requirement = REQUIREMENT
        if placement.editable is False:
            placement.editable = True

        if not args.apply:
            db.rollback()
            print("\nDry run — nothing written. Re-run with --apply.")
            return 0

        db.flush()

        from app.metadata_spec import build_snapshot
        from app.routers.metadata import _publish

        result = _publish(
            db,
            build_snapshot(db),
            "Contacts: Confidential is a person's judgement, not system-stamped — "
            "requirement System -> Optional",
            args.user,
        )
        db.commit()
        print(f"\nApplied and published: version {result.version.version_no}")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
