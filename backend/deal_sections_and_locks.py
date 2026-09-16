"""
Deals: ON CONVERSION retired, commercial terms locked, one PO field.
Opportunities: the parent link sits in RECORD STATE, as on Deals.

    python deal_sections_and_locks.py             dry run: report, write nothing
    python deal_sections_and_locks.py --apply     write, then publish

Decided 16 Sep 2026. Runs after the lock fix in app/carry_forward.py, which
compares VALUES — without it, locking these fields would refuse every save of
the section they sit in, because the form re-sends its whole section.

1  ON CONVERSION IS RETIRED

It held 32 placements of three different kinds, and the kinds go to three
different homes:

    RECORD STATE                      what the record IS, always on Details:
                                      Deal ID, Deal Name, Deal Stage, Parent
                                      Opportunity, Parent Lead, Delivery PM
    STAGE 7 — COMMERCIAL TERMS
    (AS WON)                          what was won, fixed from here on: End
                                      Client, Customer, Contract Value and the
                                      five revenue lines
    STAGE 7 — CLOSE                   the closing work: booking, references,
                                      PSP, handover, kickoff, sign-offs, the
                                      Bid Commitments Register

Fields moved into RECORD STATE drop capture stage 7 for 0, RECORD STATE's own
convention. A field's capture stage is what puts its section on a stage tab, so
leaving them at 7 would have drawn RECORD STATE on the Stage 7 tab AND on
Details — the very duplication this change removes.

The section is deactivated, not deleted: the legacy field_metadata table still
references it, and a deactivated section is an auditable record that it existed.

2  COMMERCIAL VALUES ARE LOCKED

No commercial value changes after Commercial Evaluation. The seven values a
Deal is given by carry-forward become value_locked. Contract Value is the Deal's
OWN value (the conversion sets it to TCV) and the database only permits
value_locked on carry-forward placements, so it becomes editable = false, which
app/carry_forward.py::locked_violations now enforces for Deals as well.

This REVERSES D1/D3, which let a Deal renegotiate what it inherited. A contract
that genuinely changes is a Contract Variation (phase 2), not an edit to the
booked figures. test_placements.py cases 3 and 12 are updated to match, on
purpose.

3  ONE PO FIELD: PO / LOI REFERENCE

PO Number asked for the same number as PO / LOI Reference, which covers both.
PO Number is logically deleted; its column and any value survive, so it can be
restored. Criterion E7.1 read po_number and is re-pointed in spec/criteria.json,
recorded as a register correction in spec/extensions.json.

4  OPPORTUNITIES MATCH

parent_lead lived in STAGE 4 — RFP / RFI, so the only route back to the Lead
was visible only while the Opportunity sat at Stage 4. It moves to RECORD
STATE, like Parent Lead and Parent Opportunity on a Deal.

5  PARENT OPPORTUNITY ONLY WHERE THERE IS ONE

A Deal made directly from a Lead — a paid POC / pilot — has no Opportunity.
Its Parent Opportunity field is hidden rather than shown blank, by a
visibility_condition, so the rule is register data and not a line of code.
The Related tab says the same thing in words (ParentRecordsPanel).

DEPLOY ORDER

    python deal_sections_and_locks.py --apply
    python test_column_storage.py
    python run_tests.py
"""

from __future__ import annotations

import argparse
import sys

from sqlalchemy import select

from app.clock import now_utc
from app.database import SessionLocal
from app.models import FieldPlacement, Section

COMMERCIAL_SECTION = "STAGE 7 — COMMERCIAL TERMS (AS WON)"
RETIRED_SECTION = "ON CONVERSION"

#: (module, section label, capture stage to set or None to leave, [api_name, ...])
#: Listed in display order; sort_order is assigned from the position.
LAYOUT = (
    (
        "deals",
        "RECORD STATE",
        0,
        [
            "deal_id",
            "deal_name",
            "deal_stage",
            "lead_status",
            "is_primary_pursuit",
            "pursuit_group",
            "parent_opportunity",
            "parent_lead",
            "delivery_pm",
        ],
    ),
    (
        "deals",
        COMMERCIAL_SECTION,
        None,
        [
            "end_client",
            "customer_partner_si",
            "contract_value",
            "arr_annual_recurring",
            "one_time_revenue",
            "3rd_party_one_time",
            "3rd_party_recurring_per_year",
            "contract_years",
        ],
    ),
    (
        "deals",
        "STAGE 7 — CLOSE",
        None,
        [
            "order_booked",
            "booking_date",
            "po_loi_reference",
            "contract_signed_date",
            "payment_schedule_confirmed",
            "erp_reference",
            "project_code",
            "psp_completed_date",
            "handover_pack_delivered_date",
            "kickoff_meeting_date",
            "cash_flow_sign_off_date",
            "resource_plan_sign_off_date",
            "bid_commitments_register",
            "guarantee_—_type",
            "guarantee_—_value",
            "guarantee_—_pct_of_contract_value",
            "guarantee_—_issue_date",
            "guarantee_—_expiry_date",
            "guarantee_—_issuing_bank",
            "guarantee_—_status",
        ],
    ),
)

#: Section-local sort_order starts per section, well apart, so a reader of the
#: register can tell the blocks apart. Ordering between sections is the
#: section's own sort_order, not these numbers.
FIRST_ORDER = {"RECORD STATE": 1, COMMERCIAL_SECTION: 20, "STAGE 7 — CLOSE": 40}

