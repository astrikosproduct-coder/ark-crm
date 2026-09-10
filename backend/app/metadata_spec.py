"""
The metadata layer's one description of what the register looks like on disk.

Four things live here, and they live together because they are four views of
one contract and drift the moment they are separated:

    1. FIELD_JSON_KEYS   the register's 24 columns, and which model attribute
                         each one comes from
    2. build_snapshot    the live draft, as one self-contained document
    3. spec_documents    that snapshot, rendered as the three spec/*.json
                         files the frontend consumes
    4. validate          what has to be true before a snapshot may be published

The bootstrap, the regenerator, the publish endpoint and the parity check all
go through these, so none of them can disagree about what a field row is.

DIRECTION OF TRUTH
------------------
    PostgreSQL -> spec/*.json          supported, and the only supported way
    spec/*.json -> PostgreSQL          NOT supported

bootstrap_metadata.py reads the JSON exactly once, to get the register into
the database. After that the files are GENERATED ARTIFACTS: a hand-edit is a
local change with no path back, and the next publish overwrites it. Nothing in
this module reads a spec file except read_spec_documents(), which exists to
COMPARE — never to import.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from .metadata_resolver import (
    FIELD_JSON_KEYS,
    RESOLVED_KEYS,
    field_row,
    resolved_fields,
)
from .models import (
    FieldDefinition,
    FieldPlacement,
    Module,
    Picklist,
    PicklistValue,
    Section,
    Stage,
)

# backend/app/metadata_spec.py -> backend/app -> backend -> ARKcrm
SPEC_DIR = Path(__file__).resolve().parent.parent.parent / "frontend" / "spec"

FIELDS_JSON = "fields.json"
PICKLISTS_JSON = "picklists.json"
STAGES_JSON = "stages.json"


# ---------------------------------------------------------------- shape

# The register's own columns, in the order build_spec.py writes them, paired
# with the model attribute each is stored in. Two names differ, and only two:
# `type` shadows a Python builtin and `order` is a reserved word in SQL, so
# the columns are field_type and sort_order. Every other name is identical on
# both sides, which is what keeps a regenerated file indistinguishable from a
# workbook-generated one.
#
# Do not add to this tuple. It is RawFieldSpec in src/types/field.ts, whose own
# comment says the same thing: a key here that the frontend does not know about
# is a key nothing reads.
# The register's 24 keys and the 7 resolved ones both live in
# app/metadata_resolver.py, imported above. They are defined THERE and not here
# because the resolver is what produces a field row now; this module only
# renders and validates what it is handed.
#
# `module`, `section` and `order` come from the PLACEMENT. That is the whole
# change: one_time_revenue is `STAGE 4 — RFP / RFI` on Opportunities and `ON
# CONVERSION` on Deals, and there was never one answer for it to have.

# The snapshot schema. Bumped when the shape of a snapshot changes in a way an
# older restore_snapshot could not read.
#
#   1  field_metadata rows, one per register row, keyed on module_key
#   2  placement rows, one per module a field appears on   (Round 7)
#
# A version-1 snapshot is READABLE — it is a published historical fact and it
# stays queryable — but it is NOT restorable, and restore_snapshot refuses it
# by name rather than half-applying it. See the archive tables migration 0008
# wrote for the pre-Round-7 state.
SNAPSHOT_SCHEMA_VERSION = 2


# The field types the frontend's FieldType union accepts. A type outside this
# set renders as a plain text box with no warning, so publish refuses it.
FIELD_TYPES = frozenset(
    {
        "autonumber",
        "text",
        "lookup",
        "picklist",
        "number",
        "date",
        "currency",
        "checkbox",
        "computed",
        "richtext",
        "childlist",
        "longtext",
        "multiselect",
        "file",
        "datetime",
        "percent",
        "url",
        "email",
    }
)

# The Requirement union, same file. `Mandatory` and `Optional` are the two the
# Administration screen's Required toggle moves between; the other four are
# set explicitly and are never demanded of a user — see requirementOf() in
# src/lib/spec/conditions.ts.
REQUIREMENTS = ("Mandatory", "Conditional", "Optional", "Advisory", "System", "Computed")

# Types whose values come from a picklist rather than being typed in.
PICKLIST_TYPES = frozenset({"picklist", "multiselect"})

FIELD_STATUSES = ("active", "deleted")


STAGE_SECTION_LABEL = re.compile(r"^STAGE (\d+)")


def _stage_of_section_label(label: str) -> int | None:
    """
    The stage number a section name declares, or None.

    `STAGE 4 — RFP / RFI` yields 4. `STAGE DEFINITION  (configuration)` yields
    None — it is an Administration heading describing stage config, not a
    pipeline stage, and the digit is what tells them apart.
    """
    match = STAGE_SECTION_LABEL.match(label or "")
    return int(match.group(1)) if match else None


# ------------------------------------------------------------- snapshot


def _field_state(db: Session) -> dict[str, dict[str, Any]]:
    """
    Per-placement state a fields.json row does not carry, keyed by qref.

    Everything restore_snapshot needs to rebuild a placement and its definition
    that is not already in the field row: which scope the definition is unique
    in, which record shape the placement sits in, where its values live, and
    the label override that would otherwise be indistinguishable from the
    definition's own label.
    """
    state: dict[str, dict[str, Any]] = {}
    rows = (
        select(FieldPlacement, FieldDefinition, Section.label)
        .join(FieldDefinition, FieldDefinition.id == FieldPlacement.definition_id)
        .join(Section, Section.id == FieldPlacement.section_id)
        .where(FieldPlacement.status == "active", FieldDefinition.status == "active")
    )
    for placement, definition, section_label in db.execute(rows).all():
        qref = f"{placement.module_key}.{section_label}.{placement.api_name}"
        state[qref] = {
            "definition_scope": definition.scope_key,
            "scope_key": placement.scope_key,
            "storage": placement.storage,
            "label_override": placement.label_override,
            "provenance": placement.provenance,
            "origin_module": definition.origin_module,
        }
    return state


def build_snapshot(db: Session) -> dict[str, Any]:
    """
    The live draft as one self-contained document.

    Self-contained is the point: a published snapshot must still be
    republishable after the draft has moved on, so it joins nothing back to
    the live tables. It carries the structural state (modules, sections,
    picklist and stage flags) as well as the register rows, because rolling
    back has to restore a renamed section and a deactivated option too, not
    just the fields.

    Only ACTIVE placements of ACTIVE definitions are included. A deleted field
    is absent from the snapshot for the same reason it is absent from
    fields.json — it is not part of the configuration any more. Its rows stay
    in field_definitions and field_placements, which is what makes restoring it
    possible.
    """
    sections = list(db.scalars(select(Section).order_by(Section.module_key, Section.sort_order)))
    section_label = {s.id: s.label for s in sections}

    # THE one resolver. Administration lists these same rows, so the published
    # spec and the screen an admin edits cannot describe different products.
    fields = resolved_fields(db)

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "modules": [
            {
                "module_key": m.module_key,
                "label": m.label,
                "sort_order": m.sort_order,
                "active": m.active,
                # Pipeline structure, so a snapshot is still self-contained:
                # a rollback has to restore which module owned which stages.
                "is_pipeline": m.is_pipeline,
                "stage_field": m.stage_field,
                "parent_module": m.parent_module,
                "parent_link": m.parent_link,
            }
            for m in db.scalars(select(Module).order_by(Module.sort_order, Module.module_key))
        ],
        "sections": [
            {
                "module_key": s.module_key,
                "label": s.label,
                "sort_order": s.sort_order,
                "active": s.active,
            }
            for s in sections
        ],
        "schema_version": SNAPSHOT_SCHEMA_VERSION,
        "fields": fields,
        # Placement and definition state that fields.json does not carry, kept
        # OUT of the field rows above on purpose: those rows are what the
        # frontend reads, and a key there that nothing declares would reach it
        # as a field attribute. A sidecar map instead, keyed by qref, read only
        # by restore_snapshot.
        #
        # This is what makes a rollback able to rebuild PLACEMENTS rather than
        # just field values — the scope a definition is unique in, the record
        # shape a placement sits in, and where its values are stored.
        "field_state": _field_state(db),
        "picklists": [
            {
                "picklist_key": p.picklist_key,
                "label": p.label,
                "sort_order": p.sort_order,
                "active": p.active,
                "values": [
                    {
                        "key": v.key,
                        "label": v.label,
                        "sort_order": v.sort_order,
                        "active": v.active,
                    }
                    for v in sorted(p.values, key=lambda v: (v.sort_order, v.key))
                ],
            }
            for p in db.scalars(
                select(Picklist).order_by(Picklist.sort_order, Picklist.picklist_key)
            )
        ],
        "stages": [
            {
                "stage": s.stage,
                "name": s.name,
                "prob_min": s.prob_min,
                "prob_max": s.prob_max,
                "owner_role": s.owner_role,
                "bid_phase": s.bid_phase,
                "applies_to": s.applies_to,
                "owner_module": s.owner_module,
                "sort_order": s.sort_order,
                "active": s.active,
            }
            for s in db.scalars(select(Stage).order_by(Stage.sort_order, Stage.stage))
        ],
    }


# ----------------------------------------------------- the three documents


def spec_documents(snapshot: dict[str, Any]) -> dict[str, Any]:
    """
    Render a snapshot as the three files the frontend reads.

    Pure: publish and rollback both come through here, so a republished old
    version produces byte-identical output to what that version produced when
    it was first published.

    Ordering is fixed rather than incidental. fields.json follows the module
    order the register declares and then each field's `order` within its
    module, which is the order src/lib/spec/index.ts re-sorts into anyway;
    picklists.json is keyed in the order the picklists are declared. A stable
    order is what makes the git diff after a publish readable — an unstable one
    would show 566 moved lines every time somebody renamed a label.

    A DEACTIVATED PICKLIST IS OMITTED, not emptied. optionsFor() returns [] for
    a key it does not know, and validateForSave already treats a picklist with
    no set behind it as a free string rather than rejecting every value — so
    omission degrades exactly the way the frontend already expects. Emptying it
    instead would rewrite the option rows, which is data loss to express a flag.
    """
    module_order = {m["module_key"]: i for i, m in enumerate(snapshot["modules"])}

    fields = sorted(
        snapshot["fields"],
        key=lambda f: (module_order.get(f["module"], len(module_order)), f["order"]),
    )

    picklists = {
        p["picklist_key"]: [
            {
                "key": v["key"],
                "label": v["label"],
                "sort": v["sort_order"],
                "active": v["active"],
            }
            for v in p["values"]
        ]
        for p in snapshot["picklists"]
        if p["active"]
    }

    stages = [
        {
            "stage": s["stage"],
            "name": s["name"],
            "prob_min": s["prob_min"],
            "prob_max": s["prob_max"],
            "owner_role": s["owner_role"],
            "bid_phase": s["bid_phase"],
            "applies_to": s["applies_to"],
        }
        for s in snapshot["stages"]
        if s["active"]
    ]

    # Every key a resolved row carries goes into the file: the register's 24
    # plus the 7 the frontend used to compute in moduleSplit.ts. They are data
    # now, which is what lets that projection be deleted.
    fields = [
        {k: row[k] for k in (*FIELD_JSON_KEYS, *RESOLVED_KEYS) if k in row}
        for row in fields
    ]

    documents: dict[str, Any] = {
        FIELDS_JSON: fields,
        PICKLISTS_JSON: picklists,
        STAGES_JSON: stages,
    }

    # module_split.json's structural blocks come from PostgreSQL now. Included
    # here so publish and rollback regenerate it alongside the other three; it
    # is skipped when the file is absent, since its hand-authored half cannot be
    # invented. See module_split_document().
    split = module_split_document(snapshot)
    if split is not None:
        documents[MODULE_SPLIT_JSON] = split

    return documents


MODULE_SPLIT_JSON = "module_split.json"

# The blocks of module_split.json that PostgreSQL now owns and regenerates.
# Everything else in that file is a hand-authored judgement call with no
# database representation and is preserved untouched — see
# module_split_document().
DERIVED_SPLIT_BLOCKS = ("pipeline", "ranges", "stage_field", "reassign")

# Blocks that used to decide a field's module, section, label and stage at load
# time. Every one of them is a field_placements column now:
#
#   own / shared          -> one placement per module, value_mode='own'
#   own.relabel           -> field_placements.label_override
#   own.exclude           -> the absence of a placement row
#   read_through.fields   -> value_mode='read_through'
#   relocated_fields      -> the placement's own capture_stage and section
#   section_order         -> sections.sort_order
#
# module_split.json keeps only the STRUCTURAL blocks — which modules are
# pipeline modules, which stages each owns, and which module is whose parent —
# and those are generated from `modules` and `stages`. It is no longer an
# authority on placement, which is what CLAUDE.md's "one authoritative
# resolution model" requires.
DEAD_SPLIT_BLOCKS = ("own", "shared", "relocated_fields", "section_order")


def split_config_from_snapshot(snapshot: dict[str, Any]) -> dict[str, Any]:
    """
    The pipeline structure, read out of a snapshot rather than off the session.

    From the snapshot so that a ROLLBACK regenerates the split the rolled-back
    version had. Deriving it from the live tables instead would republish an old
    field set against today's stage ownership, which is a configuration that was
    never published and never reviewed.

    `ranges` is derived from stage ownership rather than stored beside it, so
    the two cannot disagree: there is one place a stage's owner is written down.
    """
    modules = {m["module_key"]: m for m in snapshot["modules"]}
    pipeline = [k for k, m in modules.items() if m.get("is_pipeline")]

    owned: dict[str, list[int]] = {}
    for stage in snapshot["stages"]:
        owner = stage.get("owner_module")
        if owner:
            owned.setdefault(owner, []).append(stage["stage"])

    pipeline.sort(key=lambda m: min(owned.get(m, [99])))

    register_sheet = pipeline[0] if pipeline else None
    reassign: dict[str, dict[str, str]] = {}
    if register_sheet:
        moved = {
            str(s["stage"]): s["owner_module"]
            for s in snapshot["stages"]
            if s.get("owner_module") and s["owner_module"] != register_sheet
        }
        if moved:
            reassign[register_sheet] = moved

    return {
        "pipeline": pipeline,
        "ranges": {
            m: [min(owned[m]), max(owned[m])] for m in pipeline if owned.get(m)
        },
        "stage_field": {
            m: modules[m]["stage_field"] for m in pipeline if modules[m].get("stage_field")
        },
        "reassign": reassign,
    }


def module_split_document(
    snapshot: dict[str, Any], spec_dir: Path = SPEC_DIR
) -> dict[str, Any] | None:
    """
    spec/module_split.json with its DB-owned blocks rewritten from PostgreSQL.

    THE POINT OF THIS
    -----------------
    Before Round-6 gap closure, `ranges`, `pipeline`, `stage_field` and
    `reassign` existed ONLY in this file. That made a hand-edited JSON the
    authority on which module owns which stage — the one structural fact the
    backend will need the moment /api/opportunities stops being answered by
    MSW. Those four blocks are now generated from `modules.is_pipeline` /
    `stage_field` and `stages.owner_module`.

    THE BLOCKS IT DOES NOT TOUCH
    -----------------------------
    `own`, `read_through`, `shared`, `section_order`, `relocated_fields` and
    `register_corrections` are preserved byte-for-byte from the existing file.
    They are judgement calls about individual fields — which identity fields are
    read through a parent, which field was deliberately relocated to another
    stage and why — with no representation in the metadata tables and no
    sensible one short of storing prose. They stay hand-authored, on the same
    footing as spec/extensions.json.

    So this file is now PART generated and PART sidecar, and its own $note says
    which is which. Returns None if the file is missing, rather than inventing
    the hand-authored half from nothing.
    """
    path = spec_dir / MODULE_SPLIT_JSON
    if not path.exists():
        return None

    document = json.loads(path.read_text(encoding="utf-8"))
    derived = split_config_from_snapshot(snapshot)

    # Round 7: the blocks that decided WHERE A FIELD GOES are rows now, and
    # carrying them in a JSON file the frontend still reads would leave a
    # second authority sitting next to the first. They are dropped here rather
    # than left to rot, so the file cannot be mistaken for a placement source.
    for dead in DEAD_SPLIT_BLOCKS:
        document.pop(dead, None)
    read_through_block = document.get("read_through")
    if isinstance(read_through_block, dict):
        read_through_block.pop("fields", None)
        read_through_block.pop("skip_when_declared", None)
        read_through_block.pop("skip_note", None)
        read_through_block.pop("section", None)
        read_through_block.pop("source_module", None)

    for block in DERIVED_SPLIT_BLOCKS:
        if block not in derived:
            continue
        note = (document.get(block) or {}).get("$note") if isinstance(document.get(block), dict) else None
        value = derived[block]
        # Keep whatever $note the block carried: it explains the block to a
        # reader, and regenerating is not a reason to throw documentation away.
        if note and isinstance(value, dict):
            value = {"$note": note, **value}
        document[block] = value

    # read_through's parent_of / parent_link are DB-owned; the `fields` list
    # inside the same block is not. Rewrite the two maps in place.
    read_through = document.get("read_through")
    if isinstance(read_through, dict):
        modules = {m["module_key"]: m for m in snapshot["modules"]}
        pipeline = derived["pipeline"]
        parents = {
            m: modules[m]["parent_module"]
            for m in pipeline
            if modules[m].get("parent_module")
        }
        links = {
            m: modules[m]["parent_link"]
            for m in pipeline
            if modules[m].get("parent_link")
        }
        if parents:
            read_through["parent_of"] = parents
        if links:
            read_through["parent_link"] = links

    return document


def _dump(document: Any) -> str:
    """
    Exactly the formatting build_spec.py produced: one-space indent, real
    unicode (the register is full of em dashes), CRLF, and no trailing
    newline. Matching it means a regenerate shows only the lines that actually
    changed, instead of reformatting all 14,717 of them.
    """
    text = json.dumps(document, indent=1, ensure_ascii=False)
    return text.replace("\n", "\r\n")


def write_spec_documents(documents: dict[str, Any], spec_dir: Path = SPEC_DIR) -> list[Path]:
    """Write the three files. Returns the paths, in the order written."""
    written = []
    for name, document in documents.items():
        path = spec_dir / name
        # newline="" so the CRLFs in _dump survive rather than becoming CRCRLF.
        with path.open("w", encoding="utf-8", newline="") as handle:
            handle.write(_dump(document))
        written.append(path)
    return written


def read_spec_documents(spec_dir: Path = SPEC_DIR) -> dict[str, Any]:
    """
    The three files as they are on disk.

    The ONLY read of a spec file outside the bootstrap, and it exists purely so
    regenerate_spec.py --check can compare. Nothing imports from here.
    """
    names = [FIELDS_JSON, PICKLISTS_JSON, STAGES_JSON]
    if (spec_dir / MODULE_SPLIT_JSON).exists():
        names.append(MODULE_SPLIT_JSON)
    return {
        name: json.loads((spec_dir / name).read_text(encoding="utf-8"))
        for name in names
    }


# --------------------------------------------------------- semantic parity


def _field_key(row: dict[str, Any]) -> tuple[str, str, str]:
    return (row["module"], row["section"], row["api_name"])


def compare_documents(
    generated: dict[str, Any], on_disk: dict[str, Any]
) -> list[str]:
    """
    Semantic differences between what the database would write and what is on
    disk. Empty means they agree.

    Deliberately NOT a byte comparison. Three of the register's 566 rows carry
    their 24 keys in a different order to the other 563 — same keys, same
    values, different order — so byte equality reports a difference that means
    nothing, every time, forever. What matters is whether the frontend would
    read the same configuration, and that is what this checks.
    """
    problems: list[str] = []

    gen_fields = {_field_key(r): r for r in generated[FIELDS_JSON]}
    disk_fields = {_field_key(r): r for r in on_disk[FIELDS_JSON]}

    for key in sorted(disk_fields.keys() - gen_fields.keys()):
        problems.append(f"fields.json: on disk but not in the database — {'.'.join(key)}")
    for key in sorted(gen_fields.keys() - disk_fields.keys()):
        problems.append(f"fields.json: in the database but not on disk — {'.'.join(key)}")

    for key in sorted(gen_fields.keys() & disk_fields.keys()):
        gen, disk = gen_fields[key], disk_fields[key]
        for json_key in (*FIELD_JSON_KEYS, *RESOLVED_KEYS):
            if gen.get(json_key) != disk.get(json_key):
                problems.append(
                    f"fields.json: {'.'.join(key)}.{json_key} — "
                    f"database {gen.get(json_key)!r}, disk {disk.get(json_key)!r}"
                )

    gen_pl, disk_pl = generated[PICKLISTS_JSON], on_disk[PICKLISTS_JSON]
    for key in sorted(set(disk_pl) - set(gen_pl)):
        problems.append(f"picklists.json: on disk but not in the database — {key}")
    for key in sorted(set(gen_pl) - set(disk_pl)):
        problems.append(f"picklists.json: in the database but not on disk — {key}")
    for key in sorted(set(gen_pl) & set(disk_pl)):
        if gen_pl[key] != disk_pl[key]:
            problems.append(
                f"picklists.json: {key} — {len(gen_pl[key])} option(s) in the database, "
                f"{len(disk_pl[key])} on disk, or the options differ"
            )

    gen_split = generated.get(MODULE_SPLIT_JSON)
    disk_split = on_disk.get(MODULE_SPLIT_JSON)
    if gen_split and disk_split:
        for block in DERIVED_SPLIT_BLOCKS:
            want = gen_split.get(block)
            have = disk_split.get(block)
            if isinstance(want, dict) and isinstance(have, dict):
                # $note is documentation the generator carries through; it is
                # not configuration and is not compared.
                want = {k: v for k, v in want.items() if k != "$note"}
                have = {k: v for k, v in have.items() if k != "$note"}
            if want != have:
                problems.append(
                    f"module_split.json: {block} — database {want!r}, disk {have!r}"
                )

    gen_st = {s["stage"]: s for s in generated[STAGES_JSON]}
    disk_st = {s["stage"]: s for s in on_disk[STAGES_JSON]}
    for stage in sorted(set(disk_st) - set(gen_st)):
        problems.append(f"stages.json: on disk but not in the database — stage {stage}")
    for stage in sorted(set(gen_st) - set(disk_st)):
        problems.append(f"stages.json: in the database but not on disk — stage {stage}")
    for stage in sorted(set(gen_st) & set(disk_st)):
        if gen_st[stage] != disk_st[stage]:
            problems.append(
                f"stages.json: stage {stage} — database {gen_st[stage]}, disk {disk_st[stage]}"
            )

    return problems


# ------------------------------------------------------------ validation


class ValidationResult:
    """
    What a publish is allowed to do.

    Two lists, and the distinction is the whole point:

      errors    the configuration is broken and publishing it would break a
                screen. Publish refuses.
      warnings  the register has a gap. Publish proceeds and says so.

    A gap is not an error here, and treating it as one would be a mistake this
    prototype exists to avoid: eleven picklist fields in the register name no
    picklist, Conditional fields state no condition, and childlists declare no
    row shape. Every one of those is already reported on the Spec Health page
    and none of them stops the application working. Refusing to publish until
    the register is perfect would mean never publishing again.
    """

    def __init__(self) -> None:
        self.errors: list[str] = []
        self.warnings: list[str] = []

    @property
    def ok(self) -> bool:
        return not self.errors

    def as_dict(self) -> dict[str, Any]:
        return {"ok": self.ok, "errors": self.errors, "warnings": self.warnings}


def validate_snapshot(snapshot: dict[str, Any]) -> ValidationResult:
    """
    Everything that has to hold before a draft may be published.

    Checked against the SNAPSHOT rather than the session, so the same function
    validates a draft about to be published and an old version about to be
    republished — a rollback to a version whose picklist has since been
    deleted has to be caught too.
    """
    result = ValidationResult()

    modules = {m["module_key"]: m for m in snapshot["modules"]}
    sections = {(s["module_key"], s["label"]): s for s in snapshot["sections"]}
    picklists = {p["picklist_key"]: p for p in snapshot["picklists"]}
    stages = {s["stage"] for s in snapshot["stages"] if s["active"]}

    # Modules whose records move through stages at all. Only these can have a
    # meaningful mandatory_from: on Accounts, 'Mandatory' means "the form asks
    # for it", and warning that it blocks no transition would be 200 lines of
    # noise about a transition that does not exist.
    staged_modules = {
        row["module"] for row in snapshot["fields"] if row["capture_stage"] is not None
    }

    # Pipeline modules, from the snapshot's own module rows. A `STAGE DEFINITION`
    # section on `administration` is a configuration heading, not a pipeline
    # stage, so the capture-stage rule below must only fire on these three.
    pipeline_modules = {
        m["module_key"] for m in snapshot["modules"] if m.get("is_pipeline")
    }

    seen: dict[tuple[str, str, str], int] = {}

    for row in snapshot["fields"]:
        ref = f"{row['module']}.{row['section']}.{row['api_name']}"

        # 1. duplicate field identifiers. The database's unique constraint
        #    stops this, so reaching here means a snapshot was assembled by
        #    something other than build_snapshot — a rollback payload, say.
        key = _field_key(row)
        seen[key] = seen.get(key, 0) + 1
        if seen[key] == 2:
            result.errors.append(f"{ref} is defined more than once")

        # 2. module references
        module = modules.get(row["module"])
        if module is None:
            result.errors.append(f"{ref} names module {row['module']!r}, which does not exist")
        elif not module["active"]:
            result.errors.append(
                f"{ref} is on module {row['module']!r}, which is deactivated. "
                f"Delete the field or reactivate the module."
            )

        # 3. section references
        section = sections.get((row["module"], row["section"]))
        if section is None:
            result.errors.append(
                f"{ref} names section {row['section']!r}, which does not exist on that module"
            )
        elif not section["active"]:
            result.errors.append(
                f"{ref} is in section {row['section']!r}, which is deactivated. "
                f"Delete the field or reactivate the section."
            )

        # 4. invalid field definitions
        if row["type"] not in FIELD_TYPES:
            result.errors.append(f"{ref} has type {row['type']!r}, which the form engine cannot render")
        if row["requirement"] not in REQUIREMENTS:
            result.errors.append(f"{ref} has requirement {row['requirement']!r}, which is not one of {', '.join(REQUIREMENTS)}")

        # 5. picklist references
        if row["picklist"]:
            picklist = picklists.get(row["picklist"])
            if picklist is None:
                result.errors.append(
                    f"{ref} names picklist {row['picklist']!r}, which does not exist"
                )
            elif not picklist["active"]:
                result.errors.append(
                    f"{ref} names picklist {row['picklist']!r}, which is deactivated — "
                    f"the field would render with no options"
                )
            elif not any(v["active"] for v in picklist["values"]):
                result.warnings.append(
                    f"{ref} names picklist {row['picklist']!r}, which has no active values"
                )
        elif row["type"] in PICKLIST_TYPES:
            # A register gap, not a build error: eleven of these ship today and
            # the form engine already falls back to a free string.
            result.warnings.append(
                f"{ref} is a {row['type']} but names no picklist — it will accept free text"
            )

        # 6a. A field in a numbered STAGE section must say which stage it is
        #     captured at, and must agree with the section.
        #
        #     This is an ERROR, not a warning, because the failure is invisible:
        #     the stage tab selects fields by `capture_stage === stage` and the
        #     Details tab excludes every STAGE section, so a field with neither
        #     renders on no screen while looking entirely correct in
        #     Administration. Publishing that is worse than refusing to.
        #
        #     Safe to enforce: all 133 register rows in a numbered STAGE section
        #     already satisfy it, with no exceptions. `STAGE DEFINITION
        #     (configuration)` and friends carry no digit and are not matched —
        #     they describe stage config, they are not pipeline stages.
        section_stage = _stage_of_section_label(row["section"])
        if section_stage is not None and row["module"] in pipeline_modules:
            if row["capture_stage"] is None:
                result.errors.append(
                    f"{ref} sits in {row['section']!r} but has no capture stage, so it "
                    f"would render on no screen at all. Set it to {section_stage}."
                )
            elif row["capture_stage"] != section_stage:
                result.errors.append(
                    f"{ref} sits in {row['section']!r} but is captured at stage "
                    f"{row['capture_stage']}. It would render on the stage "
                    f"{row['capture_stage']} tab, not with the section it is in."
                )

        # 6. stage references
        for column in ("capture_stage", "mandatory_from"):
            value = row[column]
            if value is not None and value not in stages:
                result.errors.append(
                    f"{ref}.{column} is {value}, which is not an active stage"
                )

        if (
            row["requirement"] == "Mandatory"
            and row["mandatory_from"] is None
            and row["module"] in staged_modules
        ):
            # Layer 1 of the transition check reads mandatory_from, so a
            # Mandatory field without one blocks nothing. Worth saying; not
            # worth refusing — see staged_modules above for why this asks
            # about pipeline modules only.
            result.warnings.append(
                f"{ref} is Mandatory but has no mandatory_from, so it blocks no stage transition"
            )

        if row["requirement"] == "Conditional" and not row["condition"]:
            result.warnings.append(
                f"{ref} is Conditional but states no condition, so it is treated as optional"
            )

    # 7. orphaned metadata
    used_sections = {(r["module"], r["section"]) for r in snapshot["fields"]}
    for (module_key, label), section in sections.items():
        if section["active"] and (module_key, label) not in used_sections:
            result.warnings.append(
                f"section {module_key}.{label!r} is active but contains no fields"
            )

    used_modules = {r["module"] for r in snapshot["fields"]}
    for module_key, module in modules.items():
        if module["active"] and module_key not in used_modules:
            result.warnings.append(f"module {module_key!r} is active but contains no fields")

    used_picklists = {r["picklist"] for r in snapshot["fields"] if r["picklist"]}
    for picklist_key, picklist in picklists.items():
        if picklist["active"] and picklist_key not in used_picklists:
            result.warnings.append(
                f"picklist {picklist_key!r} is active but no field uses it"
            )

    # 8. stage sanity
    for stage in snapshot["stages"]:
        if not stage["active"]:
            continue
        low, high = stage["prob_min"], stage["prob_max"]
        if low is not None and high is not None and low > high:
            result.errors.append(
                f"stage {stage['stage']} has prob_min {low} above prob_max {high}"
            )

    return result


def validate_draft(db: Session) -> tuple[ValidationResult, dict[str, Any]]:
    """The live draft, validated. Returns the result and the snapshot checked."""
    snapshot = build_snapshot(db)
    return validate_snapshot(snapshot), snapshot


# ------------------------------------------------------------ sidecar refs


def sidecar_refs(spec_dir: Path = SPEC_DIR) -> set[str]:
    """
    Every `module.api_name` (or `module.section.api_name`) key that
    spec/extensions.json binds a computed_expr, child_spec or override to.

    Read to WARN, never to import. extensions.json is hand-maintained and is
    not regenerated, so deleting a field the sidecar still keys on leaves an
    orphaned entry that the frontend reports on its Spec Health page — the
    Administration screen should say so before the delete, not after.
    """
    path = spec_dir / "extensions.json"
    if not path.exists():
        return set()
    data = json.loads(path.read_text(encoding="utf-8"))
    return {key for key in data.get("fields", {}) if not key.startswith("$")}


def refs_of(row: dict[str, Any]) -> tuple[str, str]:
    """The two forms a sidecar key may take for one field row."""
    return (
        f"{row['module']}.{row['api_name']}",
        f"{row['module']}.{row['section']}.{row['api_name']}",
    )


def orphaned_sidecar_refs(snapshot: dict[str, Any], spec_dir: Path = SPEC_DIR) -> list[str]:
    """Sidecar keys naming a field the snapshot no longer carries."""
    live: set[str] = set()
    for row in snapshot["fields"]:
        live.update(refs_of(row))
    return sorted(sidecar_refs(spec_dir) - live)


def iter_field_rows(rows: Iterable[dict[str, Any]]) -> Iterable[tuple[str, dict[str, Any]]]:
    """(qref, row) for each register row. Used by the bootstrap and the diff."""
    for row in rows:
        yield f"{row['module']}.{row['section']}.{row['api_name']}", row


# --------------------------------------------------------------- draft diff


def diff_snapshots(previous: dict[str, Any], current: dict[str, Any]) -> list[str]:
    """
    What changed between two snapshots, in words.

    This is the review step: what an admin reads before publishing, and what a
    version note is written against. Deliberately a list of sentences rather
    than a structural diff — "leads.STAGE 4 — RFP / RFI.licence_model deleted"
    is what somebody needs to see before they approve it, and a nested object
    of before/after values is not.
    """
    changes: list[str] = []

    def by_key(rows, key):
        return {key(r): r for r in rows}

    prev_f = by_key(previous.get("fields", []), _field_key)
    curr_f = by_key(current.get("fields", []), _field_key)

    for key in sorted(curr_f.keys() - prev_f.keys()):
        changes.append(f"field added — {'.'.join(key)}")
    for key in sorted(prev_f.keys() - curr_f.keys()):
        changes.append(f"field deleted — {'.'.join(key)}")
    for key in sorted(curr_f.keys() & prev_f.keys()):
        for json_key in (*FIELD_JSON_KEYS, *RESOLVED_KEYS):
            before, after = prev_f[key].get(json_key), curr_f[key].get(json_key)
            if before != after:
                changes.append(
                    f"field changed — {'.'.join(key)}.{json_key}: {before!r} -> {after!r}"
                )

    prev_m = {m["module_key"]: m for m in previous.get("modules", [])}
    curr_m = {m["module_key"]: m for m in current.get("modules", [])}
    for key in sorted(curr_m.keys() - prev_m.keys()):
        changes.append(f"module added — {key}")
    for key in sorted(curr_m.keys() & prev_m.keys()):
        for attr in ("label", "sort_order", "active"):
            if prev_m[key][attr] != curr_m[key][attr]:
                changes.append(
                    f"module changed — {key}.{attr}: "
                    f"{prev_m[key][attr]!r} -> {curr_m[key][attr]!r}"
                )

    prev_s = {(s["module_key"], s["label"]): s for s in previous.get("sections", [])}
    curr_s = {(s["module_key"], s["label"]): s for s in current.get("sections", [])}
    for key in sorted(curr_s.keys() - prev_s.keys()):
        changes.append(f"section added — {key[0]}.{key[1]}")
    for key in sorted(prev_s.keys() - curr_s.keys()):
        changes.append(f"section removed — {key[0]}.{key[1]}")
    for key in sorted(curr_s.keys() & prev_s.keys()):
        for attr in ("sort_order", "active"):
            if prev_s[key][attr] != curr_s[key][attr]:
                changes.append(
                    f"section changed — {key[0]}.{key[1]}.{attr}: "
                    f"{prev_s[key][attr]!r} -> {curr_s[key][attr]!r}"
                )

    prev_p = {p["picklist_key"]: p for p in previous.get("picklists", [])}
    curr_p = {p["picklist_key"]: p for p in current.get("picklists", [])}
    for key in sorted(curr_p.keys() - prev_p.keys()):
        changes.append(f"picklist added — {key}")
    for key in sorted(prev_p.keys() - curr_p.keys()):
        changes.append(f"picklist removed — {key}")
    for key in sorted(curr_p.keys() & prev_p.keys()):
        if prev_p[key]["active"] != curr_p[key]["active"]:
            state = "activated" if curr_p[key]["active"] else "deactivated"
            changes.append(f"picklist {state} — {key}")
        before = {v["key"]: v for v in prev_p[key]["values"]}
        after = {v["key"]: v for v in curr_p[key]["values"]}
        for value in sorted(after.keys() - before.keys()):
            changes.append(f"picklist value added — {key}.{value}")
        for value in sorted(before.keys() - after.keys()):
            changes.append(f"picklist value removed — {key}.{value}")
        for value in sorted(after.keys() & before.keys()):
            for attr in ("label", "sort_order", "active"):
                if before[value][attr] != after[value][attr]:
                    changes.append(
                        f"picklist value changed — {key}.{value}.{attr}: "
                        f"{before[value][attr]!r} -> {after[value][attr]!r}"
                    )

    prev_st = {s["stage"]: s for s in previous.get("stages", [])}
    curr_st = {s["stage"]: s for s in current.get("stages", [])}
    for key in sorted(curr_st.keys() - prev_st.keys()):
        changes.append(f"stage added — {key}")
    for key in sorted(prev_st.keys() - curr_st.keys()):
        changes.append(f"stage removed — {key}")
    for key in sorted(curr_st.keys() & prev_st.keys()):
        for attr in ("name", "prob_min", "prob_max", "owner_role", "bid_phase", "applies_to", "sort_order", "active"):
            if prev_st[key][attr] != curr_st[key][attr]:
                changes.append(
                    f"stage changed — {key}.{attr}: "
                    f"{prev_st[key][attr]!r} -> {curr_st[key][attr]!r}"
                )

    return changes


# ------------------------------------------------------------ restore


def restore_snapshot(db: Session, snapshot: dict[str, Any]) -> list[str]:
    """
    Reconcile the live draft to an earlier snapshot. The rollback half of
    version history.

    NOTHING IS DELETED. Not one row, anywhere:

      * a field the snapshot does not carry becomes status='deleted' — the same
        logical delete the Administration screen performs, so the field and the
        business data behind it survive and it can be restored again;
      * a field the snapshot carries that is currently deleted comes BACK, with
        the snapshot's configuration;
      * a module, section, picklist, picklist value or stage the snapshot does
        not carry is DEACTIVATED, not dropped, for the same reason.

    That asymmetry is deliberate and it is what stops a rollback from being
    destructive. Rolling forward again restores everything the rollback hid,
    because none of it ever went away.

    Returns a list of what it did, for the version note.

    A PRE-ROUND-7 SNAPSHOT IS REFUSED, NOT TRANSLATED. Versions published
    before the placement model carry one row per REGISTER row keyed on
    module_key, which does not say which module a field appeared on — that is
    the very question the redesign exists to answer, and inventing the answer
    during a rollback would silently republish a different product. Those
    versions stay readable as history; the pre-Round-7 tables migration 0008
    archived are where their configuration actually lives.
    """
    version = snapshot.get("schema_version", 1)
    if version < SNAPSHOT_SCHEMA_VERSION:
        raise ValueError(
            f"This version was published against snapshot schema {version}, before "
            f"fields had placements. It can be read but not rolled back to: its rows "
            f"say which register sheet each field was filed on, not which modules it "
            f"appeared on. The pre-Round-7 configuration is preserved in the "
            f"field_metadata_pre_round7 table."
        )

    actions: list[str] = []

    # --------------------------------------------------------- modules
    live_modules = {m.module_key: m for m in db.scalars(select(Module))}
    for row in snapshot["modules"]:
        module = live_modules.get(row["module_key"])
        if module is None:
            db.add(
                Module(
                    module_key=row["module_key"],
                    label=row["label"],
                    sort_order=row["sort_order"],
                    active=row["active"],
                    is_pipeline=row.get("is_pipeline", False),
                    stage_field=row.get("stage_field"),
                    parent_module=row.get("parent_module"),
                    parent_link=row.get("parent_link"),
                )
            )
            actions.append(f"module recreated — {row['module_key']}")
        else:
            module.label = row["label"]
            module.sort_order = row["sort_order"]
            module.active = row["active"]
            # Pipeline structure travels with a rollback: a snapshot taken
            # before Opportunities existed as a module must not silently leave
            # today's stage ownership in place. Absent keys (older snapshots)
            # leave the live value alone rather than blanking it.
            if "is_pipeline" in row:
                module.is_pipeline = row["is_pipeline"]
                module.stage_field = row["stage_field"]
                module.parent_module = row["parent_module"]
                module.parent_link = row["parent_link"]

    snapshot_modules = {m["module_key"] for m in snapshot["modules"]}
    for key, module in live_modules.items():
        if key not in snapshot_modules and module.active:
            module.active = False
            actions.append(f"module deactivated — {key}")

    # -------------------------------------------------------- sections
    db.flush()
    live_sections = {(s.module_key, s.label): s for s in db.scalars(select(Section))}
    for row in snapshot["sections"]:
        key = (row["module_key"], row["label"])
        section = live_sections.get(key)
        if section is None:
            section = Section(
                module_key=row["module_key"],
                label=row["label"],
                sort_order=row["sort_order"],
                active=row["active"],
            )
            db.add(section)
            live_sections[key] = section
            actions.append(f"section recreated — {row['module_key']}.{row['label']}")
        else:
            section.sort_order = row["sort_order"]
            section.active = row["active"]

    snapshot_sections = {(s["module_key"], s["label"]) for s in snapshot["sections"]}
    for key, section in live_sections.items():
        if key not in snapshot_sections and section.active:
            section.active = False
            actions.append(f"section deactivated — {key[0]}.{key[1]}")

    # ------------------------------------------------------- picklists
    live_picklists = {p.picklist_key: p for p in db.scalars(select(Picklist))}
    for row in snapshot["picklists"]:
        picklist = live_picklists.get(row["picklist_key"])
        if picklist is None:
            picklist = Picklist(
                picklist_key=row["picklist_key"],
                label=row["label"],
                sort_order=row.get("sort_order", 0),
                active=row["active"],
            )
            db.add(picklist)
            live_picklists[row["picklist_key"]] = picklist
            actions.append(f"picklist recreated — {row['picklist_key']}")
        else:
            picklist.label = row["label"]
            picklist.sort_order = row.get("sort_order", picklist.sort_order)
            picklist.active = row["active"]

        db.flush()
        live_values = {v.key: v for v in picklist.values}
        for value_row in row["values"]:
            value = live_values.get(value_row["key"])
            if value is None:
                picklist.values.append(
                    PicklistValue(
                        picklist_key=picklist.picklist_key,
                        key=value_row["key"],
                        label=value_row["label"],
                        sort_order=value_row["sort_order"],
                        active=value_row["active"],
                    )
                )
                actions.append(
                    f"picklist value recreated — {row['picklist_key']}.{value_row['key']}"
                )
            else:
                value.label = value_row["label"]
                value.sort_order = value_row["sort_order"]
                value.active = value_row["active"]

        snapshot_values = {v["key"] for v in row["values"]}
        for key, value in live_values.items():
            if key not in snapshot_values and value.active:
                value.active = False
                actions.append(
                    f"picklist value deactivated — {row['picklist_key']}.{key}"
                )

    snapshot_picklists = {p["picklist_key"] for p in snapshot["picklists"]}
    for key, picklist in live_picklists.items():
        if key not in snapshot_picklists and picklist.active:
            picklist.active = False
            actions.append(f"picklist deactivated — {key}")

    # ---------------------------------------------------------- stages
    live_stages = {s.stage: s for s in db.scalars(select(Stage))}
    for row in snapshot["stages"]:
        stage = live_stages.get(row["stage"])
        if stage is None:
            db.add(
                Stage(
                    stage=row["stage"],
                    name=row["name"],
                    prob_min=row["prob_min"],
                    prob_max=row["prob_max"],
                    owner_role=row["owner_role"],
                    bid_phase=row["bid_phase"],
                    applies_to=row["applies_to"],
                    owner_module=row.get("owner_module"),
                    sort_order=row.get("sort_order", row["stage"]),
                    active=row.get("active", True),
                )
            )
            actions.append(f"stage recreated — {row['stage']}")
        else:
            stage.name = row["name"]
            stage.prob_min = row["prob_min"]
            stage.prob_max = row["prob_max"]
            stage.owner_role = row["owner_role"]
            stage.bid_phase = row["bid_phase"]
            stage.applies_to = row["applies_to"]
            if "owner_module" in row:
                stage.owner_module = row["owner_module"]
            stage.sort_order = row.get("sort_order", stage.sort_order)
            stage.active = row.get("active", True)

    snapshot_stages = {s["stage"] for s in snapshot["stages"]}
    for key, stage in live_stages.items():
        if key not in snapshot_stages and stage.active:
            stage.active = False
            actions.append(f"stage deactivated — {key}")

    # ---------------------------------------------------------- fields
    #
    # Rebuilds DEFINITIONS and PLACEMENTS. Nothing is deleted, exactly as
    # before: a field the snapshot does not carry becomes status='deleted' on
    # its placement, and the business column and every value in it survive.
    db.flush()
    all_sections = list(db.scalars(select(Section)))
    section_by_key = {(s.module_key, s.label): s for s in all_sections}
    label_of = {s.id: s.label for s in all_sections}

    state = snapshot.get("field_state", {})
    live_definitions = {
        (d.scope_key, d.api_name): d for d in db.scalars(select(FieldDefinition))
    }
    live_placements = {
        (p.module_key, label_of[p.section_id], p.api_name): p
        for p in db.scalars(select(FieldPlacement))
    }

    for row in snapshot["fields"]:
        key = (row["module"], row["section"], row["api_name"])
        qref = ".".join(key)
        extra = state.get(qref, {})
        section = section_by_key[(row["module"], row["section"])]

        definition_scope = extra.get("definition_scope") or row["module"]
        definition = live_definitions.get((definition_scope, row["api_name"]))
        if definition is None:
            definition = FieldDefinition(
                scope_key=definition_scope,
                api_name=row["api_name"],
                label=row["label"],
                field_type=row["type"],
                origin=row["origin"],
            )
            db.add(definition)
            live_definitions[(definition_scope, row["api_name"])] = definition
            actions.append(f"field definition recreated — {definition_scope}.{row['api_name']}")
        elif definition.status == "deleted":
            actions.append(f"field definition restored — {definition_scope}.{row['api_name']}")

        # Definition-level properties: the shape of the value and its
        # documentation. A rollback restores the label the snapshot published,
        # which is the label every module showed at the time.
        definition.status = "active"
        definition.deleted_at = None
        definition.deleted_by = None
        definition.label = row["label"] if not extra.get("label_override") else definition.label
        definition.field_type = row["type"]
        definition.max_length = row["max_length"]
        definition.picklist_key = row["picklist"]
        definition.lookup_target = row["lookup_target"]
        definition.lookup_filter = row["lookup_filter"]
        definition.computed_formula = row["computed_formula"]
        # PRESERVED, not restored-to-null, when the key is absent — and that is
        # the opposite of how anchors are handled below, deliberately.
        # anchor_field has been a column since 0013, so a snapshot taken before
        # it genuinely described a register with no anchors. computed_expr was
        # not missing before 0015: it was in spec/extensions.json, which a
        # rollback does not touch and which was still in force. Restoring null
        # here would leave every computed field on the screen with nothing to
        # compute, which no published configuration ever meant.
        definition.computed_expr = row.get("computed_expr", definition.computed_expr)
        definition.values_note = row["values_note"]
        definition.description = row["description"]
        definition.use_case = row["use_case"]
        definition.origin = row["origin"]
        definition.source_ref = row["source_ref"]
        definition.origin_module = extra.get("origin_module") or definition.origin_module
        db.flush()

        placement = live_placements.get(key)
        if placement is None:
            placement = FieldPlacement(
                definition_id=definition.id,
                api_name=row["api_name"],
                module_key=row["module"],
                scope_key=extra.get("scope_key") or row["module"],
                section_id=section.id,
                requirement=row["requirement"],
                # From the snapshot's own state map. A snapshot published
                # before that map existed carries only register fields, so
                # 'column' is the right fallback — pointing a restored field at
                # the wrong storage is worse than refusing.
                storage=extra.get("storage", "column"),
            )
            db.add(placement)
            live_placements[key] = placement
            actions.append(f"field recreated — {qref}")
        elif placement.status == "deleted":
            actions.append(f"field restored — {qref}")

        placement.definition_id = definition.id
        placement.section_id = section.id
        placement.status = "active"
        placement.deleted_at = None
        placement.deleted_by = None
        placement.deleted_by_cascade = False
        placement.sort_order = row["order"]
        placement.label_override = extra.get("label_override")
        placement.capture_stage = row["capture_stage"]
        placement.capture_any_stage = bool(row["capture_any_stage"])
        placement.mandatory_from = row["mandatory_from"]
        placement.blocks_transition = row["blocks_transition"]
        placement.requirement = row["requirement"]
        placement.required_on_skip = row["required_on_skip"]
        placement.visibility_condition = row["visibility_condition"]
        placement.condition = row["condition"]
        # The value layer travels with a rollback: which module owned a value,
        # and whether a Deal could diverge from its Opportunity, is part of the
        # configuration that was published and has to come back with it.
        placement.value_mode = row.get("value_mode", placement.value_mode)
        placement.value_locked = bool(row.get("value_locked", placement.value_locked))
        placement.editable = bool(row.get("editable", placement.editable))
        placement.storage = extra.get("storage", placement.storage)
        if placement.value_mode == "read_through":
            placement.editable = False
            placement.storage = None
        elif placement.storage is None:
            placement.storage = "column"
        # Position travels with a rollback too. Where a field DREW is part of
        # the configuration that was published — a snapshot that restored the
        # register but left On Hold Reason back on the Details tab would be
        # restoring the fields without restoring the form. `.get` because a
        # snapshot taken before anchors existed carries neither key, and there
        # the answer is genuinely "no anchor".
        placement.anchor_field = row.get("anchor_field")
        placement.anchor_position = row.get("anchor_position")
        placement.layout_span = row.get("layout_span")
        # Per-stage behaviour travels too, and is PRESERVED when absent for the
        # same reason computed_expr is: before 0015 it lived in
        # spec/extensions.json stage_scoped, which a rollback does not revert.
        # Reading a pre-B2 snapshot as "nothing was per-stage" would turn every
        # On Hold Reason back into a single value that the second hold
        # overwrites — silently, and only on rollback.
        placement.stage_scoped = row.get("stage_scoped", placement.stage_scoped)
        if placement.provenance is None:
            placement.provenance = extra.get("provenance")

    snapshot_fields = {_field_key(r) for r in snapshot["fields"]}
    for key, placement in live_placements.items():
        if key not in snapshot_fields and placement.status == "active":
            placement.status = "deleted"
            placement.deleted_at = datetime.now(timezone.utc)
            placement.deleted_by_cascade = False
            actions.append(f"field deleted — {'.'.join(key)}")

    return actions
