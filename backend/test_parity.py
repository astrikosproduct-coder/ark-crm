"""
The required parity test: the CRM before the rebuild vs the database after it.

    python test_parity.py

    PRE-CUTOVER FRONTEND-EFFECTIVE MODEL          NEW DATABASE-RESOLVED MODEL
    parity_baseline.json                    vs    field_placements + field_definitions
    (frozen by freeze_parity_baseline.py)         (via app/metadata_resolver.py)

Every field is compared on all nineteen keys section 29 of the brief names:
count, api_name, label, type, section, order, stage, visibility, editability
and value behaviour. "The counts look close" is not a result. A field present
on one side and absent on the other is a failure, and so is a single differing
key on a single field.

THE ONE ALLOWED CLASS OF DIFFERENCE
------------------------------------
Decisions D1 and D3 deliberately CHANGE value behaviour on seven Deal
placements: money fields and the two counterparties now carry their opening
value forward from the parent instead of starting empty. Those seven are
enumerated by name below. Any other value_mode difference — including a
seven-in-name-only match on a different module — fails.

Nothing else is allowed to move. Presentation parity is exact.
"""

from __future__ import annotations

import json
import sys

# The register is full of em dashes and section names carry them, so a failure
# line cannot be printed on a cp1252 console without this. A parity failure
# that crashes while reporting itself is worse than no test at all.
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from collections import Counter
from pathlib import Path

from app.database import SessionLocal, engine

engine.echo = False

from app.metadata_resolver import resolved_fields  # noqa: E402

BASELINE = Path(__file__).resolve().parent / "parity_baseline.json"

# Keys compared verbatim on every field. A difference in any of them is a
# regression: it means a field moved, was renamed, changed shape, changed
# position or changed when it is asked for.
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
)

# D1 + D3. The complete list of placements whose value behaviour is allowed to
# differ from the baseline, with what it is allowed to become.
APPROVED_VALUE_CHANGES: dict[tuple[str, str], tuple[str, str]] = {
    ("deals", "one_time_revenue"): ("own", "carry_forward"),
    ("deals", "arr_annual_recurring"): ("own", "carry_forward"),
    ("deals", "3rd_party_one_time"): ("own", "carry_forward"),
    ("deals", "3rd_party_recurring_per_year"): ("own", "carry_forward"),
    ("deals", "contract_years"): ("own", "carry_forward"),
    ("deals", "end_client"): ("own", "carry_forward"),
    ("deals", "customer_partner_si"): ("own", "carry_forward"),
}

# D4. progression_pct was published as a `computed` field on two of the three
# sheets and as an editable `number` on the third; the field was made editable
# on 02 Sep 2026 and the computed rows are stale. The rebuild resolves the
# conflict to Number with no formula, which is a DEFINITION change and shows up
# on every placement of the field.
#
# Keyed by (api_name, column) rather than by module, because a definition
# property changes everywhere at once — which is exactly the behaviour the
# placement model is for, and exactly why one decision produces three
# differences here.
# The three columns are only stale on the DEALS sheet: Leads and Opportunities
# already published progression_pct as number/Optional with no formula. So one
# decision produces exactly three differences, all on one placement — and the
# `before` values are read from the baseline rather than restated here, because
# the register's computed_formula is a sentence of prose and pasting it into a
# test would make the test about the prose.
APPROVED_DEFINITION_CHANGES: dict[tuple[str, str], object] = {
    ("progression_pct", "type"): "number",
    ("progression_pct", "computed_formula"): None,
    ("progression_pct", "requirement"): "Optional",
}

failures: list[str] = []


def fail(message: str) -> None:
    failures.append(message)


def key_of(row: dict) -> tuple[str, str, str]:
    """A field's identity: which module, which section, which name."""
    return (row["module"], row["section"], row["api_name"])