LOCKED = (
    "end_client",
    "customer_partner_si",
    "arr_annual_recurring",
    "one_time_revenue",
    "3rd_party_one_time",
    "3rd_party_recurring_per_year",
    "contract_years",
)
NOT_EDITABLE = ("contract_value",)
RETIRED_FIELDS = ("po_number",)

#: A bare identifier is truthy when set — the same form criteria use.
PARENT_OPPORTUNITY_VISIBLE = "parent_opportunity"


def section(db, module: str, label: str) -> Section | None:
    return db.scalar(select(Section).where(Section.module_key == module, Section.label == label))


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
        stamp = now_utc()

        # The new section takes the retiring one's slot in the order.
        retiring = section(db, "deals", RETIRED_SECTION)
        commercial = section(db, "deals", COMMERCIAL_SECTION)
        if commercial is None:
            slot = retiring.sort_order if retiring is not None else 3
            commercial = Section(
                module_key="deals",
                label=COMMERCIAL_SECTION,
                sort_order=slot,
                active=True,
                created_at=stamp,
                updated_at=stamp,
            )
            db.add(commercial)
            db.flush()
            changes.append(f"deals: section created — {COMMERCIAL_SECTION} (sort {slot})")

        # 1 — the new layout
        for module, label, capture_stage, names in LAYOUT:
            target = section(db, module, label)
            if target is None:
                problems.append(f"{module}: no section {label!r}")
                continue
            for position, api_name in enumerate(names):
                row = placement(db, module, api_name)
                if row is None:
                    problems.append(f"{module}.{api_name}: no active placement")
                    continue
                order = FIRST_ORDER[label] + position
                moved = []
                if row.section_id != target.id:
                    moved.append(f"section -> {label}")
                    row.section_id = target.id
                if row.sort_order != order:
                    row.sort_order = order
                if capture_stage is not None and row.capture_stage != capture_stage:
                    moved.append(f"capture_stage {row.capture_stage} -> {capture_stage}")
                    row.capture_stage = capture_stage
                if moved:
                    changes.append(f"{module}.{api_name}: " + ", ".join(moved))

        # 4 — Opportunities: the parent link where a Deal keeps its own
        opp_record_state = section(db, "opportunities", "RECORD STATE")
        parent_lead = placement(db, "opportunities", "parent_lead")
        if opp_record_state is None or parent_lead is None:
            problems.append("opportunities: RECORD STATE or parent_lead missing")
        elif parent_lead.section_id != opp_record_state.id:
            parent_lead.section_id = opp_record_state.id
            parent_lead.sort_order = 5
            changes.append(
                f"opportunities.parent_lead: section -> RECORD STATE, "
                f"capture_stage {parent_lead.capture_stage} -> 0"
            )
            parent_lead.capture_stage = 0

        # 5 — Parent Opportunity only where there is one
        row = placement(db, "deals", "parent_opportunity")
        if row is None:
            problems.append("deals.parent_opportunity: no active placement")
        elif row.visibility_condition != PARENT_OPPORTUNITY_VISIBLE:
            changes.append(
                f"deals.parent_opportunity: visibility_condition "
                f"{row.visibility_condition!r} -> {PARENT_OPPORTUNITY_VISIBLE!r}"
            )
            row.visibility_condition = PARENT_OPPORTUNITY_VISIBLE

        # 2 — commercial values locked
        for api_name in LOCKED:
            row = placement(db, "deals", api_name)
            if row is None:
                problems.append(f"deals.{api_name}: no active placement")
            elif row.value_mode != "carry_forward":
                problems.append(f"deals.{api_name}: not carry_forward, cannot be value_locked")
            elif not row.value_locked:
                row.value_locked = True
                changes.append(f"deals.{api_name}: value_locked false -> true")
        for api_name in NOT_EDITABLE:
            row = placement(db, "deals", api_name)
            if row is None:
                problems.append(f"deals.{api_name}: no active placement")
            elif row.editable:
                row.editable = False
                changes.append(f"deals.{api_name}: editable true -> false")

        # 3 — one PO field
        for api_name in RETIRED_FIELDS:
            row = placement(db, "deals", api_name)
            if row is not None:
                row.status = "deleted"
                row.deleted_at = stamp
                row.deleted_by = args.user
                row.deleted_by_cascade = False
                changes.append(f"deals.{api_name}: active -> deleted (PO / LOI Reference covers it)")

        # 1 — the old section, once nothing active is left in it
        if retiring is not None and retiring.active:
            db.flush()
            still_there = db.scalars(
                select(FieldPlacement.api_name).where(
                    FieldPlacement.section_id == retiring.id,
                    FieldPlacement.status == "active",
                )
            ).all()
            if still_there:
                problems.append(f"{RETIRED_SECTION} still holds: {', '.join(still_there)}")
            else:
                retiring.active = False
                retiring.updated_at = stamp
                changes.append(f"deals: section deactivated — {RETIRED_SECTION}")

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

        from app.metadata_spec import build_snapshot
        from app.routers.metadata import _publish

        result = _publish(
            db,
            build_snapshot(db),
            "Deals: ON CONVERSION retired into RECORD STATE, STAGE 7 — COMMERCIAL TERMS (AS WON) "
            "and STAGE 7 — CLOSE; commercial values locked; PO Number retired for PO / LOI "
            "Reference. Opportunities: Parent Lead moved to RECORD STATE.",
            args.user,
        )
        db.commit()
        print(f"\nApplied and published: version {result.version.version_no}")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
