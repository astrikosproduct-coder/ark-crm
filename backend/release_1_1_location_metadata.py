"""
Release 1.1, chunk C — Region -> Country -> State (decided 6 Oct 2026).

    python release_1_1_location_metadata.py            # dry run: validates, writes nothing
    python release_1_1_location_metadata.py --apply    # change the register, convert, publish

Run AFTER `alembic upgrade head` (r11_0001_location_fields adds the columns
and the two map tables) and AFTER release_1_1_fields_metadata.py, which adds
Europe to Region.

What it does, each step skipped when already done:

  1. Two lists from backend/data/locations.json: Country (249, keyed by the
     ISO code: IN, AE, US) and State (3,590 first-level states and provinces,
     keyed IN-MH, AE-DU).
  2. Accounts gain Country (required) and State (optional), after Region.
  3. Leads: Country becomes a dropdown; City / State becomes "City" (what was
     typed there is kept); a State dropdown sits between them. The order reads
     Destination Region, Country, State, City — on Opportunities and Deals too,
     where all four show "From the Lead". A Lead's State is required when its
     Country has states (app/field_dependencies.py), never otherwise.
  4. The maps, per module: Accounts Region -> Country -> State; Leads
     Destination Region -> Country -> State. Booking Region stays on its own:
     it says who books the revenue, not where the work is.
  5. Every Lead's free-text Country is converted to its ISO code where the
     text names one country ("UAE", "India", "Iran, Islamic Republic of").
     Anything else is LEFT AS TYPED and listed below the run, to fix by hand.
  6. Publish.

NO DDL. Run on development and on production.
"""

from __future__ import annotations

import json
import re
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
    Lead,
    Picklist,
    PicklistValue,
)
from app.routers.metadata import _publish, _validation_out, build_snapshot  # noqa: E402

DATA = Path(__file__).resolve().parent / "data" / "locations.json"

COUNTRIES = "countries"
STATES = "states"

NOTE = "Release 1.1: Region -> Country -> State on Accounts and Leads; Leads' Country is a dropdown, City / State is City"

#: What a person typed for a country that ISO spells differently.
ALIASES = {
    "uae": "AE", "u.a.e": "AE", "u.a.e.": "AE", "emirates": "AE", "dubai": "AE", "abu dhabi": "AE",
    "ksa": "SA", "k.s.a": "SA", "saudi": "SA", "kingdom of saudi arabia": "SA",
    "usa": "US", "u.s.a": "US", "u.s.a.": "US", "us": "US", "america": "US", "united states of america": "US",
    "uk": "GB", "u.k": "GB", "u.k.": "GB", "britain": "GB", "great britain": "GB", "england": "GB",
    "turkey": "TR", "russia": "RU", "vietnam": "VN", "korea": "KR", "south korea": "KR",
}

#: Copied from Country's placement onto the new State, so the two behave alike.
RULE_COLUMNS = (
    "capture_stage",
    "capture_any_stage",
    "mandatory_from",
    "blocks_transition",
    "required_on_skip",
    "visibility_condition",
    "condition",
    "value_mode",
    "value_locked",
    "editable",
    "stage_scoped",
)


def norm(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s.&-]", " ", text.lower())).strip()


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
        log.append(f"picklist {key}: created")
    existing = {v.key: v for v in picklist.values}
    added = changed = 0
    for i, row in enumerate(values, start=1):
        v = existing.get(row["key"])
        if v is None:
            db.add(PicklistValue(picklist_key=key, key=row["key"], label=row["label"], sort_order=i, active=True))
            added += 1
        elif (v.label, v.sort_order, v.active) != (row["label"], i, True):
            v.label, v.sort_order, v.active = row["label"], i, True
            changed += 1
    if added or changed:
        log.append(f"picklist {key}: {added} choices added, {changed} updated ({len(values)} in all)")
    db.flush()


