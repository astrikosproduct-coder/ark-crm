"""
Empty THIS database of every business record — the prototype's test data.

    python wipe_business_data.py            # dry run: what would be emptied
    python wipe_business_data.py --apply    # empty it

Decided 21 Sep 2026: everything in the development database was test data.
The same KEEP list as make_release_database.py — the register, the roles, the
users — survives; every other table is emptied and its numbering restarts, so
the next Lead is LEAD-00001. A table added later is emptied by default.

Runs against DATABASE_URL (backend/.env), in place, and cannot be undone. It
refuses a database whose name does not look like the development one, so it
cannot be pointed at production by accident.
"""

from __future__ import annotations

import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from sqlalchemy import text  # noqa: E402

from app.database import engine  # noqa: E402

engine.echo = False

from make_release_database import KEEP  # noqa: E402

DEVELOPMENT_DATABASES = {"ark_crm"}


def main() -> int:
    apply = "--apply" in sys.argv
    name = engine.url.database
    if name not in DEVELOPMENT_DATABASES:
        print(f"Refusing: {name!r} is not the development database ({sorted(DEVELOPMENT_DATABASES)}).")
        return 1
    with engine.begin() as conn:
        tables = [r[0] for r in conn.execute(text("SELECT tablename FROM pg_tables WHERE schemaname = 'public' ORDER BY 1"))]
        emptied = [t for t in tables if t not in KEEP]
        print(f"{'Emptying' if apply else 'Would empty'} {len(emptied)} table(s) in {name}:")
        for t in emptied:
            n = conn.execute(text(f'SELECT count(*) FROM "{t}"')).scalar_one()
            print(f"  {t:32} {n:>6} row(s)")
        if not apply:
            print("\nDry run — nothing changed. Re-run with --apply.")
            return 0
        conn.execute(text("TRUNCATE " + ", ".join(f'"{t}"' for t in emptied) + " RESTART IDENTITY CASCADE"))
        left = {t: conn.execute(text(f'SELECT count(*) FROM "{t}"')).scalar_one() for t in emptied}
        if any(left.values()):
            raise RuntimeError(f"still holding rows: {left}")
    print("\nDone. Every business table is empty.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
