"""
Deals: one SYSTEM section, and a forecast that stops being a question once won.

    python deal_register_alignment.py             dry run: report, write nothing
    python deal_register_alignment.py --apply     write, then publish

Runs AFTER migration 0030, which gave Deals the standard created_by /
created_date / modified_by / modified_date columns. This is the register half
of the same change, plus the Expected Close Month decision taken with it.

1  THE DUPLICATE SYSTEM PLACEMENTS GO

Deals carried SIX system placements where Leads and Opportunities carry four:
the standard set plus created_by_date and modified_by_date, which are the same
two facts under the Deals sheet's own names. Four of the six rendered
permanently blank, because the columns behind them were the other two. 0030
renamed the columns; these two placements are what is left of the duplication,
so they are logically deleted — the values they described are the same values,
now under the standard names, and a logical delete is reversible.

2  SYSTEM FIELDS ARE NOT EDITABLE

All of them say editable=true while the form renders them read-only and the
server discards whatever a payload claims (SYSTEM_STAMPED). The register was
asserting something untrue about every module; it now says what it means.

3  EXPECTED CLOSE MONTH IS HISTORY ON A DEAL, NOT A QUESTION

It is Mandatory from stage 0 on Deals today, so a booked Deal demands a
prediction of when it will close — while Booking Date, Contract Signed Date and
Go-Live Date all sit on the same record saying when it actually did.

It is NOT deleted. The value carries forward from the Opportunity and is kept
per stage (`expected_close_month__s0…s9`), which is the forecast history; the
dashboard's close-forecast reads it for all three modules; and forecast against
actual is the one accuracy measure this data can give. So it stays, read-only,
labelled for what it is on a Deal.

DEPLOY ORDER

    alembic upgrade head                          (0030)
    python deal_register_alignment.py --apply     this script
    python test_column_storage.py                 proves the promise holds
"""

from __future__ import annotations

import argparse
import sys

from sqlalchemy import select

from app.clock import now_utc
from app.database import SessionLocal
from app.models import FieldPlacement

PIPELINE = ("leads", "opportunities", "deals")

#: The Deals-only pair 0030 renamed away. Logically deleted, never dropped.
RETIRED = (("deals", "created_by_date"), ("deals", "modified_by_date"))

#: The four every module keeps, on every module.
SYSTEM_FIELDS = ("created_by", "created_date", "modified_by", "modified_date")

CLOSE_MONTH_LABEL = "Expected Close Month (at conversion)"


def placement(db, module: str, api_name: str) -> FieldPlacement | None:
    return db.scalar(
        select(FieldPlacement).where(
            FieldPlacement.module_key == module,
            FieldPlacement.api_name == api_name,
            FieldPlacement.status == "active",
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

    try:
        # 1 — the duplicate pair
        for module, api_name in RETIRED:
            row = placement(db, module, api_name)
            if row is None:
                continue  # already retired, or never there
            row.status = "deleted"
            row.deleted_at = now_utc()
            row.deleted_by = args.user
            row.deleted_by_cascade = False
            changes.append(f"{module}.{api_name}: active -> deleted (0030 renamed its column)")

        # 2 — system fields are not editable
        for module in PIPELINE:
            for api_name in SYSTEM_FIELDS:
                row = placement(db, module, api_name)
                if row is None:
                    problems.append(f"{module}.{api_name}: no active placement")
                    continue
                if row.editable:
                    row.editable = False
                    changes.append(f"{module}.{api_name}: editable true -> false")

        # 3 — Expected Close Month on a Deal
        row = placement(db, "deals", "expected_close_month")
        if row is None:
            problems.append("deals.expected_close_month: no active placement")
        else:
            if row.requirement != "Optional":
                changes.append(
                    f"deals.expected_close_month: requirement {row.requirement} -> Optional"
                )
                row.requirement = "Optional"
            if row.mandatory_from is not None:
                changes.append(
                    f"deals.expected_close_month: mandatory_from {row.mandatory_from} -> none"
                )
                row.mandatory_from = None
            if row.editable:
                row.editable = False
                changes.append("deals.expected_close_month: editable true -> false")
            if row.label_override != CLOSE_MONTH_LABEL:
                changes.append(
                    f"deals.expected_close_month: label_override "
                    f"{row.label_override!r} -> {CLOSE_MONTH_LABEL!r}"
                )
                row.label_override = CLOSE_MONTH_LABEL

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

        # The same publish path Administration uses: validate, freeze a
        # version, regenerate spec/*.json.
        from app.metadata_spec import build_snapshot
        from app.routers.metadata import _publish

        result = _publish(
            db,
            build_snapshot(db),
            "Deals: one SYSTEM section like every other module, system fields "
            "read-only, and Expected Close Month read-only on a booked Deal",
            args.user,
        )
        db.commit()
        print(f"\nApplied and published: version {result.version.version_no}")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
