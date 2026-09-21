"""
Opportunities' Stage 4 becomes three sections, and the three third-party money
fields say which side of the money they are on.

    python stage4_commercial_sections.py            # dry run: shows the result, writes nothing
    python stage4_commercial_sections.py --apply    # write, then publish a version

WHY (review, 15 Sep 2026)
-------------------------
STAGE 4 — RFP / RFI held thirty fields: bid logistics and the whole commercial
build-up in one list. 3rd-Party One-Time sat a few rows from Third-Party Cost
with nothing to say that the first is REVENUE — what the client pays for resold
hardware and OEM licences, inside TCV — and the second is COST, the buy price,
inside Total Cost. A reviewer could not tell them apart.

    STAGE 4 — RFP / RFI                  bid logistics; its own fields keep their order
    STAGE 4 — COMMERCIAL: REVENUE        what the client pays, up to TCV
    STAGE 4 — COMMERCIAL: COST & MARGIN  what Astrikos pays, and the margin

Labels (definition-level, so Deals' ON CONVERSION copies read the same):

    3rd-Party One-Time               -> 3rd-Party Revenue — One-Time
    3rd-Party Recurring (per year)   -> 3rd-Party Revenue — Recurring (per year)
    Third-Party Cost                 -> 3rd-Party Cost (paid to vendors)

WHAT DOES NOT CHANGE
--------------------
api_names, columns and stored values; capture_stage (4), mandatory_from and
blocks_transition; every computed_expr (TCV, Gross Margin %, Total Cost). NO DDL.

THE SECTION NAMES MUST START "STAGE 4 —". The record page draws every section
NOT named STAGE on the Details tab, and the stage tab draws fields by
capture_stage — a section called plain "Commercial" would show its fields
twice. Publish check 6a (app/metadata_spec.py) holds the STAGE-named ones to
capture_stage 4.

Positions: the Stage 4 fields are renumbered within the sort_order numbers they
already occupy, so no field of any other section moves.
"""

from __future__ import annotations

import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from fastapi import HTTPException  # noqa: E402
from sqlalchemy import select  # noqa: E402

from app.database import SessionLocal, engine  # noqa: E402

engine.echo = False

from app.models import FieldDefinition, FieldPlacement, Section  # noqa: E402
from app.routers.metadata import _publish, _validation_out, build_snapshot  # noqa: E402

MODULE = "opportunities"

BID = "STAGE 4 — RFP / RFI"
REVENUE = "STAGE 4 — COMMERCIAL: REVENUE"
COST = "STAGE 4 — COMMERCIAL: COST & MARGIN"

#: The fields each new section takes, in the order they read.
MOVES: dict[str, tuple[str, ...]] = {
    REVENUE: (
        "licence_model",
        "platform_licence_list_price",
        "arr_annual_recurring",
        "licence_discount_pct",
        "perpetual_licence_fee",
        "one_time_revenue",
        "contract_years",
        "3rd_party_one_time",
        "3rd_party_recurring_per_year",
        "total_value_tcv",
        "third_party_pct_of_tcv",
        "primary_quote",
    ),
    COST: (
        "services_and_implementation_cost",
        "third_party_cost",
        "total_cost",
        "gross_margin_pct",
        "cost_model_rcm_document",
    ),
}

#: api_name -> (label, description). Shared pipeline definitions.
DEFINITIONS: dict[str, tuple[str, str]] = {
    "3rd_party_one_time": (
        "3rd-Party Revenue — One-Time",
        "REVENUE, charged once: what the client pays for hardware and one-off OEM licences resold "
        "through the Astrikos contract. Counts in TCV. Its buy price is 3rd-Party Cost.",
    ),
    "3rd_party_recurring_per_year": (
        "3rd-Party Revenue — Recurring (per year)",
        "REVENUE, charged every year: what the client pays for OEM subscriptions and passthrough "
        "licences resold through the contract. Counts in TCV for each Contract Year. Its buy price "
        "is 3rd-Party Cost.",
    ),
    "third_party_cost": (
        "3rd-Party Cost (paid to vendors)",
        "COST: what Astrikos pays the vendors for the hardware and OEM licences being resold — the "
        "buy price. Counts in Total Cost, never in TCV.",
    ),
}

