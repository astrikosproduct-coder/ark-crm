"""
Leads gain Pilot PO Received Date — the Won date of a paid pilot.

    python pilot_po_received_date_metadata.py            # dry run: validates, writes nothing
    python pilot_po_received_date_metadata.py --apply    # place the field and publish a version
    python pilot_po_received_date_metadata.py --revert   # remove the placement and publish

Run AFTER `alembic upgrade head` — 0035 adds leads.pilot_po_received_date.

Decided 21 Sep 2026: a paid POC/pilot counts as Won, and Won is the day the
PO arrives. Marking the pilot Paid creates its Deal on that same save, so the
date is asked for there. It sits directly after Pilot Fee and takes that
field's rules exactly — shown and required only once the pilot is Paid — and
is copied into the Deal's PO Received Date (app/progression.py).

NO DDL.
"""

from __future__ import annotations

import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from fastapi import HTTPException  # noqa: E402
from sqlalchemy import select  # noqa: E402

from app.database import SessionLocal, engine  # noqa: E402

engine.echo = False

from app.models import FieldDefinition, FieldPlacement  # noqa: E402
from app.routers.metadata import _publish, _validation_out, build_snapshot  # noqa: E402

MODULE = "leads"
API_NAME = "pilot_po_received_date"
ANCHOR = "pilot_fee"

LABEL = "Pilot PO Received Date"
DESCRIPTION = (
    "The day the client's PO for the paid pilot reached us. Marking the pilot Paid creates "
    "its Deal, and this becomes that Deal's PO Received Date: the day it counts as Won."
)
USE_CASE = "Dashboard Won for paid pilots — decided 21 Sep 2026. Asked for beside Pilot Fee."

#: Copied from the anchor, so the two are enforced identically.
RULE_COLUMNS = (
    "capture_stage",
    "capture_any_stage",
    "mandatory_from",
    "blocks_transition",
    "requirement",
    "required_on_skip",
    "visibility_condition",
    "condition",
    "value_mode",
    "value_locked",
    "editable",
    "stage_scoped",
)

NOTES = {
    "apply": "Leads: Pilot PO Received Date added after Pilot Fee — a paid pilot's Won date (migration 0035)",
    "revert": "Leads: Pilot PO Received Date removed",
}


def placement(db, api_name: str) -> FieldPlacement | None:
    return db.scalars(
        select(FieldPlacement)
        .where(FieldPlacement.module_key == MODULE)
        .where(FieldPlacement.api_name == api_name)
        .where(FieldPlacement.status == "active")
    ).first()


def definition_for(db, placed: FieldPlacement) -> FieldDefinition:
    return db.get(FieldDefinition, placed.definition_id)


def shift(db, after_sort_order: int, by: int) -> None:
    for later in db.scalars(
        select(FieldPlacement)
        .where(FieldPlacement.module_key == MODULE)
        .where(FieldPlacement.sort_order > after_sort_order)
    ):
        later.sort_order += by


def apply(db) -> list[str]:
    log: list[str] = []
    anchor = placement(db, ANCHOR)
    if anchor is None:
        raise SystemExit(f"{MODULE}.{ANCHOR} is not placed — is this the ARK register?")
    anchor_def = definition_for(db, anchor)

    d = db.scalars(
        select(FieldDefinition)
        .where(FieldDefinition.scope_key == anchor_def.scope_key)
        .where(FieldDefinition.api_name == API_NAME)
    ).first()
    if d is None:
        d = FieldDefinition(
            scope_key=anchor_def.scope_key,
            api_name=API_NAME,
            label=LABEL,
            field_type="date",
            description=DESCRIPTION,
            use_case=USE_CASE,
            origin="Playbook",
            source_ref=anchor_def.source_ref,
            origin_module=MODULE,
            status="active",
        )
        db.add(d)
        db.flush()
        log.append(f"{MODULE}.{API_NAME}: definition created (date, scope {d.scope_key})")
    elif d.status != "active":
        d.status, d.deleted_at, d.deleted_by = "active", None, None
        log.append(f"{MODULE}.{API_NAME}: definition reactivated")

    if placement(db, API_NAME) is None:
        shift(db, anchor.sort_order, +1)
        db.add(
            FieldPlacement(
                definition_id=d.id,
                api_name=API_NAME,
                module_key=MODULE,
                scope_key=anchor.scope_key,
                section_id=anchor.section_id,
                sort_order=anchor.sort_order + 1,
                storage="column",
                status="active",
                provenance="register",
                **{c: getattr(anchor, c) for c in RULE_COLUMNS},
            )
        )
        db.flush()
        log.append(
            f"{MODULE}.{API_NAME}: placed after {ANCHOR} — Stage {anchor.capture_stage}, "
            f"{anchor.requirement}, blocks {anchor.blocks_transition}"
        )

    return log


def revert(db) -> list[str]:
    row = placement(db, API_NAME)
    if row is None:
        return []
    shift(db, row.sort_order, -1)
    db.delete(row)
    db.flush()
    return [f"{MODULE}.{API_NAME}: placement removed (column and values kept)"]


def main() -> int:
    mode = "apply" if "--apply" in sys.argv else "revert" if "--revert" in sys.argv else "dry"
    with SessionLocal() as db:
        log = revert(db) if mode == "revert" else apply(db)
        print(f"Pilot PO Received Date — {mode}")
        print("=" * 74)
        for line in log or ["nothing to do"]:
            print(f"  {line}")
        if not log:
            db.rollback()
            return 0
        db.flush()
        if mode == "dry":
            validation = _validation_out(build_snapshot(db))
            print(f"\nValidation: {'ok' if validation.ok else 'FAILED'}")
            for error in validation.errors:
                print(f"  error: {error}")
            db.rollback()
            print("Dry run — nothing written. Re-run with --apply.")
            return 0 if validation.ok else 1
        try:
            result = _publish(db, build_snapshot(db), NOTES[mode], None)
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
