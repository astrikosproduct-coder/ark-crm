"""
Pursuit Groups and the revenue rule — the register half of migration 0020.

    python pursuit_group_metadata.py             # dry run: what would change
    python pursuit_group_metadata.py --apply
    python pursuit_group_metadata.py --revert

Then:  python regenerate_spec.py --apply

Run AFTER `alembic upgrade head` — every storage='column' placement below needs
the column 0020 adds, and a placement without its column is exactly the silent
data loss Deal Status suffered.

WHAT CHANGES
------------
1. leads.is_primary_pursuit becomes SYSTEM. It was a Mandatory checkbox a BD
   could untick, which contradicted the group that now decides it; and as a
   default-true checkbox its "blocks 0 → 1" could never fail anyway. It stays
   visible, read-only, and gains an instance on Opportunities and Deals, so the
   flag survives conversion.

2. pursuit_group — a new System lookup on all three pipeline modules, filled by
   the server. lookup_target 'pursuit_group'.

3. leads.not_duplicate_reason — the answer given when "this End Client already
   has an open pursuit — join its group?" is declined.

4. leads.parent_pursuit — LOGICALLY DELETED. The group replaces it. Column and
   values stay; Administration's Restore brings it back.

5. fx_rate_at_entry — Conditional on the Lead (required, and shown, when the
   currency is not USD; blocks 0 → 1 like currency does), and READ THROUGH on
   Opportunities and Deals beside currency, so one pursuit has one rate. The
   type/label change itself was made by 0020 alongside the column.

6. partners__decision gains BOTH_PURSUED ("Both pursued"), and CONFLICT
   ADJUDICATION gains primary_registration, required and shown only for it.

7. The three revenue fields say, in their help text, that they are THE number
   that counts — see app/revenue.py.

NO DDL, and positions are made by shifting the module's later placements down
one, so every section stays a contiguous run (see leads_record_state.py).
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from sqlalchemy import select  # noqa: E402

from app.database import SessionLocal, engine  # noqa: E402

engine.echo = False

from app.models import (  # noqa: E402
    FieldDefinition,
    FieldPlacement,
    Picklist,
    PicklistValue,
    Section,
)

NOT_USD = "currency != 'USD'"
BOTH_PURSUED_LABEL = "Both pursued"

REVENUE_HELP = {
    "estimated_value": (
        "Indicative deal value before bid financials exist. THIS is the number a Lead adds to "
        "pipeline (Stages 0-3) — no other field is ever substituted for it. Keep it current."
    ),
    "total_value_tcv": (
        "Computed total contract value across the full term. THIS is the number an Opportunity "
        "adds to pipeline (Stages 4-6). Update the TCV lines to the agreed terms at Stage 6."
    ),
    "contract_value": (
        "Final contract value at booking. THIS is a Deal's Actual Revenue (Stages 7-9) and the "
        "basis of revenue recognition."
    ),
}

#: The descriptions these replace, for --revert.
REVENUE_HELP_BEFORE = {
    "estimated_value": "Indicative deal value before bid financials exist.",
    "total_value_tcv": "Computed total contract value across the full term.",
    "contract_value": "Final contract value at booking.",
}

# deleted_by stays NULL: a script did this, not a person. See
# close_month_record_state.py for why an honest blank beats a borrowed name.
ACTOR = None


def definition(db, api_name: str, scope: str = "pipeline") -> FieldDefinition | None:
    return db.scalars(
        select(FieldDefinition).where(FieldDefinition.api_name == api_name).where(FieldDefinition.scope_key == scope)
    ).first()


def placement(db, module: str, api_name: str) -> FieldPlacement | None:
    return db.scalars(
        select(FieldPlacement).where(FieldPlacement.module_key == module).where(FieldPlacement.api_name == api_name)
    ).first()


def section(db, module: str, label: str) -> Section | None:
    return db.scalars(select(Section).where(Section.module_key == module).where(Section.label == label)).first()


def insert_after(db, anchor: FieldPlacement, **columns) -> FieldPlacement:
    """A new placement directly after `anchor`, in the anchor's section."""
    for later in db.scalars(
        select(FieldPlacement)
        .where(FieldPlacement.module_key == anchor.module_key)
        .where(FieldPlacement.sort_order > anchor.sort_order)
    ):
        later.sort_order += 1
    row = FieldPlacement(
        module_key=anchor.module_key,
        scope_key=anchor.scope_key,
        section_id=columns.pop("section_id", anchor.section_id),
        sort_order=anchor.sort_order + 1,
        **columns,
    )
    db.add(row)
    db.flush()
    return row


