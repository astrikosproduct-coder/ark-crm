"""
Release 1.1, chunk B — the field clean-up the head asked for (6 Oct 2026).

    python release_1_1_fields_metadata.py            # dry run: validates, writes nothing
    python release_1_1_fields_metadata.py --apply    # change the register and publish a version

What it does, each step skipped when it is already done:

  1. Segment (Infrastructure / Industry / Power / Mobility) is DELETED — on
     Leads, Opportunities and Deals (one field) and on Accounts (its own).
  2. Theme is RENAMED "Segment" — same seven choices, still one choice on a
     Lead, shown "From the Lead" on Opportunities and Deals. Its api_name stays
     `theme`: stored values are keyed by it.
  3. Accounts gain a multi-choice "Segment" (`segments`) over the same seven
     choices, required, where the old Segment sat. Its values live in
     accounts.custom_fields — exactly what Administration makes, no DDL.
  4. Account Target Phase is DELETED.
  5. Region gains Europe — one list, so Accounts' Region and Leads' Destination
     and Booking Region all offer it.

Deletes are LOGICAL, as Administration's own: the rows, the typed columns and
every value in them stay. Nothing copies a Segment between a Lead and its
Account any more (decided 6 Oct 2026) — that was frontend code, removed with
this release.

NO DDL. Run on development and on production, after `alembic upgrade head`.
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from fastapi import HTTPException  # noqa: E402
from sqlalchemy import select  # noqa: E402

from app.database import SessionLocal, engine  # noqa: E402

engine.echo = False

from app.models import FieldDefinition, FieldPlacement, Picklist, PicklistValue  # noqa: E402
from app.routers.metadata import _publish, _validation_out, build_snapshot  # noqa: E402

NOTE = (
    "Release 1.1: Segment deleted; Theme renamed Segment; Accounts get a multi-choice Segment; "
    "Account Target Phase deleted; Region gains Europe"
)

THEME_LIST = "theme"
REGION_LIST = "region"
EUROPE = ("EUROPE", "Europe")

ACCOUNT_SEGMENTS = "segments"
ACCOUNT_SEGMENTS_DESCRIPTION = (
    "The markets this company works in. Choose every one that applies; a Lead picks its own Segment."
)


def now() -> datetime:
    return datetime.now(timezone.utc)


def definition(db, scope: str, api_name: str) -> FieldDefinition | None:
    return db.scalars(
        select(FieldDefinition).where(FieldDefinition.scope_key == scope).where(FieldDefinition.api_name == api_name)
    ).first()


def placement(db, module: str, api_name: str) -> FieldPlacement | None:
    return db.scalars(
        select(FieldPlacement)
        .where(FieldPlacement.module_key == module)
        .where(FieldPlacement.api_name == api_name)
        .order_by(FieldPlacement.status)  # 'active' before 'deleted'
    ).first()


def delete_everywhere(db, scope: str, api_name: str, log: list[str]) -> None:
    """DELETE /fields/{id}, as Administration does it: logical, cascaded, restorable."""
    d = definition(db, scope, api_name)
    if d is None:
        raise SystemExit(f"{scope}.{api_name} has no definition — is this the ARK register?")
    if d.status == "deleted":
        return
    stamp = now()
    d.status, d.deleted_at = "deleted", stamp
    modules = []
    for p in d.placements:
        # A field anchored to this one returns to its own section's list.
        for dependent in db.scalars(
            select(FieldPlacement)
            .where(FieldPlacement.module_key == p.module_key)
            .where(FieldPlacement.anchor_field == p.api_name)
        ):
            dependent.anchor_field = None
            dependent.anchor_position = None
        if p.status == "active":
            p.status, p.deleted_at, p.deleted_by_cascade = "deleted", stamp, True
            modules.append(p.module_key)
    log.append(f"{scope}.{api_name} ({d.label}): deleted on {', '.join(modules) or 'no module'}")


def apply(db) -> list[str]:
    log: list[str] = []

    # 1. The old Segment, everywhere.
    delete_everywhere(db, "pipeline", "segment", log)
    delete_everywhere(db, "accounts", "segment", log)

    # 2. Theme becomes Segment.
    theme = definition(db, "pipeline", "theme")
    if theme is None or theme.status != "active":
        raise SystemExit("pipeline.theme is not an active field — is this the ARK register?")
    if theme.label != "Segment":
        log.append(f"pipeline.theme: label '{theme.label}' -> 'Segment' (Leads, Opportunities, Deals)")
        theme.label = "Segment"
    theme_list = db.get(Picklist, THEME_LIST)
    if theme_list is not None and theme_list.label != "Segment":
        log.append(f"picklist {THEME_LIST}: label '{theme_list.label}' -> 'Segment'")
        theme_list.label = "Segment"

    # 3. Accounts: a multi-choice Segment where the old one sat.
    old = placement(db, "accounts", "segment")
    if old is None:
        raise SystemExit("accounts.segment was never placed — is this the ARK register?")
    d = definition(db, "accounts", ACCOUNT_SEGMENTS)
    if d is None:
        d = FieldDefinition(
            scope_key="accounts",
            api_name=ACCOUNT_SEGMENTS,
            label="Segment",
            field_type="multiselect",
            picklist_key=THEME_LIST,
            description=ACCOUNT_SEGMENTS_DESCRIPTION,
            use_case="Release 1.1 (6 Oct 2026): replaces the single-choice Segment; same choices as a Lead's Segment.",
            origin="Administration",
            origin_module="accounts",
            status="active",
        )
        db.add(d)
        db.flush()
        log.append(f"accounts.{ACCOUNT_SEGMENTS}: definition created (multiselect over '{THEME_LIST}')")
    if placement(db, "accounts", ACCOUNT_SEGMENTS) is None:
        db.add(
            FieldPlacement(
                definition_id=d.id,
                api_name=ACCOUNT_SEGMENTS,
                module_key="accounts",
                scope_key=old.scope_key,
                section_id=old.section_id,
                sort_order=old.sort_order,
                capture_stage=old.capture_stage,
                capture_any_stage=False,
                requirement="Mandatory",
                required_on_create=False,
                value_mode="own",
                editable=True,
                storage="custom_fields",
                status="active",
                provenance="admin",
            )
        )
        db.flush()
        log.append(f"accounts.{ACCOUNT_SEGMENTS}: placed where Segment was, Mandatory, values in custom_fields")

    # 4. Account Target Phase.
    delete_everywhere(db, "accounts", "account_target_phase", log)

    # 5. Europe, on the one Region list.
    region = db.get(Picklist, REGION_LIST)
    if region is None:
        raise SystemExit("The region list is missing — is this the ARK register?")
    europe = db.scalars(
        select(PicklistValue).where(PicklistValue.picklist_key == REGION_LIST).where(PicklistValue.key == EUROPE[0])
    ).first()
    if europe is None:
        last = max((v.sort_order for v in region.values), default=0)
        stamp = now()
        db.add(
            PicklistValue(
                picklist_key=REGION_LIST,
                key=EUROPE[0],
                label=EUROPE[1],
                sort_order=last + 1,
                active=True,
                created_at=stamp,
                updated_at=stamp,
            )
        )
        log.append(f"picklist {REGION_LIST}: '{EUROPE[1]}' added after the last choice")
    elif not europe.active:
        europe.active = True
        log.append(f"picklist {REGION_LIST}: '{EUROPE[1]}' reactivated")

    db.flush()
    return log


def main() -> int:
    mode = "apply" if "--apply" in sys.argv else "dry"
    with SessionLocal() as db:
        log = apply(db)
        print(f"Release 1.1 fields — {mode}")
        print("=" * 74)
        for line in log or ["nothing to do"]:
            print(f"  {line}")
        if not log:
            db.rollback()
            return 0
        if mode == "dry":
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
