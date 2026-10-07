"""
Release 1.1, chunk D — groups of companies, and the duplicate check (decided 6 Oct 2026).

    python release_1_1_accounts_metadata.py            # dry run: validates, writes nothing
    python release_1_1_accounts_metadata.py --apply    # change the register and publish

Run AFTER `alembic upgrade head` (r11_0002_account_groups adds the columns) and
AFTER release_1_1_location_metadata.py.

What it does, each step skipped when already done:

  1. Account Name's tooltip says what to type: the registered name, with no
     region, country or city in it — those are chosen below it.
  2. Accounts gain Parent Account, a lookup onto Accounts, right after Account
     Name. Optional: a company in no group, and a group's head, leave it empty.
     The API files any pick under the group's head (app/account_groups.py).
  3. Partner Tier's choices become Platinum, Gold, Authorized, Registered,
     Not a partner (decided 7 Oct 2026). Tier 1 Strategic and Tier 2
     Commercial are RETIRED, not deleted: an account holding one keeps it and
     still shows it, and the run lists those accounts to re-tier by hand.
  4. Publish.

(The duplicate check's "a different company" is one click and keeps no reason
— decided 7 Oct 2026 — so Accounts get no "Not a Duplicate — Reason" field.)

NO DDL. Run on development and on production.
"""

from __future__ import annotations

import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from fastapi import HTTPException  # noqa: E402
from sqlalchemy import select  # noqa: E402

from app.database import SessionLocal, engine  # noqa: E402

engine.echo = False

from app.models import Account, FieldDefinition, FieldPlacement, Picklist, PicklistValue  # noqa: E402
from app.routers.metadata import _publish, _validation_out, build_snapshot  # noqa: E402

NOTE = (
    "Release 1.1: Parent Account on Accounts; Account Name says to type the registered name; "
    "Partner Tier is Platinum, Gold, Authorized, Registered, Not a partner"
)

TIER_LIST = "accounts__partner_tier"
#: In this order. Registered and Not a partner keep their keys.
TIERS = [
    ("PLATINUM", "Platinum"),
    ("GOLD", "Gold"),
    ("AUTHORIZED", "Authorized"),
    ("REGISTERED", "Registered"),
    ("NOT_A_PARTNER", "Not a partner"),
]

NAME_HINT = (
    "The company's registered name, as on its trade licence or invoices, e.g. Astrikos Inc. "
    "Don't add a region, country or city to it; choose those below."
)
PARENT_HINT = (
    "The group this company belongs to. Pick any company of the group; it is filed under the "
    "group's head. Leave it empty for the head itself, or for a company in no group."
)


def partner_tiers(db, log: list[str], to_retier: list[str]) -> None:
    picklist = db.get(Picklist, TIER_LIST)
    if picklist is None:
        raise SystemExit(f"{TIER_LIST} is missing — is this the ARK register?")
    existing = {v.key: v for v in picklist.values}
    wanted = dict(TIERS)
    for order, (key, label) in enumerate(TIERS, start=1):
        v = existing.get(key)
        if v is None:
            db.add(PicklistValue(picklist_key=TIER_LIST, key=key, label=label, sort_order=order, active=True))
            log.append(f"Partner Tier: '{label}' added")
        elif (v.label, v.sort_order, v.active) != (label, order, True):
            v.label, v.sort_order, v.active = label, order, True
            log.append(f"Partner Tier: '{label}' at position {order}")
    for key, v in existing.items():
        if key not in wanted and v.active:
            v.active = False
            v.sort_order = len(TIERS) + v.sort_order
            log.append(f"Partner Tier: '{v.label}' retired")
    retired = [k for k in existing if k not in wanted]
    if retired:
        for a in db.scalars(select(Account).where(Account.partner_tier.in_(retired)).order_by(Account.account_id)):
            to_retier.append(f"{a.account_id} · {a.account_name}: {existing[a.partner_tier].label}")
    db.flush()


