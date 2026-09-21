"""
The required parity test: the register as accepted vs the database now.

Until 21 Sep 2026 the baseline was the CRM BEFORE the Round-7 rebuild. It is
now the register as accepted for go-live — see "ABSORBED INTO THE BASELINE"
below, and freeze_parity_baseline.py. What follows describes the original
cutover comparison, whose approvals are kept as the record.

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
    # 0029 (16 Sep 2026) — a bid deadline is a DAY. The time of day was read by
    # nothing, and a timestamp's "+00:00" made the form's datetime-local box
    # render empty, which read as the dates being wiped on a stage reversal.
    ("submission_deadline", "type"): "date",
    ("bid_submission_date", "type"): "date",
    ("progression_pct", "type"): "number",
    ("progression_pct", "computed_formula"): None,
    ("progression_pct", "requirement"): "Optional",
    # P1 (13 Sep 2026) — see the Pursuit Groups block below.
    ("fx_rate_at_entry", "type"): "number",
    ("fx_rate_at_entry", "label"): "FX Rate (local per 1 USD)",
    ("fx_rate_at_entry", "max_length"): None,
    ("fx_rate_at_entry", "requirement"): "Conditional",
    ("fx_rate_at_entry", "visibility_condition"): "currency != 'USD'",
    ("fx_rate_at_entry", "mandatory_from"): 0,
    ("fx_rate_at_entry", "blocks_transition"): "0 → 1",
    ("is_primary_pursuit", "requirement"): "System",
    ("is_primary_pursuit", "editable"): False,
    ("is_primary_pursuit", "mandatory_from"): None,
    ("is_primary_pursuit", "blocks_transition"): None,
    # 0022 (13 Sep 2026) — Progression % and Probability % come from the stage,
    # and changing EITHER needs the justification, so it is no longer about
    # probability alone. api_name unchanged: stored reasons keep their keys.
    ("probability_override_justification", "label"): "Override Justification",
    # 15 Sep 2026 (lead_form_review_metadata.py) — shown, and demanded, only
    # while a number differs from the stage's. The defaults it compares with are
    # server-stamped on every pipeline record; the frontend compiler accepts
    # them (src/lib/spec/conditions.ts, SERVER_STAMPED). The same expression is
    # the condition — see APPROVED_CONDITIONS.
    ("probability_override_justification", "visibility_condition"): (
        "(progression_default_pct != '' && progression_pct != progression_default_pct) || "
        "(probability_default_pct != '' && probability_pct != probability_default_pct)"
    ),
    # 15 Sep 2026 (stage4_commercial_sections.py) — the third-party money fields
    # say whether they are revenue or cost. Definition labels, so Deals' ON
    # CONVERSION copies change with them.
    ("3rd_party_one_time", "label"): "3rd-Party Revenue — One-Time",
    ("3rd_party_recurring_per_year", "label"): "3rd-Party Revenue — Recurring (per year)",
    ("third_party_cost", "label"): "3rd-Party Cost (paid to vendors)",
}

# ---------------------------------------------------------------- Phase A
#
# WHY THESE ARE APPROVALS AND NOT A RE-FREEZE
#
# parity_baseline.json records what the CRM rendered BEFORE the cutover. It is
# frozen once, at the last moment that state was still computable from the
# repository, and re-writing it would record today's layout as yesterday's —
# destroying the only fixed reference this test has. So a deliberate layout
# change is declared here, with its reason, exactly like D1/D3/D4 above.
# Undeclared drift still fails.

RECORD_STATE = "RECORD STATE — each module keeps its own instance"
#: What that section is labelled on Opportunities and Deals today.
RECORD_STATE_SHORT = "RECORD STATE"
READ_THROUGH = "READ THROUGH THE PARENT — resolved from the parent, never stored here"
STAGE_0 = "STAGE 0 — CONNECT"
HEADER = "HEADER"
HEADER_STRIP = "__header"
AGING = "Aging"

# A1. Leads gained its own RECORD STATE section, so that changing the status of
# a Stage 1 lead no longer means clicking back to the Stage 0 tab. Opportunities
# and Deals already had one; Leads was the odd module out. capture_stage goes
# NULL with the move — see leads_record_state.py for why keeping 0 would have
# rendered the section on the Stage 0 tab AND the Details tab at once.
APPROVED_RELOCATIONS: dict[tuple[str, str], tuple[str, str]] = {
    ("leads", "project_stage"): (STAGE_0, RECORD_STATE),
    ("leads", "lead_status"): (STAGE_0, RECORD_STATE),
    # A4. Expected Close Month joins them. A forecast reviewed monthly was
    # filed under the stage it was first asked at, so revising the close month
    # of a Stage 5 pursuit meant clicking back to Stage 0 — and, worse, a
    # capture_stage of 0 kept the placement on Leads (range 0-3) so the field
    # did not exist on Opportunities or Deals at all. See
    # close_month_record_state.py.
    #
    # A5 MOVED BOTH ON AGAIN, to HEADER, which is why these two name HEADER
    # rather than RECORD STATE as their destination. See the block below.
    ("leads", "probability_pct"): (STAGE_0, HEADER),
    ("leads", "expected_close_month"): (STAGE_0, HEADER),
    # A5. THE KEY FACTS BECOME FIELDS.
    #
    # Overall RAG, Next Milestone, Next Milestone Date, Expected Close Month,
    # Progression % and Probability % were drawn by three hand-built strips
    # above the tabs, each saving on a 300ms debounce as the user typed. One
    # keystroke pause cost a record PUT, a refetch and a remount of every form
    # on the screen, which is what the reviewer reported as "changing
    # Probability feels too slow". They are ordinary placements in HEADER now,
    # drawn by RecordForm at the top of the stage tab and saved by its Save
    # button. Nothing about what they store or how per-stage values work
    # changed — see backend/move_key_facts_to_header.py.
    ("leads", "overall_rag"): (HEADER_STRIP, HEADER),
    ("leads", "next_milestone"): (HEADER_STRIP, HEADER),
    ("leads", "next_milestone_date"): (HEADER_STRIP, HEADER),
    ("opportunities", "overall_rag"): (HEADER_STRIP, HEADER),
    ("opportunities", "next_milestone"): (HEADER_STRIP, HEADER),
    ("opportunities", "next_milestone_date"): (HEADER_STRIP, HEADER),
    ("opportunities", "probability_pct"): (RECORD_STATE, HEADER),
    ("deals", "overall_rag"): (HEADER_STRIP, HEADER),
    ("deals", "next_milestone"): (HEADER_STRIP, HEADER),
    ("deals", "next_milestone_date"): (HEADER_STRIP, HEADER),
    ("deals", "probability_pct"): (RECORD_STATE, HEADER),
    # 15 Sep 2026 (lead_form_review_metadata.py). Demo Completed is asked at
    # Demo Presentation, directly before Demo Date and on Demo Date's stage
    # rule, not at Connect — a new lead was being asked whether a demo it had
    # not been offered yet was finished.
    ("leads", "demo_completed"): (STAGE_0, "STAGE 1 — DEMO PRESENTATION"),
    # 15 Sep 2026 (stage4_commercial_sections.py). Opportunities' Stage 4 held
    # thirty fields in one section, bid logistics and money mixed, and the
    # 3rd-party REVENUE lines sat beside 3rd-party COST with nothing to tell
    # them apart. The money moves to two STAGE 4 sections of its own; when each
    # field is asked for does not change.
    **{
        ("opportunities", api_name): ("STAGE 4 — RFP / RFI", "STAGE 4 — COMMERCIAL: REVENUE")
        for api_name in (
            "licence_model",
            "platform_licence_list_price",
            "arr_annual_recurring",
            "licence_discount_pct",
            "perpetual_licence_fee",
            "one_time_revenue",
            "contract_years",
            "3rd_party_one_time",
            "3rd_party_recurring_per_year",
            "total_value_tcv",
            "third_party_pct_of_tcv",
            "primary_quote",
        )
    },
    **{
        ("opportunities", api_name): ("STAGE 4 — RFP / RFI", "STAGE 4 — COMMERCIAL: COST & MARGIN")
        for api_name in (
            "services_and_implementation_cost",
            "third_party_cost",
            "total_cost",
            "gross_margin_pct",
            "cost_model_rcm_document",
        )
    },
}

# A4, second half. Opportunities and Deals gain their own instance of it, so
# the forecast date survives into RFP, Commercial Evaluation and Close — the
# stages a forecast is actually read at. A gained key is otherwise a FIELD
# APPEARED failure, which is the correct default: fields do not turn up
# unannounced.
#
# HEADER rather than RECORD STATE since A5 above, which is where the instance
# each module gained now sits.
APPROVED_ADDITIONS: dict[tuple[str, str], str] = {
    ("opportunities", "expected_close_month"): HEADER,
    ("deals", "expected_close_month"): HEADER,
    # P1. PURSUIT GROUPS (migration 0020, pursuit_group_metadata.py). Partner-A
    # and Partner-B bring the same project; both are pursued and only the
    # primary counts toward pipeline (Playbook §7.2). The group decides which,
    # so the flag it stamps must exist on every module a pursuit becomes —
    # a flag left behind on a converted Lead is how duplicates inflated
    # pipeline in the first place.
    ("leads", "pursuit_group"): STAGE_0,
    ("leads", "not_duplicate_reason"): STAGE_0,
    ("opportunities", "is_primary_pursuit"): RECORD_STATE_SHORT,
    ("opportunities", "pursuit_group"): RECORD_STATE_SHORT,
    ("deals", "is_primary_pursuit"): RECORD_STATE_SHORT,
    ("deals", "pursuit_group"): RECORD_STATE_SHORT,
    # P1. USD pipeline totals divide by the pursuit's one FX rate, which lives on
    # the Lead and is read through beside currency, exactly as currency is.
    ("opportunities", "fx_rate_at_entry"): READ_THROUGH,
    ("deals", "fx_rate_at_entry"): READ_THROUGH,
    # P1. "Both pursued" names which registration's pursuit is primary.
    ("partners", "primary_registration"): "CONFLICT ADJUDICATION",
}

# A4, third half. Close Date Pushback Count is deleted from the register on all
# three modules: `computed` with an empty formula, and models.Lead's property
# returned a hardcoded 0 with a docstring saying it needed a history of
# expected_close_month edits that nothing persisted. Logical delete — the rows
# stay, and there was never a business column anywhere to preserve.
APPROVED_DELETIONS: dict[tuple[str, str], str] = {
    # P1. Superseded by pursuit_group. Logical delete; column and values kept.
    ("leads", "parent_pursuit"): STAGE_0,
    ("leads", "close_date_pushback_count"): AGING,
    ("opportunities", "close_date_pushback_count"): AGING,
    ("deals", "close_date_pushback_count"): AGING,
    # Deleted in Administration on 15 Sep 2026 (register version 109) and
    # confirmed as deliberate on 16 Sep. An Administration-created field, so
    # its values were always custom_fields JSONB and no column existed to keep;
    # the placement survives as status 'deleted' and can be restored.
    ("opportunities", "rfp_document_file"): "STAGE 4 — RFP / RFI",
}

# A6. CROSS-CUTTING is renamed Aging.
#
# A RENAME IS NOT A RELOCATION, and declaring it as twenty-one relocations
# would say something false: nothing moved. The section kept its id, its
# sort_order and every placement in it — `sections.label` changed, which is
# exactly the case the surrogate key on that table exists for.
#
# So it is applied to the BASELINE's keys as they are read, below, rather than
# waived field by field. Every field in the section is then still compared
# key-for-key on all eighteen COMPARED columns, and relative order inside it is
# still checked: the rename buys the label and nothing else.
#
# Why the name changed: CROSS-CUTTING is workbook jargon, and after the reasons
# were anchored beside the status they describe (A2) and the two transition
# reasons became history_only, the heading only ever appeared above Days in
# Current Stage and Days Since Last Update. It was named for what the register
# files there; it is now named for what a BD user sees under it.
APPROVED_SECTION_RENAMES: dict[tuple[str, str], str] = {
    ("leads", "CROSS-CUTTING"): AGING,
    ("opportunities", "CROSS-CUTTING"): AGING,
    ("deals", "CROSS-CUTTING"): AGING,
}


def as_renamed(row: dict) -> dict:
    """A baseline row under its section's current name."""
    section = APPROVED_SECTION_RENAMES.get((row["module"], row["section"]))
    return row if section is None else {**row, "section": section}


