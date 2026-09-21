"""
Deal registrations carry a Currency — the same field as a Lead's.

    python registration_currency_metadata.py            # dry run: validates, writes nothing
    python registration_currency_metadata.py --apply    # place the field and publish a version
    python registration_currency_metadata.py --revert   # remove the placement and publish

Run AFTER `alembic upgrade head` — 0028 adds deal_registrations.currency.

ONE FIELD, NOT TWO. No definition is created. DEAL REGISTRATION gets a
placement of the existing pipeline Currency definition — the one Leads,
Opportunities and Deals already place — with the same leads__currency picklist.
Rename Currency, or add a currency to its picklist, in Administration and it
changes on all four at once. A lead created from a registration takes the
registration's currency (RegistrationDetailPage.tsx).

It sits before Estimated Value, as it does on a Lead. NO DDL.
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
from partner_lifecycle_metadata import insert_after, placement, remove_placement  # noqa: E402

NOTES = {
    "apply": "Partners: Deal Registration gains Currency — the Leads Currency field, same picklist (migration 0028)",
    "revert": "Partners: Currency removed from Deal Registration",
}


def shared_currency(db) -> FieldDefinition:
    d = db.scalars(
        select(FieldDefinition).where(FieldDefinition.scope_key == "pipeline").where(FieldDefinition.api_name == "currency")
    ).first()
    if d is None or d.picklist_key != "leads__currency":
        raise SystemExit("The pipeline Currency definition (picklist leads__currency) was not found — is this the ARK register?")
    return d


def apply(db) -> list[str]:
    if placement(db, "currency") is not None:
        return []
    definition = shared_currency(db)
    anchor, value = placement(db, "project_name"), placement(db, "estimated_value")
    if anchor is None or value is None or anchor.section_id != value.section_id or value.sort_order != anchor.sort_order + 1:
        raise SystemExit("Expected Project Name directly before Estimated Value in DEAL REGISTRATION — layout has changed, place it by hand.")
    insert_after(
        db,
        anchor,
        definition_id=definition.id,
        api_name="currency",
        capture_stage=None,
        capture_any_stage=False,
        mandatory_from=None,
        blocks_transition=None,
        requirement="Mandatory",
        required_on_skip=None,
        visibility_condition=None,
        condition=None,
        value_mode="own",
        value_locked=False,
        editable=True,
        storage="column",
        stage_scoped="none",
        status="active",
        provenance="register",
    )
    return [f"partners.currency: placed in DEAL REGISTRATION before Estimated Value (definition {definition.id}, shared with Leads)"]


def revert(db) -> list[str]:
    row = placement(db, "currency")
    if row is None:
        return []
    remove_placement(db, row)
    return ["partners.currency: placement removed (column and values kept)"]


def main() -> int:
    mode = "apply" if "--apply" in sys.argv else "revert" if "--revert" in sys.argv else "dry"
    with SessionLocal() as db:
        log = revert(db) if mode == "revert" else apply(db)
        print(f"Registration currency — {mode}")
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
