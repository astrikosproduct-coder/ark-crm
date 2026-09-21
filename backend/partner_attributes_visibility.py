"""
Accounts — PARTNER ATTRIBUTES shows only for an organisation that can be a partner.

    python partner_attributes_visibility.py             dry run: report, write nothing
    python partner_attributes_visibility.py --apply     write, then publish

THE RULE
--------
Partner Tier, Partner Type, Partner Satisfaction Score and Engagement Cadence
describe a partner. They mean nothing on an End Client or a Sector Specialist,
so each placement gets a visibility_condition that holds when Account Type
carries at least one OTHER type: Partner / SI, Consultant / Specifier or
OEM / Technology Partner.

  * End Client only, Sector Specialist only, or both      -> hidden
  * End Client + Partner / SI (a two-party organisation)  -> shown
  * Account Type blank                                    -> hidden

The condition names the types to SHOW rather than the two to hide, because
account_type is a multiselect and the expression language has `includes` but
no "contains only". Consequence worth knowing: a new Account Type value added
in Administration is hidden from this section until it is added here too.

A visibility condition is a register fact, so it is written to
field_placements and published — never typed into spec/fields.json.
"""

from __future__ import annotations

import argparse
import sys

from sqlalchemy import select

from app.database import SessionLocal
from app.models import FieldPlacement

MODULE = "accounts"

FIELDS = (
    "partner_tier",
    "partner_type",
    "partner_satisfaction_score",
    "engagement_cadence",
)

CONDITION = (
    "account_type includes 'Partner / SI'"
    " || account_type includes 'Consultant / Specifier'"
    " || account_type includes 'OEM / Technology Partner'"
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="write the changes and publish")
    parser.add_argument("--user", default=None, help="acting user_id for the published version")
    args = parser.parse_args()

    db = SessionLocal()
    changes: list[str] = []
    problems: list[str] = []

    try:
        for api_name in FIELDS:
            placement = db.scalar(
                select(FieldPlacement).where(
                    FieldPlacement.module_key == MODULE,
                    FieldPlacement.api_name == api_name,
                )
            )
            if placement is None:
                problems.append(f"{MODULE}.{api_name}: no placement on this module")
                continue
            if placement.visibility_condition == CONDITION:
                continue
            changes.append(
                f"{MODULE}.{api_name}: visibility_condition "
                f"{placement.visibility_condition!r} -> {CONDITION!r}"
            )
            placement.visibility_condition = CONDITION

        print(f"{len(changes)} change(s):")
        for line in changes:
            print(f"  {line}")
        if problems:
            print(f"\n{len(problems)} problem(s):")
            for line in problems:
                print(f"  {line}")

        if not args.apply:
            db.rollback()
            print("\nDry run — nothing written. Re-run with --apply.")
            return 1 if problems else 0

        if problems:
            db.rollback()
            print("\nNOT APPLIED — fix the problems above first.")
            return 1

        db.flush()

        # Same publish path Administration uses: validate, freeze a version,
        # regenerate spec/*.json.
        from app.metadata_spec import build_snapshot
        from app.routers.metadata import _publish

        result = _publish(
            db,
            build_snapshot(db),
            "Accounts: PARTNER ATTRIBUTES shows only when Account Type is not solely "
            "End Client and/or Sector Specialist",
            args.user,
        )
        db.commit()
        print(f"\nApplied and published: version {result.version.version_no}")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