def main() -> int:
    if not BASELINE.exists():
        print(
            f"No {BASELINE.name}. Run freeze_parity_baseline.py --write BEFORE "
            "the cutover — after it, the pre-cutover presentation cannot be "
            "recomputed from the repository."
        )
        return 1

    document = json.loads(BASELINE.read_text(encoding="utf-8"))
    before = {key_of(r): r for r in document["fields"]}

    db = SessionLocal()
    try:
        after = {key_of(r): r for r in resolved_fields(db)}
    finally:
        db.close()

    print("=" * 74)
    print("PARITY — pre-cutover frontend presentation vs database resolution")
    print("=" * 74)
    print(f"\n  before  {len(before)} fields   (parity_baseline.json)")
    print(f"  after   {len(after)} fields   (field_placements)\n")

    # ---------------------------------------------------------- 1. the sets
    lost = sorted(before.keys() - after.keys())
    gained = sorted(after.keys() - before.keys())

    for key in lost:
        fail(f"FIELD LOST — {'.'.join(key)} rendered before the rebuild and does not now")
    for key in gained:
        fail(f"FIELD APPEARED — {'.'.join(key)} did not render before the rebuild")

    # ------------------------------------------------------- 2. every key
    value_changes: list[str] = []
    definition_changes: list[str] = []
    for key in sorted(before.keys() & after.keys()):
        b, a = before[key], after[key]
        for column in COMPARED:
            if b.get(column) == a.get(column):
                continue
            sentinel = object()
            approved = APPROVED_DEFINITION_CHANGES.get((key[2], column), sentinel)
            if approved is not sentinel and a.get(column) == approved:
                definition_changes.append(
                    f"{'.'.join(key)}.{column}: {b.get(column)!r} -> {a.get(column)!r}"
                )
                continue
            fail(
                f"{'.'.join(key)}.{column} - before {b.get(column)!r}, "
                f"after {a.get(column)!r}"
            )

        if b["value_mode"] != a["value_mode"]:
            approved = APPROVED_VALUE_CHANGES.get((key[0], key[2]))
            if approved == (b["value_mode"], a["value_mode"]):
                value_changes.append(
                    f"{key[0]}.{key[2]}: {b['value_mode']} -> {a['value_mode']}"
                )
            else:
                fail(
                    f"UNAPPROVED VALUE CHANGE — {'.'.join(key)}.value_mode "
                    f"{b['value_mode']!r} -> {a['value_mode']!r}"
                )

    # ------------------------------------------------ 3. per-module counts
    print("  per-module field counts:\n")
    print(f"    {'module':22}{'before':>8}{'after':>8}")
    before_counts = Counter(r["module"] for r in before.values())
    after_counts = Counter(r["module"] for r in after.values())
    for module in sorted(set(before_counts) | set(after_counts)):
        b, a = before_counts[module], after_counts[module]
        flag = "" if b == a else "   <-- DIFFERS"
        print(f"    {module:22}{b:>8}{a:>8}{flag}")
        if b != a:
            fail(f"module {module} had {b} fields and now has {a}")

    # --------------------------------------------- 4. approved differences
    print("")
    print(f"  approved definition changes (D4): {len(definition_changes)}")
    for line in sorted(definition_changes):
        print(f"    {line}")
    print(f"\n  approved value-behaviour changes (D1, D3): {len(value_changes)}")
    for line in sorted(value_changes):
        print(f"    {line}")
    missing = set(APPROVED_VALUE_CHANGES) - {
        (c.split(":")[0].split(".")[0], c.split(":")[0].split(".", 1)[1])
        for c in value_changes
    }
    if missing:
        fail(
            "approved carry-forward changes that did NOT happen: "
            + ", ".join(f"{m}.{a}" for m, a in sorted(missing))
        )

    # ------------------------------------------------------------ verdict
    print()
    print("=" * 74)
    if failures:
        print(f"PARITY FAILED — {len(failures)} difference(s)\n")
        for line in failures[:60]:
            print("   ", line)
        if len(failures) > 60:
            print(f"    ... and {len(failures) - 60} more")
        return 1

    print("PARITY EXACT")
    print(
        f"  {len(before)} fields, {len(COMPARED)} keys each, zero unexplained "
        f"differences.\n  {len(value_changes)} value-behaviour changes, all "
        f"approved by name (D1, D3)."
    )
    print("=" * 74)
    return 0


if __name__ == "__main__":
    sys.exit(main())
