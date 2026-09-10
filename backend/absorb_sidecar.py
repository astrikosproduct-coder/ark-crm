"""
B2 — move two behaviours out of spec/extensions.json and into the register.

    python absorb_sidecar.py            # dry run: what would change
    python absorb_sidecar.py --apply
    python absorb_sidecar.py --revert    # everything back to none/NULL

Then:  python regenerate_spec.py --apply

WHAT THIS IS
------------
A one-shot configuration change, the same family as anchor_reasons.py: it
writes through the API's own validation rather than issuing SQL of its own, so
what it sets is exactly what Administration would set. Nothing about the SCHEMA
changes here — 0015 added the columns. This is data.

Once Administration's field editor grows the two controls (B3), this script has
no reason to exist and should be deleted rather than kept as the way these get
set.

WHAT MOVES, AND WHY EACH IS REGISTER DATA
------------------------------------------
1. stage_scoped, onto the placement.

   Derived by replaying extensions.json's own rule, exactly as
   src/lib/stageScope.ts::isPerStageValue does today:

       carry_forward   named in stage_scoped.carry_forward.fields
       sticky          named in stage_scoped.sticky.extra, OR in a section
                       stage_scoped.sticky.sections lists, with a type nobody
                       types into excluded and (require_condition) a
                       visibility_condition present
       none            everything else

   The rule produced a set; the set is what a column should hold. Storing the
   answer rather than the rule is the whole point — an admin can then make one
   field sticky without editing a rule that silently catches four others.

2. computed_expr, onto the definition.

   The 28 expressions in the `fields` sidecar. NOT into computed_formula, which
   already holds the register's English sentence about the same rule and is
   shown to the user beside it. See models.FieldDefinition.computed_expr.

WHAT DELIBERATELY DOES NOT MOVE
--------------------------------
    default_by          names a resolver function in lib/spec/resolvers.ts
    sticky.extra[].when names a predicate in stageScope.ts
    history_only        Stage Skip / Stage Reversal Reason. Written by the
                        transition dialog and NOT stage-scoped at all — the
                        transitions table already carries one reason per move
    type_override       the prototype's departure from the register, which is
    label_override      a finding for reviewers, not a correction to apply
    note, unexpressed   review annotations
    child_spec          binds to a child table shape in the frontend
    lookup_filter_expr  the same question as computed_expr and a fair candidate
                        for the next pass; out of scope here on purpose

The first three name FUNCTIONS. A register column holding a function name is a
register that cannot be read without the code beside it, and the whole reason
these two moved is that an admin could not set them. An admin cannot write a
resolver either.

type_override is the interesting refusal. It looks like an edit and is not: the
register says `file` and the prototype renders `url` because there is no server
for an upload to land on. Writing `url` into field_type would erase the fact
that the register asked for something the prototype cannot honour, and that
gap is exactly what this prototype is built to surface.
"""

from __future__ import annotations

import json
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from collections import defaultdict  # noqa: E402

from sqlalchemy import select  # noqa: E402

from app.database import SessionLocal, engine  # noqa: E402

engine.echo = False

from app import metadata_resolver as R  # noqa: E402
from app.metadata_spec import SPEC_DIR  # noqa: E402
from app.models import FieldDefinition, FieldPlacement  # noqa: E402
from app.routers.metadata import _apply_stage_scoped  # noqa: E402

EXTENSIONS = SPEC_DIR / "extensions.json"

# Types nobody types into. A computed CROSS-CUTTING row is record-level state,
# not a reason given at a stage. Mirrors DERIVED in src/lib/stageScope.ts.
DERIVED = {"computed", "autonumber"}


def load_sidecar() -> dict:
    return json.loads(EXTENSIONS.read_text(encoding="utf-8"))


# ------------------------------------------------------- stage_scoped


def stage_scoped_for(spec: dict, row: dict) -> str:
    """
    What `row` should carry, by extensions.json's own rule.

    A direct transcription of isPerStageValue(). Kept as one function so a
    difference between the two is a difference in one place, and so the dry run
    can print the reason each row got its answer.
    """
    if row["module"] not in spec["modules"]:
        return "none"
    api_name = row["api_name"]
    if any(f["api_name"] == api_name for f in spec["carry_forward"]["fields"]):
        return "carry_forward"
    if any(e["api_name"] == api_name for e in spec["sticky"].get("extra", [])):
        return "sticky"
    if (
        row["section"] in spec["sticky"]["sections"]
        and row["type"] not in DERIVED
        and (not spec["sticky"].get("require_condition") or row["visibility_condition"])
    ):
        return "sticky"
    return "none"


