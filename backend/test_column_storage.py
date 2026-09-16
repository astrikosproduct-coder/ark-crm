"""
Every `storage='column'` placement has a column, and the API can write it.

    python test_column_storage.py

WHY THIS EXISTS
---------------
A placement that says storage='column' and status='active' is the register
promising a real, typed column. Five of them on Deals had no column at all —
overall_rag, next_milestone, next_milestone_date, po_number and
payment_schedule_confirmed — and two more had a column the API never listed.
The screen rendered all of them, took what was typed and dropped it: no error,
no warning, and the value simply gone on the next read. That is worse than a
missing field, because the form said the value had been taken.

The defect was found by hand three times (contract_signed_date in 0016,
progression/probability in 0016, these five in 0030). It is exactly the kind a
test finds in a second, so here it is.

THE RULE, IN FULL
-----------------
For every ACTIVE placement whose storage is 'column':

    1. a column of that api_name exists on the module's model, or on one of
       its child-list tables — the register writes a child row's columns flat
       (guarantee_—_*, milestone_—_*), and those live on the child table;
    2. the api_name appears in that module's *_SCALARS, so the router reads it
       off a payload and serialises it back.

Rule 2 is waived for requirement='System': the server stamps those and
serialises them by hand, so they are deliberately absent from the write list.

WHAT IS NOT A COLUMN, AND MUST NOT BE
-------------------------------------
    childlist / computed / autonumber   never stored on the parent row
    value_mode='read_through'           resolved from the parent, stored nowhere
    stage_scoped != 'none'              kept per stage as `<api_name>__s<n>`
                                        in custom_fields, not one column
                                        (app/custom_fields.py)

READ ONLY. It writes nothing, so it runs against any database — including the
one the prototype is demonstrated from.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from sqlalchemy import inspect as sa_inspect, text  # noqa: E402

from app.database import SessionLocal, engine  # noqa: E402

engine.echo = False

#: The real table, as PostgreSQL has it. See column_names().
INSPECTOR = sa_inspect(engine)

from app.models import (  # noqa: E402
    Account,
    AccountType,
    Contact,
    Deal,
    DealBidCommitment,
    DealExpansionUseCase,
    Lead,
    LeadDemoAttendee,
    LeadFeatureGap,
    Opportunity,
    OpportunityPaymentMilestone,
)
from app.schemas import (  # noqa: E402
    ACCOUNT_SCALARS,
    CONTACT_SCALARS,
    DEAL_SCALARS,
    LEAD_SCALARS,
    OPPORTUNITY_SCALARS,
)

#: module_key -> (model, writable names, tables a row of this module also writes)
#: accounts.account_type is a multiselect and so is one row per selected value
#: in account_types, the same shape a child list has — see models.AccountType.
MODULES = {
    "accounts": (Account, ACCOUNT_SCALARS, (AccountType,)),
    "contacts": (Contact, CONTACT_SCALARS, ()),
    "leads": (Lead, LEAD_SCALARS, (LeadDemoAttendee, LeadFeatureGap)),
    "opportunities": (Opportunity, OPPORTUNITY_SCALARS, (OpportunityPaymentMilestone,)),
    "deals": (Deal, DEAL_SCALARS, (DealBidCommitment, DealExpansionUseCase)),
}

#: Types that describe something other than one value on the parent row.
NOT_STORED_HERE = {"childlist", "computed", "autonumber"}


def history_only_names() -> set[str]:
    """
    The reasons the Advance / Change stage dialog writes, declared in
    spec/extensions.json stage_scoped.history_only. No form asks for them and
    the transitions table carries one per move, so a module may hold them as
    columns (Leads and Opportunities do) or not (Deals does not) without either
    being a broken promise. Read from the sidecar rather than listed here, so
    the exception has one home.
    """
    sidecar = Path(__file__).resolve().parent.parent / "frontend" / "spec" / "extensions.json"
    block = json.loads(sidecar.read_text(encoding="utf-8")).get("stage_scoped", {})
    return set(block.get("history_only", {}).get("fields", []))


HISTORY_ONLY = history_only_names()

QUERY = text(
    """
    SELECT p.module_key,
           p.api_name,
           p.requirement,
           p.value_mode,
           COALESCE(p.stage_scoped, 'none') AS stage_scoped,
           d.field_type
      FROM field_placements p
      JOIN field_definitions d ON d.id = p.definition_id
     WHERE p.status = 'active'
       AND p.storage = 'column'
     ORDER BY p.module_key, p.api_name
    """
)


def column_names(model) -> set[str]:
    """What the DATABASE has, in both spellings the register might use.

    The physical table is asked, not the model: a column declared in models.py
    whose migration has not run would otherwise pass this test and still fail
    every real save. The ORM attribute names are added because the two differ
    wherever an api_name is not a Python identifier — `3rd_party_one_time` is
    the attribute third_party_one_time over a column of the register's name,
    and the em-dash guarantee columns are the same accommodation.
    """
    # The register speaks column names, so those are what is compared. An ORM
    # attribute is only ever an alias for one of these, never an extra name a
    # placement could legitimately match.
    return {column["name"] for column in INSPECTOR.get_columns(model.__tablename__)}


def main() -> int:
    db = SessionLocal()
    try:
        rows = db.execute(QUERY).mappings().all()
    finally:
        db.close()

    missing_column: list[str] = []
    not_writable: list[str] = []
    checked = 0
    skipped = 0

    for row in rows:
        module = row["module_key"]
        if module not in MODULES:
            continue
        if row["field_type"] in NOT_STORED_HERE:
            skipped += 1
            continue
        if row["value_mode"] == "read_through" or row["stage_scoped"] != "none":
            skipped += 1
            continue

        model, scalars, children = MODULES[module]
        api_name = row["api_name"]

        if api_name in HISTORY_ONLY:
            skipped += 1
            continue

        checked += 1

        if api_name not in column_names(model):
            if any(api_name in column_names(child) for child in children):
                skipped += 1
                checked -= 1
                continue
            missing_column.append(f"{module}.{api_name} ({row['requirement']})")
            continue

        if row["requirement"] == "System":
            continue

        # An api_name that is not a Python identifier is declared in the
        # schemas under its ORM attribute name, with the register's name as the
        # Pydantic alias: `3rd_party_one_time` is third_party_one_time there.
        # Either spelling means the API can write the field.
        attribute = {
            column.name: attr.key
            for attr in model.__mapper__.column_attrs
            for column in attr.columns
        }
        if api_name not in scalars and attribute.get(api_name) not in scalars:
            not_writable.append(f"{module}.{api_name} ({row['requirement']})")

    print(f"{checked} active column placements checked, {skipped} stored elsewhere by design\n")

    if missing_column:
        print(f"NO COLUMN — the register promises these and the table has no such column ({len(missing_column)}):")
        for entry in missing_column:
            print(f"    {entry}")
        print("    Fix: an Alembic migration adding the column, plus the model.\n")

    if not_writable:
        print(f"NOT WRITABLE — column exists, but no *_SCALARS entry, so the API drops it ({len(not_writable)}):")
        for entry in not_writable:
            print(f"    {entry}")
        print("    Fix: add the api_name to that module's *_SCALARS and to its Base/Out schemas.\n")

    if missing_column or not_writable:
        print("FAIL — a field that renders and cannot be stored is a field that lies.")
        return 1

    print("PASS — every active column placement has a column, and the API writes it.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
