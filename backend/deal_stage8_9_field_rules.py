"""
Deals — Incremental Value always visible at Stage 9; CSAT Score bounded 1 to 10.

    python deal_stage8_9_field_rules.py             dry run: report, write nothing
    python deal_stage8_9_field_rules.py --apply     write, then publish

INCREMENTAL VALUE (deals, Stage 9)
----------------------------------
The placement was Mandatory from Stage 9 AND hidden unless
`opportunity_type == 'Expansion'`. On a New Logo deal that is a field the
9 -> New Lead move requires and the form never draws — a transition nobody can
satisfy. The visibility condition is removed: the field shows on every Deal at
Stage 9, and stays Mandatory there. The Leads placement keeps its own condition
(an Expansion Lead is the only kind that has an incremental value), and Create
Expansion Lead now carries the Deal's value into it — see DealDetailPage.tsx.

CSAT SCORE (deals, Stage 8)
---------------------------
Min value 1, Max value 10, both inclusive. A definition property, enforced by
the form (lib/spec/validation.ts) and on save (app/thresholds.py, now called by
routers/deals.py as well).

Register facts, so written to the metadata tables and published — never typed
into spec/fields.json.
"""

from __future__ import annotations

import argparse
import sys

from sqlalchemy import select

from app.database import SessionLocal
from app.models import FieldDefinition, FieldPlacement

MODULE = "deals"
CSAT_MIN = 1.0
CSAT_MAX = 10.0


def _placement(db, api_name: str) -> FieldPlacement | None:
    return db.scalar(
        select(FieldPlacement).where(
            FieldPlacement.module_key == MODULE,
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

    try:
        incremental = _placement(db, "incremental_value")
        if incremental is None:
            problems.append(f"{MODULE}.incremental_value: no placement on this module")
        elif incremental.visibility_condition is not None:
            changes.append(
                f"{MODULE}.incremental_value: visibility_condition "
                f"{incremental.visibility_condition!r} -> None"
            )
            incremental.visibility_condition = None

        csat = _placement(db, "csat_score")
        if csat is None:
            problems.append(f"{MODULE}.csat_score: no placement on this module")
        else:
            definition = db.get(FieldDefinition, csat.definition_id)
            if definition.min_value != CSAT_MIN or definition.max_value != CSAT_MAX:
                changes.append(
                    f"csat_score: range {definition.min_value!r}..{definition.max_value!r} "
                    f"-> {CSAT_MIN}..{CSAT_MAX}"
                )
                definition.min_value = CSAT_MIN
                definition.max_value = CSAT_MAX

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

        if not changes:
            db.rollback()
            print("\nNothing to apply.")
            return 0

        db.flush()

        # Same publish path Administration uses: validate, freeze a version,
        # regenerate spec/*.json.
        from app.metadata_spec import build_snapshot
        from app.routers.metadata import _publish

        result = _publish(
            db,
            build_snapshot(db),
            "Deals: Incremental Value always visible at Stage 9; CSAT Score bounded 1-10",
            args.user,
        )
        db.commit()
        print(f"\nApplied and published: version {result.version.version_no}")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
