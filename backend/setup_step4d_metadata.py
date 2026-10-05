"""
Setup rebuild, 4d — three register changes that replace code, published once.

    python setup_step4d_metadata.py            # dry run: says what it would change
    python setup_step4d_metadata.py --apply    # change them and publish a version

1. Accounts → Phone becomes a Phone field with the country codes.
   It was a plain text box; Contacts' Phone and Mobile already had the code
   dropdown in front of the number. Every Phone field takes its codes from the
   one Global Set (routers/metadata.py DIAL_CODE_SET), so this is the type and
   that list. The value stays in the same column, as one string: a number
   typed before shows whole, never re-prefixed (PhoneInput.splitPhone).

2. Leads → Currency gets USD as its default value (migration 0042).
3. Deal Registrations → Currency, the same.
   Both were written in code — LeadCreatePage, NewRegistrationPage and the
   two server creates. "Nothing should be hard-coded" (1 Oct 2026): they are
   register defaults now, changed in Setup and published like anything else,
   and app/register_defaults.py applies them on the server.

Idempotent: a change already made is reported and skipped. It stops if the
draft has other unpublished changes, because publishing would take them too.

DEPLOY ORDER: after `alembic upgrade` reaches 0042 and before the new code
starts. Run delete_stray_sections.py first; both publish.
NO DDL — rows in `field_definitions` and `field_placements`.
"""

from __future__ import annotations

import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from fastapi import HTTPException  # noqa: E402
from sqlalchemy import select  # noqa: E402

from app.database import SessionLocal, engine  # noqa: E402

engine.echo = False

from app.metadata_spec import diff_snapshots  # noqa: E402
from app.models import FieldDefinition, FieldPlacement, Picklist, PicklistValue  # noqa: E402
from app.routers.metadata import (  # noqa: E402
    DIAL_CODE_SET,
    _latest_version,
    _publish,
    _validation_out,
    build_snapshot,
)

NOTE = "Accounts Phone takes country codes; Currency starts as USD on Leads and Deal Registrations"

#: (module, api_name, default key)
DEFAULTS = (("leads", "currency", "USD"), ("registrations", "currency", "USD"))


def _placement(db, module: str, api_name: str) -> tuple[FieldPlacement, FieldDefinition] | None:
    row = db.execute(
        select(FieldPlacement, FieldDefinition)
        .join(FieldDefinition, FieldDefinition.id == FieldPlacement.definition_id)
        .where(
            FieldPlacement.module_key == module,
            FieldPlacement.api_name == api_name,
            FieldPlacement.status == "active",
            FieldPlacement.value_mode != "read_through",
        )
    ).first()
    return (row[0], row[1]) if row else None


def plan(db) -> tuple[list[str], bool]:
    """(what happens, whether anything stops the run)."""
    lines: list[str] = []
    stop = False

    if db.get(Picklist, DIAL_CODE_SET) is None:
        return [f"stop: the country-code list {DIAL_CODE_SET} is missing"], True

    found = _placement(db, "accounts", "phone")
    if found is None:
        lines.append("accounts.phone: not found — skipped")
    else:
        _, definition = found
        if definition.field_type == "phone" and definition.picklist_key == DIAL_CODE_SET:
            lines.append("accounts.phone: already a Phone field with country codes")
        elif definition.field_type not in ("text", "phone"):
            lines.append(f"stop: accounts.phone is a {definition.field_type} field, not text")
            stop = True
        else:
            lines.append(
                f"accounts.phone: {definition.field_type} -> phone, choices -> {DIAL_CODE_SET}"
            )
            definition.field_type = "phone"
            definition.picklist_key = DIAL_CODE_SET

    for module, api_name, key in DEFAULTS:
        found = _placement(db, module, api_name)
        if found is None:
            lines.append(f"{module}.{api_name}: not found — skipped")
            continue
        placement, definition = found
        live = db.scalar(
            select(PicklistValue).where(
                PicklistValue.picklist_key == definition.picklist_key,
                PicklistValue.key == key,
                PicklistValue.active.is_(True),
            )
        )
        if definition.field_type != "picklist" or live is None:
            lines.append(f"stop: {module}.{api_name} has no active choice {key}")
            stop = True
        elif placement.default_value == key:
            lines.append(f"{module}.{api_name}: default already {key}")
        else:
            lines.append(f"{module}.{api_name}: default {placement.default_value!r} -> {key!r}")
            placement.default_value = key
    return lines, stop


def main() -> int:
    apply = "--apply" in sys.argv
    with SessionLocal() as db:
        latest = _latest_version(db)
        pending = diff_snapshots(latest.snapshot, build_snapshot(db)) if latest else ["never published"]
        if pending:
            print("Stopped: the draft has unpublished changes, and publishing would take them too.")
            for line in pending[:20]:
                print(f"  {line}")
            print("Publish or undo them in Setup first, then run this again.")
            return 1

        lines, stop = plan(db)
        print(f"Setup 4d register changes — {'apply' if apply else 'dry run'}")
        print("=" * 74)
        for line in lines:
            print(f"  {line}")
        if stop:
            db.rollback()
            print("\nStopped — nothing written.")
            return 1
        db.flush()
        if not diff_snapshots(latest.snapshot, build_snapshot(db)):
            db.rollback()
            print("\nNothing to change.")
            return 0
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