# A2. The six reason placements were Conditional in the register while stating
# no `condition`, so requirementOf() returned {required: false, unruled: true}:
# the box appeared and let the user save straight past it. The condition is the
# same expression as the visibility_condition, deliberately — "when is it
# SHOWN" and "when is it DEMANDED" are different questions with the same answer
# here. Set by anchor_reasons.py, which B3 deleted once the field editor grew
# the control; this table is now the only record of what it approved.
APPROVED_CONDITIONS: dict[tuple[str, str], str] = {
    # P1. The FX rate is demanded exactly when there is a currency to convert.
    ("leads", "fx_rate_at_entry"): "currency != 'USD'",
    ("leads", "on_hold_reason"): "lead_status == 'On Hold'",
    ("leads", "closed_lost_reason_code"): "lead_status == 'Closed Lost'",
    ("opportunities", "on_hold_reason"): "lead_status == 'On Hold'",
    ("opportunities", "closed_lost_reason_code"): "lead_status == 'Closed Lost'",
    ("deals", "on_hold_reason"): "lead_status == 'On Hold'",
    ("deals", "closed_lost_reason_code"): "lead_status == 'Closed Lost'",
    # 15 Sep 2026 — Override Justification, demanded exactly while it is shown.
    **{
        (module, "probability_override_justification"): APPROVED_DEFINITION_CHANGES[
            ("probability_override_justification", "visibility_condition")
        ]
        for module in ("leads", "opportunities", "deals")
    },
}

