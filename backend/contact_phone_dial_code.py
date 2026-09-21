"""
Contacts — Phone and Mobile get a country dial-code dropdown.

    python contact_phone_dial_code.py             dry run: report and validate, write nothing
    python contact_phone_dial_code.py --apply     write, then publish

WHAT CHANGES
------------
  * A new picklist, `contacts__dial_code`. Each value's KEY is the dial code
    itself ("+971") because that is the text stored in front of the number;
    the label names the country ("UAE (+971)"). The first value is the
    control's default, so the order below is UAE first — reorder it in
    Administration, never in code.
  * contacts.phone and contacts.mobile become type `phone`, naming that
    picklist. The form draws a dial-code dropdown beside the number and stores
    ONE string, "+971 50 123 4567", in the existing column. No DDL, and every
    number already saved still displays as it was.

GCC + key markets, per the decision on 14 Sep 2026: the six GCC states ARK's
own Accounts country list starts with, then the wider MEA and the home markets
of the partners and OEMs ARK works with. More are added in Administration.
"""

from __future__ import annotations

import argparse
import sys

from sqlalchemy import func, select

from app.database import SessionLocal
from app.models import FieldDefinition, FieldPlacement, Picklist, PicklistValue

MODULE = "contacts"
FIELDS = ("phone", "mobile")
FIELD_TYPE = "phone"

PICKLIST_KEY = "contacts__dial_code"
PICKLIST_LABEL = "Contacts · Dial Code"

DIAL_CODES: tuple[tuple[str, str], ...] = (
    ("+971", "UAE (+971)"),
    ("+966", "KSA (+966)"),
    ("+974", "Qatar (+974)"),
    ("+968", "Oman (+968)"),
    ("+965", "Kuwait (+965)"),
    ("+973", "Bahrain (+973)"),
    ("+20", "Egypt (+20)"),
    ("+962", "Jordan (+962)"),
    ("+961", "Lebanon (+961)"),
    ("+212", "Morocco (+212)"),
    ("+90", "Türkiye (+90)"),
    ("+91", "India (+91)"),
    ("+92", "Pakistan (+92)"),
    ("+44", "UK (+44)"),
    ("+1", "USA (+1)"),
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
        picklist = db.get(Picklist, PICKLIST_KEY)
        if picklist is None:
            highest = db.scalar(select(func.max(Picklist.sort_order))) or 0
            picklist = Picklist(
                picklist_key=PICKLIST_KEY, label=PICKLIST_LABEL, sort_order=highest + 1
            )
            db.add(picklist)
            changes.append(f"picklist {PICKLIST_KEY}: created")
        existing = {
            v.key
            for v in db.scalars(
                select(PicklistValue).where(PicklistValue.picklist_key == PICKLIST_KEY)
            )
        }
        for sort, (key, label) in enumerate(DIAL_CODES, start=1):
            if key in existing:
                continue
            db.add(PicklistValue(picklist_key=PICKLIST_KEY, key=key, label=label, sort_order=sort))
            changes.append(f"picklist {PICKLIST_KEY}: value {key} = {label}")
        db.flush()

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
            definition = db.get(FieldDefinition, placement.definition_id)
            if definition is None:
                problems.append(f"{MODULE}.{api_name}: placement has no definition")
                continue
            # The type is the DEFINITION's. Refuse to retype one another module
            # also places — Accounts has its own Phone and was not asked about.
            sharers = db.scalars(
                select(FieldPlacement.module_key).where(
                    FieldPlacement.definition_id == definition.id,
                    FieldPlacement.module_key != MODULE,
                )
            ).all()
            if sharers:
                problems.append(
                    f"{MODULE}.{api_name}: definition {definition.id} is also placed on "
                    f"{', '.join(sorted(set(sharers)))} — retyping it would change those too"
                )
                continue
            if definition.field_type != FIELD_TYPE or definition.picklist_key != PICKLIST_KEY:
                changes.append(
                    f"{MODULE}.{api_name}: type {definition.field_type} -> {FIELD_TYPE}, "
                    f"picklist {definition.picklist_key} -> {PICKLIST_KEY}"
                )
                definition.field_type = FIELD_TYPE
                definition.picklist_key = PICKLIST_KEY

        print(f"{len(changes)} change(s):")
        for line in changes:
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
            "Contacts: Phone and Mobile get a dial-code dropdown (type phone, "
            "picklist contacts__dial_code)",
            args.user,
        )
        db.commit()
        print(f"\nApplied and published: version {result.version.version_no}")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
