"""
Partner lifecycle — the register half of migration 0025.

    python partner_lifecycle_metadata.py             # dry run: what would change
    python partner_lifecycle_metadata.py --apply
    python partner_lifecycle_metadata.py --revert

Run AFTER `alembic upgrade head` (every storage='column' placement below needs
the column 0025 adds), then:

    python regenerate_spec.py --apply

WHAT CHANGES
------------
1. partners__registration_status gains WITHDRAWN "Withdrawn". It is set only by
   the Withdraw action; a PUT naming it is refused (routers/registrations.py).

2. closed_lost_reason_code gains PARTNER_WITHDRAWN "Partner withdrew" — not the
   same thing as "Partner conflict", which is the loser of an adjudication.

3. The three adjudication criteria become picklists:
     Who Registered First          Registration A / Registration B / Same day —
                                   SYSTEM, derived from the Submitted Dates
     Stronger Client Relationship  A / B / Comparable / Neither has an
                                   established relationship
     Better Delivery Capability    A / B / Comparable / Neither meets the
                                   requirement

4. DEAL REGISTRATION gains Withdrawn Date and Withdrawal Reason (System, shown
   only when the status is Withdrawn). CONFLICT ADJUDICATION gains Decision
   Rationale & Evidence (required once a Decision is set — enforced by the
   server) and Evidence Link.

NO DDL. Positions are made by shifting the module's later placements down one,
so every section stays a contiguous run (see pursuit_group_metadata.py).
"""

from __future__ import annotations

import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from sqlalchemy import func, select  # noqa: E402

from app.database import SessionLocal, engine  # noqa: E402

engine.echo = False

from app.models import FieldDefinition, FieldPlacement, Picklist, PicklistValue  # noqa: E402

MODULE = "partners"
WITHDRAWN_LABEL = "Withdrawn"

NEW_PICKLISTS = {
    "partners__who_registered_first": (
        "Who Registered First",
        [("REGISTRATION_A", "Registration A"), ("REGISTRATION_B", "Registration B"), ("SAME_DAY", "Same day")],
    ),
    "partners__relationship_assessment": (
        "Stronger Client Relationship",
        [
            ("REGISTRATION_A", "Registration A"),
            ("REGISTRATION_B", "Registration B"),
            ("COMPARABLE", "Comparable"),
            ("NEITHER", "Neither has an established relationship"),
        ],
    ),
    "partners__delivery_assessment": (
        "Better Delivery Capability",
        [
            ("REGISTRATION_A", "Registration A"),
            ("REGISTRATION_B", "Registration B"),
            ("COMPARABLE", "Comparable"),
            ("NEITHER", "Neither meets the requirement"),
        ],
    ),
}

NEW_VALUES = [
    ("partners__registration_status", "WITHDRAWN", WITHDRAWN_LABEL),
    ("closed_lost_reason_code", "PARTNER_WITHDRAWN", "Partner withdrew"),
]

#: api_name -> (picklist, description, requirement, editable)
CRITERIA = {
    "who_registered_first": (
        "partners__who_registered_first",
        "Which registration was submitted first. Set by ARK from the two Submitted Dates — never typed.",
        "System",
        False,
    ),
    "stronger_client_relationship": (
        "partners__relationship_assessment",
        "Which partner holds the stronger relationship with the End Client.",
        "Mandatory",
        True,
    ),
    "better_delivery_capability": (
        "partners__delivery_assessment",
        "Which partner is better able to deliver this project.",
        "Mandatory",
        True,
    ),
}

#: For --revert: what the three criteria were before.
CRITERIA_BEFORE = {
    "who_registered_first": "Assessment against adjudication criterion one.",
    "stronger_client_relationship": "Assessment against adjudication criterion two.",
    "better_delivery_capability": "Assessment against adjudication criterion three.",
}

WITHDRAWN_ONLY = f"registration_status == '{WITHDRAWN_LABEL}'"