# Modules whose ABSOLUTE sort_order may differ from the baseline because a
# relocation renumbered them. spec/fields.json numbers placements in one
# sequence across the module, so inserting a section shifts every field after
# it — sixteen differences from one decision, none of them meaning anything.
#
# The absolute number is waived; the RELATIVE order within each section is not,
# and is checked separately below. That is the invariant that actually matters:
# a field is allowed to renumber, and is not allowed to move past its
# neighbours.
RENUMBERED_MODULES = {"leads", "opportunities", "deals", "partners"}

# ---------------------------------------------------------------------------
# ABSORBED INTO THE BASELINE, 21 Sep 2026
# ---------------------------------------------------------------------------
# Every approval above described a change between the PRE-CUTOVER baseline and
# the register. On 21 Sep 2026 the user accepted the register as it stood and
# the baseline was re-frozen from the database (freeze_parity_baseline.py
# --from-database --replace), so each of those changes is now part of "before"
# and none can happen again. Left in force, the test would report every one of
# them as an approval that "did not happen" — correctly, by its own design.
#
# The lists are kept above as the record of what was decided and why. They are
# emptied here so this test compares the register against the accepted state
# EXACTLY — including absolute order, since nothing has been renumbered since.
# Approve a new deliberate change by adding it to the relevant dict below this
# block, with its reason, exactly as D1–D4 were; or re-freeze, as a decision.
APPROVED_VALUE_CHANGES = {}
APPROVED_DEFINITION_CHANGES = {}
APPROVED_RELOCATIONS = {}
APPROVED_ADDITIONS = {}
APPROVED_DELETIONS = {}
APPROVED_SECTION_RENAMES = {}
APPROVED_CONDITIONS = {}
RENUMBERED_MODULES = set()

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
    before = {key_of(r): r for r in map(as_renamed, document["fields"])}

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

    # An approved relocation shows up as a lost key and a gained key for the
    # same field. Pair them off first, so a genuine loss is still a failure.
    relocations: list[str] = []
    for (module, api_name), (from_section, to_section) in APPROVED_RELOCATIONS.items():
        old_key = (module, from_section, api_name)
        new_key = (module, to_section, api_name)
        if old_key in lost and new_key in gained:
            lost.remove(old_key)
            gained.remove(new_key)
            relocations.append(f"{module}.{api_name}: {from_section} -> {to_section}")

    # An approved addition is a gained key with no matching loss, and an
    # approved deletion is a lost key with no matching gain. Each is taken out
    # of its list by name and section, so a field arriving in a section nobody
    # approved — or vanishing from one — still fails.
    additions: list[str] = []
    for (module, api_name), section in APPROVED_ADDITIONS.items():
        key = (module, section, api_name)
        if key in gained:
            gained.remove(key)
            additions.append(f"{module}.{api_name} -> {section}")

    deletions: list[str] = []
    for (module, api_name), section in APPROVED_DELETIONS.items():
        key = (module, section, api_name)
        if key in lost:
            lost.remove(key)
            deletions.append(f"{module}.{api_name} (was {section})")

    for key in lost:
        fail(f"FIELD LOST — {'.'.join(key)} rendered before the rebuild and does not now")
    for key in gained:
        fail(f"FIELD APPEARED — {'.'.join(key)} did not render before the rebuild")

    # ------------------------------------------------------- 2. every key
    value_changes: list[str] = []
    definition_changes: list[str] = []
    renumbered: list[str] = []
    ruled: list[str] = []
    for key in sorted(before.keys() & after.keys()):
        b, a = before[key], after[key]
        for column in COMPARED:
            if b.get(column) == a.get(column):
                continue

            # Absolute position, waived only for a module a relocation
            # renumbered. Relative order is checked in section 2b below.
            if column == "order" and key[0] in RENUMBERED_MODULES:
                renumbered.append(
                    f"{'.'.join(key)}: order {b.get(column)} -> {a.get(column)}"
                )
                continue

            if column == "condition" and APPROVED_CONDITIONS.get(
                (key[0], key[2])
            ) == a.get(column):
                ruled.append(f"{key[0]}.{key[2]}: {a.get(column)!r}")
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

    # ------------------------------ 2b. relative order inside every section
    #
    # The point of waiving absolute `order` for a renumbered module is that the
    # numbers shifted, not that the layout is now unreviewed. A field may take
    # a new number; it may not overtake the field next to it. Relocated fields
    # are dropped from their old section's sequence before comparing, because
    # leaving is what they were approved to do — and from their NEW section's,
    # because arriving is the other half of the same approval. Dropping only
    # the departure made an approved relocation fail a second time, under the
    # wrong name, in whichever section it landed in: the destination's
    # sequence gained a field the baseline's could not contain. It went
    # unnoticed through A1 and A4 only because their destination section did
    # not exist in the baseline at all, and the loop below skips those.
    for module in sorted(RENUMBERED_MODULES):
        moved_out = {
            (m, api): from_section
            for (m, api), (from_section, _to) in APPROVED_RELOCATIONS.items()
            if m == module
        }
        moved_in = {
            (m, api): to_section
            for (m, api), (_from, to_section) in APPROVED_RELOCATIONS.items()
            if m == module
        }

        def sequence(rows: dict, section: str, *, side: str) -> list[str]:
            """
            The section's fields in order, minus the ones approved to be in
            only one of the two sides.

            A relocated or deleted field is dropped from the BEFORE sequence
            and an added one from the AFTER sequence, because leaving, going
            and arriving are what they were each approved to do. What is left
            is the invariant this check exists for: the fields present on both
            sides did not overtake one another.
            """
            ordered = sorted(
                (r for k, r in rows.items() if k[0] == module and k[1] == section),
                key=lambda r: r["order"],
            )
            out = []
            for row in ordered:
                api_name = row["api_name"]
                if side == "before":
                    if moved_out.get((module, api_name)) == section:
                        continue
                    if APPROVED_DELETIONS.get((module, api_name)) == section:
                        continue
                else:
                    if moved_in.get((module, api_name)) == section:
                        continue
                    if APPROVED_ADDITIONS.get((module, api_name)) == section:
                        continue
                out.append(api_name)
            return out

        sections = {k[1] for k in before if k[0] == module} | {
            k[1] for k in after if k[0] == module
        }
        for section in sorted(sections):
            # A section with nothing in the baseline is new. There is no
            # previous sequence to preserve, and anything arriving in it that
            # was not an approved relocation has already failed as a FIELD
            # APPEARED above — so comparing [] against its contents would
            # report the relocation a second time under a worse name.
            if not any(k[0] == module and k[1] == section for k in before):
                continue
            was = sequence(before, section, side="before")
            now = sequence(after, section, side="after")
            if was != now:
                fail(
                    f"RELATIVE ORDER CHANGED — {module}.{section}: "
                    f"{was} -> {now}"
                )

    # ------------------------------------------------ 3. per-module counts
    print("  per-module field counts:\n")
    print(f"    {'module':22}{'before':>8}{'after':>8}")
    before_counts = Counter(r["module"] for r in before.values())
    after_counts = Counter(r["module"] for r in after.values())
    # A module's count may move by exactly the additions and deletions declared
    # for it above, and by nothing else. Stating the arithmetic rather than
    # waiving the check keeps an undeclared appearance or loss a failure even
    # on a module that has one of each.
    declared = Counter()
    for module, _api in APPROVED_ADDITIONS:
        declared[module] += 1
    for module, _api in APPROVED_DELETIONS:
        declared[module] -= 1

    for module in sorted(set(before_counts) | set(after_counts)):
        b, a = before_counts[module], after_counts[module]
        expected = b + declared[module]
        flag = "" if b == a else f"   <-- {a - b:+d}, declared {declared[module]:+d}"
        print(f"    {module:22}{b:>8}{a:>8}{flag}")
        if a != expected:
            fail(
                f"module {module} had {b} fields and now has {a}; "
                f"{declared[module]:+d} was declared, so {expected} was expected"
            )

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

    # Phase A. Printed rather than passed over in silence: an approval is only
    # worth having if somebody reading the output can see what was approved.
    print(f"\n  approved relocations (Phase A): {len(relocations)}")
    for line in sorted(relocations):
        print(f"    {line}")
    print(f"\n  approved additions (Phase A): {len(additions)}")
    for line in sorted(additions):
        print(f"    {line}")
    if len(additions) != len(APPROVED_ADDITIONS):
        fail(
            f"{len(APPROVED_ADDITIONS)} additions are approved but "
            f"{len(additions)} happened — the approval list is stale"
        )

    print(f"\n  approved deletions (Phase A): {len(deletions)}")
    for line in sorted(deletions):
        print(f"    {line}")
    if len(deletions) != len(APPROVED_DELETIONS):
        fail(
            f"{len(APPROVED_DELETIONS)} deletions are approved but "
            f"{len(deletions)} happened — the approval list is stale"
        )

    if len(relocations) != len(APPROVED_RELOCATIONS):
        fail(
            f"{len(APPROVED_RELOCATIONS)} relocations are approved but "
            f"{len(relocations)} happened — the approval list is stale"
        )

    print(f"\n  conditions added to unruled Conditional rows (A2): {len(ruled)}")
    for line in sorted(ruled):
        print(f"    {line}")

    print(f"\n  renumbered by a relocation, relative order unchanged: {len(renumbered)}")
    if renumbered:
        modules = sorted({line.split(".")[0] for line in renumbered})
        print(f"    {len(renumbered)} placements across {', '.join(modules)}")

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
