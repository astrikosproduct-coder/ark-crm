"""
Metadata model v2: every field owned by one module, as in Zoho.

    python metadata_v2.py              # dry run: checks, moves, compares, rolls back
    python metadata_v2.py --apply      # the same, committed, then published

Run after `alembic upgrade 0038_metadata_v2_schema` and before
`alembic upgrade head` (0039 enforces what this leaves behind). The approved
list it follows is docs/phase2/metadata-v2-step1-signoff.md.

WHAT IT DOES
------------
A. The shared `pipeline` scope is dissolved. Each definition is given to the
   module that holds its value; a field Leads, Opportunities and Deals each
   hold (Lead Status, Probability…) becomes three definitions. A field shown
   live "from the Lead" keeps pointing at the Lead's definition — it owns
   nothing. api_names never change, so no stored value moves.
   G1 (24 Sep): the Deal's End Client is shown live from the Lead too.
B. Conversion Mapping rows are written from today's behaviour.
C. Deal Registrations, Conflicts and Partner Scorecards (hidden) become
   modules filed under Partners. Their tables and rows are not touched.
D. Six picklists become global; Lead, Opportunity and Deal Status become one
   local list each (G3), with the values the server reads by key protected.
E. Modules that are not built, or not modules at all, are hidden.
F. The "READ THROUGH THE PARENT" section becomes "From the Lead".

WHY IT READS THE DATABASE IT RUNS ON
------------------------------------
Production publishes live, so its register can differ from development's.
Nothing here is pasted from development: every move is computed from the rows
in front of it, and anything the approved list does not expect STOPS the run
with the rows named, before a single write.

THE CHECK
---------
The spec the app reads is built before and after, and compared field by field.
Only the differences listed in EXPECTED_DIFFERENCES may appear; anything else
fails the run and nothing is committed. A user should notice nothing.

NO DDL against a business table. The one index created here is on
field_placements, the register's own table.
"""

from __future__ import annotations

import sys
from typing import Any

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from sqlalchemy import select, text  # noqa: E402

from app.database import SessionLocal, engine  # noqa: E402

engine.echo = False

from app.metadata_resolver import resolved_fields  # noqa: E402
from app.models import (  # noqa: E402
    ConversionMapping,
    FieldDefinition,
    FieldPlacement,
    Layout,
    Module,
    Picklist,
    PicklistValue,
    Section,
)

PIPELINE = ("leads", "opportunities", "deals")
OWNER_ORDER = {"leads": 0, "opportunities": 1, "deals": 2}

# ------------------------------------------------------------ the approved list

#: A1 — Lead-owned, shown live on Opportunities and Deals.
READ_THROUGH = {
    "opportunity_name", "bd_owner", "deal_source", "opportunity_type", "sap_solution_suite",
    "segment", "theme", "currency", "fx_rate_at_entry", "partner_deal_registration",
    "booking_region", "destination_region", "country", "city_state", "primary_contact",
    "gorilla_flag", "lighthouse_project", "suite_demonstrated", "alliance_structure",
    "consultant_specifier", "pre_bid_alliance_partner", "probable_award_date",
    "presales_owner", "sales_owner", "total_project_value",
}
#: A2 — owned before the Deal, copied into a Deal-owned field at conversion.
CARRIED_FROM_OPPORTUNITY = {
    "arr_annual_recurring", "contract_years", "one_time_revenue",
    "3rd_party_one_time", "3rd_party_recurring_per_year",
}
CARRIED_FROM_LEAD = {"end_client", "customer_partner_si"}
#: G1, decided 24 Sep 2026: shown live on the Deal instead of copied.
LIVE_ON_DEAL = {"end_client"}
#: A3 — each module holds its own value; split one definition per module.
SPLIT = {
    "closed_lost_reason_code", "created_by", "created_date", "days_in_current_stage",
    "days_since_last_update", "expected_close_month", "incremental_value",
    "is_primary_pursuit", "lead_status", "modified_by", "modified_date", "next_milestone",
    "next_milestone_date", "on_hold_reason", "overall_rag", "parent_lead",
    "probability_override_justification", "probability_pct", "progression_pct",
    "project_stage", "pursuit_group", "stage_reversal_reason", "stage_skip_reason",
}
#: C — the registration's Currency borrows the Lead's definition today.
PARTNER_BORROWED = {"currency"}

