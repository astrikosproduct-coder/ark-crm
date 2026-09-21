"""
Expected Timeline is a date, and Decided By's help text names no role — the
register half of migration 0026.

    python expected_timeline_metadata.py             # dry run: what would change
    python expected_timeline_metadata.py --apply     # change the register AND publish a version
    python expected_timeline_metadata.py --revert    # put both back (publishes too)

Run AFTER `alembic upgrade head`: 0026 makes deal_registrations.expected_timeline
a DATE column, and this makes the register say the same. Publishing is part of
--apply on purpose — regenerate_spec.py alone writes the files but records no
metadata version, so Administration would go on listing the change as pending.

Decided By said "normally the BD Director". No role is defined in ARK yet, so
the help text does not name one (14 Sep 2026).

NO DDL. Only field_definitions rows change.
"""

from __future__ import annotations

import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from sqlalchemy import select  # noqa: E402

from app.database import SessionLocal, engine  # noqa: E402

engine.echo = False

from app.models import FieldDefinition  # noqa: E402
from app.routers.metadata import _publish, build_snapshot  # noqa: E402

MODULE = "partners"

#: api_name -> (after, before)
CHANGES = {
    "expected_timeline": (
        {"field_type": "date", "max_length": None},
        {"field_type": "text", "max_length": 100},
    ),
    "decided_by": (
        {"description": "Who adjudicated."},
        {"description": "Who adjudicated, normally the BD Director."},
    ),
}

NOTES = {
    "apply": "Partners: Expected Timeline is a date (migration 0026); Decided By help text names no role",
    "revert": "Partners: Expected Timeline back to text; Decided By help text restored",
}


def change(db, forward: bool) -> list[str]:
    log: list[str] = []
    for api_name, (after, before) in CHANGES.items():
        d = db.scalars(
            select(FieldDefinition).where(FieldDefinition.scope_key == MODULE).where(FieldDefinition.api_name == api_name)
        ).first()
        if d is None:
            raise SystemExit(f"partners.{api_name} has no definition — is this the ARK register?")
        for attr, value in (after if forward else before).items():
            if getattr(d, attr) != value:
                log.append(f"partners.{api_name}.{attr}: {getattr(d, attr)!r} -> {value!r}")
                setattr(d, attr, value)
    return log


def main() -> int:
    mode = "apply" if "--apply" in sys.argv else "revert" if "--revert" in sys.argv else "dry"
    with SessionLocal() as db:
        log = change(db, forward=mode != "revert")
        print(f"Expected Timeline / Decided By — {mode}")
        print("=" * 74)
        for line in log or ["nothing to do"]:
            print(f"  {line}")
        if mode == "dry" or not log:
            db.rollback()
            if mode == "dry":
                print("\nDry run — nothing written. Re-run with --apply.")
            return 0
        db.flush()
        result = _publish(db, build_snapshot(db), NOTES[mode], None)
        db.commit()
        print(f"\nPublished metadata version {result.version.version_no}.")
        for path in result.written:
            print(f"  wrote {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
