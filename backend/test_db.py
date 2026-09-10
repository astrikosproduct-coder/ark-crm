"""
The test database: a copy of the live one, made fresh, thrown away after.

    python run_tests.py            # refreshes it, then runs the suite

WHAT THIS SOLVES
----------------
Until now the test scripts ran against the development database — the same one
the prototype is demonstrated from. Five of the six write to it. That is not a
hypothetical risk: the Phase A1 anchor fixture reset the placements it touched
to NULL on teardown, which after A2 unanchored On Hold Reason and Closed Lost
Reason Code on Leads. The screens silently went back to the two-save journey.

test_support.RegisterGuard was the containment for that, and it stays — it
repairs a register a test damaged. This removes the need for the repair: a
writing test now cannot reach the demonstrated database at all.

WHY A TEMPLATE COPY AND NOT A FRESH BOOTSTRAP
----------------------------------------------
test_support.py's docstring names the objection to a second database, and it
was right: bootstrap_metadata.py, seed.py and the migrate_* scripts all assume
one database, so a second one built from scratch has to be kept in step or the
tests prove nothing about the register that actually ships.

    CREATE DATABASE ark_crm_test TEMPLATE ark_crm

answers it by not having the problem. Nothing is kept in step, because the test
database IS the live register — every Administration edit, every anchor, every
Phase A change — copied byte for byte, seconds before the suite runs. Parity
still compares against the frozen baseline and still means what it meant.

TWO WAYS TO MAKE THE COPY, AND WHY BOTH ARE HERE
-------------------------------------------------
PostgreSQL will not use a database as a TEMPLATE while any other session is
connected to it, and the FastAPI dev server holds a pool. Requiring it to be
stopped would mean a test suite people skip, which is not a seatbelt.

So the preferred path is pg_dump, run INSIDE the postgres container. That has
nothing to do with convenience and everything to do with versions: the server
is PostgreSQL 17 and the client tools on this machine are 16, and pg_dump
refuses that pairing. The container has 17 of both. It copies happily while the
app is connected.

    docker exec ark-postgres sh -c 'pg_dump ark_crm | psql ark_crm_test'

TEMPLATE is the fallback for a machine with no Docker — a direct server-side
copy, no client tools involved at all, but it needs exclusive access. When it
cannot get it, refresh() reports what is connected and stops rather than
evicting anyone: terminating a backend someone is demonstrating from, to run a
test, is the worse failure.

Either way the test database IS the live register, seconds old.

WHAT IS NOT COVERED
-------------------
The business tables are copied too, so a test that creates an Opportunity is
still creating it in a copy of real data. It is still responsible for deleting
it — a test that leaves rows behind is a test that will not pass twice, and the
copy will hide that from you until the day it runs against something else.

And a database copy isolates the database, which is not everything a test
touches. test_metadata_round6.py publishes, and publishing writes
frontend/spec/*.json — real files, in the repo, shared with the running
frontend. It records their checksums first and asserts at the end that all
three are byte-identical, so it puts them back; but that is the test's own
discipline, not containment. A publishing test that failed halfway would leave
regenerated spec files behind, and `git status` is what would tell you.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import urllib.parse

from dotenv import load_dotenv
from sqlalchemy import create_engine, text

load_dotenv()

#: The database the suite is allowed to write to, derived from the live one so
#: the two can never be configured apart. Not read from an env var of its own:
#: a TEST_DATABASE_URL someone could point anywhere is the hazard this file
#: exists to remove.
TEST_SUFFIX = "_test"


def _configured_url() -> str:
    """
    Whatever DATABASE_URL currently says — which is NOT always the live one.

    run_tests.py sets it to the test database in the child process, so a name
    read from here can already be the copy. Everything below normalises rather
    than assuming, and both accessors are idempotent as a result: asking for
    the test database while connected to the test database gives the same
    answer, not `ark_crm_test_test`. An earlier version did exactly that and
    every writing test refused itself.
    """
    url = os.getenv("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL is not set — check backend/.env")
    return url


def _split(url: str) -> tuple[str, str]:
    """(everything up to the database name, the database name)."""
    head, _, name = url.rpartition("/")
    return head, name


def live_database_name() -> str:
    name = _split(_configured_url())[1]
    return name[: -len(TEST_SUFFIX)] if name.endswith(TEST_SUFFIX) else name


def test_database_name() -> str:
    name = _split(_configured_url())[1]
    return name if name.endswith(TEST_SUFFIX) else name + TEST_SUFFIX


def live_url() -> str:
    head, _ = _split(_configured_url())
    return f"{head}/{live_database_name()}"


def test_url() -> str:
    head, _ = _split(_configured_url())
    return f"{head}/{test_database_name()}"


def _admin_engine():
    """
    A connection to `postgres`, not to either database.

    CREATE DATABASE and DROP DATABASE cannot run inside a transaction and
    cannot run from a session connected to the database being copied, so this
    deliberately connects to neither. echo is off: the app's engine logs every
    statement, and three DDL lines do not need that treatment.
    """
    head, _ = _split(live_url())
    return create_engine(f"{head}/postgres", isolation_level="AUTOCOMMIT", echo=False)


def blocking_connections() -> list[tuple[str, str]]:
    """
    (application_name, client_addr) of every OTHER session on the live
    database. A non-empty list is why a refresh cannot proceed.
    """
    engine = _admin_engine()
    try:
        with engine.connect() as conn:
            rows = conn.execute(
                text(
                    "SELECT coalesce(nullif(application_name, ''), '(unnamed)'), "
                    "       coalesce(host(client_addr), 'local') "
                    "FROM pg_stat_activity "
                    "WHERE datname = :db AND pid <> pg_backend_pid()"
                ),
                {"db": live_database_name()},
            ).all()
        return [(str(a), str(b)) for a, b in rows]
    finally:
        engine.dispose()


def _port() -> int:
    return urllib.parse.urlsplit(live_url()).port or 5432


def _credentials() -> tuple[str, str]:
    u = urllib.parse.urlsplit(live_url())
    return u.username or "postgres", urllib.parse.unquote(u.password or "")


def postgres_container() -> str | None:
    """
    The container publishing the database's port, or None.

    Matched on the published port rather than on a name, so renaming the
    container does not silently drop the suite onto the fallback path. Only
    consulted when the database is on this machine: a remote host's port
    number says nothing about what is running in Docker locally.
    """
    host = urllib.parse.urlsplit(live_url()).hostname
    if host not in ("localhost", "127.0.0.1", "::1"):
        return None
    if not shutil.which("docker"):
        return None
    try:
        result = subprocess.run(
            ["docker", "ps", "--filter", f"publish={_port()}", "--format", "{{.Names}}"],
            capture_output=True,
            text=True,
            timeout=20,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    names = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    return names[0] if names else None


def _drop_test_database() -> None:
    engine = _admin_engine()
    try:
        with engine.connect() as conn:
            # FORCE is safe here and only here: this is the database we own and
            # are about to replace. It is never used against the live one.
            conn.execute(text(f'DROP DATABASE IF EXISTS "{test_database_name()}" WITH (FORCE)'))
    finally:
        engine.dispose()


def _copy_via_docker(container: str) -> None:
    """pg_dump | psql, both inside the container, both version 17."""
    live, test = live_database_name(), test_database_name()
    user, password = _credentials()

    engine = _admin_engine()
    try:
        with engine.connect() as conn:
            conn.execute(text(f'CREATE DATABASE "{test}"'))
    finally:
        engine.dispose()

    # ON_ERROR_STOP so a half-restored database fails the run instead of
    # passing tests against a database missing half its tables.
    script = (
        f'pg_dump -U {user} -d {live} '
        f'| psql -q -v ON_ERROR_STOP=1 -U {user} -d {test}'
    )
    result = subprocess.run(
        ["docker", "exec", "-e", f"PGPASSWORD={password}", container, "sh", "-c", script],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        _drop_test_database()
        raise RuntimeError(
            f"Copy failed inside container {container!r}:\n"
            f"{(result.stderr or result.stdout).strip()[:2000]}"
        )


def _copy_via_template() -> None:
    """Server-side copy. Needs exclusive access to the live database."""
    live, test = live_database_name(), test_database_name()
    blockers = blocking_connections()
    if blockers:
        listed = "\n".join(f"      {name}  from {addr}" for name, addr in blockers)
        raise RuntimeError(
            f"Cannot copy {live}: {len(blockers)} other session(s) are connected, "
            f"and Docker is not\n    available to copy it another way.\n"
            f"{listed}\n\n"
            f"    PostgreSQL will not use a database as a template while anything "
            f"else is on it.\n"
            f"    Stop the FastAPI dev server (and any open psql) and run this "
            f"again. Nothing is\n"
            f"    terminated for you on purpose — evicting a session you are "
            f"demonstrating from, to\n"
            f"    run a test, is the worse failure."
        )
    engine = _admin_engine()
    try:
        with engine.connect() as conn:
            conn.execute(text(f'CREATE DATABASE "{test}" TEMPLATE "{live}"'))
    finally:
        engine.dispose()


def refresh() -> str:
    """
    Drop the test database and recreate it as a copy of the live one.

    Returns the test database's URL. Raises with an actionable message if the
    copy cannot be made — the caller should print it, not swallow it.
    """
    _drop_test_database()
    container = postgres_container()
    if container:
        _copy_via_docker(container)
    else:
        _copy_via_template()
    return test_url()


def require_test_database() -> None:
    """
    Refuse to run unless app.database is pointed at the test copy.

    Called at the top of every test that writes. The check is made against the
    engine the application actually built — not against the environment — so it
    cannot be satisfied by an env var that was set too late to matter.
    """
    from app.database import engine

    actual = engine.url.database
    if actual == test_database_name():
        return

    raise SystemExit(
        f"\n  REFUSING TO RUN.\n\n"
        f"    This test writes, and app.database is connected to {actual!r}.\n"
        f"    Writing tests may only run against {test_database_name()!r}, a "
        f"fresh copy of it.\n\n"
        f"    Run the suite through its entry point instead:\n\n"
        f"        python run_tests.py\n"
        f"        python run_tests.py test_anchors.py      # just this one\n"
    )


def describe() -> str:
    host = urllib.parse.urlsplit(live_url()).hostname or "?"
    return f"{test_database_name()} on {host}, copied from {live_database_name()}"
