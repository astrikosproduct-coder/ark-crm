"""
One-time bootstrap: frontend/spec/*.json -> the Round-6 metadata tables.

Run:  python bootstrap_metadata.py              # dry run, prints what it would write
      python bootstrap_metadata.py --apply
      python bootstrap_metadata.py --refresh-extensions --apply

THIS IS THE ONLY TIME JSON IS READ INTO THE DATABASE
-----------------------------------------------------
Round 6 makes PostgreSQL the source of truth for editable metadata. The spec
files become generated artifacts: regenerate_spec.py writes them, the frontend
reads them, and nothing reads them back in.

So this script exists to cross that line exactly once, and it refuses to cross
it twice. If field_metadata already holds rows, --apply stops. Re-running it
would silently overwrite whatever an admin had edited with whatever a developer
happened to have in their working copy of fields.json — which is precisely the
JSON -> PostgreSQL direction Round 6 does not support.

To move the register on after bootstrap, edit it in Administration and publish.
To move a WORKBOOK regenerate in — a genuinely new register from
build_spec.py — that is a data-migration task with its own diff and its own
review, not this script.

WHAT IT READS, AND WHAT IT DOES WITH EACH
------------------------------------------
  fields.json      566 register rows -> modules, sections, field_metadata
  picklists.json   107 picklists, 494 values -> picklists, picklist_values
  stages.json      10 stages -> stages
  extensions.json  the hand-maintained sidecar. Mirrored READ-ONLY onto
                   field_metadata.extension so the Administration screen can
                   warn that a field has a computed_expr or a child_spec
                   behind it. Never regenerated, never written back, and
                   deliberately NOT merged into the register columns: the
                   frontend merges the sidecar itself at load time, and doing
                   it here as well would give the same field two definitions.

                   extensions.json's `new_fields` rows are NOT imported. The
                   frontend appends them to the register list at load
                   (src/lib/spec/index.ts), so importing them here would make
                   every one of them appear twice.
"""

import json
import sys
from pathlib import Path

from sqlalchemy import func, select

from app.database import SessionLocal, engine
from app.metadata_spec import FIELD_JSON_KEYS, SPEC_DIR
from app.models import FieldMetadata, Module, Picklist, PicklistValue, Section, Stage

# app.database sets echo=True, which is useful when debugging a request
# and unreadable in a command-line script that writes 566 rows. The
# engine's own configuration is left alone; only this process is quiet.
# app.database creates the engine with echo=True, which is useful when
# debugging a request and unreadable in a script that writes 566 rows.
# echo is an engine flag that bypasses logger levels, so it is turned
# off on the object; this process only, the module is left alone.
engine.echo = False

# The register carries a module key, never a display name. These are the names
# the application already shows for the same keys — see MODULES in
# src/lib/modules.ts — so the Administration screen and the navigation agree.
# bids_pocs has no entry there because no screen is built for it yet.
MODULE_LABELS = {
    "accounts": "Accounts",
    "activities_docs": "Activities & Documents",
    "administration": "Administration",
    "bids_pocs": "Bids & POCs",
    "contacts": "Contacts",
    "deals": "Deals",
    "leads": "Leads",
    "partners": "Partners",
    "products": "Products",
    "quotes": "Quotes",
}


def load(name: str):
    return json.loads((SPEC_DIR / name).read_text(encoding="utf-8"))


def picklist_label(key: str) -> str:
    """
    `leads__deal_source` -> `Leads · Deal Source`.

    Not a register concept — picklists.json is a bare map. Derived once here so
    the Administration list reads as words rather than as keys, and editable
    afterwards like any other label.
    """
    parts = key.split("__")
    return " · ".join(part.replace("_", " ").title() for part in parts)


def sidecar_for(extensions: dict, module: str, section: str, api_name: str) -> dict | None:
    """
    This field's sidecar entry, if it has one.

    A sidecar key may be `module.api_name` or `module.section.api_name`. The
    qualified form wins, exactly as src/lib/spec/index.ts resolves it.
    """
    fields = extensions.get("fields", {})
    return fields.get(f"{module}.{section}.{api_name}") or fields.get(f"{module}.{api_name}")