# ------------------------------------------------------- computed_expr


def definition_index(rows: list[dict], db) -> tuple[dict[str, int], set[str]]:
    """
    Sidecar key -> definition id, plus the keys that are ambiguous.

    A key is written against the REGISTER's module — `leads.total_value_tcv`
    for a field whose placement is on Opportunities now — so both the live
    module and origin_module are indexed, exactly as sidecarKeysFor() does in
    src/lib/spec/index.ts. A key resolving to two different definitions is
    reported and skipped rather than resolved to whichever was seen last.
    """
    by_key: dict[str, set[int]] = defaultdict(set)
    placements = {
        (p.module_key, p.api_name): p.definition_id
        for p in db.scalars(select(FieldPlacement).where(FieldPlacement.status == "active"))
    }
    for row in rows:
        definition_id = placements.get((row["module"], row["api_name"]))
        if definition_id is None:
            continue
        by_key[f"{row['module']}.{row['api_name']}"].add(definition_id)
        if row.get("register_module") and row["register_module"] != row["module"]:
            by_key[f"{row['register_module']}.{row['api_name']}"].add(definition_id)

    resolved = {k: next(iter(v)) for k, v in by_key.items() if len(v) == 1}
    ambiguous = {k for k, v in by_key.items() if len(v) > 1}
    return resolved, ambiguous


# ------------------------------------------------------------- report


def main() -> int:
    apply = "--apply" in sys.argv
    revert = "--revert" in sys.argv
    if apply and revert:
        print("  --apply and --revert are opposites. Pick one.")
        return 2

    sidecar = load_sidecar()
    spec = sidecar["stage_scoped"]
    entries = {k: v for k, v in sidecar["fields"].items() if not k.startswith("$")}

    db = SessionLocal()
    try:
        rows = R.resolved_fields(db)
        placements = {
            (p.module_key, p.api_name): p
            for p in db.scalars(
                select(FieldPlacement).where(FieldPlacement.status == "active")
            )
        }

        # ---------------------------------------------- 1. stage_scoped
        print("=" * 74)
        print("  1  stage_scoped")
        print("=" * 74)

        wanted: list[tuple[FieldPlacement, str, str]] = []
        for row in rows:
            placement = placements.get((row["module"], row["api_name"]))
            if placement is None:
                continue
            target = "none" if revert else stage_scoped_for(spec, row)
            if placement.stage_scoped != target:
                wanted.append((placement, placement.stage_scoped, target))

        if not wanted:
            print("  nothing to change — every placement already carries its answer")
        for placement, before, after in wanted:
            print(f"  {placement.module_key}.{placement.api_name}: {before} -> {after}")
            if apply or revert:
                _apply_stage_scoped(db, placement, after)

        # -------------------------------------------- 2. computed_expr
        print()
        print("=" * 74)
        print("  2  computed_expr")
        print("=" * 74)

        index, ambiguous = definition_index(rows, db)
        changed = 0
        unresolved: list[str] = []
        for key, entry in sorted(entries.items()):
            expr = entry.get("computed_expr")
            if expr is None:
                continue
            if key in ambiguous:
                unresolved.append(f"{key} (ambiguous — names more than one field)")
                continue
            definition_id = index.get(key)
            if definition_id is None:
                unresolved.append(f"{key} (no active placement anywhere)")
                continue
            definition = db.get(FieldDefinition, definition_id)
            target = None if revert else expr
            if definition.computed_expr == target:
                continue
            changed += 1
            print(f"  {key}")
            print(f"      formula (prose, unchanged): {definition.computed_formula!r}")
            print(f"      expr    {definition.computed_expr!r} -> {target!r}")
            if apply or revert:
                definition.computed_expr = target

        if not changed:
            print("  nothing to change")
        if unresolved:
            print(f"\n  {len(unresolved)} not applied:")
            for line in unresolved:
                print(f"      {line}")

        # ------------------------------------------------------ commit
        print()
        print("=" * 74)
        if apply or revert:
            db.commit()
            verb = "reverted" if revert else "applied"
            print(f"  {verb}: {len(wanted)} placements, {changed} expressions")
            print("  now run:  python regenerate_spec.py --apply")
        else:
            db.rollback()
            print(f"  DRY RUN — {len(wanted)} placements, {changed} expressions would change")
            print("  re-run with --apply")
        print("=" * 74)
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