def placement(db, module: str, api_name: str) -> FieldPlacement | None:
    return db.scalars(
        select(FieldPlacement)
        .where(FieldPlacement.module_key == module)
        .where(FieldPlacement.api_name == api_name)
        .where(FieldPlacement.status == "active")
    ).first()


def definition(db, scope: str, api_name: str) -> FieldDefinition | None:
    return db.scalars(
        select(FieldDefinition).where(FieldDefinition.scope_key == scope).where(FieldDefinition.api_name == api_name)
    ).first()


def make_room(db, module: str, after_sort_order: int, by: int) -> None:
    for later in db.scalars(
        select(FieldPlacement).where(FieldPlacement.module_key == module).where(FieldPlacement.sort_order > after_sort_order)
    ):
        later.sort_order += by


def add_field(db, log: list[str], *, after: FieldPlacement, api_name: str, label: str, field_type: str,
              description: str, use_case: str, lookup_target: str | None = None, editable: bool = True,
              visibility_condition: str | None = None) -> None:
    if placement(db, "accounts", api_name) is not None:
        return
    d = definition(db, "accounts", api_name)
    if d is None:
        d = FieldDefinition(
            scope_key="accounts",
            api_name=api_name,
            label=label,
            field_type=field_type,
            lookup_target=lookup_target,
            description=description,
            use_case=use_case,
            origin="Release 1.1",
            status="active",
        )
        db.add(d)
        db.flush()
        log.append(f"accounts.{api_name}: definition created ({label}, {field_type})")
    make_room(db, "accounts", after.sort_order, 1)
    db.add(
        FieldPlacement(
            definition_id=d.id,
            api_name=api_name,
            module_key="accounts",
            scope_key=after.scope_key,
            section_id=after.section_id,
            sort_order=after.sort_order + 1,
            requirement="Optional",
            value_mode="own",
            editable=editable,
            visibility_condition=visibility_condition,
            storage="column",
            status="active",
            provenance="register",
        )
    )
    db.flush()
    log.append(f"accounts.{api_name}: placed after {after.api_name}")


def main() -> int:
    mode = "apply" if "--apply" in sys.argv else "dry"
    with SessionLocal() as db:
        log: list[str] = []
        name = definition(db, "accounts", "account_name")
        name_p = placement(db, "accounts", "account_name")
        if name is None or name_p is None:
            raise SystemExit("accounts.account_name is not placed — is this the ARK register?")
        if placement(db, "accounts", "country") is None:
            raise SystemExit("accounts.country is missing — run release_1_1_location_metadata.py --apply first")

        if name.description != NAME_HINT:
            name.description = NAME_HINT
            log.append("accounts.account_name: tooltip says to type the registered name")

        add_field(
            db, log, after=name_p, api_name="parent_account", label="Parent Account", field_type="lookup",
            lookup_target="account", description=PARENT_HINT,
            use_case="Release 1.1 (6 Oct 2026): one group of companies, one level deep, under its head.",
        )
        to_retier: list[str] = []
        partner_tiers(db, log, to_retier)

        print(f"Release 1.1 accounts — {mode}")
        print("=" * 74)
        for line in log or ["nothing to do"]:
            print(f"  {line}")
        if to_retier:
            print(f"\n{len(to_retier)} account(s) keep a retired Partner Tier — choose its new tier by hand:")
            for line in to_retier:
                print(f"  {line}")
        if not log:
            db.rollback()
            return 0
        if mode == "dry":
            validation = _validation_out(build_snapshot(db))
            print(f"\nValidation: {'ok' if validation.ok else 'FAILED'}")
            for error in validation.errors:
                print(f"  error: {error}")
            db.rollback()
            print("Dry run — nothing written. Re-run with --apply.")
            return 0 if validation.ok else 1
        try:
            result = _publish(db, build_snapshot(db), NOTE, None)
        except HTTPException as exc:
            db.rollback()
            print(f"\nNot published, nothing written: {exc.detail}")
            return 1
        db.commit()
        print(f"\nPublished metadata version {result.version.version_no}.")
        for path in result.written:
            print(f"  wrote {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
