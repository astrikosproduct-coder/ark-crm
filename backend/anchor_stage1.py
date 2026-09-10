"""
Phase A — anchor the Leads Stage 1 conditionals to the field that reveals them.

    python anchor_stage1.py             # dry run
    python anchor_stage1.py --apply
    python anchor_stage1.py --revert

Then:  python regenerate_spec.py --apply

WHY THIS ONE IS NOT COSMETIC
-----------------------------
test_parity.py reported three Leads Stage 1 sort_order differences against the
frozen baseline, and they were being read as drift worth re-freezing away.
They are not. The rotation moved
`data_site_access_confirmation_document` — whose visibility_condition is
`agreed_next_step == 'POC scoping'` — from below `agreed_next_step` to two rows
ABOVE it. A field that appears above the question that reveals it is the same
defect On Hold Reason had, in a smaller form: the user answers Agreed Next
Step and a box silently appears further up the form, where they have already
stopped looking.

The baseline had it right and the register drifted. Re-freezing first would
have recorded the defect as the intended state.

WHAT IS ANCHORED, AND WHY FLAT RATHER THAN CHAINED
---------------------------------------------------
Three fields on Leads Stage 1, all conditional on the same trigger:

    data_site_access_confirmation_document   agreed_next_step · after · full
    pilot_commercial_model                   agreed_next_step · after · half
    pilot_fee                                agreed_next_step · after · half

pilot_fee's own condition is `agreed_next_step == 'POC scoping' &&
pilot_commercial_model == 'Paid'`, so anchoring it to pilot_commercial_model
would be defensible and anchors.ts supports the chain. It is anchored flat to
agreed_next_step instead, for two reasons. Its visibility is already fully
stated by its own condition, so the chain buys no behaviour. And
arrangeAnchored() only attaches a child whose anchor is currently VISIBLE — a
field whose anchor is hidden falls back to drawing in its own section
position. Anchoring to agreed_next_step, which is unconditional, means all
three always attach; anchoring to a conditional field means pilot_fee draws
somewhere else on exactly the runs where pilot_commercial_model is hidden.

Only the two `pilot_*` fields were already in the right place. They are
anchored anyway: their correct position today is held up by sort_order alone,
which is the mechanism that just demonstrably drifted for the field next to
them.

WHAT IT DOES NOT CHANGE
-----------------------
Not `condition`. Unlike the six reason placements in anchor_reasons.py, these
three already carry one — they are the only three rows in the register that
do — so the red asterisk and the readiness count already work.

The sort_order rotation is corrected as well as anchored. With an anchor the
order no longer decides where the field draws, but leaving the register
reading `document, interest level, agreed next step` would keep the field
list confusing to anyone reading it in Administration, and would keep
test_parity reporting a difference nobody should dismiss.
"""

from __future__ import annotations

import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from sqlalchemy import select  # noqa: E402

from app.database import SessionLocal, engine  # noqa: E402

engine.echo = False

from app.models import FieldPlacement  # noqa: E402
from app.routers.metadata import _apply_anchor  # noqa: E402

MODULE = "leads"

# api_name -> (anchor, position, layout_span)
PLAN = {
    "data_site_access_confirmation_document": ("agreed_next_step", "after", "full"),
    "pilot_commercial_model": ("agreed_next_step", "after", "half"),
    "pilot_fee": ("agreed_next_step", "after", "half"),
}

# The reading order the register should have inside STAGE 1, restoring the
# baseline's intent: the document follows the step that calls for it.
STAGE1_ORDER = (
    "demo_date",
    "suite_demonstrated",
    "demo_attendees",
    "interest_level",
    "agreed_next_step",
    "data_site_access_confirmation_document",
    "pilot_commercial_model",
    "pilot_fee",
    "client_feedback",
    "competitors_mentioned",
    "feature_gaps_logged",
    "demo_debrief_notes",
)


def placement(db, api_name: str) -> FieldPlacement | None:
    return db.scalars(
        select(FieldPlacement)
        .where(FieldPlacement.module_key == MODULE)
        .where(FieldPlacement.api_name == api_name)
    ).first()


def reorder_stage1(db) -> list[str]:
    """Renumber STAGE 1 in STAGE1_ORDER, keeping the block where it sits."""
    rows = [p for name in STAGE1_ORDER if (p := placement(db, name)) is not None]
    if len(rows) != len(STAGE1_ORDER):
        found = {p.api_name for p in rows}
        missing = [n for n in STAGE1_ORDER if n not in found]
        return [f"!! STAGE 1 reorder skipped — not found: {missing}"]

    slots = sorted(p.sort_order for p in rows)
    log = []
    for target, row in zip(slots, rows):
        if row.sort_order != target:
            log.append(f"{row.api_name}: sort_order {row.sort_order} -> {target}")
            row.sort_order = target
    return log


def apply(db) -> list[str]:
    log: list[str] = []
    for api_name, (anchor, position, span) in PLAN.items():
        row = placement(db, api_name)
        if row is None:
            log.append(f"!! {api_name} has no placement on {MODULE} — skipped")
            continue
        if row.anchor_field == anchor and row.anchor_position == position:
            log.append(f"{api_name} already anchored to {anchor}")
        else:
            # Through the API's own helper, so the anchor set here is exactly
            # the anchor Administration would set — cycle check included.
            _apply_anchor(db, row, {"anchor_field": anchor, "anchor_position": position})
            log.append(f"{api_name}: anchor -> {anchor} ({position})")
        if row.layout_span != span:
            log.append(f"{api_name}: layout_span {row.layout_span} -> {span}")
            row.layout_span = span

    db.flush()
    log.extend(reorder_stage1(db))
    return log


def revert(db) -> list[str]:
    log: list[str] = []
    for api_name in PLAN:
        row = placement(db, api_name)
        if row is None or row.anchor_field is None:
            continue
        _apply_anchor(db, row, {"anchor_field": None})
        row.layout_span = None
        log.append(f"{api_name}: anchor cleared")
    db.flush()
    return log


def main() -> int:
    mode = "apply" if "--apply" in sys.argv else "revert" if "--revert" in sys.argv else "dry"

    with SessionLocal() as db:
        log = revert(db) if mode == "revert" else apply(db)

        print(f"Leads Stage 1 conditionals — {mode}")
        print("=" * 66)
        for line in log:
            print(f"  {line}")
        if not log:
            print("  nothing to do")

        if mode == "dry":
            db.rollback()
            print("\nDry run — nothing written. Re-run with --apply.")
        else:
            db.commit()
            print(f"\n{len(log)} change(s) committed.")
            print("Now run:  python regenerate_spec.py --apply")
    return 0


if __name__ == "__main__":
    sys.exit(main())