#: C — partner sections that become modules, filed under Partners.
PARTNER_MODULES = {
    "DEAL REGISTRATION": ("registrations", "Deal Registrations", "partners", False),
    "CONFLICT ADJUDICATION": ("conflicts", "Conflicts", "registrations", False),
    "QUARTERLY SCORECARD": ("partner_scorecards", "Partner Scorecards", "partners", True),
}

#: D — shared by fields on several modules.
GLOBAL_PICKLISTS = {
    "leads__currency": "Currency",
    "leads_stage": "Pipeline Stage",
    "closed_lost_reason_code": "Closed Lost Reason",
    "overall_rag": "Overall RAG",
    "region": "Region",
    "segment": "Segment",
    # Found on the dry run, 24 Sep: Phone and Mobile on a Contact share it.
    "contacts__dial_code": "Dial Code",
}
#: D — local, relabelled without the module prefix.
LOCAL_RELABEL = {
    "leads__lead_status": "Lead Status",
    "leads__alliance_structure": "Alliance Structure",
    "leads__deal_source": "Deal Source",
    "leads__opportunity_type": "Opportunity Type",
}
#: G3 — one status list per module. Keys copied exactly, so stored values match.
STATUS_SOURCE = "leads__lead_status"
STATUS_LISTS = {
    "opportunities": ("opportunities__lead_status", "Opportunity Status", {"POC_PILOT_DEAL"}),
    "deals": ("deals__lead_status", "Deal Status", set()),
}
#: Read by key in app/revenue.py, the Kanban and the stage-move rules.
SYSTEM_STATUS_KEYS = {"OPEN", "ON_HOLD", "CLOSED_LOST", "CONVERTED", "POC_PILOT_DEAL"}
#: Lead Status never holds this — the server refuses it on a Lead.
RETIRED_ON_LEADS = {"POC_PILOT_DEAL"}

#: E — kept, not offered in Administration.
HIDDEN_MODULES = (
    "administration", "demo_module", "bids_pocs", "quotes", "products", "activities_docs",
)

#: F
READ_THROUGH_SECTION = "READ THROUGH THE PARENT — resolved from the parent, never stored here"
FROM_THE_LEAD = "From the Lead"

# ------------------------------------------------------------ conversion rows

SYSTEM_ROWS = {
    "lead_to_opportunity": [
        ("opportunities", "parent_lead", "The Lead it came from"),
        ("opportunities", "project_stage", "Set to the stage the Lead moves to"),
        ("opportunities", "lead_status", "Starts Open"),
        ("opportunities", "progression_pct", "From the stage"),
        ("opportunities", "probability_pct", "From the stage"),
    ],
    "opportunity_to_deal": [
        ("deals", "parent_opportunity", "The Opportunity it came from"),
        ("deals", "parent_lead", "The Opportunity's Lead"),
        ("deals", "deal_stage", "Set to the stage the Opportunity moves to"),
        ("deals", "lead_status", "Starts Open"),
        ("deals", "progression_pct", "From the stage"),
        ("deals", "probability_pct", "From the stage"),
    ],
    "lead_to_deal_pilot": [
        ("deals", "parent_lead", "The Lead whose pilot was paid"),
        ("deals", "deal_stage", "Stage 7 — Close"),
        ("deals", "lead_status", "POC/Pilot Deal"),
        ("deals", "progression_pct", "Stage 7's Progression"),
        ("deals", "probability_pct", "100% — a paid pilot is Won"),
    ],
}
#: (path, source module, source field, target field, transform, locked)
COPY_ROWS = [
    *[("opportunity_to_deal", "opportunities", n, n, None, False)
      for n in ("arr_annual_recurring", "contract_years", "one_time_revenue",
                "3rd_party_one_time", "3rd_party_recurring_per_year")],
    *[("opportunity_to_deal", "leads", n, n, None, False)
      for n in sorted(CARRIED_FROM_LEAD - LIVE_ON_DEAL)],
    # G2, decided 24 Sep 2026: locked. They carry the paid pilot's Won rule.
    ("lead_to_deal_pilot", "leads", "pilot_fee", "contract_value", None, True),
    ("lead_to_deal_pilot", "leads", "pilot_po_received_date", "po_received_date", None, True),
    ("lead_to_deal_pilot", "leads", "opportunity_name", "deal_name", "paid_poc_name", True),
    *[("lead_to_deal_pilot", "leads", n, n, None, True)
      for n in sorted(CARRIED_FROM_LEAD - LIVE_ON_DEAL)],
]