def remove_placement(db, row: FieldPlacement) -> None:
    for later in db.scalars(
        select(FieldPlacement)
        .where(FieldPlacement.module_key == row.module_key)
        .where(FieldPlacement.sort_order > row.sort_order)
    ):
        later.sort_order -= 1
    db.delete(row)
    db.flush()


def ensure_definition(db, log, **columns) -> FieldDefinition:
    existing = definition(db, columns["api_name"], columns["scope_key"])
    if existing is not None:
        if existing.status != "active":
            existing.status, existing.deleted_at, existing.deleted_by = "active", None, None
            log.append(f"{columns['api_name']}: definition reactivated")
        return existing
    row = FieldDefinition(**columns)
    db.add(row)
    db.flush()
    log.append(f"{columns['api_name']}: definition created ({columns['field_type']})")
    return row


SYSTEM_FLAGS = dict(
    capture_stage=0,
    capture_any_stage=False,
    mandatory_from=None,
    blocks_transition=None,
    requirement="System",
    required_on_skip=None,
    visibility_condition=None,
    condition=None,
    value_mode="own",
    value_locked=False,
    editable=False,
    storage="column",
    stage_scoped="none",
    status="active",
)


def apply(db) -> list[str]:
    log: list[str] = []

    # ------------------------------------------------ 1. is_primary_pursuit
    primary_def = definition(db, "is_primary_pursuit")
    primary_def.description = (
        "Whether this record's pursuit is the one that counts toward pipeline. Set by ARK from the "
        "Pursuit Group — change the primary on the group, never here."
    )
    primary_def.values_note = "System — true unless a Pursuit Group names another pursuit as primary"
    lead_primary = placement(db, "leads", "is_primary_pursuit")
    if lead_primary.requirement != "System":
        for key, value in SYSTEM_FLAGS.items():
            setattr(lead_primary, key, value)
        log.append("leads.is_primary_pursuit: Mandatory checkbox -> System, read-only")

    # ------------------------------------------------------ 2. pursuit_group
    group_def = ensure_definition(
        db,
        log,
        scope_key="pipeline",
        api_name="pursuit_group",
        label="Pursuit Group",
        field_type="lookup",
        lookup_target="pursuit_group",
        description=(
            "The group of pursuits chasing the same project at the same End Client through different "
            "partners. Only the group's primary pursuit counts toward pipeline."
        ),
        use_case="§7.2 — duplicates must not inflate pipeline value; only primary pursuits roll up.",
        origin="Playbook",
        source_ref="§7.2",
        origin_module="leads",
        status="active",
    )
    if placement(db, "leads", "pursuit_group") is None:
        insert_after(
            db, lead_primary, definition_id=group_def.id, api_name="pursuit_group", provenance="register", **SYSTEM_FLAGS
        )
        log.append("leads.pursuit_group: placed after is_primary_pursuit")

    for module in ("opportunities", "deals"):
        # Beside Deal/Lead Status, in whatever that section is called today.
        anchor = placement(db, module, "lead_status")
        target = db.get(Section, anchor.section_id)
        if placement(db, module, "is_primary_pursuit") is None:
            anchor = insert_after(
                db,
                anchor,
                section_id=target.id,
                definition_id=primary_def.id,
                api_name="is_primary_pursuit",
                provenance="own_instance",
                **SYSTEM_FLAGS,
            )
            log.append(f"{module}.is_primary_pursuit: own instance in RECORD STATE")
        else:
            anchor = placement(db, module, "is_primary_pursuit")
        if placement(db, module, "pursuit_group") is None:
            insert_after(
                db,
                anchor,
                section_id=target.id,
                definition_id=group_def.id,
                api_name="pursuit_group",
                provenance="own_instance",
                **SYSTEM_FLAGS,
            )
            log.append(f"{module}.pursuit_group: own instance in RECORD STATE")

    # ----------------------------------------------- 3. not_duplicate_reason
    reason_def = ensure_definition(
        db,
        log,
        scope_key="pipeline",
        api_name="not_duplicate_reason",
        label="Not a Duplicate — Reason",
        field_type="longtext",
        description=(
            "Why this lead is a different project from another open pursuit at the same End Client. "
            "Asked when the lead is saved beside one and not joined to its Pursuit Group."
        ),
        use_case="§7.2 — a second pursuit for the same client is either grouped or explained.",
        origin="Playbook",
        source_ref="§7.2",
        origin_module="leads",
        status="active",
    )
    if placement(db, "leads", "not_duplicate_reason") is None:
        insert_after(
            db,
            placement(db, "leads", "pursuit_group"),
            definition_id=reason_def.id,
            api_name="not_duplicate_reason",
            provenance="register",
            **{**SYSTEM_FLAGS, "requirement": "Optional", "editable": True},
        )
        log.append("leads.not_duplicate_reason: placed after pursuit_group")

    # ---------------------------------------------------- 4. parent_pursuit
    stamp = datetime.now(timezone.utc)
    parent_def = definition(db, "parent_pursuit")
    for row in db.scalars(select(FieldPlacement).where(FieldPlacement.api_name == "parent_pursuit")):
        if row.status != "deleted":
            row.status, row.deleted_at, row.deleted_by, row.deleted_by_cascade = "deleted", stamp, ACTOR, True
            log.append(f"{row.module_key}.parent_pursuit: placement -> deleted (column kept)")
    if parent_def.status != "deleted":
        parent_def.status, parent_def.deleted_at, parent_def.deleted_by = "deleted", stamp, ACTOR
        log.append("parent_pursuit: definition -> deleted (superseded by pursuit_group; no DDL)")

    # ---------------------------------------------------------- 5. fx rate
    fx_def = definition(db, "fx_rate_at_entry")
    fx_def.description = (
        "Local currency units per 1 USD, captured when the pursuit is entered — AED 3.6725. Every USD "
        "pipeline figure for this pursuit divides by it. Not needed for USD."
    )
    lead_fx = placement(db, "leads", "fx_rate_at_entry")
    if lead_fx.condition != NOT_USD:
        lead_fx.requirement = "Conditional"
        lead_fx.condition = NOT_USD
        lead_fx.visibility_condition = NOT_USD
        lead_fx.mandatory_from = 0
        lead_fx.blocks_transition = "0 → 1"
        log.append(f"leads.fx_rate_at_entry: Optional -> Conditional on {NOT_USD!r}, blocks 0 → 1")

    for module in ("opportunities", "deals"):
        if placement(db, module, "fx_rate_at_entry") is not None:
            continue
        currency = placement(db, module, "currency")
        insert_after(
            db,
            currency,
            definition_id=fx_def.id,
            api_name="fx_rate_at_entry",
            capture_stage=0,
            capture_any_stage=False,
            mandatory_from=0,
            blocks_transition="0 → 1",
            requirement="Conditional",
            required_on_skip=False,
            visibility_condition=NOT_USD,
            condition=NOT_USD,
            value_mode="read_through",
            value_locked=False,
            editable=False,
            storage=None,
            stage_scoped="none",
            status="active",
            provenance="read_through",
        )
        log.append(f"{module}.fx_rate_at_entry: read through the Lead, after currency")

    # ------------------------------------------------ 6. Both pursued
    picklist = db.get(Picklist, "partners__decision")
    values = list(db.scalars(select(PicklistValue).where(PicklistValue.picklist_key == picklist.picklist_key)))
    both = next((v for v in values if v.key == "BOTH_PURSUED"), None)
    if both is None:
        db.add(
            PicklistValue(
                picklist_key=picklist.picklist_key,
                key="BOTH_PURSUED",
                label=BOTH_PURSUED_LABEL,
                sort_order=max(v.sort_order for v in values) + 1,
                active=True,
            )
        )
        log.append("partners__decision: + BOTH_PURSUED 'Both pursued'")
    elif not both.active:
        both.active = True
        log.append("partners__decision: BOTH_PURSUED reactivated")

    primary_reg_def = ensure_definition(
        db,
        log,
        scope_key="partners",
        api_name="primary_registration",
        label="Primary Registration",
        field_type="lookup",
        lookup_target="deal_registration",
        description=(
            "When both registrations are pursued, the one whose pursuit counts toward pipeline. Must "
            "be Registration A or Registration B."
        ),
        use_case="§7.2 — both partners are pursued; only the primary pursuit rolls up.",
        origin="Playbook",
        source_ref="§7.2",
        origin_module="partners",
        status="active",
    )
    if placement(db, "partners", "primary_registration") is None:
        insert_after(
            db,
            placement(db, "partners", "decision"),
            definition_id=primary_reg_def.id,
            api_name="primary_registration",
            capture_stage=None,
            capture_any_stage=False,
            mandatory_from=None,
            blocks_transition=None,
            requirement="Conditional",
            required_on_skip=None,
            visibility_condition=f"decision == '{BOTH_PURSUED_LABEL}'",
            condition=f"decision == '{BOTH_PURSUED_LABEL}'",
            value_mode="own",
            value_locked=False,
            editable=True,
            storage="column",
            stage_scoped="none",
            status="active",
            provenance="register",
        )
        log.append("partners.primary_registration: placed after decision")

    # ------------------------------------------------------- 7. help text
    for api_name, text in REVENUE_HELP.items():
        d = definition(db, api_name)
        if d.description != text:
            d.description = text
            log.append(f"{api_name}: help text names it the pipeline's one revenue source")

    return log


