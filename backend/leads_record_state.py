"""
Phase A — give Leads a RECORD STATE section, like Opportunities and Deals.

    python leads_record_state.py             # dry run: what would change
    python leads_record_state.py --apply
    python leads_record_state.py --revert    # put the three fields back

Then:  python regenerate_spec.py --apply

THE PROBLEM
-----------
`lead_status` is filed under `STAGE 0 — CONNECT` on Leads, at sort_order 19.
Status is not a Stage 0 fact — a lead is Open, On Hold or Closed Lost at every
stage — so putting it in a stage section means that to change the status of a
Stage 1 lead you first click back to the Stage 0 tab. Phase A2 made this
plainly visible rather than causing it: On Hold Reason is anchored to
`lead_status`, so the reason box went to Stage 0 too.

Opportunities and Deals already do the right thing. Both carry a `RECORD
STATE — each module keeps its own instance` section, which is not a numbered
STAGE section and therefore renders on the Details tab, reachable from any
stage. Leads is the odd one out, and only because the pipeline split gave the
other two a section Leads never got.

WHAT MOVES
----------
Three placements, from `STAGE 0 — CONNECT` to a new `RECORD STATE` section
with the same label the other two modules use:

    project_stage      Lead Stage
    lead_status        Lead Status
    probability_pct    Probability (%)

That is exactly the trio Opportunities carries, so after this all three
pipeline modules describe their own record state the same way.

WHY capture_stage BECOMES NULL, AND WHY THAT IS THE WHOLE RISK
---------------------------------------------------------------
All three currently have `capture_stage = 0`. Moving them while they keep it
would recreate a bug the codebase already has once, in Deals' ON CONVERSION:

    sectionsForStage(module, stage)   lib/pipeline.ts
        every section holding a field whose capture_stage === stage

    detailSections                    PipelineRecordPage.tsx
        every section not starting with "STAGE" and not __header

A section can satisfy both. `ON CONVERSION` has capture_stage 7 and does not
start with "STAGE", so its 32 fields render on the Stage 7 tab AND the Details
tab of every Deal. RECORD STATE on Leads would do the same at stage 0, because
0 is inside the Leads range — which is why Opportunities and Deals get away
with `capture_stage = 0` on theirs: 0 is outside 4–6 and 7–9, so their stage
tabs never ask for it.

So the three move to `capture_stage = NULL, capture_any_stage = True`, which
is what they always meant: they apply at every stage. Nothing else reads
capture_stage — only sectionForStage and sectionsForStage in lib/pipeline.ts —
and 32 of the 35 STAGE 0 fields keep theirs, so sectionForStage(leads, 0)
still answers `STAGE 0 — CONNECT` and the create page is unaffected in that
respect. (It IS affected in another; see LeadCreatePage's lead_status default.)

The same latent trap exists on Opportunities and Deals and is deliberately NOT
touched here: it is harmless while their ranges exclude stage 0, both modules
work today, and widening the blast radius of this change to fix a bug nobody
can reach is how working screens break.

WHY THE RENUMBER
----------------
spec/fields.json orders fields by placement sort_order across the whole
module (metadata_resolver.py:204), and sectionsFor() reads section order off
each section's FIRST APPEARANCE in that sequence. Sections are therefore
contiguous runs of sort_order, and the register relies on it — see the comment
on sectionsFor in lib/spec/index.ts.

Pulling 18, 19 and 20 out of the STAGE 0 run would leave a hole in it and put
RECORD STATE's first appearance in the middle of another section's range.
Nothing would visibly break today, because the Details tab filters the STAGE
sections out anyway, but the invariant would be quietly false and the next
person to trust it would be wrong. So Leads' placements are renumbered
contiguously in section order afterwards: HEADER, RECORD STATE, STAGE 0…3,
__header, Aging, SYSTEM — the same shape Opportunities already has.
"""

from __future__ import annotations

import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from sqlalchemy import select  # noqa: E402

from app.database import SessionLocal, engine  # noqa: E402

engine.echo = False

from app.models import FieldPlacement, Section  # noqa: E402

MODULE = "leads"
RECORD_STATE = "RECORD STATE — each module keeps its own instance"
MOVING = ("project_stage", "lead_status", "probability_pct")

# Leads' sections in the order they should render. Anything not named keeps a
# position after these — the four empty STAGE 4–7 sections the pipeline split
# left behind on Leads hold no placements and are left alone rather than
# deleted, which is a separate decision from this one.
SECTION_ORDER = (
    "HEADER",
    RECORD_STATE,
    "STAGE 0 — CONNECT",
    "STAGE 1 — DEMO PRESENTATION",
    "STAGE 2 — POC / PILOT",
    "STAGE 3 — PRESCRIPTION",
    "__header",
    "Aging",
    "SYSTEM",
)


