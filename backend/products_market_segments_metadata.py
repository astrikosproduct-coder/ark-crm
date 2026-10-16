"""
Products, phase 1 — the markets a product serves (13 Oct 2026).

    python products_market_segments_metadata.py            # dry run: validates, writes nothing
    python products_market_segments_metadata.py --apply    # change the register and publish

Segment -> Segment Category -> Subsegment on a product: three multi-choice
fields that follow one another, the way Region -> Country -> State do
(Release 1.1's Map Dependency Fields). The taxonomy is the go-to-market
workbook's, read from backend/data/market_segments.json (written by
tools/build_market_segments.py).

What it does, each step skipped when already done:

  1. Two lists: Segment Category (41 choices) and Subsegment (132). Both
     GLOBAL, like Segment itself, so another module can use them later.
     Segment is the list Leads and Accounts already use (`theme`) — a product's
     Segment and a Lead's Segment are the same seven choices.
  2. Products gain Segment, Segment Category and Subsegment, after Catalogue
     Category. All three take several choices and are Optional: a product in
     the catalogue today has none until someone tags it. Their values live in
     products.custom_fields, exactly as a field made in Setup — NO DDL.
  3. The maps, on Products: Segment -> Segment Category -> Subsegment. A
     product with two Segments is offered the categories of both
     (app/field_dependencies.py).
  4. Publish.

WHAT IT LEAVES ALONE
  * Leads and Accounts. Nothing is added to them (decided 12 Oct 2026: Products
    only; a Lead's own Segment is what a product is matched to, later).
  * Segment's labels. The workbook spells three of the seven differently
    ("Data Centres" for ARK's "Data Centers"). They are the same choices; the
    difference is listed below the run and nothing is renamed — a rename shows
    on every Lead and Account, so it is made in Setup, by a person.
  * Choices already loaded. A label changed in Setup since is kept; a choice
    retired there stays retired. Only missing choices and missing pairs are
    added, so re-running after a newer workbook adds what is new.

Run on development and on production, after `alembic upgrade head` and after
products_step1_metadata.py.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from fastapi import HTTPException  # noqa: E402
from sqlalchemy import func, select  # noqa: E402

from app.database import SessionLocal, engine  # noqa: E402

engine.echo = False

from app.models import (  # noqa: E402
    FieldDefinition,
    FieldDependency,
    FieldDependencyValue,
    FieldPlacement,
    Picklist,
    PicklistValue,
)
from app.routers.metadata import _publish, _validation_out, build_snapshot  # noqa: E402

DATA = Path(__file__).resolve().parent / "data" / "market_segments.json"

MODULE = "products"
SEGMENT_LIST = "theme"
CATEGORY_LIST = "segment_categories"
SUBSEGMENT_LIST = "subsegments"

AFTER = "catalogue_category"

#: api_name, label, the list it chooses from, what it says under the field.
FIELDS = (
    (
        "segments",
        "Segment",
        SEGMENT_LIST,
        "The markets this product is sold into. Choose every one that applies.",
    ),
    (
        "segment_categories",
        "Segment Category",
        CATEGORY_LIST,
        "The parts of those markets it serves. Offers the categories of the Segments chosen.",
    ),
    (
        "subsegments",
        "Subsegment",
        SUBSEGMENT_LIST,
        "The kinds of customer it serves. Offers the subsegments of the Segment Categories chosen.",
    ),
)

USE_CASE = "Products phase 1 (13 Oct 2026): the go-to-market taxonomy, Segment -> Segment Category -> Subsegment."
NOTE = "Products: Segment -> Segment Category -> Subsegment, several choices each; 41 categories and 132 subsegments loaded"


def placement(db, api_name: str) -> FieldPlacement | None:
    return db.scalars(
        select(FieldPlacement)
        .where(FieldPlacement.module_key == MODULE)
        .where(FieldPlacement.api_name == api_name)
        .where(FieldPlacement.status == "active")
    ).first()


def definition(db, api_name: str) -> FieldDefinition | None:
    return db.scalars(
        select(FieldDefinition).where(FieldDefinition.scope_key == MODULE).where(FieldDefinition.api_name == api_name)
    ).first()


def ensure_list(db, key: str, label: str, values: list[dict[str, str]], log: list[str]) -> None:
    picklist = db.get(Picklist, key)
    if picklist is None:
        top = db.scalar(select(func.max(Picklist.sort_order))) or 0
        picklist = Picklist(picklist_key=key, label=label, sort_order=top + 1, active=True, is_global=True)
        db.add(picklist)
        db.flush()
        log.append(f"picklist {key}: created ({label}, global)")
    existing = {v.key for v in picklist.values}
    last = max((v.sort_order for v in picklist.values), default=0)
    added = 0
    for row in values:
        if row["key"] in existing:
            continue  # its label and whether it is active are Setup's to change
        last += 1
        db.add(PicklistValue(picklist_key=key, key=row["key"], label=row["label"], sort_order=last, active=True))
        added += 1
    if added:
        log.append(f"picklist {key}: {added} choices added ({len(existing) + added} in all)")
    db.flush()


def fields(db, log: list[str]) -> None:
    anchor = placement(db, AFTER)
    if anchor is None:
        raise SystemExit(f"{MODULE}.{AFTER} is not placed — is this the ARK register?")
    missing = [f for f in FIELDS if placement(db, f[0]) is None]
    if not missing:
        return
    # Room for the three, in order, straight after Catalogue Category.
    for later in db.scalars(
        select(FieldPlacement)
        .where(FieldPlacement.module_key == MODULE)
        .where(FieldPlacement.sort_order > anchor.sort_order)
    ):
        later.sort_order += len(missing)
    for offset, (api_name, label, picklist, description) in enumerate(missing, start=1):
        d = definition(db, api_name)
        if d is None:
            d = FieldDefinition(
                scope_key=MODULE,
                api_name=api_name,
                label=label,
                field_type="multiselect",
                picklist_key=picklist,
                description=description,
                use_case=USE_CASE,
                origin="Administration",
                origin_module=MODULE,
                status="active",
            )
            db.add(d)
            db.flush()
            log.append(f"{MODULE}.{api_name}: definition created ({label}, several choices from '{picklist}')")
        db.add(
            FieldPlacement(
                definition_id=d.id,
                api_name=api_name,
                module_key=MODULE,
                scope_key=anchor.scope_key,
                section_id=anchor.section_id,
                sort_order=anchor.sort_order + offset,
                capture_any_stage=False,
                requirement="Optional",
                required_on_create=False,
                value_mode="own",
                editable=True,
                storage="custom_fields",
                status="active",
                provenance="admin",
            )
        )
        log.append(f"{MODULE}.{api_name}: placed after Catalogue Category, Optional, values in custom_fields")
    db.flush()


def maps(db, data: dict, log: list[str]) -> None:
    wanted = [
        ("segments", "segment_categories", {(c["segment"], c["key"]) for c in data["categories"]}),
        ("segment_categories", "subsegments", {(s["category"], s["key"]) for s in data["subsegments"]}),
    ]
    for parent, child, pairs in wanted:
        dep = db.scalars(
            select(FieldDependency).where(FieldDependency.module_key == MODULE).where(FieldDependency.child_field == child)
        ).first()
        if dep is None:
            dep = FieldDependency(module_key=MODULE, parent_field=parent, child_field=child)
            db.add(dep)
            db.flush()
        elif dep.parent_field != parent:
            raise SystemExit(
                f"{MODULE}.{child} already follows {dep.parent_field}, not {parent} — stop and look before changing a map."
            )
        have = {(v.parent_value, v.child_value) for v in dep.values}
        new = sorted(pairs - have)
        if not new:
            continue
        dep.values.extend(FieldDependencyValue(parent_value=p, child_value=c) for p, c in new)
        log.append(f"{MODULE}: {parent} -> {child}, {len(new)} pairs added ({len(have) + len(new)} in all)")
    db.flush()


def segment_notes(db, data: dict) -> list[str]:
    """The workbook's Segments against ARK's list: must all exist; spelling differences are reported."""
    segment_list = db.get(Picklist, SEGMENT_LIST)
    if segment_list is None:
        raise SystemExit(f"The Segment list ('{SEGMENT_LIST}') is missing — is this the ARK register?")
    labels = {v.key: v.label for v in segment_list.values if v.active}
    absent = [s["key"] for s in data["segments"] if s["key"] not in labels]
    if absent:
        raise SystemExit(f"Segment lacks {absent} — the workbook names a market ARK's Segment list does not have.")
    return [
        f"“{labels[s['key']]}” in ARK is “{s['workbook_label']}” in the workbook"
        for s in data["segments"]
        if labels[s["key"]] != s["workbook_label"]
    ]


def main() -> int:
    mode = "apply" if "--apply" in sys.argv else "dry"
    if not DATA.exists():
        raise SystemExit(f"STOPPED: {DATA} is missing — run tools/build_market_segments.py.")
    data = json.loads(DATA.read_text(encoding="utf-8"))
    with SessionLocal() as db:
        log: list[str] = []
        differences = segment_notes(db, data)
        ensure_list(db, CATEGORY_LIST, "Segment Category", data["categories"], log)
        ensure_list(db, SUBSEGMENT_LIST, "Subsegment", data["subsegments"], log)
        fields(db, log)
        maps(db, data, log)

        print(f"Products market segments — {mode}")
        print("=" * 74)
        for line in log or ["nothing to do"]:
            print(f"  {line}")
        if differences:
            print("\nSegment is spelled differently in the workbook — the same choices, NOT renamed:")
            for line in differences:
                print(f"  {line}")
            print("  To rename one, change its label in Setup. It then reads that way on Leads and Accounts too.")
        if not log:
            db.rollback()
            return 0
        if mode == "dry":
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