def revert(db) -> list[str]:
    log: list[str] = []
    for module, api_name in (
        ("partners", "primary_registration"),
        ("opportunities", "fx_rate_at_entry"),
        ("deals", "fx_rate_at_entry"),
        ("leads", "not_duplicate_reason"),
        ("leads", "pursuit_group"),
        ("opportunities", "pursuit_group"),
        ("deals", "pursuit_group"),
        ("opportunities", "is_primary_pursuit"),
        ("deals", "is_primary_pursuit"),
    ):
        row = placement(db, module, api_name)
        if row is not None:
            remove_placement(db, row)
            log.append(f"{module}.{api_name}: placement removed")

    for api_name, scope in (("pursuit_group", "pipeline"), ("not_duplicate_reason", "pipeline"), ("primary_registration", "partners")):
        d = definition(db, api_name, scope)
        if d is not None:
            db.delete(d)
            log.append(f"{api_name}: definition removed")

    lead_primary = placement(db, "leads", "is_primary_pursuit")
    lead_primary.requirement, lead_primary.editable = "Mandatory", True
    lead_primary.mandatory_from, lead_primary.blocks_transition = 0, "0 → 1"
    primary_def = definition(db, "is_primary_pursuit")
    primary_def.description = "Marks this as the counted record where the same project is chased through several partners."
    primary_def.values_note = "Default true"
    log.append("leads.is_primary_pursuit: back to a Mandatory checkbox")

    for row in db.scalars(select(FieldPlacement).where(FieldPlacement.api_name == "parent_pursuit")):
        row.status, row.deleted_at, row.deleted_by, row.deleted_by_cascade = "active", None, None, False
    parent_def = definition(db, "parent_pursuit")
    parent_def.status, parent_def.deleted_at, parent_def.deleted_by = "active", None, None
    log.append("parent_pursuit: restored")

    lead_fx = placement(db, "leads", "fx_rate_at_entry")
    lead_fx.requirement, lead_fx.condition, lead_fx.visibility_condition = "Optional", None, None
    lead_fx.mandatory_from, lead_fx.blocks_transition = None, None
    definition(db, "fx_rate_at_entry").description = "The rate to USD captured at the moment of entry."
    log.append("leads.fx_rate_at_entry: back to Optional")

    both = db.scalars(
        select(PicklistValue).where(PicklistValue.picklist_key == "partners__decision").where(PicklistValue.key == "BOTH_PURSUED")
    ).first()
    if both is not None:
        db.delete(both)
        log.append("partners__decision: BOTH_PURSUED removed")

    for api_name, text in REVENUE_HELP_BEFORE.items():
        definition(db, api_name).description = text
    log.append("revenue help text restored")
    db.flush()
    return log


def main() -> int:
    mode = "apply" if "--apply" in sys.argv else "revert" if "--revert" in sys.argv else "dry"
    with SessionLocal() as db:
        log = revert(db) if mode == "revert" else apply(db)
        print(f"Pursuit Groups and the revenue rule — {mode}")
        print("=" * 74)
        for line in log or ["nothing to do"]:
            print(f"  {line}")
        if mode == "dry":
            db.rollback()
            print("\nDry run — nothing written. Re-run with --apply.")
        else:
            db.commit()
            print(f"\n{len(log)} change(s) committed.\nNow run:  python regenerate_spec.py --apply")
    return 0


if __name__ == "__main__":
    sys.exit(main())
