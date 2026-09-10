"""
Phase A — Expected Close Month becomes record state; Close Date Pushback Count goes.

    python close_month_record_state.py             # dry run: what would change
    python close_month_record_state.py --apply
    python close_month_record_state.py --revert

Then:  python regenerate_spec.py --apply

TWO CHANGES, ONE SCRIPT, BECAUSE THEY ARE ONE DECISION
-------------------------------------------------------
Close Date Pushback Count counts the times Expected Close Month moved. It has
never been able to: `computed_formula` is the empty string, and models.Lead's
property returned a hardcoded 0 with a docstring saying it needs "a history of
expected_close_month edits, which nothing persists yet". The reason nothing
persisted one is the other half of this script — a single column, overwritten
on every revision. So the dead field is deleted and the field it depended on is
given the shape that would make it computable, in one move.

CHANGE 1 — expected_close_month, STAGE 0 -> RECORD STATE
---------------------------------------------------------
It is a forecast, revised monthly ("§7.1 — the basis of the rolling forecast;
must be reviewed monthly", its own use_case), filed under the stage it was
first asked at. Two consequences, and the second is the serious one:

  * to revise the close month of a Stage 5 pursuit you first click back to the
    Stage 0 tab — the same complaint that moved lead_status in
    leads_record_state.py, for the same reason;

  * it did not exist on Opportunities or Deals AT ALL. A field follows the
    stage that captures it (module_split.json `reassign`), capture_stage 0 is
    inside Leads' 0-3 range, so the placement stayed on Leads and no other
    module ever got one. The forecast date was absent from RFP, Commercial
    Evaluation and Close: the three stages a forecast is actually read at.

So: the Leads placement moves to `RECORD STATE — each module keeps its own
instance` with capture_stage NULL / capture_any_stage True, and Opportunities
and Deals gain their own instance of it — provenance `own_instance`, exactly
what project_stage / lead_status / probability_pct already carry there.

capture_stage MUST go NULL, for the reason leads_record_state.py documents at
length: sectionsForStage() offers every section holding a field whose
capture_stage equals the stage, and RECORD STATE does not start with "STAGE",
so a capture_stage of 0 would render the section on the Stage 0 tab AND the
Details tab at once. mandatory_from 0 and blocks_transition "0 → 1" are KEPT —
the field is still demanded at Connect and still blocks the first advance. Only
where it is asked changes, not whether.

The two new placements take capture_stage 0 / capture_any_stage False, matching
probability_pct's own_instance rows on those modules rather than inventing a
third shape. 0 is outside 4-6 and 7-9, so neither module's stage tabs ask for
the section — the trap above cannot fire there.

CHANGE 2 — close_date_pushback_count, deleted
----------------------------------------------
A LOGICAL delete: status='deleted' on the definition and on all three
placements, deleted_at/deleted_by stamped, the row kept, no DDL of any kind.
There is no business column to preserve anywhere — it is `computed`, the
register gave it no formula, and no leads/opportunities/deals table has ever
had a column by that name — so nothing is at risk in either direction and
--revert brings it back exactly as it was.

The Playbook rule it carried (§7.2, "a second pushback triggers management
discussion and re-qualification") is NOT being implemented here and is not
being quietly dropped either: it was never enforced, and after Change 1 the
history it needs finally exists — `expected_close_month__s0…s9` in
custom_fields, written by stageScope.ts's carry_forward mechanism. Counting the
stages at which the month moved later is then a real computation over real
values, rather than a column that cannot see its own past.

WHY THE RENUMBER
----------------
spec/fields.json orders placements by sort_order across the whole module and
sectionsFor() reads section order off each section's first appearance in that
sequence, so sections must stay contiguous runs — see leads_record_state.py,
which established both the invariant and this fix. Pulling a field out of
STAGE 0 and deleting one out of CROSS-CUTTING leaves two holes; all three
pipeline modules are renumbered contiguously in section order afterwards.
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from sqlalchemy import select  # noqa: E402

from app.database import SessionLocal, engine  # noqa: E402

engine.echo = False

from app.models import FieldDefinition, FieldPlacement, Section  # noqa: E402

RECORD_STATE = "RECORD STATE — each module keeps its own instance"
READ_THROUGH = "READ THROUGH THE PARENT — resolved from the parent, never stored here"
STAGE_0 = "STAGE 0 — CONNECT"

MOVING = "expected_close_month"
DELETING = "close_date_pushback_count"

# deleted_by is a FK to users and stays NULL here. No human pressed the button
# — a migration did — and naming a person who was not there to make the audit
# row look complete is worse than an honest blank. deleted_at still stamps, so
# WHEN is recorded even though WHO has no true answer.
ACTOR = None

# The modules that gain their own instance, and the sort_order the new
# placement takes inside RECORD STATE. Both sit directly after probability_pct,
# which is the last of the existing trio on each — the renumber below settles
# the absolute numbers, this only fixes the order within the section.
GAINING = ("opportunities", "deals")

# Section order per module, for the contiguous renumber. Leads' list is
# leads_record_state.py's, unchanged.
SECTION_ORDER: dict[str, tuple[str, ...]] = {
    "leads": (
        "HEADER",
        RECORD_STATE,
        STAGE_0,
        "STAGE 1 — DEMO PRESENTATION",
        "STAGE 2 — POC / PILOT",
        "STAGE 3 — PRESCRIPTION",
        "__header",
        "CROSS-CUTTING",
        "SYSTEM",
    ),
    "opportunities": (
        "HEADER",
        RECORD_STATE,
        "STAGE 4 — RFP / RFI",
        "STAGE 5 — TECHNICAL EVALUATION",
        "STAGE 6 — COMMERCIAL EVALUATION",
        "__header",
        READ_THROUGH,
        "CROSS-CUTTING",
        "SYSTEM",
    ),
    "deals": (
        "HEADER",
        RECORD_STATE,
        "ON CONVERSION",
        "STAGE 7 — CLOSE",
        "STAGE 8 — PROJECT SUCCESS",
        "STAGE 9 — EXPANSION & RENEWAL",
        "__header",
        READ_THROUGH,
        "CROSS-CUTTING",
        "SYSTEM",
    ),
}


def sections_of(db, module: str) -> dict[str, Section]:
    rows = db.scalars(select(Section).where(Section.module_key == module)).all()
    return {s.label: s for s in rows}


def placement(db, module: str, api_name: str) -> FieldPlacement | None:
    return db.scalars(
        select(FieldPlacement)
        .where(FieldPlacement.module_key == module)
        .where(FieldPlacement.api_name == api_name)
    ).first()


def renumber(db, module: str) -> list[str]:
    """Contiguous sort_order across one module, in section order."""
    by_label = sections_of(db, module)
    rank = {}
    for position, label in enumerate(SECTION_ORDER[module]):
        section = by_label.get(label)
        if section is not None:
            rank[section.id] = position
    fallback = len(SECTION_ORDER[module])

    rows = list(
        db.scalars(
            select(FieldPlacement)
            .where(FieldPlacement.module_key == module)
            .where(FieldPlacement.status == "active")
            .order_by(FieldPlacement.sort_order)
        )
    )
    rows.sort(key=lambda p: (rank.get(p.section_id, fallback), p.sort_order, p.id))

    changes = []
    for position, row in enumerate(rows, start=1):
        if row.sort_order != position:
            changes.append(f"  {module}.{row.api_name}: {row.sort_order} -> {position}")
            row.sort_order = position
    return changes


def move_close_month(db) -> list[str]:
    log: list[str] = []

    source = placement(db, "leads", MOVING)
    if source is None:
        return [f"!! {MOVING} has no placement on leads — nothing moved"]

    record_state = sections_of(db, "leads").get(RECORD_STATE)
    if record_state is None:
        return [
            f"!! leads has no {RECORD_STATE!r} section — run leads_record_state.py first"
        ]

    if source.section_id == record_state.id:
        log.append(f"leads.{MOVING} already in RECORD STATE")
    else:
        log.append(
            f"leads.{MOVING}: section {source.section_id} -> {record_state.id}, "
            f"capture_stage {source.capture_stage} -> None, "
            f"capture_any_stage {source.capture_any_stage} -> True "
            f"(mandatory_from {source.mandatory_from} and "
            f"blocks_transition {source.blocks_transition!r} kept)"
        )
        source.section_id = record_state.id
        source.capture_stage = None
        source.capture_any_stage = True

    # The two new own instances.
    for module in GAINING:
        existing = placement(db, module, MOVING)
        if existing is not None:
            if existing.status != "active":
                existing.status = "active"
                existing.deleted_at = None
                existing.deleted_by = None
                log.append(f"{module}.{MOVING}: reactivated")
            else:
                log.append(f"{module}.{MOVING} already placed")
            continue

        target = sections_of(db, module).get(RECORD_STATE)
        if target is None:
            log.append(f"!! {module} has no {RECORD_STATE!r} section — skipped")
            continue

        # Sit directly after the module's own probability_pct, so RECORD STATE
        # reads the same way on all three modules.
        anchor = placement(db, module, "probability_pct")
        after = anchor.sort_order if anchor is not None else target.sort_order

        db.add(
            FieldPlacement(
                definition_id=source.definition_id,
                api_name=MOVING,
                module_key=module,
                scope_key=module,
                section_id=target.id,
                # Provisional — renumber() below settles it. Half-steps keep
                # the intended position through the sort that precedes it.
                sort_order=after,
                capture_stage=0,
                capture_any_stage=False,
                mandatory_from=source.mandatory_from,
                blocks_transition=source.blocks_transition,
                requirement=source.requirement,
                required_on_skip=source.required_on_skip,
                visibility_condition=None,
                condition=None,
                value_mode="own",
                value_locked=False,
                editable=True,
                storage="column",
                status="active",
                provenance="own_instance",
            )
        )
        log.append(
            f"{module}.{MOVING}: created own_instance placement in RECORD STATE "
            f"(capture_stage 0, mandatory_from {source.mandatory_from})"
        )

    return log


def delete_pushback(db) -> list[str]:
    log: list[str] = []
    stamp = datetime.now(timezone.utc)

    definition = db.scalars(
        select(FieldDefinition).where(FieldDefinition.api_name == DELETING)
    ).first()
    if definition is None:
        return [f"!! no field_definitions row for {DELETING}"]

    rows = list(
        db.scalars(
            select(FieldPlacement).where(FieldPlacement.api_name == DELETING)
        )
    )
    for row in rows:
        if row.status == "deleted":
            log.append(f"{row.module_key}.{DELETING} already deleted")
            continue
        row.status = "deleted"
        row.deleted_at = stamp
        row.deleted_by = ACTOR
        # Exactly what DELETE /fields/{id} stamps, so Administration's own
        # Restore button brings all three placements back and knows it may.
        row.deleted_by_cascade = True
        log.append(f"{row.module_key}.{DELETING}: placement status -> deleted")

    if definition.status == "deleted":
        log.append(f"{DELETING} definition already deleted")
    else:
        definition.status = "deleted"
        definition.deleted_at = stamp
        definition.deleted_by = ACTOR
        log.append(f"{DELETING}: definition status -> deleted (row kept, no DDL)")

    return log


def apply(db) -> list[str]:
    log = move_close_month(db)
    log.extend(delete_pushback(db))
    db.flush()
    for module in SECTION_ORDER:
        log.extend(renumber(db, module))
    return log


def revert(db) -> list[str]:
    log: list[str] = []

    source = placement(db, "leads", MOVING)
    stage0 = sections_of(db, "leads").get(STAGE_0)
    if source is not None and stage0 is not None and source.section_id != stage0.id:
        source.section_id = stage0.id
        source.capture_stage = 0
        source.capture_any_stage = False
        log.append(f"leads.{MOVING}: back to {STAGE_0}, capture_stage 0")

    for module in GAINING:
        row = placement(db, module, MOVING)
        if row is not None:
            db.delete(row)
            log.append(f"{module}.{MOVING}: own_instance placement removed")

    definition = db.scalars(
        select(FieldDefinition).where(FieldDefinition.api_name == DELETING)
    ).first()
    if definition is not None and definition.status == "deleted":
        definition.status = "active"
        definition.deleted_at = None
        definition.deleted_by = None
        log.append(f"{DELETING}: definition restored")
    for row in db.scalars(
        select(FieldPlacement).where(FieldPlacement.api_name == DELETING)
    ):
        if row.status == "deleted":
            row.status = "active"
            row.deleted_at = None
            row.deleted_by = None
            row.deleted_by_cascade = False
            log.append(f"{row.module_key}.{DELETING}: placement restored")

    db.flush()
    for module in SECTION_ORDER:
        log.extend(renumber(db, module))
    return log


def main() -> int:
    mode = "dry"
    if "--apply" in sys.argv:
        mode = "apply"
    elif "--revert" in sys.argv:
        mode = "revert"

    with SessionLocal() as db:
        log = revert(db) if mode == "revert" else apply(db)

        print(f"Expected Close Month -> RECORD STATE, Pushback Count deleted — {mode}")
        print("=" * 74)
        for line in log:
            print(f"  {line}" if not line.startswith("  ") else line)
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