# ------------------------------------------------------------ expected diff

#: Spec keys a field may change, and why. Everything else must be identical.
EXPECTED_DIFFERENCES = {
    "moved to its own module": "module",
    "section renamed to From the Lead": "section",
    "status list is the module's own": "picklist",
    "shown live from the Lead (G1)": "value_mode",
}


class Stop(Exception):
    """The register is not what the approved list expects. Nothing is written."""


# ============================================================ pre-flight


def preflight(db) -> None:
    """Every shared pipeline definition must be one the approved list names."""
    problems: list[str] = []
    shared = db.execute(
        select(FieldDefinition, FieldPlacement)
        .join(FieldPlacement, FieldPlacement.definition_id == FieldDefinition.id)
        .where(FieldDefinition.scope_key == "pipeline")
    ).all()
    by_def: dict[int, list[FieldPlacement]] = {}
    defs: dict[int, FieldDefinition] = {}
    for d, p in shared:
        by_def.setdefault(d.id, []).append(p)
        defs[d.id] = d

    known = READ_THROUGH | CARRIED_FROM_OPPORTUNITY | CARRIED_FROM_LEAD | SPLIT
    for def_id, placements in by_def.items():
        name = defs[def_id].api_name
        modules = sorted(p.module_key for p in placements)
        if len(placements) == 1:
            continue
        if name not in known:
            problems.append(f"{name}: shared by {modules}, not on the approved list")
            continue
        modes = {p.module_key: p.value_mode for p in placements}
        if name in READ_THROUGH:
            ok = modes.get("leads") == "own" and all(
                modes.get(m) == "read_through" for m in ("opportunities", "deals")
            ) and set(modes) - {"partners"} == set(PIPELINE)
        elif name in CARRIED_FROM_OPPORTUNITY:
            ok = modes == {"opportunities": "own", "deals": "carry_forward"}
        elif name in CARRIED_FROM_LEAD:
            ok = modes == {"leads": "own", "opportunities": "read_through", "deals": "carry_forward"}
        else:
            ok = all(mode == "own" for mode in modes.values())
        if not ok:
            problems.append(f"{name}: modes {modes} are not what the approved list expects")

    listed = {defs[i].api_name for i, ps in by_def.items() if len(ps) > 1}
    for name in sorted(known - listed):
        problems.append(f"{name}: on the approved list but not shared any more")

    for _, (module_key, *_rest) in PARTNER_MODULES.items():
        if db.get(Module, module_key) is not None:
            problems.append(f"module {module_key} already exists — has this already run?")

    for section_label in PARTNER_MODULES:
        section = db.scalar(
            select(Section).where(Section.module_key == "partners", Section.label == section_label)
        )
        if section is None:
            problems.append(f"partners section {section_label!r} is missing")

    if problems:
        raise Stop("\n".join(f"  - {p}" for p in problems))


# ============================================================ A. ownership


DEFINITION_COLUMNS = (
    "api_name", "label", "field_type", "max_length", "min_value", "max_value",
    "picklist_key", "lookup_target", "lookup_filter", "values_note", "origin",
    "source_ref", "description", "use_case", "computed_formula", "computed_expr",
    "origin_module", "status", "deleted_at", "deleted_by", "extension",
)


def _clone(db, definition: FieldDefinition, scope: str, label: str) -> FieldDefinition:
    copy = FieldDefinition(**{c: getattr(definition, c) for c in DEFINITION_COLUMNS})
    copy.scope_key = scope
    copy.label = label
    db.add(copy)
    db.flush()
    return copy


