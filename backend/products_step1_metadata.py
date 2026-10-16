"""
Products, step 1 — the four fields that pick from the catalogue (12 Oct 2026).

    python products_step1_metadata.py            # dry run: validates, writes nothing
    python products_step1_metadata.py --apply    # change the register and publish a version

Run AFTER `alembic upgrade head` (0044) and `load_price_book.py --apply`.

Four fields were meant to pick a product and were typed by hand from 3 Sep
2026, while Products had no table. It has one now. Each step is skipped when it
is already done:

  1. Leads · S!aP Solution Suite — its filter read "Suite Type must be Primary
     suite", and a catalogue item has no Suite Type. It now says what was always
     applied: "Catalogue Category must be Segment Library".
  2. Leads · Suite Demonstrated — offered the whole catalogue (user packs
     included). Suites only, the same filter (decided 12 Oct 2026).
  3. Leads · Secondary S!aP Suites — a multiselect with no choices behind it.
     It picks several PRODUCTS: lookup target `product`, the same filter.
  4. Deals · Expansion Suites — as 3.

Opportunities and Deals show the first two "From the Lead"; they share the
Lead's field, so they follow without a step of their own.

The type of 3 and 4 stays `multiselect`: one field, several values. What makes
it a picker of records is the lookup target, which the form, the export and the
server's check all read (app/products.py).

The filter the app APPLIES is spec/extensions.json's `lookup_filter_expr`,
which this release edits by hand in the same commit; the sentence here is the
register's own wording of it, shown in Setup.

NO DDL. Run on development and on production.
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

NOTE = (
    "Products, step 1: S!aP Solution Suite, Suite Demonstrated, Secondary S!aP Suites and "
    "Expansion Suites pick from the catalogue — Segment Library items only"
)

TARGET = "product"
FILTER = "Catalogue Category must be Segment Library"

#: (owning module, api_name, the type it must already be)
FIELDS = (
    ("leads", "sap_solution_suite", "lookup"),
    ("leads", "suite_demonstrated", "lookup"),
    ("leads", "secondary_sap_suites", "multiselect"),
    ("deals", "expansion_suites", "multiselect"),
)


def definition_of(db, module: str, api_name: str) -> FieldDefinition:
    """The field's definition, through its OWN placement on the owning module."""
    placed = db.scalars(
        select(FieldPlacement)
        .where(FieldPlacement.module_key == module)
        .where(FieldPlacement.api_name == api_name)
        .where(FieldPlacement.status == "active")
        .where(FieldPlacement.value_mode != "read_through")
    ).first()
    if placed is None:
        raise SystemExit(f"STOPPED: {module}.{api_name} is not placed — is this the ARK register?")
    definition = db.get(FieldDefinition, placed.definition_id)
    if definition.scope_key != module:
        raise SystemExit(f"STOPPED: {module}.{api_name} is owned by {definition.scope_key}, not {module}.")
    return definition


def apply(db) -> list[str]:
    log: list[str] = []
    for module, api_name, expected_type in FIELDS:
        definition = definition_of(db, module, api_name)
        if definition.field_type != expected_type:
            raise SystemExit(
                f"STOPPED: {module}.{api_name} is a {definition.field_type}, expected {expected_type}. "
                "Someone has changed it in Setup — decide what it should be before running this."
            )
        if definition.picklist_key:
            raise SystemExit(
                f"STOPPED: {module}.{api_name} has been given the list {definition.picklist_key!r} in Setup."
            )
        if definition.lookup_target != TARGET:
            log.append(f"{module}.{api_name}: lookup target {definition.lookup_target!r} -> {TARGET!r}")
            definition.lookup_target = TARGET
        if definition.lookup_filter != FILTER:
            log.append(f"{module}.{api_name}: filter {definition.lookup_filter!r} -> {FILTER!r}")
            definition.lookup_filter = FILTER
    db.flush()
    return log


def main() -> int:
    apply_it = "--apply" in sys.argv
    with SessionLocal() as db:
        log = apply(db)
        print(f"Products, step 1: the catalogue pickers — {'apply' if apply_it else 'dry run'}")
        print("=" * 74)
        for line in log or ["nothing to do"]:
            print(f"  {line}")
        if not log:
            db.rollback()
            return 0
        if not apply_it:
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
