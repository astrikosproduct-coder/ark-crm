"""
The audit trail tells the truth about who, when and what.

These are the tests for the three claims the History timeline rests on, and
each one is a claim that was FALSE before Sep 2026:

1. WHO comes from the Entra session, not the request body. The browser used to
   send `modified_by`, so the record's own idea of who last touched it was
   whatever the person touching it typed. A BD could sign a colleague's name to
   their own edit without leaving the form.

2. WHEN comes from the server clock. `modified_date` was `new Date()` in the
   browser — so a laptop with a wrong clock wrote a wrong timestamp with no ill
   intent required at all, and a deliberate one could write any date it liked.

3. WHAT is a before/after diff, not a list of field names. The editor PUTs a
   whole section, so `changed_fields` reports twenty fields for a one-field
   save and never held an old value.

The forgery tests below send deliberately wrong values in the payload and
assert the server ignored them. They are the point of the file: a test that
only checked the happy path would still pass if every one of these fields went
back to being client-writable tomorrow.
"""

import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from test_db import require_test_database  # noqa: E402

# Before app.main is imported, and so before any engine exists to write with.
# This file creates and deletes Leads; run directly, without this, it wrote
# them to the LIVE database — and a run that failed partway never reached its
# own cleanup, which is how five "Audit trail probe" leads were left behind in
# Sep 2026. Run it through run_tests.py, which points it at the test copy.
require_test_database()

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from test_support import sign_in_as_admin  # noqa: E402

client = TestClient(app)
USER = sign_in_as_admin(app)

#: A value no honest client would send: a real user id that is not the signed-in
#: one, and a timestamp two years in the past.
FORGED_ACTOR = "USR-999"
FORGED_TIME = datetime(2024, 1, 1, tzinfo=timezone.utc).isoformat()

failures: list[str] = []


def check(label: str, condition: bool, detail: str = "") -> None:
    if condition:
        print(f"  pass  {label}")
    else:
        failures.append(f"{label}{' — ' + detail if detail else ''}")
        print(f"  FAIL  {label}{' — ' + detail if detail else ''}")


def audit_rows(record_id: str) -> list[dict]:
    r = client.get("/api/audit-log", params={"record_id": record_id})
    r.raise_for_status()
    return r.json()


def changes_of(row: dict) -> dict[str, dict]:
    """The row's diff, keyed by field name, for readable assertions."""
    return {c["field"]: c for c in (row.get("changed") or [])}


print("\n" + "=" * 74)
print("  AUDIT TRAIL — identity, clock and diff")
print("=" * 74)

# --------------------------------------------------------------- create

before_create = datetime.now(timezone.utc) - timedelta(seconds=5)

created = client.post(
    "/api/leads",
    json={
        "opportunity_name": "Audit trail probe",
        "country": "AE",
        "project_stage": "0_CONNECT",
        "lead_status": "OPEN",
        # Both forged. Neither may survive.
        "created_by": FORGED_ACTOR,
        "modified_by": FORGED_ACTOR,
        "created_date": FORGED_TIME,
        "modified_date": FORGED_TIME,
    },
)
check("create returns 201", created.status_code == 201, created.text[:300])
lead = created.json()
lead_id = lead["id"]

check(
    "created_by is the signed-in user, not the payload's",
    lead["created_by"] == USER.user_id,
    f"got {lead['created_by']!r}, forged value was {FORGED_ACTOR!r}",
)
check(
    "modified_by is the signed-in user, not the payload's",
    lead["modified_by"] == USER.user_id,
    f"got {lead['modified_by']!r}",
)

stamped = datetime.fromisoformat(lead["created_date"])
check(
    "created_date is the server clock, not the payload's 2024 date",
    stamped >= before_create,
    f"got {lead['created_date']}",
)

rows = audit_rows(lead_id)
# A create writes one 'created' row. Taking the stage's Progression % /
# Probability % is part of creating the record, not a second event.
creates = [r for r in rows if r["action"] == "created"]
check("create wrote exactly one 'created' row", len(creates) == 1, f"got {len(creates)}")
check(
    "every audit row from the request names the session user",
    all(r["actor"] == USER.user_id for r in rows),
    f"got {[r['actor'] for r in rows]!r}",
)
check("a create carries no diff", creates and not creates[0].get("changed"))

check(
    "a create writes no separate progression/probability row",
    not [r for r in rows if r["action"] in ("stage_pct", "overridden")],
    f"got {[r['action'] for r in rows]!r}",
)

# --------------------------------------------------------------- update

patched = client.patch(
    f"/api/leads/{lead_id}",
    json={
        "overall_rag": "GREEN",
        "city_state": "Dubai",
        # Sent unchanged: must NOT appear in the diff.
        "country": "AE",
        # Forged again, on the path that actually matters — the one the record
        # editor uses on every save.
        "modified_by": FORGED_ACTOR,
        "modified_date": FORGED_TIME,
    },
)
check("patch returns 200", patched.status_code == 200, patched.text[:300])
updated = patched.json()