NOTE = (
    "Opportunities: Stage 4 split into RFP / RFI, Commercial: Revenue and Commercial: Cost & Margin; "
    "third-party labels say revenue or cost"
)


def apply(db) -> tuple[list[str], list[str]]:
    log: list[str] = []
    problems: list[str] = []

    sections = {s.label: s for s in db.scalars(select(Section).where(Section.module_key == MODULE))}
    bid = sections.get(BID)
    if bid is None:
        return log, [f"{MODULE} has no section {BID!r} — the layout has changed; place these by hand."]

    # ------------------------------------------------ the two new sections
    for offset, label in enumerate((REVENUE, COST), start=1):
        if label in sections:
            continue
        for later in db.scalars(
            select(Section).where(Section.module_key == MODULE, Section.sort_order >= bid.sort_order + offset)
        ):
            later.sort_order += 1
        section = Section(module_key=MODULE, label=label, sort_order=bid.sort_order + offset, active=True)
        db.add(section)
        db.flush()
        sections[label] = section
        log.append(f"{MODULE}: section {label!r} created after {BID!r}")

    # ------------------------------------------------------ the placements
    stage4_ids = [sections[label].id for label in (BID, REVENUE, COST)]
    placements = list(
        db.scalars(
            select(FieldPlacement)
            .where(
                FieldPlacement.module_key == MODULE,
                FieldPlacement.section_id.in_(stage4_ids),
                FieldPlacement.status == "active",
            )
            .order_by(FieldPlacement.sort_order, FieldPlacement.id)
        )
    )
    by_name = {p.api_name: p for p in placements}
    moving = [name for names in MOVES.values() for name in names]
    missing = [name for name in moving if name not in by_name]
    if missing:
        problems.append(f"not in Stage 4 on {MODULE}: {', '.join(missing)}")
        return log, problems

    staying = [p for p in placements if p.api_name not in moving]
    ordered = [(p, bid.id) for p in staying]
    for label, names in MOVES.items():
        ordered += [(by_name[name], sections[label].id) for name in names]

    numbers = sorted(p.sort_order for p in placements)
    moved = renumbered = 0
    for (placement, section_id), number in zip(ordered, numbers):
        if placement.section_id != section_id:
            moved += 1
        elif placement.sort_order != number:
            renumbered += 1
        placement.section_id = section_id
        placement.sort_order = number
    if moved:
        log.append(f"{MODULE}: {moved} fields moved into the two Commercial sections")
    if renumbered:
        log.append(f"{MODULE}: {renumbered} fields renumbered within Stage 4 (same numbers, new order)")

    # --------------------------------------------------------- the labels
    for api_name, (label, description) in DEFINITIONS.items():
        definition = db.scalars(
            select(FieldDefinition).where(
                FieldDefinition.api_name == api_name,
                FieldDefinition.scope_key == "pipeline",
                FieldDefinition.status == "active",
            )
        ).first()
        if definition is None:
            problems.append(f"no active pipeline definition for {api_name}")
            continue
        if definition.label != label or definition.description != description:
            log.append(f"{api_name}: label {definition.label!r} -> {label!r}, help text says revenue or cost")
            definition.label = label
            definition.description = description

    return log, problems


def show_result(db) -> None:
    """Stage 4 as the published snapshot would draw it."""
    rows = [
        r
        for r in build_snapshot(db)["fields"]
        if r.get("module") == MODULE and str(r.get("section", "")).startswith("STAGE 4")
    ]
    rows.sort(key=lambda r: r.get("order") or r.get("sort_order") or 0)
    current = None
    for r in rows:
        if r.get("section") != current:
            current = r.get("section")
            print(f"\n  {current}")
        print(f"    {r.get('order') or r.get('sort_order')!s:>4}  {r.get('api_name'):34} {r.get('label')}")


def main() -> int:
    applying = "--apply" in sys.argv
    with SessionLocal() as db:
        log, problems = apply(db)
        print(f"Stage 4 commercial sections — {'apply' if applying else 'dry run'}")
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
            show_result(db)
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
