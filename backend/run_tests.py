"""
The backend test suite's one entry point.

    python run_tests.py                       # everything
    python run_tests.py test_anchors.py       # one script
    python run_tests.py --no-refresh          # reuse the existing copy

WHAT IT DOES
------------
1. Copies the live database to `<name>_test` (see test_db.py).
2. Runs each test script in a subprocess with DATABASE_URL pointed at the copy.
3. Runs the parity check twice — once before the writing tests and once after.

WHY DATABASE_URL IS SET IN THE SUBPROCESS AND NOT IN A FIXTURE
---------------------------------------------------------------
app/database.py builds its engine at import time, so by the time any test code
runs the connection is already made. Setting the variable in the child's
environment is the only interception that is not import-order dependent, and
python-dotenv's load_dotenv() does not override a variable that is already set,
so .env cannot win it back.

The scripts do not trust this. Each writing test calls
test_db.require_test_database(), which inspects the engine the application
actually built. Running one directly still refuses, with the command to use.

WHY PARITY RUNS TWICE
---------------------
The first run proves the copy is faithful — that the test database is the
register that ships, not an approximation of it. The second proves the writing
tests put back everything they touched. A suite that passes its own tests and
leaves the register altered has not passed; before this, nothing checked.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import test_db  # noqa: E402

HERE = Path(__file__).parent

#: Read-only. Proves the copy is the register, and later that it still is.
PARITY = "test_parity.py"

#: Every test that writes, in dependency order — the register model first, the
#: value plumbing on top of it, the Round 6 gap closures last.
WRITING = [
    "test_placements.py",
    "test_anchors.py",
    "test_custom_fields.py",
    "test_metadata_round6.py",
    "test_round6_gaps.py",
    "test_progression.py",
    "test_audit_timeline.py",
    "test_pursuit_groups.py",
    "test_partner_stamps.py",
    "test_partner_lifecycle.py",
    "test_lead_delete.py",
    "test_conversions.py",
    "test_deal_milestones.py",
    "test_dashboard.py",
    "test_dashboard_weighted.py",
    "test_list_query.py",
    "test_feedback.py",
    "test_spreadsheets.py",
    "test_delete_guards.py",
    "test_required_fields.py",
    "test_pursuit_erase.py",
]


def run(script: str, env: dict[str, str]) -> tuple[str, bool, float]:
    print("\n" + "=" * 74)
    print(f"  {script}")
    print("=" * 74, flush=True)
    started = time.monotonic()
    result = subprocess.run([sys.executable, script], cwd=HERE, env=env)
    return script, result.returncode == 0, time.monotonic() - started


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    refresh = "--no-refresh" not in sys.argv

    if refresh:
        print(f"Copying {test_db.live_database_name()} -> {test_db.test_database_name()} ...")
        try:
            test_db.refresh()
        except RuntimeError as exc:
            print(f"\n  {exc}\n")
            return 2
        print(f"  ready: {test_db.describe()}")
    else:
        print(f"  reusing: {test_db.describe()}")

    env = dict(os.environ)
    env["DATABASE_URL"] = test_db.test_url()

    if args:
        scripts = args
        closing_parity = False
    else:
        scripts = [PARITY, *WRITING]
        closing_parity = True

    results = [run(script, env) for script in scripts]

    if closing_parity:
        print("\n" + "=" * 74)
        print("  test_parity.py  (again — did the writing tests put it all back?)")
        print("=" * 74, flush=True)
        started = time.monotonic()
        code = subprocess.run([sys.executable, PARITY], cwd=HERE, env=env).returncode
        results.append(("test_parity.py (after)", code == 0, time.monotonic() - started))

    print("\n" + "=" * 74)
    print("  SUITE")
    print("=" * 74)
    failed = [name for name, ok, _ in results if not ok]
    for name, ok, seconds in results:
        print(f"  {'pass' if ok else 'FAIL'}  {name:<28} {seconds:6.1f}s")
    print()
    if failed:
        print(f"  {len(failed)} of {len(results)} FAILED: {', '.join(failed)}")
        return 1
    print(f"  all {len(results)} passed, against {test_db.describe()}")
    print("  the demonstrated database was never opened for writing.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