NEW_FIELDS = [
    dict(
        api_name="withdrawn_date",
        label="Withdrawn Date",
        field_type="date",
        after="registration_status",
        requirement="System",
        editable=False,
        visibility=WITHDRAWN_ONLY,
        description="The day ARK recorded the partner's withdrawal. Set by the Withdraw action.",
        use_case="§6.2 — a withdrawn registration no longer confers exclusivity.",
    ),
    dict(
        api_name="withdrawal_reason",
        label="Withdrawal Reason",
        field_type="longtext",
        after="withdrawn_date",
        requirement="System",
        editable=False,
        visibility=WITHDRAWN_ONLY,
        description="Why the partner withdrew, as recorded by the Withdraw action.",
        use_case="§6.2 — kept with the registration so the pursuit's history explains itself.",
    ),
    dict(
        api_name="decision_rationale",
        label="Decision Rationale & Evidence",
        field_type="longtext",
        after="primary_registration",
        requirement="Conditional",
        editable=True,
        visibility=None,
        description=(
            "Why the decision was taken, and the proof behind it. Required once a Decision is recorded — "
            "the server refuses a decision without it."
        ),
        use_case="§6.2 — an adjudication both partners may contest must be explainable afterwards.",
    ),
    dict(
        api_name="evidence_link",
        label="Evidence Link",
        field_type="url",
        after="decision_rationale",
        requirement="Optional",
        editable=True,
        visibility=None,
        description="A link to the proof — an email, meeting minutes, a document on the shared drive. Nothing is uploaded.",
        use_case="§6.2 — points a reviewer at the evidence without copying it into the CRM.",
    ),
]


def definition(db, api_name: str) -> FieldDefinition | None:
    return db.scalars(
        select(FieldDefinition).where(FieldDefinition.api_name == api_name).where(FieldDefinition.scope_key == MODULE)
    ).first()


def placement(db, api_name: str) -> FieldPlacement | None:
    return db.scalars(
        select(FieldPlacement).where(FieldPlacement.module_key == MODULE).where(FieldPlacement.api_name == api_name)
    ).first()


