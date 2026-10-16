"""
Release 1.2 — Segment -> Segment Category -> Subsegment on Leads and Accounts
(decided 15 Oct 2026).

    python release_1_2_market_segments_metadata.py            # dry run: validates, writes nothing
    python release_1_2_market_segments_metadata.py --apply    # change the register and publish

The go-to-market taxonomy (backend/data/market_segments.json — the same file
phase-2's Products use, with the same list keys, so the two meet at the merge):
7 Segments, 41 Segment Categories, 132 Subsegments.

What it does, each step skipped when already done:

  1. Two lists: Segment Category (41) and Subsegment (132). Segment is the list
     Leads and Accounts already use (`theme`).
  2. Leads gain Segment Category and Subsegment, ONE choice each, straight
     after Segment. A pursuit is one project, so a dashboard grouped by
     Subsegment counts it once. Opportunities and Deals show both "From the
     Lead", read-only, as they show Segment — no copy that could drift.
  3. Accounts gain Segment Category and Subsegment, SEVERAL choices each,
     straight after their (several-choice) Segment.
  4. The maps: Leads Segment -> Segment Category -> Subsegment; Accounts the
     same over several choices (app/field_dependencies.py offers the choices
     of every parent choice held).
  5. Publish.

All four fields are Optional (records and import sheets made before today
have none) and keep their values in the record's custom_fields — as Accounts'
Segment does since Release 1.1. NO DDL, no migration. Picked by hand on a
Lead, never copied from its Account, as Segment.

WHAT IT LEAVES ALONE
  * Segment's own labels. Three are spelled differently in the workbook ("Data
    Centres" for ARK's "Data Centers"); they are the same choices and nothing
    is renamed. The difference is listed below the run.
  * Choices already loaded: a label changed since is kept, a retired choice
    stays retired. Only missing choices and missing pairs are added.

Run on development and on production, after `alembic upgrade head`.
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

SEGMENT_LIST = "theme"
CATEGORY_LIST = "segment_categories"
SUBSEGMENT_LIST = "subsegments"

USE_CASE = "Release 1.2 (15 Oct 2026): the go-to-market taxonomy, Segment -> Segment Category -> Subsegment."
NOTE = "Release 1.2: Segment Category and Subsegment on Leads (one each, shown From the Lead) and Accounts (several)"

#: Leads: api_name, label, list, description. One choice each.
LEAD_FIELDS = (
    ("segment_category", "Segment Category", CATEGORY_LIST,
     "The part of the Segment this project is in. Offers the categories of the Segment chosen."),
    ("subsegment", "Subsegment", SUBSEGMENT_LIST,
     "The kind of customer this project is for. Offers the subsegments of the Segment Category chosen."),
)
#: Accounts: several choices each.
ACCOUNT_FIELDS = (
    ("segment_categories", "Segment Category", CATEGORY_LIST,
     "The parts of those Segments this company works in. Offers the categories of the Segments chosen."),
    ("subsegments", "Subsegment", SUBSEGMENT_LIST,
     "The kinds of customer it is. Offers the subsegments of the Segment Categories chosen."),
)

#: Copied from Segment's read-through placement on Opportunities and Deals.
READ_THROUGH_COLUMNS = (
    "capture_stage",
    "capture_any_stage",
    "value_mode",
    "value_locked",
    "editable",
    "stage_scoped",
)


def placement(db, module: str, api_name: str) -> FieldPlacement | None:
    return db.scalars(
        select(FieldPlacement)
        .where(FieldPlacement.module_key == module)
        .where(FieldPlacement.api_name == api_name)
        .where(FieldPlacement.status == "active")
    ).first()


def definition(db, scope: str, api_name: str) -> FieldDefinition | None:
    return db.scalars(
        select(FieldDefinition).where(FieldDefinition.scope_key == scope).where(FieldDefinition.api_name == api_name)
    ).first()


def ensure_list(db, key: str, label: str, values: list[dict[str, str]], log: list[str]) -> None:
    picklist = db.get(Picklist, key)
    if picklist is None:
        top = db.scalar(select(func.max(Picklist.sort_order))) or 0
        picklist = Picklist(picklist_key=key, label=label, sort_order=top + 1, active=True)
        db.add(picklist)
        db.flush()
        log.append(f"picklist {key}: created ({label})")
    existing = {v.key for v in picklist.values}
    last = max((v.sort_order for v in picklist.values), default=0)
    added = 0
    for row in values:
        if row["key"] in existing:
            continue  # its label and whether it is active are Administration's to change
        last += 1
        db.add(PicklistValue(picklist_key=key, key=row["key"], label=row["label"], sort_order=last, active=True))
        added += 1
    if added:
        log.append(f"picklist {key}: {added} choices added ({len(existing) + added} in all)")
    db.flush()


def ensure_definition(db, scope: str, api_name: str, label: str, field_type: str, picklist: str, description: str,
                      log: list[str], **extra) -> FieldDefinition:
    d = definition(db, scope, api_name)
    if d is None:
        d = FieldDefinition(
            scope_key=scope,
            api_name=api_name,
            label=label,
            field_type=field_type,
            picklist_key=picklist,
            description=description,
            use_case=USE_CASE,
            status="active",
            **extra,
        )
        db.add(d)
        db.flush()
        log.append(f"{scope}.{api_name}: definition created ({label}, {field_type} over '{picklist}')")
    return d


def make_room(db, module: str, after_sort_order: int, by: int) -> None:
    for later in db.scalars(
        select(FieldPlacement).where(FieldPlacement.module_key == module).where(FieldPlacement.sort_order > after_sort_order)
    ):
        later.sort_order += by


def lead_scope(db) -> tuple[str, dict]:
    """Where a Lead field's definition lives. Before metadata v2 (production at
    Release 1.2) the pipeline modules share the "pipeline" scope; after it
    (phase-2) a field is owned by one module — Leads, shown From the Lead on the
    other two. The script reads which register it runs on."""
    if definition(db, "pipeline", "theme") is not None:
        return "pipeline", {}
    if definition(db, "leads", "theme") is not None:
        return "leads", {"origin_module": "leads"}
    raise SystemExit("Segment (theme) has no definition — is this the ARK register?")


def leads(db, log: list[str]) -> None:
    """Own on Leads, after Segment; read through on Opportunities and Deals, after theirs."""
    scope, extra = lead_scope(db)
    definitions = [
        ensure_definition(db, scope, api_name, label, "picklist", picklist, description, log, origin="Release 1.2", **extra)
        for api_name, label, picklist, description in LEAD_FIELDS
    ]
    for module in ("leads", "opportunities", "deals"):
        segment = placement(db, module, "theme")
        if segment is None:
            raise SystemExit(f"{module}.theme (Segment) is not placed — is this the ARK register?")
        missing = [(d, f) for d, f in zip(definitions, LEAD_FIELDS) if placement(db, module, f[0]) is None]
        if not missing:
            continue
        make_room(db, module, segment.sort_order, len(missing))
        own = module == "leads"
        for offset, (d, (api_name, label, _, _)) in enumerate(missing, start=1):
            common = dict(
                definition_id=d.id,
                api_name=api_name,
                module_key=module,
                scope_key=segment.scope_key,
                section_id=segment.section_id,
                sort_order=segment.sort_order + offset,
                requirement="Optional",
                required_on_create=False,
                status="active",
            )
            if own:
                db.add(
                    FieldPlacement(
                        **common,
                        capture_stage=segment.capture_stage,
                        capture_any_stage=segment.capture_any_stage,
                        value_mode="own",
                        editable=True,
                        storage="custom_fields",
                        provenance="register",
                    )
                )
                log.append(f"leads.{api_name}: placed after Segment, Optional, one choice, values in custom_fields")
            else:
                db.add(
                    FieldPlacement(
                        **common,
                        storage=segment.storage,
                        provenance="read_through",
                        **{c: getattr(segment, c) for c in READ_THROUGH_COLUMNS},
                    )
                )
                log.append(f"{module}.{api_name}: shown From the Lead, after Segment")
    db.flush()


def accounts(db, log: list[str]) -> None:
    segments = placement(db, "accounts", "segments")
    if segments is None:
        raise SystemExit("accounts.segments (Segment) is not placed — run Release 1.1's scripts first")
    missing = [f for f in ACCOUNT_FIELDS if placement(db, "accounts", f[0]) is None]
    if not missing:
        return
    make_room(db, "accounts", segments.sort_order, len(missing))
    for offset, (api_name, label, picklist, description) in enumerate(missing, start=1):
        d = ensure_definition(
            db, "accounts", api_name, label, "multiselect", picklist, description, log,
            origin="Administration", origin_module="accounts",
        )
        db.add(
            FieldPlacement(
                definition_id=d.id,
                api_name=api_name,
                module_key="accounts",
                scope_key=segments.scope_key,
                section_id=segments.section_id,
                sort_order=segments.sort_order + offset,
                capture_stage=segments.capture_stage,
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
        log.append(f"accounts.{api_name}: placed after Segment, Optional, several choices, values in custom_fields")
    db.flush()


def maps(db, data: dict, log: list[str]) -> None:
    to_category = {(c["segment"], c["key"]) for c in data["categories"]}
    to_subsegment = {(s["category"], s["key"]) for s in data["subsegments"]}
    wanted = [
        ("leads", "theme", "segment_category", to_category),
        ("leads", "segment_category", "subsegment", to_subsegment),
        ("accounts", "segments", "segment_categories", to_category),
        ("accounts", "segment_categories", "subsegments", to_subsegment),
    ]
    for module, parent, child, pairs in wanted:
        dep = db.scalars(
            select(FieldDependency).where(FieldDependency.module_key == module).where(FieldDependency.child_field == child)
        ).first()
        if dep is None:
            dep = FieldDependency(module_key=module, parent_field=parent, child_field=child)
            db.add(dep)
            db.flush()
        elif dep.parent_field != parent:
            raise SystemExit(
                f"{module}.{child} already follows {dep.parent_field}, not {parent} — stop and look before changing a map."
            )
        have = {(v.parent_value, v.child_value) for v in dep.values}
        new = sorted(pairs - have)
        if not new:
            continue
        dep.values.extend(FieldDependencyValue(parent_value=p, child_value=c) for p, c in new)
        log.append(f"{module}: {parent} -> {child}, {len(new)} pairs added ({len(have) + len(new)} in all)")
    db.flush()


def segment_notes(db, data: dict) -> list[str]:
    """The workbook's Segments against ARK's list: all must exist; spelling differences are reported."""
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
        raise SystemExit(f"STOPPED: {DATA} is missing.")
    data = json.loads(DATA.read_text(encoding="utf-8"))
    with SessionLocal() as db:
        log: list[str] = []
        differences = segment_notes(db, data)
        ensure_list(db, CATEGORY_LIST, "Segment Category", data["categories"], log)
        ensure_list(db, SUBSEGMENT_LIST, "Subsegment", data["subsegments"], log)
        leads(db, log)
        accounts(db, log)
        maps(db, data, log)

        print(f"Release 1.2 market segments — {mode}")
        print("=" * 74)
        for line in log or ["nothing to do"]:
            print(f"  {line}")
        if differences:
            print("\nSegment is spelled differently in the workbook — the same choices, NOT renamed:")
            for line in differences:
                print(f"  {line}")
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