def ensure_definition(db, scope: str, api_name: str, label: str, picklist: str, description: str, log: list[str]):
    d = definition(db, scope, api_name)
    if d is None:
        d = FieldDefinition(
            scope_key=scope,
            api_name=api_name,
            label=label,
            field_type="picklist",
            picklist_key=picklist,
            description=description,
            use_case="Release 1.1 (6 Oct 2026): Region -> Country -> State.",
            origin="Release 1.1",
            status="active",
        )
        db.add(d)
        db.flush()
        log.append(f"{scope}.{api_name}: definition created ({label}, picklist {picklist})")
    return d


def make_room(db, module: str, after_sort_order: int, by: int) -> None:
    for later in db.scalars(
        select(FieldPlacement).where(FieldPlacement.module_key == module).where(FieldPlacement.sort_order > after_sort_order)
    ):
        later.sort_order += by


def accounts(db, log: list[str]) -> None:
    region = placement(db, "accounts", "region")
    if region is None:
        raise SystemExit("accounts.region is not placed — is this the ARK register?")
    wanted = [
        ("country", "Country", COUNTRIES, "Mandatory",
         "Where this company is registered. Offers the countries of the Region chosen."),
        ("state", "State", STATES, "Optional",
         "The state, emirate or province it is registered in. Offers the states of the Country chosen."),
    ]
    missing = [w for w in wanted if placement(db, "accounts", w[0]) is None]
    if not missing:
        return
    make_room(db, "accounts", region.sort_order, len(wanted))
    for offset, (api_name, label, picklist, requirement, description) in enumerate(wanted, start=1):
        d = ensure_definition(db, "accounts", api_name, label, picklist, description, log)
        if placement(db, "accounts", api_name) is None:
            db.add(
                FieldPlacement(
                    definition_id=d.id,
                    api_name=api_name,
                    module_key="accounts",
                    scope_key=region.scope_key,
                    section_id=region.section_id,
                    sort_order=region.sort_order + offset,
                    requirement=requirement,
                    value_mode="own",
                    editable=True,
                    storage="column",
                    status="active",
                    provenance="register",
                )
            )
            log.append(f"accounts.{api_name}: placed after Region, {requirement}")
    db.flush()


def pipeline(db, log: list[str]) -> None:
    country = definition(db, "pipeline", "country")
    city = definition(db, "pipeline", "city_state")
    if country is None or city is None:
        raise SystemExit("pipeline.country / city_state are missing — is this the ARK register?")
    if (country.field_type, country.picklist_key) != ("picklist", COUNTRIES):
        log.append(f"pipeline.country: {country.field_type} -> picklist over '{COUNTRIES}'")
        country.field_type, country.picklist_key = "picklist", COUNTRIES
        country.description = "The country the work is delivered in. Offers the countries of the Destination Region."
    if city.label != "City":
        log.append(f"pipeline.city_state: label '{city.label}' -> 'City' (what was typed is kept)")
        city.label = "City"
        city.description = "The city the work is delivered in."

    state = ensure_definition(
        db, "pipeline", "state", "State", STATES,
        "The state, emirate or province the work is delivered in. Offers the states of the Country chosen.",
        log,
    )
    for module in ("leads", "opportunities", "deals"):
        if placement(db, module, "state") is not None:
            continue
        trio = [placement(db, module, n) for n in ("country", "city_state", "destination_region")]
        if None in trio:
            raise SystemExit(f"{module}: Country, City / State and Destination Region are not all placed")
        orders = sorted(p.sort_order for p in trio)
        base = orders[0]
        if orders != [base, base + 1, base + 2]:
            raise SystemExit(f"{module}: Country, City / State and Destination Region are not side by side ({orders})")
        make_room(db, module, base + 2, 1)
        country_p, city_p, region_p = trio
        region_p.sort_order, country_p.sort_order, city_p.sort_order = base, base + 1, base + 3
        own = module == "leads"
        db.add(
            FieldPlacement(
                definition_id=state.id,
                api_name="state",
                module_key=module,
                scope_key=country_p.scope_key,
                section_id=country_p.section_id,
                sort_order=base + 2,
                # Mandatory, but only ever demanded when the Country chosen has
                # states — app/field_dependencies.py::offers_choices.
                requirement="Mandatory" if own else country_p.requirement,
                storage="column" if own else country_p.storage,
                status="active",
                provenance="register",
                **{c: getattr(country_p, c) for c in RULE_COLUMNS},
            )
        )
        log.append(
            f"{module}.state: placed; order is now Destination Region, Country, State, City"
            + (" — Mandatory when the Country has states" if own else " — shown From the Lead")
        )
    db.flush()


