"""
Phase A — the key-facts boxes stop being hand-built strips and become fields.

    python move_key_facts_to_header.py             dry run: report, write nothing
    python move_key_facts_to_header.py --apply     write, then publish

WHAT THIS CHANGES, AND WHY IT IS A REGISTER CHANGE RATHER THAN A UI ONE
-----------------------------------------------------------------------
Six values were drawn by three hand-built surfaces that each saved on a 300ms
debounce as the user typed — HeaderStrip (Overall RAG, Next Milestone, Next
Milestone Date), StageMetricsStrip (Expected Close Month) and ProgressionChips
(Progression %, Probability %). One keystroke pause meant a full record PUT, a
refetch, and a remount of every form on the screen. They are ordinary fields of
the register and there is no reason they cannot be drawn by the form engine and
saved by the same Save button as everything else.

Where a field DRAWS is `field_placements.section_id`, so that is what moves.
Nothing about what the fields mean, what they store, or how per-stage values
work changes here — Probability % is still carry-forward, still writes
`probability_pct__s<n>` plus the plain column at the record's current stage, and
is still an override needing a justification when it disagrees with the ladder.

    __header  ->  HEADER    overall_rag, next_milestone, next_milestone_date
    RECORD STATE -> HEADER  expected_close_month, probability_pct
    (already HEADER)        progression_pct

Two more edits ride along, both register facts rather than presentation:

  * `next_milestone` becomes `longtext`. It is a sentence about what happens
    next, not a name, and a single-line box was the wrong shape for it.
  * `probability_override_justification` gets `anchor_field = probability_pct`,
    so the box that explains an override draws directly under the number that
    caused it, inside the same form and the same save. That is what anchors
    exist for — see src/lib/spec/anchors.ts — and it is how On Hold Reason
    already behaves next to Lead Status.

WHAT IS DELIBERATELY LEFT ALONE
-------------------------------
The Opportunities priority flags (Low Hanging, Top 10) stay in `__header`.
They are not an ordinary field pair: the rank is unique across records, so the
picker has to read the whole collection to know which ranks are still free, and
the form engine has no vocabulary for that. HeaderStrip keeps rendering those
and renders nothing at all on Leads and Deals, where `__header` is now empty.
"""

from __future__ import annotations

import argparse
import sys

from sqlalchemy import select

from app.database import SessionLocal
from app.models import FieldDefinition, FieldPlacement, Section

MODULES = ("leads", "opportunities", "deals")

#: api_name -> sort_order within HEADER. The order the boxes read in: what the
#: record is, then what happens next, then the three numbers.
MOVE_TO_HEADER: dict[str, int] = {
    "overall_rag": 10,
    "next_milestone": 20,
    "next_milestone_date": 30,
    "expected_close_month": 40,
    "progression_pct": 50,
    "probability_pct": 60,
}

ANCHOR = ("probability_override_justification", "probability_pct", "after")

RETYPE = ("next_milestone", "longtext")


def placement_for(db, module: str, api_name: str) -> FieldPlacement | None:
    return db.scalar(
        select(FieldPlacement).where(
            FieldPlacement.module_key == module,
            FieldPlacement.api_name == api_name,
        )
    )


def header_section(db, module: str) -> Section | None:
    return db.scalar(
        select(Section).where(Section.module_key == module, Section.label == "HEADER")
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="write the changes and publish")
    parser.add_argument("--user", default=None, help="acting user_id for the published version")
    args = parser.parse_args()

    db = SessionLocal()
    changes: list[str] = []
    problems: list[str] = []

    try:
        for module in MODULES:
            header = header_section(db, module)
            if header is None:
                problems.append(f"{module}: no HEADER section — cannot move anything into it")
                continue

            for api_name, order in MOVE_TO_HEADER.items():
                placement = placement_for(db, module, api_name)
                if placement is None:
                    problems.append(f"{module}.{api_name}: no placement on this module")
                    continue

                was = db.get(Section, placement.section_id)
                was_label = was.label if was else "?"
                if placement.section_id == header.id and placement.sort_order == order:
                    continue
                changes.append(
                    f"{module}.{api_name}: {was_label} #{placement.sort_order} "
                    f"-> HEADER #{order}"
                )
                placement.section_id = header.id
                placement.sort_order = order

            api_name, anchor_to, position = ANCHOR
            placement = placement_for(db, module, api_name)
            if placement is None:
                problems.append(f"{module}.{api_name}: no placement on this module")
            elif placement.anchor_field != anchor_to or placement.anchor_position != position:
                changes.append(
                    f"{module}.{api_name}: anchor {placement.anchor_field or 'none'} "
                    f"-> {anchor_to} ({position})"
                )
                placement.anchor_field = anchor_to
                placement.anchor_position = position

        # The type is the DEFINITION's, not the placement's — one concept, one
        # type, on every module that places it.
        api_name, field_type = RETYPE
        definitions = db.scalars(
            select(FieldDefinition).where(
                FieldDefinition.api_name == api_name,
                FieldDefinition.status != "deleted",
            )
        ).all()
        if not definitions:
            problems.append(f"{api_name}: no active definition")
        for definition in definitions:
            if definition.field_type == field_type:
                continue
            changes.append(
                f"{api_name} (definition {definition.id}, scope {definition.scope_key}): "
                f"type {definition.field_type} -> {field_type}"
            )
            definition.field_type = field_type

        print(f"{len(changes)} change(s):")
        for line in changes:
            print(f"  {line}")
        if problems:
            print(f"\n{len(problems)} problem(s):")
            for line in problems:
                print(f"  {line}")

        if not args.apply:
            db.rollback()
            print("\nDry run — nothing written. Re-run with --apply.")
            return 1 if problems else 0

        if problems:
            db.rollback()
            print("\nNOT APPLIED — fix the problems above first.")
            return 1

        db.flush()

        # Publish through the same path Administration uses, so the draft is
        # validated, frozen as a version, and written out to spec/*.json. A
        # direct write of the JSON would leave the database and the files
        # agreeing by luck rather than by construction.
        from app.metadata_spec import build_snapshot
        from app.routers.metadata import _publish

        result = _publish(
            db,
            build_snapshot(db),
            "Key facts become ordinary HEADER fields; next_milestone -> longtext",
            args.user,
        )
        db.commit()
        print(f"\nApplied and published: {result}")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
