"""
Freeze the PRE-CUTOVER frontend-effective presentation as a parity baseline.

    python freeze_parity_baseline.py            report only
    python freeze_parity_baseline.py --write    write parity_baseline.json

    python freeze_parity_baseline.py --from-database --replace
        ACCEPT the register as it stands: re-freeze the baseline from what the
        database resolves today, overwriting the old one. See below.

Run ONCE, before spec/fields.json is regenerated from the placement tables.

WHY THIS FILE HAS TO EXIST
---------------------------
The required parity test compares

    what the CRM rendered before the rebuild   vs   what the database resolves now

and the first half is computed by src/lib/spec/moduleSplit.ts from
spec/fields.json + extensions.json + module_split.json. The cutover rewrites
fields.json and strips the placement blocks out of module_split.json — so the
moment the cutover lands, the "before" side can no longer be recomputed from
the repository. Comparing against something that no longer exists is not a
test.

So it is frozen here, at the last moment it is still true, and checked in. From
then on parity is a comparison against a fixed, reviewable artefact rather than
against whatever the code happens to do today, which is the only version of
this test that can still fail in six months.

The baseline is written by replaying rebuild_metadata.py's one-shot port of the
legacy split — the same function that produced the placement rows — so the two
cannot disagree about what "before" meant.

RE-FREEZING FROM THE DATABASE (--from-database --replace)
---------------------------------------------------------
Used once, on 21 Sep 2026, by the user's decision. By then the test reported
185 differences, every one of them a deliberate register change made in
Administration or by a metadata script after the cutover — Deal sections and
locks, Partner lifecycle, pursuit groups, PO Received Date. They were reviewed
and ACCEPTED as the register's intended state rather than resolved one by one.

So the baseline stops meaning "the CRM before the Round-7 rebuild" and starts
meaning "the register as accepted for go-live". The test keeps its value: from
here on any field that moves, renames or changes when it is asked for, without
the baseline being deliberately re-frozen, fails. Re-freeze again only as a
decision, never to make a red test green.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

from rebuild_metadata import _legacy_effective_rows

BASELINE = Path(__file__).resolve().parent / "parity_baseline.json"

# What the comparison is made on. Section 29 of the brief lists these by name:
# count, api_name, label, type, section, order, stage, visibility, editability
# and value behaviour. The first eight are register facts and are compared
# verbatim; the last two are computed from the pre-cutover `carry` value, which
# is what the old model expressed them with.
COMPARED = (
    "module",
    "section",
    "order",
    "api_name",
    "label",
    "type",
    "capture_stage",
    "capture_any_stage",
    "mandatory_from",
    "blocks_transition",
    "requirement",
    "picklist",
    "max_length",
    "lookup_target",
    "visibility_condition",
    "condition",
    "computed_formula",
    "editable",
    "value_mode",
)

# The pre-cutover `carry` value, expressed in the new vocabulary.
#
#   own / moved / shared / own_instance   all meant "this module holds its own
#                                         value" and differed only in how the
#                                         loader picked the field and which
#                                         section the copy landed in
#   new                                   provenance, never behaviour
#   read_through                          the one that was genuinely a value rule
CARRY_TO_MODE = {
    "own": "own",
    "moved": "own",
    "shared": "own",
    "own_instance": "own",
    "new": "own",
    "read_through": "read_through",
}


def baseline_rows() -> list[dict]:
    rows = []
    for r in _legacy_effective_rows():
        mode = CARRY_TO_MODE[r["carry"]]
        rows.append(
            {
                "module": r["module"],
                "section": r["section"],
                "order": r["order"],
                "api_name": r["api_name"],
                "label": r["label"],
                "type": r["type"],
                "capture_stage": r.get("capture_stage"),
                "capture_any_stage": bool(r.get("capture_any_stage")),
                "mandatory_from": r.get("mandatory_from"),
                "blocks_transition": r.get("blocks_transition"),
                "requirement": r["requirement"],
                "picklist": r.get("picklist"),
                "max_length": r.get("max_length"),
                "lookup_target": r.get("lookup_target"),
                "visibility_condition": r.get("visibility_condition"),
                "condition": r.get("condition"),
                "computed_formula": r.get("computed_formula"),
                # A read-through field renders read-only; everything else was
                # editable. That is the whole of what the old model said about
                # editability, and it said it through `carry`.
                "editable": mode != "read_through",
                "value_mode": mode,
                # Kept for the report, not compared: the old vocabulary, so a
                # reviewer can see which mechanism put each row where it is.
                "legacy_carry": r["carry"],
            }
        )
    return rows


def database_rows() -> list[dict]:
    """The register as the database resolves it now — the accepted state."""
    from app.database import SessionLocal, engine
    from app.metadata_resolver import resolved_fields

    engine.echo = False
    with SessionLocal() as db:
        resolved = resolved_fields(db)
    # legacy_carry is report-only (never compared); a field frozen from the
    # database has no legacy mechanism, so it records the value mode itself.
    return [{**{k: r.get(k) for k in COMPARED}, "legacy_carry": r.get("value_mode")} for r in resolved]


def main(write: bool, from_database: bool = False, replace: bool = False) -> int:
    rows = database_rows() if from_database else baseline_rows()
    by_module = Counter(r["module"] for r in rows)
    by_carry = Counter(r["legacy_carry"] for r in rows)

    print(f"pre-cutover frontend-effective presentation: {len(rows)} fields\n")
    for module, n in by_module.most_common():
        print(f"  {module:20} {n}")
    print()
    print("  legacy carry values:", dict(by_carry.most_common()))

    note = (
            "The frontend-effective field presentation immediately BEFORE the "
            "Round-7 placement cutover, computed by replaying "
            "src/lib/spec/moduleSplit.ts over the pre-cutover spec files. This "
            "is the fixed 'before' side of the required parity test — see "
            "test_parity.py. Do not regenerate it: regenerating would make the "
            "test compare the new model against itself."
    )
    if from_database:
        note = (
            "The field register AS ACCEPTED FOR GO-LIVE, 21 Sep 2026 — re-frozen "
            "from the database by the user's decision, which accepted the 185 "
            "post-cutover register changes the parity test then reported. The "
            "fixed 'before' side of test_parity.py: any field that differs from "
            "this without a deliberate re-freeze is a regression. Re-freeze only "
            "as a decision (freeze_parity_baseline.py --from-database --replace)."
        )
    document = {
        "$note": note,
        "generated_by": "backend/freeze_parity_baseline.py" + (" --from-database" if from_database else ""),
        "field_count": len(rows),
        "by_module": dict(sorted(by_module.items())),
        "compared_keys": list(COMPARED),
        "fields": sorted(
            rows, key=lambda r: (r["module"], r["order"], r["api_name"])
        ),
    }

    if not write:
        print("\nreport only — pass --write to freeze it")
        return 0

    if BASELINE.exists() and not replace:
        existing = json.loads(BASELINE.read_text(encoding="utf-8"))
        print(
            f"\nREFUSING to overwrite {BASELINE.name} "
            f"({existing.get('field_count')} fields, already frozen).\n"
            "It is the fixed 'before' side of the parity test. Delete it by "
            "hand if you genuinely mean to re-freeze against today's code."
        )
        return 1

    BASELINE.write_text(
        json.dumps(document, indent=1, ensure_ascii=False), encoding="utf-8"
    )
    print(f"\nfrozen -> {BASELINE}")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--from-database", action="store_true", help="freeze what the database resolves now")
    parser.add_argument("--replace", action="store_true", help="overwrite an existing baseline (with --from-database)")
    args = parser.parse_args()
    if args.replace and not args.from_database:
        parser.error("--replace only re-freezes from the database; pass --from-database as well")
    sys.exit(main(args.write or args.replace, args.from_database, args.replace))