def dissolve_pipeline_scope(db, log: list[str]) -> None:
    # G1 first: the Deal's End Client stops owning a value, so the split below
    # sees the Lead as its only owner.
    for name in sorted(LIVE_ON_DEAL):
        placement = db.scalar(
            select(FieldPlacement).where(
                FieldPlacement.module_key == "deals", FieldPlacement.api_name == name
            )
        )
        read_through_section = db.scalar(
            select(Section).where(
                Section.module_key == "deals", Section.label == READ_THROUGH_SECTION
            )
        )
        placement.value_mode = "read_through"
        placement.storage = None
        placement.editable = False
        placement.value_locked = False
        placement.stage_scoped = "none"
        placement.section_id = read_through_section.id
        placement.sort_order = 1 + max(
            db.scalars(
                select(FieldPlacement.sort_order).where(
                    FieldPlacement.section_id == read_through_section.id
                )
            ),
            default=0,
        )
        log.append(f"A  deals.{name}: shown live from the Lead (G1)")

    for definition in list(
        db.scalars(select(FieldDefinition).where(FieldDefinition.scope_key == "pipeline"))
    ):
        placements = list(
            db.scalars(select(FieldPlacement).where(FieldPlacement.definition_id == definition.id))
        )
        owners = sorted(
            (p for p in placements if p.value_mode in ("own", "carry_forward")),
            key=lambda p: OWNER_ORDER.get(p.module_key, 9),
        )
        if not owners:
            raise Stop(f"  - {definition.api_name}: no module holds its value")
        keeper, *others = owners
        definition.scope_key = keeper.module_key
        if keeper.label_override:
            definition.label = keeper.label_override
            keeper.label_override = None
        for other in others:
            copy = _clone(db, definition, other.module_key, other.label_override or definition.label)
            other.definition_id = copy.id
            other.label_override = None
        if others:
            log.append(
                f"A  {definition.api_name}: split — "
                + ", ".join(p.module_key for p in owners)
            )
        # Read-through placements keep pointing at the keeper: that is what
        # "shown live from the Lead" means in the model.


# ============================================================ C. partners


def promote_partner_sections(db, log: list[str]) -> None:
    partners = db.get(Module, "partners")
    for offset, (section_label, (key, label, parent, hidden)) in enumerate(PARTNER_MODULES.items()):
        db.add(
            Module(
                module_key=key,
                label=label,
                sort_order=partners.sort_order,
                active=True,
                hidden=hidden,
                setup_parent=parent,
            )
        )
        db.flush()
        layout = db.scalar(select(Layout).where(Layout.module_key == key, Layout.is_default))
        section = db.scalar(
            select(Section).where(Section.module_key == "partners", Section.label == section_label)
        )
        section.module_key = key
        section.layout_id = layout.id
        moved = 0
        for placement in db.scalars(select(FieldPlacement).where(FieldPlacement.section_id == section.id)):
            placement.module_key = key
            placement.scope_key = key
            definition = db.get(FieldDefinition, placement.definition_id)
            definition.scope_key = key
            definition.origin_module = key
            moved += 1
        log.append(f"C  {section_label} -> module {key}{' (hidden)' if hidden else ''}: {moved} fields")


# ============================================================ D. picklists


def picklists(db, log: list[str]) -> None:
    for key, label in GLOBAL_PICKLISTS.items():
        picklist = db.get(Picklist, key)
        picklist.is_global = True
        picklist.label = label
    log.append(f"D  global: {', '.join(GLOBAL_PICKLISTS)}")
    for key, label in LOCAL_RELABEL.items():
        db.get(Picklist, key).label = label

    source = db.get(Picklist, STATUS_SOURCE)
    for module_key, (key, label, leave_out) in STATUS_LISTS.items():
        db.add(Picklist(picklist_key=key, label=label, active=True, sort_order=source.sort_order))
        db.flush()
        for value in source.values:
            if value.key in leave_out:
                continue
            db.add(
                PicklistValue(
                    picklist_key=key,
                    key=value.key,
                    label=value.label,
                    sort_order=value.sort_order,
                    active=value.active,
                    is_system=value.key in SYSTEM_STATUS_KEYS,
                )
            )
        placement = db.scalar(
            select(FieldPlacement).where(
                FieldPlacement.module_key == module_key, FieldPlacement.api_name == "lead_status"
            )
        )
        db.get(FieldDefinition, placement.definition_id).picklist_key = key
        log.append(f"D  {module_key}.lead_status -> its own list {key} ({label})")

    for value in source.values:
        value.is_system = value.key in SYSTEM_STATUS_KEYS
        if value.key in RETIRED_ON_LEADS:
            value.active = False
    log.append(f"D  {STATUS_SOURCE}: {', '.join(sorted(RETIRED_ON_LEADS))} retired on Leads")


