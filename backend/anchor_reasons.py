"""
Phase A2 — anchor the six reason placements to the status that reveals them.

    python anchor_reasons.py            # dry run: what would change
    python anchor_reasons.py --apply
    python anchor_reasons.py --revert    # put them back where they were

Then:  python regenerate_spec.py --apply

WHAT THIS IS
------------
A one-shot configuration change, in the same family as migrate_leads.py: it
writes rows through the API's own validation rather than issuing SQL of its
own, so the anchor it sets is exactly the anchor Administration would set.
It is a script and not an Alembic migration because nothing about the SCHEMA
changes — 0013 already added the columns. This is data.

Once Administration's field editor grows the anchor control (Phase B), this
script has no reason to exist and should be deleted rather than kept as the
way anchors get set.

WHAT IT CHANGES, AND WHY EACH PART IS NEEDED
---------------------------------------------
Two reason fields, on three modules, six placements:

    on_hold_reason           anchor lead_status · after · full
    closed_lost_reason_code  anchor lead_status · after · half

`anchor_field` is the point: the box draws under the status that revealed it,
inside the same RecordForm, so the condition can fire against live form state
instead of waiting for a save. See lib/spec/anchors.ts.

`condition` is the part the plan missed, and without it the rest is half a
feature. Both rows are `Conditional` in the register and carry only a
`visibility_condition` — `condition` is null. requirementOf() reads
`condition`, not `visibility_condition`, so a Conditional field with none
returns {required: false, unruled: true}: the box would appear and then let
the user save straight past it with nothing in it. Setting `condition` to the
same expression is what makes the red asterisk real and what makes the
readiness panel count it.

    Two different questions, deliberately the same answer here:
      visibility_condition   when is this field SHOWN
      condition              when is it DEMANDED

`layout_span` is presentation only. On Hold Reason is free text and takes the
row; Closed Lost Reason Code is a picklist and does not need it.

WHAT IT DOES NOT CHANGE
-----------------------
Not `section`. All six rows stay CROSS-CUTTING, which is what the register
files them as and what Spec Health reads. Section says what KIND of field this
is; anchor says where it draws. That they now disagree is the whole design.
"""

from __future__ import annotations

import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from sqlalchemy import select  # noqa: E402

from app.database import SessionLocal, engine  # noqa: E402

engine.echo = False

from app.models import FieldPlacement  # noqa: E402
from app.routers.metadata import _apply_anchor  # noqa: E402

MODULES = ("leads", "opportunities", "deals")

# api_name -> (anchor, position, layout_span, condition)
#
# The condition is written against the LABEL rather than the stored key, which
# is how every condition in the register is written — scopeOver() in
# lib/spec/conditions.ts normalises both sides through the picklist before
# comparing, so 'On Hold' matches the stored ON_HOLD.
PLAN = {
    "on_hold_reason": (
        "lead_status",
        "after",
        "full",
        "lead_status == 'On Hold'",
    ),
    "closed_lost_reason_code": (
        "lead_status",
        "after",
        "half",
        "lead_status == 'Closed Lost'",
    ),
}


def main() -> int:
    apply = "--apply" in sys.argv
    revert = "--revert" in sys.argv

    db = SessionLocal()
    changes: list[str] = []
    try:
        for module in MODULES:
            for api_name, (anchor, position, span, condition) in PLAN.items():
                placement = db.scalar(
                    select(FieldPlacement).where(
                        FieldPlacement.module_key == module,
                        FieldPlacement.api_name == api_name,
                        FieldPlacement.status == "active",
                    )
                )
                if placement is None:
                    print(f"  SKIP  {module}.{api_name} — no active placement")
                    continue

                if revert:
                    before = (
                        placement.anchor_field,
                        placement.layout_span,
                        placement.condition,
                    )
                    _apply_anchor(db, placement, {"anchor_field": None})
                    placement.layout_span = None
                    placement.condition = None
                    if any(before):
                        changes.append(f"{module}.{api_name} — released")
                    continue

                before = (
                    placement.anchor_field,
                    placement.anchor_position,
                    placement.layout_span,
                    placement.condition,
                )
                # Through the endpoint's own helper, so the anchor is validated
                # exactly as Administration validates it: the target must be an
                # active field on this module, and the chain must not loop.
                _apply_anchor(
                    db,
                    placement,
                    {"anchor_field": anchor, "anchor_position": position},
                )
                placement.layout_span = span
                placement.condition = condition
                after = (anchor, position, span, condition)
                if before != after:
                    changes.append(
                        f"{module}.{api_name} — anchor {before[0]!r} -> {anchor!r}, "
                        f"span {before[2]!r} -> {span!r}, "
                        f"condition {before[3]!r} -> {condition!r}"
                    )

        if not changes:
            print("\nNothing to change — the configuration already says this.")
            db.rollback()
            return 0

        print(f"\n{len(changes)} placement(s):")
        for line in changes:
            print(f"  {line}")

        if apply or revert:
            db.commit()
            print("\nWritten. Now run:  python regenerate_spec.py --apply")
        else:
            db.rollback()
            print("\nDry run. Re-run with --apply to write.")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
