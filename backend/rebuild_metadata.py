"""
Round 7 — rebuild the metadata tables into the field placement model.

    python rebuild_metadata.py             dry run: report, write nothing
    python rebuild_metadata.py --apply     write field_definitions + field_placements

Reads the CURRENT FRONTEND-EFFECTIVE PRESENTATION and turns it into rows:

    spec/fields.json + extensions.json + module_split.json
                    |
                    |  the legacy split, replayed ONCE  (_legacy section below)
                    v
    field_definitions   one row per concept   (577)
    field_placements    one row per concept-on-a-module   (673)

WHY THE FRONTEND IS THE SOURCE AND NOT field_metadata.module_key
-----------------------------------------------------------------
Because module_key is the thing being replaced. It records which sheet of the
workbook a row was typed on, and the register files the whole Stage 0-7
pipeline on the `leads` sheet — so it says Opportunities has 0 fields while the
CRM renders 105. What the user sees is the only defensible source for what the
user should be able to administer, so that is what this reads.

THIS FILE IS A ONE-SHOT MIGRATION TOOL. IT IS NOT A RESOLVER.
--------------------------------------------------------------
The `_legacy_*` functions below are a faithful port of
src/lib/spec/moduleSplit.ts. They exist to turn a projection into data exactly
once. NOTHING IN app/ MAY IMPORT THIS MODULE — that would be the second
implementation of one projection rule that the brief forbids, and the two would
drift the first time either changed. app/metadata_resolver.py is the single
authoritative resolution model, and it does no projection at all: it reads
placement rows.

test_placements.py asserts that no module under app/ imports this file.

WHAT IT WILL NOT DO
-------------------
No DDL. No write to any business table. No change to picklists, picklist_values
or stages. field_metadata is read and left exactly as it is — migration 0008
already archived it to field_metadata_pre_round7, and it is retired in a later
migration only once parity has been proved.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from sqlalchemy import select, text

from app.database import SessionLocal, engine

engine.echo = False

from app.models import (  # noqa: E402
    FieldDefinition,
    FieldMetadata,
    FieldPlacement,
    Module,
    Section,
)

SPEC_DIR = Path(__file__).resolve().parent.parent / "frontend" / "spec"


def load(name: str) -> Any:
    return json.loads((SPEC_DIR / name).read_text(encoding="utf-8"))


# =========================================================================
# D1 / D3 — THE CARRY-FORWARD SET
# =========================================================================
#
# The only placements in the system whose value is seeded from their parent and
# then owned. Listed by name rather than derived, because "which values a Deal
# inherits from its Opportunity" is a commercial decision and deriving it from
# a name collision would make it an accident.
#
# D1  Deal money fields. The Opportunity owns its number; the Deal opens with
#     that number and may renegotiate it. Before this, the register carried two
#     unrelated rows (leads Stage 4 and deals Stage 7) and the Deal simply
#     started empty, with nothing recording that the two were the same figure.
#
# D3  end_client and customer_partner_si. The Deal owns its own value and MUST
#     be able to diverge — a Deal can be booked against a different contracting
#     entity than the pursuit was run against. They are NOT read-through on
#     Deals. Note the asymmetry with Opportunities, which DOES read these
#     through: an Opportunity is the same pursuit as its Lead, a Deal is a
#     signed contract and is allowed to differ.
#
# value_locked is false for every one of them: carried, then freely editable.
CARRY_FORWARD: dict[str, dict[str, str]] = {
    "deals": {
        # --- D1
        "one_time_revenue": "D1 money field — Deal opens at the Opportunity's figure, may renegotiate",
        "arr_annual_recurring": "D1 money field",
        "3rd_party_one_time": "D1 money field",
        "3rd_party_recurring_per_year": "D1 money field",
        "contract_years": "D1 money field",
        # --- D3
        "end_client": "D3 — Deal owns its own value, seeded from the Opportunity, may diverge",
        "customer_partner_si": "D3 — same rule as end_client",
    }
}


# =========================================================================
# DUPLICATE-DEFINITION RESOLUTION
# =========================================================================
#
# 17 source rows collapse into 13 concepts. Twelve of the thirteen agree
# exactly on type, picklist and lookup target, so merging them is mechanical.
# One does not, and it is resolved here by name rather than by a rule, because
# a rule that silently picks a winner is how a register conflict becomes a
# quiet data-shape change.
#
# Any conflicting group NOT listed here aborts the rebuild.
CONFLICT_RESOLUTION: dict[tuple[str, str], dict[str, Any]] = {
    # D4. Two sheets carry progression_pct as `computed`/`Computed`; the
    # HEADER row carries it as `number`/`Optional`. The field was made
    # editable on 02 Sep 2026 — its own use_case records the change — so the
    # computed rows are stale. Number wins, and nothing derives it from stage.
    ("pipeline", "progression_pct"): {
        "field_type": "number",
        "computed_formula": None,
        "why": "D4 — editable Number since 02 Sep 2026; the `computed` rows are stale",
    }
}

# D4, the placement half.
#
# The `type` and `computed_formula` fix above is a DEFINITION change and lands
# on all three placements at once. `requirement` is a PLACEMENT column, so the
# stale Deals row would otherwise keep requirement='Computed' on a field that
# is no longer computed anywhere — residual computed-ness on one module, and
# exactly the kind of half-applied decision this model exists to make visible.
#
# It changes no rendering (editability is decided by `type`; see DERIVED in
# src/components/form/FieldControl.tsx) and one validation rule: a 'Computed'
# field is skipped by the mandatory check. Optional is skipped too, so the
# behaviour is identical and the row now says what it means.
PLACEMENT_OVERRIDES: dict[tuple[str, str], dict[str, Any]] = {
    ("deals", "progression_pct"): {
        "requirement": "Optional",
        "why": "D4 - matches the Leads and Opportunities placements; the field is not computed",
    }
}

# Columns that must agree across the rows of one concept, because they describe
# the SHAPE of the value. A disagreement here means the same column would hold
# two different kinds of thing, so it is an error rather than something to pick.
SHAPE_KEYS = ("field_type", "picklist_key", "lookup_target", "max_length")


# =========================================================================
# _legacy — THE PROJECTION, REPLAYED ONCE
# =========================================================================
#
# A port of src/lib/spec/moduleSplit.ts::applyModuleSplit, faithful to the
# point of reproducing its ordering. Everything below runs once, produces
# rows, and is then dead. Do not import it from app/.
#
# The sidecar merge that index.ts performs BEFORE the split is deliberately not
# replayed: every key spec/extensions.json can override (type_override,
# label_override, computed_expr, child_spec, ...) is read after placement is
# decided. None of them touch module, section, capture_stage or order, so the
# split lands identically with or without them, and leaving them out keeps this
# port to the one thing it is for.


def _legacy_effective_rows() -> list[dict[str, Any]]:
    """Every field the CRM renders today, as (module, section, order, ...)."""
    register = load("fields.json")
    extensions = load("extensions.json")
    split = load("module_split.json")

    new_fields = extensions.get("new_fields", [])
    new_qrefs = {
        f"{f['module']}.{f['section']}.{f['api_name']}" for f in new_fields
    }
    merged = [dict(f) for f in register] + [dict(f) for f in new_fields]

    pipeline: list[str] = split["pipeline"]
    shared_sections: list[str] = split["shared"]["sections"]
    own_fields: dict[str, Any] = split["own"]["fields"]
    read_through: list[str] = split["read_through"]["fields"]
    relocated = {
        k: v
        for k, v in (split.get("relocated_fields") or {}).items()
        if not k.startswith("$")
    }

    def is_shared_section(section: str) -> bool:
        upper = (section or "").upper()
        return any(upper.startswith(s) for s in shared_sections)

    def ref_of(f: dict) -> str:
        return f"{f['module']}.{f['api_name']}"

    def placements_for(f: dict, is_new: bool) -> list[tuple[str, str]]:
        home = f["module"]
        if is_new:
            return [(home, "new")]
        reassign = split["reassign"].get(home)
        if not reassign:
            return [(home, "own")]
        if is_shared_section(f.get("section", "")):
            return [(m, "own" if m == home else "shared") for m in pipeline]
        own = own_fields.get(f["api_name"])
        if own:
            excluded = set(own.get("exclude") or [])
            return [
                (m, "own" if m == home else "own_instance")
                for m in pipeline
                if m not in excluded
            ]
        rel = relocated.get(ref_of(f))
        stage = rel["capture_stage"] if rel else f.get("capture_stage")
        target = reassign.get(str(stage)) if stage is not None else None
        if target:
            return [(target, "moved")]
        return [(home, "own")]

    out: list[dict[str, Any]] = []

    for f in merged:
        rel = relocated.get(ref_of(f))
        is_new = f"{f['module']}.{f['section']}.{f['api_name']}" in new_qrefs
        for module, carry in placements_for(f, is_new):
            section = (
                split["own"]["section"]
                if carry == "own_instance"
                else (rel["section"] if rel else f["section"])
            )
            relabel = (own_fields.get(f["api_name"]) or {}).get("relabel", {}).get(module)
            row = dict(f)
            row.update(
                module=module,
                section=section,
                label=relabel or f["label"],
                carry=carry,
                register_module=f["module"],
                register_order=f["order"],
                label_override=relabel,
                read_through_from=None,
                read_through_via=None,
            )
            if rel:
                row["capture_stage"] = rel["capture_stage"]
                if "mandatory_from" in rel:
                    row["mandatory_from"] = rel["mandatory_from"]
                if "blocks_transition" in rel:
                    row["blocks_transition"] = rel["blocks_transition"]
            out.append(row)

    # ---- read-through rows, added LAST so a module that declares the field
    # ---- itself keeps its own (Deals declares end_client and
    # ---- customer_partner_si, so it takes 24 of the 26 rather than all).
    source = split["read_through"]["source_module"]
    rt_section = split["read_through"]["section"]
    skip_declared = split["read_through"]["skip_when_declared"]
    for module in pipeline:
        if module == source:
            continue
        parent = split["read_through"]["parent_of"].get(module)
        via = split["read_through"]["parent_link"].get(module)
        declared = {r["api_name"] for r in out if r["module"] == module}
        for api_name in read_through:
            if skip_declared and api_name in declared:
                continue
            src = next(
                (
                    f
                    for f in merged
                    if f["module"] == source and f["api_name"] == api_name
                ),
                None,
            )
            if src is None:
                raise SystemExit(
                    f"module_split.json read_through names {api_name!r}, "
                    f"which {source!r} does not declare."
                )
            row = dict(src)
            row.update(
                module=module,
                section=rt_section,
                carry="read_through",
                register_module=src["module"],
                register_order=src["order"],
                label_override=None,
                read_through_from=parent,
                read_through_via=via,
            )
            out.append(row)

    _legacy_renumber(out, split, pipeline)
    return out


def _legacy_renumber(
    rows: list[dict[str, Any]], split: dict, pipeline: list[str]
) -> None:
    """
    Reproduce moduleSplit.ts's per-module section ordering and renumbering.

    Register order is preserved WITHIN a section; only the sequence of sections
    is decided here, and only for the three pipeline modules. Every other module
    keeps the register's own numbering untouched.
    """
    order_cfg = split["section_order"]

    def section_rank(first: dict) -> int:
        section = (first.get("section") or "").upper()
        if section.startswith("HEADER"):
            return order_cfg["HEADER"]
        if section.startswith("RECORD STATE"):
            return order_cfg["RECORD STATE"]
        if section.startswith("READ THROUGH"):
            return order_cfg["READ THROUGH THE PARENT"]
        if section.startswith("CROSS-CUTTING"):
            return order_cfg["CROSS-CUTTING"]
        if section.startswith("SYSTEM"):
            return order_cfg["SYSTEM"]
        if first.get("capture_stage") is not None:
            return order_cfg["stage_offset"] + first["capture_stage"]
        return order_cfg["unstaged"]

    for module in pipeline:
        module_rows = [r for r in rows if r["module"] == module]
        sections: dict[str, list[dict]] = {}
        for r in module_rows:
            sections.setdefault(r["section"], []).append(r)

        # Two sections may share a rank — ON CONVERSION and STAGE 7 — CLOSE
        # both sit at Stage 7 on Deals. The one the register numbered lower
        # goes first. Python's sort is stable, as JavaScript's is.
        ordered = sorted(
            sections.items(),
            key=lambda kv: (
                section_rank(kv[1][0]),
                min(r.get("register_order", r["order"]) for r in kv[1]),
            ),
        )
        n = 0
        for _, group in ordered:
            group.sort(key=lambda r: r.get("register_order", r["order"]))
            for r in group:
                n += 1
                r["order"] = n


# =========================================================================
# scope keys
# =========================================================================

PIPELINE_SCOPE = "pipeline"


def _slug(label: str) -> str:
    """A section label reduced to something usable inside a scope key."""
    s = re.sub(r"[^a-z0-9]+", "_", (label or "").lower()).strip("_")
    return s[:80] or "section"


def compute_scopes(
    rows: list[dict[str, Any]], pipeline: set[str]
) -> dict[tuple[str, str, str], str]:
    """
    The record shape each (module, section, api_name) belongs to.

    Almost always the module itself. The exception is the ten api_names defined
    in two or three sections of ONE module — `bids_pocs.status`,
    `activities_docs.related_to`, `products.sort_order` and the rest. Every one
    of them is a child ENTITY modelled as a section (`GATE CHECKLIST ITEM`,
    `TBE QUERY`, `DEPLOYMENT SIZE`), so they are real data rather than register
    errors, and uniqueness has to be expressible over them.

    Only fields actually involved in a collision get a section-scoped key. A
    child-entity field whose name happens not to clash keeps the plain module
    scope, because the scope exists to make the constraint writable, not to
    model child entities — which stays pre-existing debt, out of scope here.
    """
    by_name: dict[tuple[str, str], set[str]] = defaultdict(set)
    for r in rows:
        by_name[(r["module"], r["api_name"])].add(r["section"])

    scopes: dict[tuple[str, str, str], str] = {}
    for r in rows:
        module, api_name, section = r["module"], r["api_name"], r["section"]
        if len(by_name[(module, api_name)]) > 1:
            scopes[(module, section, api_name)] = f"{module}__{_slug(section)}"
        else:
            scopes[(module, section, api_name)] = module

    # A collision inside a pipeline module would mean one concept could not be
    # shared across the three, and the 'pipeline' definition scope would be
    # wrong. Verified absent today; asserted so a later change cannot introduce
    # one silently.
    bad = [
        (m, a)
        for (m, a), secs in by_name.items()
        if m in pipeline and len(secs) > 1
    ]
    if bad:
        raise SystemExit(
            "Pipeline modules must not define one api_name in two sections; "
            f"found {bad}. The 'pipeline' definition scope cannot hold them."
        )
    return scopes


def definition_scope(placement_scope: str, module: str, pipeline: set[str]) -> str:
    """
    The namespace a DEFINITION is unique in.

    'pipeline' for Leads/Opportunities/Deals, which is exactly what makes
    One-Time Revenue one row instead of two. Otherwise the placement's own
    record shape.
    """
    return PIPELINE_SCOPE if module in pipeline else placement_scope


# =========================================================================
# rebuild
# =========================================================================

FROM_ROW = {
    "field_type": "type",
    "max_length": "max_length",
    "picklist_key": "picklist",
    "lookup_target": "lookup_target",
    "lookup_filter": "lookup_filter",
    "computed_formula": "computed_formula",
    "values_note": "values_note",
    "description": "description",
    "use_case": "use_case",
    "origin": "origin",
    "source_ref": "source_ref",
}

PROVENANCE = {
    "own": "register",
    "moved": "reassigned_by_stage",
    "shared": "shared_section",
    "own_instance": "own_instance",
    "read_through": "read_through",
    "new": "new_fields",
}


def main(apply: bool) -> int:
    rows = _legacy_effective_rows()
    db = SessionLocal()
    try:
        pipeline = {
            m.module_key
            for m in db.scalars(select(Module).where(Module.is_pipeline.is_(True)))
        }
        module_keys = {m.module_key for m in db.scalars(select(Module))}

        unknown = {r["module"] for r in rows} - module_keys
        if unknown:
            raise SystemExit(f"Effective presentation names unknown modules: {unknown}")

        scopes = compute_scopes(rows, pipeline)

        # ---- the storage mode and the extension mirror come from the register
        # ---- rows themselves; a field the admin created is custom-stored and
        # ---- must stay that way. Keyed on the register qref, which is what
        # ---- field_metadata is unique on.
        legacy: dict[tuple[str, str, str], FieldMetadata] = {}
        section_label = {s.id: s.label for s in db.scalars(select(Section))}
        for f in db.scalars(select(FieldMetadata)):
            legacy[(f.module_key, section_label[f.section_id], f.api_name)] = f

        # ============================================ 1. definitions
        groups: dict[tuple[str, str], list[dict]] = defaultdict(list)
        for r in rows:
            scope = definition_scope(
                scopes[(r["module"], r["section"], r["api_name"])],
                r["module"],
                pipeline,
            )
            groups[(scope, r["api_name"])].append(r)

        conflicts: list[str] = []
        definitions: dict[tuple[str, str], dict[str, Any]] = {}

        for key, members in sorted(groups.items()):
            scope, api_name = key
            resolution = CONFLICT_RESOLUTION.get(key, {})

            values: dict[str, Any] = {}
            for attr, json_key in FROM_ROW.items():
                seen = {r.get(json_key) for r in members}
                if attr in resolution:
                    values[attr] = resolution[attr]
                    continue
                if len(seen) == 1:
                    values[attr] = seen.pop()
                    continue
                if attr in SHAPE_KEYS:
                    conflicts.append(
                        f"{scope}.{api_name}: {attr} disagrees {sorted(map(str, seen))} "
                        f"across {sorted({r['register_module'] for r in members})}"
                    )
                    values[attr] = members[0].get(json_key)
                else:
                    # Documentation and provenance may legitimately differ
                    # between two sheets describing one concept. The longest
                    # answer is the one that says the most; picking it is a
                    # presentation choice, not a data-shape decision.
                    values[attr] = max(
                        (r.get(json_key) for r in members),
                        key=lambda v: len(str(v or "")),
                    )

            # A relabelled placement must not decide the canonical label —
            # project_stage is "Lead Stage" in the register and "Opportunity
            # Stage" only on one module, which is a placement override.
            base_labels = {r["label"] for r in members if not r.get("label_override")}
            values["label"] = (
                sorted(base_labels)[0] if base_labels else members[0]["label"]
            )

            origin_modules = {r["register_module"] for r in members}
            values["origin_module"] = (
                members[0]["register_module"]
                if len(origin_modules) == 1
                else sorted(origin_modules)[0]
            )

            src = next(
                (
                    legacy.get((r["register_module"], r["section"], r["api_name"]))
                    for r in members
                    if legacy.get((r["register_module"], r["section"], r["api_name"]))
                ),
                None,
            )
            values["extension"] = src.extension if src is not None else None

            definitions[key] = values

        if conflicts:
            print("REFUSING TO REBUILD — unresolved shape conflicts:\n")
            for c in conflicts:
                print("   ", c)
            print(
                "\nAdd each to CONFLICT_RESOLUTION with an explicit decision, "
                "or fix the register. A shape conflict means one column would "
                "hold two kinds of value; it is not something to guess."
            )
            return 1

        # ============================================ 2. sections
        #
        # The split puts fields into sections that do not exist yet —
        # opportunities has no section rows at all, and HEADER / __header live
        # only in extensions.json. They are created here in the order the
        # effective presentation puts them, so a module's form reads top to
        # bottom the way it renders.
        wanted: dict[str, list[str]] = {}
        for r in sorted(rows, key=lambda r: (r["module"], r["order"])):
            wanted.setdefault(r["module"], [])
            if r["section"] not in wanted[r["module"]]:
                wanted[r["module"]].append(r["section"])

        existing = {
            (s.module_key, s.label): s for s in db.scalars(select(Section))
        }
        created_sections = 0
        for module, labels in wanted.items():
            for i, label in enumerate(labels, start=1):
                section = existing.get((module, label))
                if section is None:
                    section = Section(
                        module_key=module, label=label, sort_order=i, active=True
                    )
                    db.add(section)
                    existing[(module, label)] = section
                    created_sections += 1
                elif module in pipeline and section.sort_order != i:
                    # Only the pipeline modules are re-sequenced, exactly as
                    # moduleSplit.ts only renumbered those three.
                    section.sort_order = i
        if apply:
            db.flush()

        # ============================================ 3. write
        counts = Counter()
        carry_applied: list[str] = []
        storage_claims: list[tuple[str, str, str]] = []

        if apply:
            db.query(FieldPlacement).delete()
            db.query(FieldDefinition).delete()
            db.flush()

        def_rows: dict[tuple[str, str], FieldDefinition] = {}
        for key, values in sorted(definitions.items()):
            scope, api_name = key
            row = FieldDefinition(scope_key=scope, api_name=api_name, **values)
            def_rows[key] = row
            if apply:
                db.add(row)
        if apply:
            db.flush()

        for r in sorted(rows, key=lambda r: (r["module"], r["order"])):
            module, api_name, section = r["module"], r["api_name"], r["section"]
            placement_scope = scopes[(module, section, api_name)]
            key = (definition_scope(placement_scope, module, pipeline), api_name)

            src = legacy.get((r["register_module"], r["section"], api_name)) or legacy.get(
                (r["register_module"], r["section"], api_name)
            )
            storage = src.storage if src is not None else "column"

            carry = r["carry"]
            if carry == "read_through":
                value_mode, editable, store = "read_through", False, None
            elif api_name in CARRY_FORWARD.get(module, {}):
                value_mode, editable, store = "carry_forward", True, storage
                carry_applied.append(f"{module}.{api_name}")
            else:
                value_mode, editable, store = "own", True, storage

            if store == "column":
                storage_claims.append((module, api_name, section))

            placement = FieldPlacement(
                definition_id=def_rows[key].id if apply else 0,
                api_name=api_name,
                module_key=module,
                scope_key=placement_scope,
                section_id=existing[(module, section)].id if apply else 0,
                sort_order=r["order"],
                label_override=r.get("label_override"),
                capture_stage=r.get("capture_stage"),
                capture_any_stage=bool(r.get("capture_any_stage")),
                mandatory_from=r.get("mandatory_from"),
                blocks_transition=r.get("blocks_transition"),
                requirement=PLACEMENT_OVERRIDES.get((module, api_name), {}).get(
                    "requirement", r["requirement"]
                ),
                required_on_skip=r.get("required_on_skip"),
                visibility_condition=r.get("visibility_condition"),
                condition=r.get("condition"),
                value_mode=value_mode,
                value_locked=False,
                editable=editable,
                storage=store,
                status="active",
                provenance=PROVENANCE.get(carry, "register"),
            )
            if apply:
                db.add(placement)
            counts[(module, value_mode)] += 1
            counts[module] += 1

        # ---- deleted register rows keep a deleted definition AND a deleted
        # ---- placement, so a restore has somewhere to come back to. They are
        # ---- absent from the effective presentation by definition, which is
        # ---- why they are added here rather than in the loop above.
        deleted_added = 0
        for f in db.scalars(select(FieldMetadata).where(FieldMetadata.status == "deleted")):
            label = section_label[f.section_id]
            module = f.module_key
            scope = definition_scope(module, module, pipeline)
            key = (scope, f.api_name)
            if key in def_rows:
                # The name is live somewhere else; the deleted row is that same
                # concept, so only the placement is deleted, not the definition.
                continue
            definition = FieldDefinition(
                scope_key=scope,
                api_name=f.api_name,
                label=f.label,
                field_type=f.field_type,
                max_length=f.max_length,
                picklist_key=f.picklist_key,
                lookup_target=f.lookup_target,
                lookup_filter=f.lookup_filter,
                computed_formula=f.computed_formula,
                values_note=f.values_note,
                description=f.description,
                use_case=f.use_case,
                origin=f.origin,
                source_ref=f.source_ref,
                origin_module=module,
                status="deleted",
                deleted_at=f.deleted_at,
                deleted_by=f.deleted_by,
                extension=f.extension,
            )
            if apply:
                db.add(definition)
                db.flush()
            section = existing.get((module, label))
            if section is None:
                continue
            placement = FieldPlacement(
                definition_id=definition.id if apply else 0,
                api_name=f.api_name,
                module_key=module,
                scope_key=module,
                section_id=section.id if apply else 0,
                sort_order=f.sort_order,
                capture_stage=f.capture_stage,
                capture_any_stage=f.capture_any_stage,
                mandatory_from=f.mandatory_from,
                blocks_transition=f.blocks_transition,
                requirement=f.requirement,
                required_on_skip=f.required_on_skip,
                visibility_condition=f.visibility_condition,
                condition=f.condition,
                value_mode="own",
                editable=True,
                storage=f.storage,
                status="deleted",
                deleted_at=f.deleted_at,
                deleted_by=f.deleted_by,
                # deleted on its own, NOT by a definition cascade — a later
                # definition restore must not resurrect it.
                deleted_by_cascade=False,
                provenance="register",
            )
            if apply:
                db.add(placement)
            deleted_added += 1

        if apply:
            db.commit()

        # ============================================ 4. report
        print(f"{'APPLIED' if apply else 'DRY RUN — nothing written'}\n")
        print(f"  source rows (effective presentation)   {len(rows)}")
        print(f"  canonical field_definitions            {len(definitions)}")
        print(f"  field_placements                       {len(rows)}")
        print(f"  deleted definitions carried            {deleted_added}")
        print(f"  sections created                       {created_sections}")
        multi = sum(1 for m in groups.values() if len({r['module'] for r in m}) > 1)
        print(f"  definitions with >1 placement          {multi}")
        print()
        print("  placements per module:")
        for module in sorted(
            {r["module"] for r in rows}, key=lambda m: -counts[m]
        ):
            modes = {
                mode: counts[(module, mode)]
                for mode in ("own", "read_through", "carry_forward")
                if counts[(module, mode)]
            }
            print(f"    {module:20} {counts[module]:4}   {modes}")
        print()
        print(f"  placement overrides applied ({len(PLACEMENT_OVERRIDES)}):")
        for (module, api), spec in PLACEMENT_OVERRIDES.items():
            changed = {k: v for k, v in spec.items() if k != "why"}
            print(f"    {module}.{api:26} {changed}")
        print()
        print(f"  carry_forward placements ({len(carry_applied)}):")
        for name in carry_applied:
            module, api = name.split(".", 1)
            print(f"    {name:44} {CARRY_FORWARD[module][api]}")

        _report_storage(db, storage_claims)
        return 0
    finally:
        db.close()


def _report_storage(db, claims: list[tuple[str, str, str]]) -> None:
    """
    Which placements claim a typed column their business table does not have.

    Reported, never fixed: creating the column would be exactly the dynamic DDL
    the architecture forbids, and silently switching the placement to
    custom_fields would move real business data's home without being asked.
    A claim listed here is a Round-7 business-table gap, not a metadata bug.
    """
    tables = {}
    for module, _, _ in claims:
        if module in tables:
            continue
        rows = db.execute(
            text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = :t"
            ),
            {"t": module},
        )
        tables[module] = {r[0] for r in rows}

    missing = [
        (module, api) for module, api, _ in claims if tables.get(module) and api not in tables[module]
    ]
    print()
    if not missing:
        print("  storage='column': every claim backed by a real column.")
        return
    by_module = Counter(m for m, _ in missing)
    print(
        f"  storage='column' with NO column on the business table: {len(missing)}"
    )
    for module, n in by_module.most_common():
        sample = [a for m, a in missing if m == module][:4]
        print(f"    {module:20} {n:4}   e.g. {', '.join(sample)}")
    print(
        "    ^ pre-existing Round-7 business-table gap, reported not fixed:\n"
        "      adding the columns would be dynamic DDL, and switching them to\n"
        "      custom_fields would relocate business data without being asked."
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply", action="store_true", help="write the rows (default: dry run)"
    )
    sys.exit(main(parser.parse_args().apply))
