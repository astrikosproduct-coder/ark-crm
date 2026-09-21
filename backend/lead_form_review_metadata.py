"""
Three register corrections from the 15 Sep 2026 Leads form review.

    python lead_form_review_metadata.py            # dry run: validates, writes nothing
    python lead_form_review_metadata.py --apply    # write, then publish a version

1. DEMO COMPLETED MOVES TO STAGE 1, directly before Demo Date.
   It sat in STAGE 0 — CONNECT with capture_stage 0 and blocked 0 → 1, so a
   brand-new lead was asked whether a demo it had not yet been offered was
   finished. A demo is completed at Demo Presentation, beside the date it was
   delivered on: capture_stage 1, mandatory from 1, blocks 1 → 2 — the same as
   Demo Date. X0.2 (leaving Connect) reads demo_agreed, not this field, so no
   criterion changes with it. Its use_case said "Exit criterion X0.2", which
   stopped being true when X0.2 moved to demo_agreed; corrected here.

2. NOT A DUPLICATE — REASON IS SHOWN ONLY WHEN IT HOLDS ONE, AND IS READ-ONLY.
   The reason is given in a dialog — the duplicate dialog on a Lead save, or
   Partners' "different project" answer carried into the lead a registration
   creates (RegistrationDetailPage.tsx). An always-visible empty box invited a
   second, disconnected way to type it that the duplicate check never asked for.

3. OVERRIDE JUSTIFICATION IS SHOWN, AND DEMANDED, ONLY WHILE OVERRIDDEN.
   On leads, opportunities and deals. The rule is app/progression.py's: a
   Progression % or Probability % that differs from the value the stage set.
   progression_default_pct / probability_default_pct are served on every
   pipeline record, and the frontend's expression compiler accepts them on a
   module that places the field they belong to (src/lib/spec/conditions.ts,
   SERVER_STAMPED). A record with no default yet — a create — is never flagged.
   Visibility and requirement are the same expression on purpose: when it is
   shown and when it is demanded are one question here.

NO DDL. Placements, and one definition's use_case.
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
    "Leads form review: Demo Completed moves to Stage 1 before Demo Date; "
    "Not a Duplicate Reason shown only when given; Override Justification shown only while overridden"
)

PIPELINE = ("leads", "opportunities", "deals")

NOT_DUPLICATE_SHOWN = "not_duplicate_reason != ''"

OVERRIDDEN = (
    "(progression_default_pct != '' && progression_pct != progression_default_pct) || "
    "(probability_default_pct != '' && probability_pct != probability_default_pct)"
)

DEMO_USE_CASE_WAS = "Exit criterion X0.2"
DEMO_USE_CASE = "Stage 1 exit — the demo was delivered, on the Demo Date beside it."


def placement(db, module: str, api_name: str) -> FieldPlacement | None:
    return db.scalars(
        select(FieldPlacement)
        .where(FieldPlacement.module_key == module)
        .where(FieldPlacement.api_name == api_name)
        .where(FieldPlacement.status == "active")
    ).first()


def move_before(db, row: FieldPlacement, anchor: FieldPlacement) -> None:
    """
    Take `row` out of its place and put it directly before `anchor`, in the
    anchor's section. sort_order is one sequence across the module, so the gap
    is closed first and then opened again at the anchor.
    """
    for later in db.scalars(
        select(FieldPlacement)
        .where(FieldPlacement.module_key == row.module_key)
        .where(FieldPlacement.sort_order > row.sort_order)
        .where(FieldPlacement.id != row.id)
    ):
        later.sort_order -= 1
    db.flush()
    target = anchor.sort_order
    for later in db.scalars(
        select(FieldPlacement)
        .where(FieldPlacement.module_key == row.module_key)
        .where(FieldPlacement.sort_order >= target)
        .where(FieldPlacement.id != row.id)
    ):
        later.sort_order += 1
    row.sort_order = target
    row.section_id = anchor.section_id
    db.flush()


def apply(db) -> tuple[list[str], list[str]]:
    log: list[str] = []
    problems: list[str] = []

    # ------------------------------------------------ 1. demo_completed
    demo_completed = placement(db, "leads", "demo_completed")
    demo_date = placement(db, "leads", "demo_date")
    if demo_completed is None or demo_date is None:
        problems.append("leads.demo_completed or leads.demo_date has no active placement")
    else:
        in_place = (
            demo_completed.section_id == demo_date.section_id
            and demo_completed.sort_order == demo_date.sort_order - 1
        )
        if not in_place:
            move_before(db, demo_completed, demo_date)
            log.append("leads.demo_completed: moved into Demo Date's section, directly before it")
        stage_rule = (demo_date.capture_stage, demo_date.mandatory_from, demo_date.blocks_transition)
        if (demo_completed.capture_stage, demo_completed.mandatory_from, demo_completed.blocks_transition) != stage_rule:
            (demo_completed.capture_stage, demo_completed.mandatory_from, demo_completed.blocks_transition) = stage_rule
            log.append(
                f"leads.demo_completed: capture_stage {stage_rule[0]}, mandatory_from {stage_rule[1]}, "
                f"blocks {stage_rule[2]} (Demo Date's own)"
            )
        definition = db.get(FieldDefinition, demo_completed.definition_id)
        if definition is not None and definition.use_case.startswith(DEMO_USE_CASE_WAS):
            definition.use_case = DEMO_USE_CASE
            log.append("demo_completed: use_case no longer names X0.2")

    # ------------------------------------------ 2. not_duplicate_reason
    not_duplicate = placement(db, "leads", "not_duplicate_reason")
    if not_duplicate is None:
        problems.append("leads.not_duplicate_reason has no active placement")
    elif not_duplicate.visibility_condition != NOT_DUPLICATE_SHOWN or not_duplicate.editable:
        not_duplicate.visibility_condition = NOT_DUPLICATE_SHOWN
        not_duplicate.editable = False
        log.append(f"leads.not_duplicate_reason: visible when {NOT_DUPLICATE_SHOWN!r}, read-only")

    # ------------------------------ 3. probability_override_justification
    for module in PIPELINE:
        row = placement(db, module, "probability_override_justification")
        if row is None:
            problems.append(f"{module}.probability_override_justification has no active placement")
            continue
        if row.visibility_condition == OVERRIDDEN and row.condition == OVERRIDDEN:
            continue
        row.visibility_condition = OVERRIDDEN
        row.condition = OVERRIDDEN
        log.append(f"{module}.probability_override_justification: shown and demanded only while overridden")

    return log, problems


def main() -> int:
    applying = "--apply" in sys.argv
    with SessionLocal() as db:
        log, problems = apply(db)
        print(f"Leads form review — {'apply' if applying else 'dry run'}")
        print("=" * 74)
        for line in log or ["nothing to do"]:
            print(f"  {line}")
        if problems:
            print("\nProblems — nothing written:")
            for line in problems:
                print(f"  {line}")
            db.rollback()
            return 1
        if not log:
            db.rollback()
            return 0
        db.flush()
        if not applying:
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