def insert_after(db, anchor: FieldPlacement, **columns) -> FieldPlacement:
    for later in db.scalars(
        select(FieldPlacement)
        .where(FieldPlacement.module_key == anchor.module_key)
        .where(FieldPlacement.sort_order > anchor.sort_order)
    ):
        later.sort_order += 1
    row = FieldPlacement(
        module_key=anchor.module_key,
        scope_key=anchor.scope_key,
        section_id=anchor.section_id,
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


def apply(db) -> list[str]:
    log: list[str] = []

    # ------------------------------------------------------ 1-3. picklists
    for key, (label, values) in NEW_PICKLISTS.items():
        if db.get(Picklist, key) is None:
            top = db.scalar(select(func.max(Picklist.sort_order))) or 0
            db.add(Picklist(picklist_key=key, label=label, active=True, sort_order=top + 1))
            db.flush()
            log.append(f"picklist {key} created")
        existing = {v.key: v for v in db.scalars(select(PicklistValue).where(PicklistValue.picklist_key == key))}
        for order, (value_key, value_label) in enumerate(values, start=1):
            if value_key not in existing:
                db.add(PicklistValue(picklist_key=key, key=value_key, label=value_label, sort_order=order, active=True))
                log.append(f"{key}: + {value_key} '{value_label}'")
            elif not existing[value_key].active:
                existing[value_key].active = True
                log.append(f"{key}: {value_key} reactivated")

    for key, value_key, value_label in NEW_VALUES:
        values = list(db.scalars(select(PicklistValue).where(PicklistValue.picklist_key == key)))
        found = next((v for v in values if v.key == value_key), None)
        if found is None:
            db.add(
                PicklistValue(
                    picklist_key=key,
                    key=value_key,
                    label=value_label,
                    sort_order=max((v.sort_order for v in values), default=0) + 1,
                    active=True,
                )
            )
            log.append(f"{key}: + {value_key} '{value_label}'")
        elif not found.active:
            found.active = True
            log.append(f"{key}: {value_key} reactivated")
    db.flush()

    # ------------------------------------------------- 3. criteria types
    for api_name, (picklist_key, description, requirement, editable) in CRITERIA.items():
        d = definition(db, api_name)
        if d is None:
            raise SystemExit(f"partners.{api_name} has no definition — is this the ARK register?")
        if d.field_type != "picklist" or d.picklist_key != picklist_key:
            d.field_type, d.picklist_key, d.max_length = "picklist", picklist_key, None
            log.append(f"partners.{api_name}: text -> picklist {picklist_key}")
        if d.description != description:
            d.description = description
        p = placement(db, api_name)
        if p.requirement != requirement or p.editable != editable:
            p.requirement, p.editable = requirement, editable
            log.append(f"partners.{api_name}: {requirement}{'' if editable else ', read-only'}")

    # ---------------------------------------------------- 4. new fields
    for spec in NEW_FIELDS:
        d = definition(db, spec["api_name"])
        if d is None:
            d = FieldDefinition(
                scope_key=MODULE,
                api_name=spec["api_name"],
                label=spec["label"],
                field_type=spec["field_type"],
                description=spec["description"],
                use_case=spec["use_case"],
                origin="Playbook",
                source_ref="§6.2",
                origin_module=MODULE,
                status="active",
            )
            db.add(d)
            db.flush()
            log.append(f"partners.{spec['api_name']}: definition created ({spec['field_type']})")
        elif d.status != "active":
            d.status, d.deleted_at, d.deleted_by = "active", None, None
            log.append(f"partners.{spec['api_name']}: definition reactivated")

        if placement(db, spec["api_name"]) is None:
            anchor = placement(db, spec["after"])
            if anchor is None:
                raise SystemExit(f"partners.{spec['after']} is not placed — cannot position {spec['api_name']}")
            insert_after(
                db,
                anchor,
                definition_id=d.id,
                api_name=spec["api_name"],
                capture_stage=None,
                capture_any_stage=False,
                mandatory_from=None,
                blocks_transition=None,
                requirement=spec["requirement"],
                required_on_skip=None,
                visibility_condition=spec["visibility"],
                condition=None,
                value_mode="own",
                value_locked=False,
                editable=spec["editable"],
                storage="column",
                stage_scoped="none",
                status="active",
                provenance="register",
            )
            log.append(f"partners.{spec['api_name']}: placed after {spec['after']}")

    return log


def revert(db) -> list[str]:
    log: list[str] = []
    for spec in reversed(NEW_FIELDS):
        p = placement(db, spec["api_name"])
        if p is not None:
            remove_placement(db, p)
            log.append(f"partners.{spec['api_name']}: placement removed (column and values kept)")
        d = definition(db, spec["api_name"])
        if d is not None:
            db.delete(d)
            log.append(f"partners.{spec['api_name']}: definition removed")

    for api_name, description in CRITERIA_BEFORE.items():
        d = definition(db, api_name)
        d.field_type, d.picklist_key, d.description = "text", None, description
        p = placement(db, api_name)
        p.requirement, p.editable = "Mandatory", True
        log.append(f"partners.{api_name}: back to text")

    for key, value_key, _ in NEW_VALUES:
        row = db.scalars(
            select(PicklistValue).where(PicklistValue.picklist_key == key).where(PicklistValue.key == value_key)
        ).first()
        if row is not None:
            db.delete(row)
            log.append(f"{key}: {value_key} removed")

    for key in NEW_PICKLISTS:
        for row in db.scalars(select(PicklistValue).where(PicklistValue.picklist_key == key)):
            db.delete(row)
        picklist = db.get(Picklist, key)
        if picklist is not None:
            db.flush()
            db.delete(picklist)
            log.append(f"picklist {key} removed")
    db.flush()
    return log


def main() -> int:
    mode = "apply" if "--apply" in sys.argv else "revert" if "--revert" in sys.argv else "dry"
    with SessionLocal() as db:
        log = revert(db) if mode == "revert" else apply(db)
        print(f"Partner lifecycle — {mode}")
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
