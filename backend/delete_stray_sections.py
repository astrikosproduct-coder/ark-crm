"""
Delete the empty stage sections a pipeline module does not own.

    python delete_stray_sections.py            # dry run: says what it would delete
    python delete_stray_sections.py --apply    # delete them and publish a version

Decided 1 Oct 2026 (Setup rebuild, 4c): a module's layout shows only its own
sections. Metadata v2 moved every field to the module that owns its stage, and
left behind, on Leads, the now-empty "STAGE 4 — RFP / RFI" … "STAGE 7 — CLOSE"
— sections for stages Opportunities and Deals own. They hold no field, appear
on no record, and only cluttered the layout.

A section is deleted only when ALL of these hold:
  * it is on a pipeline module;
  * its name declares a stage ("STAGE 5 — …") that module does not own
    (stages.owner_module);
  * no field row points at it — not even one waiting in Unused Items.

Anything else out of range is reported and left alone. It stops if the draft
has other unpublished changes, because publishing would take them too.

DEPLOY ORDER: run on development now; on production with the Phase 2 batch.
NO DDL — rows in `sections`.
"""

from __future__ import annotations

import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from fastapi import HTTPException  # noqa: E402
from sqlalchemy import func, select  # noqa: E402

from app.database import SessionLocal, engine  # noqa: E402

engine.echo = False

from app.metadata_spec import diff_snapshots  # noqa: E402
from app.models import FieldPlacement, Module, Section, Stage  # noqa: E402
from app.routers.metadata import (  # noqa: E402
    _latest_version,
    _publish,
    _stage_of_section,
    _validation_out,
    build_snapshot,
)

NOTE = "Deleted empty stage sections their module does not own"


def plan(db) -> tuple[list[str], list[str], int]:
    """(deleted, left alone, how many deleted)."""
    deleted: list[str] = []
    kept: list[str] = []
    for module in db.scalars(select(Module).where(Module.is_pipeline.is_(True))):
        owned = set(db.scalars(select(Stage.stage).where(Stage.owner_module == module.module_key)))
        for section in db.scalars(select(Section).where(Section.module_key == module.module_key)):
            stage = _stage_of_section(section.label)
            if stage is None or stage in owned:
                continue
            rows = db.scalar(
                select(func.count()).select_from(FieldPlacement).where(FieldPlacement.section_id == section.id)
            )
            if rows:
                kept.append(f"{module.module_key}: {section.label} — {rows} field row(s) point at it, left alone")
            else:
                db.delete(section)
                deleted.append(f"{module.module_key}: {section.label} — deleted")
    return deleted, kept, len(deleted)


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

        deleted, kept, count = plan(db)
        print(f"Delete stray stage sections — {'apply' if apply else 'dry run'}")
        print("=" * 74)
        for line in deleted + kept or ["nothing to do"]:
            print(f"  {line}")
        if count == 0:
            db.rollback()
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