# ============================================================ E, F


def hide_modules(db, log: list[str]) -> None:
    for key in HIDDEN_MODULES:
        module = db.get(Module, key)
        if module is not None:
            module.hidden = True
    log.append(f"E  hidden: {', '.join(HIDDEN_MODULES)}, partner_scorecards")


def rename_read_through_sections(db, log: list[str]) -> None:
    for section in db.scalars(select(Section).where(Section.label == READ_THROUGH_SECTION)):
        section.label = FROM_THE_LEAD
        log.append(f"F  {section.module_key}: section renamed to {FROM_THE_LEAD!r}")


# ============================================================ B. mappings


def conversion_mappings(db, log: list[str]) -> None:
    order = 0
    for path, rows in SYSTEM_ROWS.items():
        for target_module, target, note in rows:
            order += 1
            db.add(
                ConversionMapping(
                    path=path, kind="system", target_module=target_module,
                    target_api_name=target, locked=True, note=note, sort_order=order,
                )
            )
    for path, source_module, source, target, transform, locked in COPY_ROWS:
        order += 1
        db.add(
            ConversionMapping(
                path=path, kind="copy", source_module=source_module, source_api_name=source,
                target_module="deals", target_api_name=target, transform=transform,
                locked=locked, sort_order=order,
            )
        )
    log.append(f"B  {order} conversion mapping rows")


# ============================================================ the invariant


OWNER_INDEX = (
    "CREATE UNIQUE INDEX IF NOT EXISTS uq_field_placements_one_owner "
    "ON field_placements (definition_id) WHERE value_mode <> 'read_through'"
)


def enforce_single_owner(db, log: list[str]) -> None:
    left = db.scalar(select(FieldDefinition.id).where(FieldDefinition.scope_key == "pipeline"))
    if left is not None:
        raise Stop("  - a definition is still in the shared pipeline scope")
    db.execute(text(OWNER_INDEX))
    log.append("   every definition has exactly one owning module (index created)")


# ============================================================ the check


COMPARED = (
    "section", "order", "label", "type", "picklist", "lookup_target", "capture_stage",
    "capture_any_stage", "mandatory_from", "blocks_transition", "requirement",
    "required_on_skip", "required_on_create", "visibility_condition", "condition",
    "computed_formula", "value_mode", "editable", "read_through_from", "read_through_via",
    "register_module", "anchor_field", "anchor_position", "layout_span", "stage_scoped",
    "computed_expr", "min_value", "max_value", "max_length",
)

PARTNER_SECTION_MODULE = {label: key for label, (key, *_rest) in PARTNER_MODULES.items()}


