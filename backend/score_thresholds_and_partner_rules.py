"""
Scores get a 1–10 range; the partner fields get the rule they were missing.

    python score_thresholds_and_partner_rules.py             dry run: report and validate
    python score_thresholds_and_partner_rules.py --apply     write, then publish

Needs migration 0023 (field_definitions.min_value / max_value).

1. THRESHOLDS — decided 14 Sep 2026: 1 to 10, both ends included.
     accounts.partner_satisfaction_score   min 1, max 10
     contacts.relationship_score           min 1, max 10
   A threshold is the DEFINITION's, so it holds on every module that places the
   field. Records already outside the range are reported, not changed: a person
   corrects them on their next save, which the API will insist on.

2. THE "CONDITIONAL WITH NO RULE" GAP on Accounts — decided 14 Sep 2026.
   Partner Tier, Partner Type and Engagement Cadence were Conditional with no
   condition, so they were optional everywhere (Spec Health: `unruled`). They
   are now required exactly when they show: the same partner-type expression
   that is their visibility_condition becomes their condition.

   Relationship Score on Contacts had the same gap and is made plainly
   Optional — nothing in the register says when a score becomes necessary.
"""

from __future__ import annotations

import argparse
import sys

from sqlalchemy import or_, select

from app.database import SessionLocal
from app.models import Account, Contact, FieldDefinition, FieldPlacement

THRESHOLDS: tuple[tuple[str, str, float, float], ...] = (
    ("accounts", "partner_satisfaction_score", 1, 10),
    ("contacts", "relationship_score", 1, 10),
)

PARTNER_CONDITION = (
    "account_type includes 'Partner / SI'"
    " || account_type includes 'Consultant / Specifier'"
    " || account_type includes 'OEM / Technology Partner'"
)
PARTNER_REQUIRED = ("partner_tier", "partner_type", "engagement_cadence")

MAKE_OPTIONAL = (("contacts", "relationship_score"),)

#: For the out-of-range report: module -> (model, id column).
TABLES = {"accounts": (Account, "account_id"), "contacts": (Contact, "contact_id")}


def placement_for(db, module: str, api_name: str) -> FieldPlacement | None:
    return db.scalar(
        select(FieldPlacement).where(
            FieldPlacement.module_key == module,
            FieldPlacement.api_name == api_name,
        )
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="write the changes and publish")
    parser.add_argument("--user", default=None, help="acting user_id for the published version")
    args = parser.parse_args()

    db = SessionLocal()
    changes: list[str] = []
    problems: list[str] = []
    notes: list[str] = []

    try:
        # ---- 1. thresholds
        for module, api_name, low, high in THRESHOLDS:
            placement = placement_for(db, module, api_name)
            if placement is None:
                problems.append(f"{module}.{api_name}: no placement on this module")
                continue
            definition = db.get(FieldDefinition, placement.definition_id)
            sharers = db.scalars(
                select(FieldPlacement.module_key).where(
                    FieldPlacement.definition_id == definition.id,
                    FieldPlacement.module_key != module,
                )
            ).all()
            if sharers:
                notes.append(
                    f"{api_name}: the range also applies on {', '.join(sorted(set(sharers)))}, "
                    f"which places the same definition"
                )
            if definition.min_value != low or definition.max_value != high:
                changes.append(
                    f"{module}.{api_name}: range {definition.min_value}–{definition.max_value} "
                    f"-> {low:g}–{high:g}"
                )
                definition.min_value = low
                definition.max_value = high

            model, id_column = TABLES[module]
            column = getattr(model, api_name)
            outside = db.execute(
                select(getattr(model, id_column), column).where(
                    column.is_not(None), or_(column < low, column > high)
                )
            ).all()
            for record_id, value in outside:
                notes.append(f"{record_id}: {api_name} = {value}, outside {low:g}–{high:g}")

        # ---- 2a. partner fields: required when shown
        for api_name in PARTNER_REQUIRED:
            placement = placement_for(db, "accounts", api_name)
            if placement is None:
                problems.append(f"accounts.{api_name}: no placement on this module")
                continue
            if placement.requirement != "Conditional" or placement.condition != PARTNER_CONDITION:
                changes.append(
                    f"accounts.{api_name}: {placement.requirement} / condition "
                    f"{placement.condition!r} -> Conditional / partner types"
                )
                placement.requirement = "Conditional"
                placement.condition = PARTNER_CONDITION

        # ---- 2b. optional
        for module, api_name in MAKE_OPTIONAL:
            placement = placement_for(db, module, api_name)
            if placement is None:
                problems.append(f"{module}.{api_name}: no placement on this module")
                continue
            if placement.requirement != "Optional" or placement.condition is not None:
                changes.append(f"{module}.{api_name}: {placement.requirement} -> Optional")
                placement.requirement = "Optional"
                placement.condition = None

        print(f"{len(changes)} change(s):")
        for line in changes:
            print(f"  {line}")
        if notes:
            print(f"\n{len(notes)} note(s):")
            for line in notes:
                print(f"  {line}")
        if problems:
            print(f"\n{len(problems)} problem(s):")
            for line in problems:
                print(f"  {line}")

        db.flush()
        from app.metadata_spec import build_snapshot
        from app.routers.metadata import _publish, _validation_out

        validation = _validation_out(build_snapshot(db))
        print(f"\npublish validation: ok={validation.ok}, {len(validation.errors)} error(s)")
        for line in validation.errors:
            print(f"  ERROR {line}")

        if not args.apply:
            db.rollback()
            print("\nDry run — nothing written. Re-run with --apply.")
            return 1 if problems or not validation.ok else 0

        if problems or not validation.ok:
            db.rollback()
            print("\nNOT APPLIED — fix the problems above first.")
            return 1

        result = _publish(
            db,
            build_snapshot(db),
            "Scores 1–10 (Partner Satisfaction, Relationship); Partner Tier/Type/"
            "Engagement Cadence required on partner accounts; Relationship Score Optional",
            args.user,
        )
        db.commit()
        print(f"\nApplied and published: version {result.version.version_no}")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