def maps(db, data: dict, log: list[str]) -> None:
    region_keys = {v.key for v in db.get(Picklist, "region").values}
    missing = set(data["regions"]) - region_keys
    if missing:
        raise SystemExit(f"Region lacks {sorted(missing)} — run release_1_1_fields_metadata.py --apply first")
    region_map = {r: set(codes) for r, codes in data["regions"].items()}
    state_map = {c: {s["key"] for s in rows} for c, rows in data["states"].items()}
    wanted = [
        ("accounts", "region", "country", region_map),
        ("accounts", "country", "state", state_map),
        ("leads", "destination_region", "country", region_map),
        ("leads", "country", "state", state_map),
    ]
    for module, parent, child, mapping in wanted:
        dep = db.scalars(
            select(FieldDependency).where(FieldDependency.module_key == module).where(FieldDependency.child_field == child)
        ).first()
        pairs = {(p, c) for p, cs in mapping.items() for c in cs}
        if dep is None:
            dep = FieldDependency(module_key=module, parent_field=parent, child_field=child)
            db.add(dep)
            db.flush()
        elif dep.parent_field == parent and {(v.parent_value, v.child_value) for v in dep.values} == pairs:
            continue
        dep.parent_field = parent
        dep.values.clear()
        db.flush()
        dep.values.extend(FieldDependencyValue(parent_value=p, child_value=c) for p, c in sorted(pairs))
        log.append(f"{module}: {parent} -> {child}, {len(pairs)} pairs")
    db.flush()


def convert_leads(db, data: dict, log: list[str], unmatched: list[str]) -> None:
    known = {c["key"] for c in data["countries"]}
    names = {norm(c["label"]): c["key"] for c in data["countries"]}
    for code, others in data["aliases"].items():
        for other in others:
            names.setdefault(norm(other), code)
    for code in known:
        names.setdefault(code.lower(), code)
    for alias, code in ALIASES.items():
        names.setdefault(norm(alias), code)

    converted = 0
    for lead in db.scalars(select(Lead).where(Lead.country.is_not(None)).order_by(Lead.lead_id)):
        typed = (lead.country or "").strip()
        if not typed or typed in known:
            continue
        code = names.get(norm(typed))
        if code is None:
            unmatched.append(f"{lead.lead_id} · {lead.opportunity_name}: Country '{typed}'")
            continue
        lead.country = code
        converted += 1
    if converted:
        log.append(f"leads: {converted} free-text Countries converted to their ISO code")
    db.flush()


def main() -> int:
    mode = "apply" if "--apply" in sys.argv else "dry"
    data = json.loads(DATA.read_text(encoding="utf-8"))
    states = [s for rows in data["states"].values() for s in rows]
    with SessionLocal() as db:
        log: list[str] = []
        unmatched: list[str] = []
        ensure_list(db, COUNTRIES, "Country", data["countries"], log)
        ensure_list(db, STATES, "State", sorted(states, key=lambda s: (s["key"].split("-")[0], s["label"])), log)
        accounts(db, log)
        pipeline(db, log)
        maps(db, data, log)
        convert_leads(db, data, log, unmatched)

        print(f"Release 1.1 locations — {mode}")
        print("=" * 74)
        for line in log or ["nothing to do"]:
            print(f"  {line}")
        if unmatched:
            print(f"\n{len(unmatched)} Lead(s) keep a Country that names no single country — fix by hand:")
            for line in unmatched:
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