def compare(before: list[dict[str, Any]], after: list[dict[str, Any]]) -> list[str]:
    """Every difference that is not on the expected list."""

    def key_before(row: dict[str, Any]) -> tuple[str, str, str]:
        module = row["module"]
        if module == "partners":
            module = PARTNER_SECTION_MODULE.get(row["section"], module)
        return (module, row["section"], row["api_name"])

    def key_after(row: dict[str, Any]) -> tuple[str, str, str]:
        section = row["section"]
        return (row["module"], section, row["api_name"])

    old = {key_before(r): r for r in before}
    new = {key_after(r): r for r in after}

    def normalise(k):
        module, section, name = k
        if section == FROM_THE_LEAD or section == READ_THROUGH_SECTION:
            return (module, "(from the lead)", name)
        return k

    old = {normalise(k): v for k, v in old.items()}
    new = {normalise(k): v for k, v in new.items()}
    unexpected: list[str] = []

    # G1 moved one field between sections — pair it by (module, api_name).
    for name in LIVE_ON_DEAL:
        o = next((k for k in old if k[0] == "deals" and k[2] == name), None)
        n = next((k for k in new if k[0] == "deals" and k[2] == name), None)
        if o and n:
            before_row, after_row = old.pop(o), new.pop(n)
            for column in ("label", "type", "lookup_target", "register_module"):
                if before_row.get(column) != after_row.get(column):
                    unexpected.append(f"deals.{name}: {column} changed")
            if after_row["value_mode"] != "read_through" or after_row["read_through_from"] != "leads":
                unexpected.append(f"deals.{name}: not shown live from the Lead")

    for k in sorted(set(old) | set(new)):
        if k not in new:
            unexpected.append(f"{'.'.join(k)}: disappeared")
            continue
        if k not in old:
            unexpected.append(f"{'.'.join(k)}: appeared")
            continue
        for column in COMPARED:
            a, b = old[k].get(column), new[k].get(column)
            if a == b:
                continue
            if column == "section" and k[1] == "(from the lead)":
                continue
            if column == "register_module" and b == k[0] and k[0] in PARTNER_SECTION_MODULE.values():
                continue
            if column == "picklist" and k[2] == "lead_status" and k[0] in STATUS_LISTS:
                continue
            unexpected.append(f"{'.'.join(k)}: {column} {a!r} -> {b!r}")
    return unexpected


def picklist_changes(db) -> list[str]:
    """Local lists still serving more than one active definition."""
    rows = db.execute(
        text(
            "SELECT d.picklist_key, count(DISTINCT d.id) FROM field_definitions d "
            "JOIN field_placements p ON p.definition_id = d.id "
            "JOIN picklists pl ON pl.picklist_key = d.picklist_key "
            "JOIN modules m ON m.module_key = p.module_key "
            "WHERE d.status = 'active' AND p.status = 'active' AND NOT pl.is_global "
            "AND NOT m.hidden GROUP BY 1 HAVING count(DISTINCT d.id) > 1"
        )
    ).all()
    return [f"{key}: local but used by {n} fields" for key, n in rows]


# ============================================================ main


def run(db) -> list[str]:
    log: list[str] = []
    preflight(db)
    before = resolved_fields(db)
    dissolve_pipeline_scope(db, log)
    promote_partner_sections(db, log)
    picklists(db, log)
    hide_modules(db, log)
    rename_read_through_sections(db, log)
    conversion_mappings(db, log)
    db.flush()
    enforce_single_owner(db, log)
    after = resolved_fields(db)

    problems = compare(before, after)
    problems += picklist_changes(db)
    log.append(f"   spec compared: {len(before)} fields before, {len(after)} after")
    if problems:
        raise Stop("the spec changed in ways the approved list does not allow:\n"
                   + "\n".join(f"  - {p}" for p in problems))
    log.append("   only the expected differences — a user sees nothing change")
    return log


def main() -> int:
    apply = "--apply" in sys.argv
    db = SessionLocal()
    try:
        try:
            log = run(db)
        except Stop as stop:
            db.rollback()
            print(f"STOPPED — nothing was written.\n{stop}")
            return 1
        print("\n".join(log))
        if not apply:
            db.rollback()
            print("\nDry run — nothing written. Re-run with --apply.")
            return 0
        from app.routers.metadata import _publish, _validation_out, build_snapshot

        validation = _validation_out(build_snapshot(db))
        if not validation.ok:
            db.rollback()
            print("STOPPED — the draft does not validate:")
            for error in validation.errors:
                print(f"  - {error}")
            return 1
        db.commit()
        result = _publish(
            db,
            build_snapshot(db),
            "Metadata v2 — every field owned by one module; Deal Registrations and "
            "Conflicts are modules; one status list per module",
            None,
        )
        print(f"\nCommitted and published: version {getattr(result, 'version_no', result)}")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