def main(apply: bool, refresh_extensions: bool) -> None:
    fields = load("fields.json")
    picklists = load("picklists.json")
    stages = load("stages.json")
    extensions = load("extensions.json")

    db = SessionLocal()
    try:
        existing = db.scalar(select(func.count()).select_from(FieldMetadata)) or 0

        if refresh_extensions:
            _refresh_extensions(db, fields, extensions, apply)
            return

        if existing:
            print(
                f"REFUSED: field_metadata already holds {existing} rows.\n\n"
                "The bootstrap runs once. Re-running it would overwrite metadata that\n"
                "has since been edited in Administration with whatever is in this\n"
                "working copy of spec/fields.json — the JSON -> PostgreSQL direction\n"
                "Round 6 does not support.\n\n"
                "  To change the register:  edit it in Administration, then publish.\n"
                "  To refresh only the read-only sidecar mirror:\n"
                "      python bootstrap_metadata.py --refresh-extensions --apply"
            )
            sys.exit(1)

        # ------------------------------------------------ modules & sections
        # Register order, taken from first appearance. The register has no
        # module sheet and no section sheet; the order fields are written in
        # IS the order, because `order` is contiguous per section.
        module_keys: list[str] = []
        section_keys: list[tuple[str, str]] = []
        for row in fields:
            if row["module"] not in module_keys:
                module_keys.append(row["module"])
            key = (row["module"], row["section"])
            if key not in section_keys:
                section_keys.append(key)

        unlabelled = [m for m in module_keys if m not in MODULE_LABELS]
        if unlabelled:
            print(f"! no display label for module(s): {', '.join(unlabelled)} — using the key")

        print(f"modules          {len(module_keys)}")
        print(f"sections         {len(section_keys)}")
        print(f"picklists        {len(picklists)}")
        print(f"picklist values  {sum(len(v) for v in picklists.values())}")
        print(f"stages           {len(stages)}")
        print(f"fields           {len(fields)}")

        sidecar_hits = sum(
            1
            for row in fields
            if sidecar_for(extensions, row["module"], row["section"], row["api_name"])
        )
        print(f"sidecar mirrors  {sidecar_hits}")

        if not apply:
            print("\nDry run. Re-run with --apply.")
            return

        for index, module_key in enumerate(module_keys, start=1):
            db.add(
                Module(
                    module_key=module_key,
                    label=MODULE_LABELS.get(module_key, module_key),
                    sort_order=index,
                    active=True,
                )
            )

        section_ids: dict[tuple[str, str], Section] = {}
        per_module: dict[str, int] = {}
        for module_key, label in section_keys:
            per_module[module_key] = per_module.get(module_key, 0) + 1
            section = Section(
                module_key=module_key,
                label=label,
                sort_order=per_module[module_key],
                active=True,
            )
            db.add(section)
            section_ids[(module_key, label)] = section

        # ------------------------------------------------------- picklists
        # enumerate over the file's own key order: that is the register's
        # declaration order, and it is what keeps a regenerated picklists.json
        # diffing against the original instead of reshuffling all 107.
        for index, (key, options) in enumerate(picklists.items(), start=1):
            db.add(
                Picklist(
                    picklist_key=key,
                    label=picklist_label(key),
                    sort_order=index,
                    active=True,
                )
            )
            for option in options:
                db.add(
                    PicklistValue(
                        picklist_key=key,
                        key=option["key"],
                        label=option["label"],
                        sort_order=option["sort"],
                        active=option["active"],
                    )
                )

        # ---------------------------------------------------------- stages
        for row in stages:
            db.add(
                Stage(
                    stage=row["stage"],
                    name=row["name"],
                    progression_pct=row.get("progression_pct"),
                    probability_pct=row.get("probability_pct"),
                    owner_role=row["owner_role"],
                    bid_phase=row["bid_phase"],
                    applies_to=row["applies_to"],
                    sort_order=row["stage"],
                    active=True,
                )
            )

        # Sections and picklists have to exist before a field can point at them.
        db.flush()

        # ---------------------------------------------------------- fields
        for row in fields:
            values = {}
            for json_key, attr in FIELD_JSON_KEYS:
                if attr in ("module_key", "__section__"):
                    continue
                values[attr] = row[json_key]

            db.add(
                FieldMetadata(
                    module_key=row["module"],
                    section_id=section_ids[(row["module"], row["section"])].id,
                    status="active",
                    # Every register field has a typed column on its business
                    # table and keeps it. Set explicitly rather than left to the
                    # model default, which is 'custom_fields' — right for a
                    # field created in Administration, wrong for all 566 of
                    # these.
                    storage="column",
                    extension=sidecar_for(
                        extensions, row["module"], row["section"], row["api_name"]
                    ),
                    **values,
                )
            )

        db.commit()
        print("\nApplied.")
        print("Next:  python regenerate_spec.py --check")
    finally:
        db.close()


def _refresh_extensions(db, fields, extensions, apply: bool) -> None:
    """
    Re-read the sidecar onto field_metadata.extension and nothing else.

    Safe to run repeatedly: extension is a read-only mirror that no regenerate
    ever writes out, so refreshing it cannot overwrite an Administration edit.
    It exists because extensions.json is hand-maintained and moves independently
    of the database.
    """
    changed = 0
    rows = {(f.module_key, f.section.label, f.api_name): f for f in db.scalars(select(FieldMetadata))}

    for row in fields:
        field = rows.get((row["module"], row["section"], row["api_name"]))
        if field is None:
            continue
        sidecar = sidecar_for(extensions, row["module"], row["section"], row["api_name"])
        if field.extension != sidecar:
            changed += 1
            if apply:
                field.extension = sidecar

    if apply:
        db.commit()
        print(f"Applied. {changed} sidecar mirror(s) updated.")
    else:
        print(f"Dry run. {changed} sidecar mirror(s) would be updated. Re-run with --apply.")


if __name__ == "__main__":
    main(
        apply="--apply" in sys.argv,
        refresh_extensions="--refresh-extensions" in sys.argv,
    )
