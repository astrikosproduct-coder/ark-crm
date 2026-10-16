"""
Release 1.2 — Partner Tier only for a Systems Integrator or a Strategic MSI
(the head's rule, 14 Oct 2026).

    python release_1_2_partner_tier_metadata.py            # dry run: validates, writes nothing
    python release_1_2_partner_tier_metadata.py --apply    # change the register and publish

Until now Partner Tier was shown and required on every partner-type account
(Partner / SI, Consultant / Specifier, OEM / Technology Partner). From here it
is shown and required only when Partner Type is Systems Integrator or Strategic
MSI. An OEM / Technology or Sector Specialist partner is not tiered.

A tier already stored on an account whose Partner Type is neither stays in the
column — logical, never deleted — and is simply no longer shown. The run lists
those accounts so nobody is surprised that the tier disappeared from screen.

NO DDL. Run on development and on production, after `alembic upgrade head`.
"""

from __future__ import annotations

import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from fastapi import HTTPException  # noqa: E402
from sqlalchemy import select  # noqa: E402

from app.database import SessionLocal, engine  # noqa: E402

engine.echo = False

from app.models import Account, FieldPlacement  # noqa: E402
from app.routers.metadata import _publish, _validation_out, build_snapshot  # noqa: E402

NOTE = "Release 1.2: Partner Tier only when Partner Type is Systems Integrator or Strategic MSI"

PARTNER_ACCOUNT = (
    "account_type includes 'Partner / SI' || account_type includes 'Consultant / Specifier' "
    "|| account_type includes 'OEM / Technology Partner'"
)
TIERED = "partner_type == 'Systems Integrator' || partner_type == 'Strategic MSI'"
RULE = f"({PARTNER_ACCOUNT}) && ({TIERED})"

#: Partner Type keys that keep a tier. Anything else holding one is listed.
TIERED_KEYS = {"SYSTEMS_INTEGRATOR", "STRATEGIC_MSI"}


def main() -> int:
    mode = "apply" if "--apply" in sys.argv else "dry"
    with SessionLocal() as db:
        tier = db.scalars(
            select(FieldPlacement)
            .where(FieldPlacement.module_key == "accounts")
            .where(FieldPlacement.api_name == "partner_tier")
            .where(FieldPlacement.status == "active")
        ).first()
        if tier is None:
            raise SystemExit("accounts.partner_tier is not placed — is this the ARK register?")

        log: list[str] = []
        if tier.condition != RULE:
            tier.condition = RULE
            log.append("accounts.partner_tier: required only for a Systems Integrator or Strategic MSI")
        if tier.visibility_condition != RULE:
            tier.visibility_condition = RULE
            log.append("accounts.partner_tier: shown only for a Systems Integrator or Strategic MSI")

        hidden = [
            f"{a.account_name}: {a.partner_tier} (Partner Type {a.partner_type or 'blank'})"
            for a in db.scalars(select(Account).where(Account.partner_tier.is_not(None)).order_by(Account.account_name))
            if a.partner_type not in TIERED_KEYS
        ]

        print(f"Release 1.2 Partner Tier — {mode}")
        print("=" * 74)
        for line in log or ["nothing to do"]:
            print(f"  {line}")
        if hidden:
            print(f"\n{len(hidden)} account(s) keep a tier that will no longer show (the value is kept):")
            for line in hidden:
                print(f"  {line}")
        if not log:
            db.rollback()
            return 0
        db.flush()
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
