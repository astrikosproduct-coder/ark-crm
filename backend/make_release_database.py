"""
Build the database production starts from: the register, and nothing else.

    python make_release_database.py            # dry run: shows what it would keep and empty
    python make_release_database.py --write    # writes db_backups/ark_crm_release_<date>.dump

Decided 21 Sep 2026: production starts EMPTY — no Leads, Opportunities, Deals,
Accounts, Contacts, registrations, audit history or feedback. It cannot start
from `alembic upgrade head` on a blank database, because the field register —
every field, section, placement, picklist, stage and publish — is not in the
migrations. It was built by bootstrap_metadata.py once, then moved on by dozens
of metadata scripts and Administration edits, and PostgreSQL is its only
complete copy. bootstrap_metadata.py refuses to run twice for that reason.

So production is made the same way the test database is (test_db.py): a
byte-for-byte copy of this one. Then everything that is not the register is
emptied, the result is checked, and it is written to one file to restore on the
server.

A KEEP LIST, NOT AN EMPTY LIST
------------------------------
Only the tables named in KEEP survive. Every other table — including one added
next month that nobody remembers to list — is emptied. Forgetting a table can
therefore only ever lose prototype data, never leak it into production.

The one user kept is the first administrator (decided 21 Sep 2026: Kishan
Pawar, ADMIN + DEVELOPER, already linked to his Microsoft account). The
register's own rows name that user as their author, so the row stays and the
check below refuses to write the file if anyone else is in it.

The file lands in db_backups/, which git ignores. It holds no business data,
but it is still a full database: treat it as one.
"""

from __future__ import annotations

import subprocess
import sys
from datetime import date
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from sqlalchemy import create_engine, text  # noqa: E402

import test_db  # noqa: E402

#: The register, the roles, and the first administrator. Nothing else survives.
KEEP = {
    "alembic_version",  # so production is at head and migrates forward from here
    "modules",
    "sections",
    "field_definitions",
    "field_placements",
    "field_metadata",
    "field_metadata_pre_round7",
    "picklists",
    "picklist_values",
    "stages",
    "metadata_versions",
    "roles",
    "users",
    "user_roles",
}

FIRST_ADMIN_EMAIL = "kishan.pawar@astrikos.ai"
FIRST_ADMIN_ROLES = {"ADMIN", "DEVELOPER"}

RELEASE = "ark_crm_release"
OUT_DIR = Path(__file__).resolve().parent.parent / "db_backups"


def release_url() -> str:
    head, _ = test_db._split(test_db.live_url())
    return f"{head}/{RELEASE}"


def admin_run(sql: str) -> None:
    engine = test_db._admin_engine()
    try:
        with engine.connect() as conn:
            conn.execute(text(sql))
    finally:
        engine.dispose()


def in_container(container: str, script: str) -> str:
    user, password = test_db._credentials()
    result = subprocess.run(
        ["docker", "exec", "-e", f"PGPASSWORD={password}", "-e", f"PGUSER={user}", container, "sh", "-c", script],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError((result.stderr or result.stdout).strip()[:2000])
    return result.stdout


def counts(conn, tables: list[str]) -> dict[str, int]:
    return {t: conn.execute(text(f'SELECT count(*) FROM "{t}"')).scalar_one() for t in tables}


def main(write: bool) -> int:
    container = test_db.postgres_container()
    if container is None:
        print("No local Postgres container found — this needs Docker, like run_tests.py.")
        return 1
    live = test_db.live_database_name()

    print(f"Copying {live} -> {RELEASE} (inside {container}) ...")
    admin_run(f'DROP DATABASE IF EXISTS "{RELEASE}" WITH (FORCE)')
    admin_run(f'CREATE DATABASE "{RELEASE}"')
    try:
        in_container(container, f"pg_dump -d {live} | psql -q -v ON_ERROR_STOP=1 -d {RELEASE}")

        engine = create_engine(release_url(), echo=False)
        try:
            with engine.begin() as conn:
                tables = [r[0] for r in conn.execute(text("SELECT tablename FROM pg_tables WHERE schemaname = 'public' ORDER BY 1"))]
                missing = KEEP - set(tables)
                if missing:
                    raise RuntimeError(f"KEEP names tables that do not exist: {sorted(missing)}")
                emptied = [t for t in tables if t not in KEEP]
                kept = [t for t in tables if t in KEEP]
                before = counts(conn, kept)

                print(f"\nEmptying {len(emptied)} table(s):")
                for t, n in counts(conn, emptied).items():
                    print(f"  {t:32} {n:>6} row(s)")
                conn.execute(text("TRUNCATE " + ", ".join(f'"{t}"' for t in emptied) + " RESTART IDENTITY CASCADE"))

                # ---- the checks that decide whether the file is written at all
                problems: list[str] = []
                after = counts(conn, kept)
                for t in kept:
                    if after[t] != before[t]:
                        problems.append(f"{t} changed from {before[t]} to {after[t]} rows — a cascade reached the register")
                for t, n in counts(conn, emptied).items():
                    if n:
                        problems.append(f"{t} still holds {n} row(s)")
                users = conn.execute(text("SELECT user_id, lower(email), active FROM users")).all()
                if len(users) != 1 or users[0][1] != FIRST_ADMIN_EMAIL or not users[0][2]:
                    problems.append(f"expected exactly one active user, {FIRST_ADMIN_EMAIL}; found {users}")
                else:
                    roles = {r[0] for r in conn.execute(text("SELECT role_id FROM user_roles WHERE user_id = :u"), {"u": users[0][0]})}
                    if not FIRST_ADMIN_ROLES <= roles:
                        problems.append(f"the first administrator holds {sorted(roles)}, needs {sorted(FIRST_ADMIN_ROLES)}")

                print(f"\nKept {len(kept)} table(s):")
                for t in kept:
                    print(f"  {t:32} {after[t]:>6} row(s)")
                if problems:
                    print("\nNOT WRITTEN:")
                    for p in problems:
                        print(f"  - {p}")
                    return 1
        finally:
            engine.dispose()

        print(f"\nChecks passed: register intact, business tables empty, one user ({FIRST_ADMIN_EMAIL}).")
        if not write:
            print("Dry run — nothing written. Re-run with --write.")
            return 0

        OUT_DIR.mkdir(exist_ok=True)
        target = OUT_DIR / f"ark_crm_release_{date.today():%Y%m%d}.dump"
        inside = f"/tmp/{target.name}"
        in_container(container, f"pg_dump -Fc --no-owner --no-privileges -d {RELEASE} -f {inside}")
        subprocess.run(["docker", "cp", f"{container}:{inside}", str(target)], check=True, capture_output=True)
        in_container(container, f"rm -f {inside}")
        print(f"\nWrote {target}  ({target.stat().st_size // 1024} KB)")
        print("Restore it on the server — see DEPLOY.md, step 5.")
        return 0
    finally:
        admin_run(f'DROP DATABASE IF EXISTS "{RELEASE}" WITH (FORCE)')


if __name__ == "__main__":
    sys.exit(main("--write" in sys.argv))