check(
    "a forged modified_by on update is ignored",
    updated["modified_by"] == USER.user_id,
    f"got {updated['modified_by']!r}",
)
check(
    "a forged modified_date on update is ignored",
    datetime.fromisoformat(updated["modified_date"]) >= before_create,
    f"got {updated['modified_date']}",
)

rows = audit_rows(lead_id)
updates = [r for r in rows if r["action"] == "updated"]
check("the update wrote an 'updated' row", len(updates) == 1, f"got {len(updates)}")

latest = updates[0]
diff = changes_of(latest)

check(
    "the diff names overall_rag with both values",
    diff.get("overall_rag", {}).get("from") is None
    and diff.get("overall_rag", {}).get("to") == "GREEN",
    f"got {diff.get('overall_rag')!r}",
)
check(
    "the diff names city_state",
    diff.get("city_state", {}).get("to") == "Dubai",
    f"got {diff.get('city_state')!r}",
)
check(
    "a field sent UNCHANGED is not reported as a change",
    "country" not in diff,
    f"country appeared as {diff.get('country')!r}",
)
check(
    "system fields never appear in the diff",
    not {"modified_by", "modified_date", "created_by", "created_date"} & set(diff),
    f"got {sorted(set(diff))}",
)
check(
    "changed_fields still records everything the request carried",
    "country" in (latest.get("changed_fields") or []),
    f"got {latest.get('changed_fields')!r}",
)

# --------------------------------------------------------------- a real move

moved = client.patch(f"/api/leads/{lead_id}", json={"overall_rag": "RED"})
check("second update returns 200", moved.status_code == 200, moved.text[:300])
diff = changes_of([r for r in audit_rows(lead_id) if r["action"] == "updated"][0])
check(
    "an edited value records its previous value, not just the new one",
    diff.get("overall_rag", {}).get("from") == "GREEN"
    and diff.get("overall_rag", {}).get("to") == "RED",
    f"got {diff.get('overall_rag')!r}",
)

# --------------------------------------------------- child lists (the noise bug)
#
# The record editor PUTs a whole section, child lists included. Reporting a list
# as changed because it was PRESENT — which is what the first cut did — meant
# editing one text box logged "Demo Attendees updated" every single time, and
# the History tab filled with changes nobody had made.

# `attendee` is a foreign key to contacts and `organisation` one to accounts,
# so the row carries only the free-text column. This is a test about whether a
# list CHANGE is detected, not about what a row may contain.
attendee = {"attendee": None, "job_title": "CTO", "organisation": None, "attendee_role": None}

added = client.patch(f"/api/leads/{lead_id}", json={"demo_attendees": [attendee]})
check("adding a child row returns 200", added.status_code == 200, added.text[:300])
diff = changes_of([r for r in audit_rows(lead_id) if r["action"] == "updated"][0])
check(
    "adding a child row IS recorded",
    diff.get("demo_attendees", {}).get("kind") == "list",
    f"got {diff.get('demo_attendees')!r}",
)

# The same rows again, exactly as the editor would resend them.
resent = client.patch(
    f"/api/leads/{lead_id}", json={"demo_attendees": [attendee], "city_state": "Dubai Marina"}
)
check("resending an unchanged child list returns 200", resent.status_code == 200, resent.text[:300])
diff = changes_of([r for r in audit_rows(lead_id) if r["action"] == "updated"][0])
check(
    "an UNCHANGED child list is NOT reported as a change",
    "demo_attendees" not in diff,
    f"demo_attendees appeared as {diff.get('demo_attendees')!r}",
)
check(
    "the real change in that same save is still recorded",
    diff.get("city_state", {}).get("to") == "Dubai Marina",
    f"got {diff.get('city_state')!r}",
)

removed = client.patch(f"/api/leads/{lead_id}", json={"demo_attendees": []})
check("removing a child row returns 200", removed.status_code == 200, removed.text[:300])
diff = changes_of([r for r in audit_rows(lead_id) if r["action"] == "updated"][0])
check(
    "removing a child row IS recorded",
    diff.get("demo_attendees", {}).get("kind") == "list",
    f"got {diff.get('demo_attendees')!r}",
)

# --------------------------------------------------------------- transitions

transition = client.post(
    "/api/transitions",
    json={
        "module": "leads",
        "record_id": lead_id,
        "from": 0,
        "to": 1,
        "reason": "Demo booked.",
        "is_skip": False,
        "is_reversal": False,
        "actor": FORGED_ACTOR,
        "timestamp": FORGED_TIME,
    },
)
check("transition returns 201", transition.status_code == 201, transition.text[:300])
row = transition.json()
check(
    "a forged transition actor is ignored",
    row["actor"] == USER.user_id,
    f"got {row['actor']!r}",
)
check(
    "a forged transition timestamp is ignored",
    datetime.fromisoformat(row["timestamp"]) >= before_create,
    f"got {row['timestamp']}",
)

# --------------------------------------------------------------- clean up

client.delete(f"/api/leads/{lead_id}")

print("-" * 74)
if failures:
    print(f"  {len(failures)} FAILED")
    for line in failures:
        print(f"    - {line}")
    sys.exit(1)
print("  all passed")
