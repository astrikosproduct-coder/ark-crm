"""
Twelve draft sales targets at 0 for every active BD Owner, for one fiscal year.

    python seed_sales_targets.py --actor kishan.pawar@astrikos.ai               # dry run: writes nothing
    python seed_sales_targets.py --actor kishan.pawar@astrikos.ai --apply
    python seed_sales_targets.py --actor USR-001 --fiscal-year FY28 --apply

Run AFTER `alembic upgrade head` — 0040 creates sales_targets.

Dashboard Phase 1, 28 Sep 2026. Seeds FY27 (01 Apr 2026 - 31 Mar 2027) unless
told otherwise: the current fiscal year, from FISCAL_YEAR_START_MONTH.

SAFE TO RUN AGAIN. An owner-month that already has a target is skipped, so a
BD Owner granted the role mid-year gets their twelve rows and nobody gets a
second set. Rows go through app/sales_targets.py, the API's own path, so each
is audited like one created on screen.

--actor names the person the rows are recorded as created by — an email or a
user id. There is no anonymous author: identity is the server's, and here the
server is you. Production starts with no users, so run this once BD Owners
have been added and given the role.
"""

from __future__ import annotations

import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from sqlalchemy import func, select  # noqa: E402

from app.database import SessionLocal, engine  # noqa: E402

engine.echo = False

from app import fiscal  # noqa: E402
from app.clock import today_company  # noqa: E402
from app.models import User  # noqa: E402
from app.sales_targets import active_bd_owners, seed_year  # noqa: E402


def _arg(name: str) -> str | None:
    if name in sys.argv:
        at = sys.argv.index(name)
        return sys.argv[at + 1] if at + 1 < len(sys.argv) else None
    return None


def main() -> int:
    apply = "--apply" in sys.argv
    who = _arg("--actor")
    label = _arg("--fiscal-year") or fiscal.label_of(today_company())
    if not who:
        print("Say who is seeding: --actor <email or user id>.")
        return 2
    try:
        first, last = fiscal.first_day(label), fiscal.last_day(label)
    except ValueError as error:
        print(error)
        return 2

    with SessionLocal() as db:
        actor = db.get(User, who) or db.scalar(select(User).where(func.lower(User.email) == who.lower()))
        if actor is None:
            print(f"No user {who!r}.")
            return 2

        owners = active_bd_owners(db)
        print(f"{label}: {first:%d %b %Y} to {last:%d %b %Y} (fiscal year starts in month {fiscal.FISCAL_YEAR_START_MONTH})")
        print(f"Active BD Owners: {len(owners)}")
        for owner in owners:
            print(f"  {owner.user_id}  {owner.name}")
        if not owners:
            print("Nothing to seed. Give someone the BD Owner role first.")
            return 0

        created, skipped = seed_year(db, label, actor=actor.user_id)
        verb = "Creating" if apply else "Would create"
        print(f"{verb} {len(created)} draft target(s) at 0; {skipped} owner-month(s) already have one.")
        if not apply:
            db.rollback()
            print("Dry run — nothing written. Re-run with --apply.")
            return 0
        db.commit()
        print(f"Written, as {actor.name}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