def sections_of(db) -> dict[str, Section]:
    rows = db.scalars(select(Section).where(Section.module_key == MODULE)).all()
    return {s.label: s for s in rows}


def placements_of(db) -> list[FieldPlacement]:
    return list(
        db.scalars(
            select(FieldPlacement)
            .where(FieldPlacement.module_key == MODULE)
            .where(FieldPlacement.status == "active")
            .order_by(FieldPlacement.sort_order)
        )
    )


def renumber(db) -> list[str]:
    """Contiguous sort_order across the module, in section order."""
    by_label = sections_of(db)
    rank = {}
    for position, label in enumerate(SECTION_ORDER):
        section = by_label.get(label)
        if section is not None:
            rank[section.id] = position
    # Sections not in SECTION_ORDER sort after the named ones, stably.
    fallback = len(SECTION_ORDER)

    rows = placements_of(db)
    rows.sort(key=lambda p: (rank.get(p.section_id, fallback), p.sort_order, p.id))

    changes = []
    for position, placement in enumerate(rows, start=1):
        if placement.sort_order != position:
            changes.append(f"{placement.api_name}: {placement.sort_order} -> {position}")
            placement.sort_order = position
    return changes


def apply(db) -> list[str]:
    log: list[str] = []
    by_label = sections_of(db)

    section = by_label.get(RECORD_STATE)
    if section is None:
        section = Section(
            module_key=MODULE,
            label=RECORD_STATE,
            # Real position is settled by the section renumber below; this is
            # only so the row is never written with a meaningless 0.
            sort_order=2,
            active=True,
        )
        db.add(section)
        db.flush()
        log.append(f"created section {RECORD_STATE!r} (id={section.id})")
    elif not section.active:
        section.active = True
        log.append(f"reactivated section {RECORD_STATE!r}")
    else:
        log.append(f"section {RECORD_STATE!r} already exists (id={section.id})")

    # Section display order, so the Details tab reads HEADER, RECORD STATE,
    # Aging, SYSTEM — the order Opportunities already has.
    by_label = sections_of(db)
    for position, label in enumerate(SECTION_ORDER, start=1):
        row = by_label.get(label)
        if row is not None and row.sort_order != position:
            log.append(f"section {label!r}: sort_order {row.sort_order} -> {position}")
            row.sort_order = position

    for api_name in MOVING:
        placement = db.scalars(
            select(FieldPlacement)
            .where(FieldPlacement.module_key == MODULE)
            .where(FieldPlacement.api_name == api_name)
        ).first()
        if placement is None:
            log.append(f"!! {api_name} has no placement on {MODULE} — skipped")
            continue
        if placement.section_id == section.id:
            log.append(f"{api_name} already in {RECORD_STATE!r}")
            continue
        log.append(
            f"{api_name}: section {placement.section_id} -> {section.id}, "
            f"capture_stage {placement.capture_stage} -> None, "
            f"capture_any_stage {placement.capture_any_stage} -> True"
        )
        placement.section_id = section.id
        placement.capture_stage = None
        placement.capture_any_stage = True

    db.flush()
    log.extend(renumber(db))
    return log


def revert(db) -> list[str]:
    log: list[str] = []
    by_label = sections_of(db)
    stage0 = by_label.get("STAGE 0 — CONNECT")
    if stage0 is None:
        return ["!! STAGE 0 — CONNECT not found; nothing reverted"]

    for api_name in MOVING:
        placement = db.scalars(
            select(FieldPlacement)
            .where(FieldPlacement.module_key == MODULE)
            .where(FieldPlacement.api_name == api_name)
        ).first()
        if placement is None or placement.section_id == stage0.id:
            continue
        log.append(f"{api_name}: back to STAGE 0 — CONNECT, capture_stage 0")
        placement.section_id = stage0.id
        placement.capture_stage = 0
        placement.capture_any_stage = False

    section = by_label.get(RECORD_STATE)
    if section is not None:
        section.active = False
        log.append(f"deactivated section {RECORD_STATE!r}")

    db.flush()
    log.extend(renumber(db))
    return log


def main() -> int:
    mode = "dry"
    if "--apply" in sys.argv:
        mode = "apply"
    elif "--revert" in sys.argv:
        mode = "revert"

    with SessionLocal() as db:
        log = revert(db) if mode == "revert" else apply(db)

        print(f"Leads RECORD STATE — {mode}")
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
