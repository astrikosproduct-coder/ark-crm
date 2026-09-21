"""
Phase A end-to-end: the On Hold journey, one step at a time.

    python walkthrough_on_hold.py

Not a unit test. This walks the exact sequence a BD user walks, through the
real API against the real database, and prints what the screen would show at
each step — so the claim "one input, one place, one save" can be checked
rather than taken on trust.

THE JOURNEY BEFORE PHASE A
---------------------------
    open a Lead -> Stage 0 tab -> Edit -> Lead Status = On Hold
    -> nothing appears -> SAVE
    -> page re-renders, a panel appears below the section
    -> type the reason -> SAVE AGAIN

Two saves, two surfaces, and nothing on screen between the first two steps
saying a reason was going to be wanted. On a Stage 1 lead it was worse: the
status lived in STAGE 0 — CONNECT, so the user had to click back a tab first.

WHAT IT SHOULD BE NOW
---------------------
    open a Lead -> Details tab -> Edit -> Lead Status = On Hold
    -> the reason box appears immediately beneath it, required
    -> type the reason -> SAVE

One save. And the answer is kept per stage, so a lead held at Stage 0 and held
again at Stage 3 has two answers, both readable, neither overwriting the other.

The record this creates is deleted before the script exits.
"""

from __future__ import annotations

import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import select, text  # noqa: E402

from app.database import SessionLocal, engine  # noqa: E402

engine.echo = False

from app.main import app  # noqa: E402
from app.metadata_resolver import resolved_fields  # noqa: E402
from app.models import FieldPlacement  # noqa: E402
from test_support import sign_in_as_admin  # noqa: E402

client = TestClient(app)
user = sign_in_as_admin(app)

STEPS: list[tuple[str, bool, str]] = []


def step(n: str, ok: bool, detail: str = "") -> None:
    STEPS.append((n, ok, detail))
    mark = "OK  " if ok else "FAIL"
    print(f"  {mark}  {n}")
    if detail:
        print(f"          {detail}")


print("=" * 74)
print("PHASE A WALKTHROUGH — putting a Lead on hold")
print("=" * 74)
print(f"\n  acting as {user.user_id} ({user.email})\n")

# ---------------------------------------------------------------- 0. layout
print("0  what the register says the screen looks like")
print("-" * 46)

with SessionLocal() as db:
    rows = {r["api_name"]: r for r in resolved_fields(db, "leads")}

status = rows.get("lead_status")
reason = rows.get("on_hold_reason")

step(
    "Lead Status lives in RECORD STATE, not in a stage section",
    status is not None and status["section"].startswith("RECORD STATE"),
    f"section={status['section'] if status else '?'}",
)
step(
    "RECORD STATE has no capture stage, so it draws on Details only",
    status is not None and status["capture_stage"] is None,
    f"capture_stage={status['capture_stage'] if status else '?'} "
    f"(a value here would put it on the Stage 0 tab AS WELL)",
)
step(
    "On Hold Reason is anchored to Lead Status",
    reason is not None
    and reason["anchor_field"] == "lead_status"
    and reason["anchor_position"] == "after",
    f"anchor={reason['anchor_field'] if reason else '?'}/"
    f"{reason['anchor_position'] if reason else '?'} span={reason['layout_span'] if reason else '?'}",
)
step(
    "…while still filed under Aging in the register",
    reason is not None and reason["section"] == "Aging",
    f"section={reason['section'] if reason else '?'} — section says WHAT KIND, "
    f"anchor says WHERE. They disagree on purpose.",
)
step(
    "it states the condition that DEMANDS it, not just the one that shows it",
    reason is not None
    and reason["condition"] == "lead_status == 'On Hold'"
    and reason["visibility_condition"] == "lead_status == 'On Hold'",
    f"condition={reason['condition']!r}" if reason else "",
)

# ------------------------------------------------------------ 1. create it
print("\n1  create a lead — the create form no longer asks for status")
print("-" * 46)

created = client.post(
    "/api/leads",
    json={
        "opportunity_name": "Phase A walkthrough — delete me",
        "project_stage": "0_CONNECT",
        "lead_status": "OPEN",
        "probability_pct": 5,
    },
)
if created.status_code not in (200, 201):
    print(f"\n  could not create a lead: {created.status_code} {created.text[:300]}")
    sys.exit(1)

lead = created.json()
lead_id = lead.get("lead_id") or lead.get("id")
step(
    f"lead created — {lead_id}",
    bool(lead_id),
    "LeadCreatePage seeds lead_status: 'OPEN' because the field moved off the "
    "one section that page renders",
)
step(
    "it opens Open, not null",
    lead.get("lead_status") == "OPEN",
    f"lead_status={lead.get('lead_status')!r}",
)

# ------------------------------------------------- 2. one save, both fields
print("\n2  put it on hold — status AND reason in ONE save")
print("-" * 46)

held = client.patch(
    f"/api/leads/{lead_id}",
    json={
        "lead_status": "ON_HOLD",
        # The per-stage key the anchored box writes. This is the payload the
        # single save sends: the question and its answer travel together
        # because they are in the same RecordForm.
        "on_hold_reason__s0": "Client budget freeze until Q3",
    },
)
step(
    "the save was accepted",
    held.status_code == 200,
    f"{held.status_code} {held.text[:200] if held.status_code != 200 else ''}",
)

# ------------------------------------------- 3. the bug that would have hid
print("\n3  read it back — the per-stage value actually persisted")
print("-" * 46)

fetched = client.get(f"/api/leads/{lead_id}").json()
step(
    "status is On Hold",
    fetched.get("lead_status") == "ON_HOLD",
    f"lead_status={fetched.get('lead_status')!r}",
)
step(
    "the Stage 0 reason survived the round trip",
    fetched.get("on_hold_reason__s0") == "Client budget freeze until Q3",
    f"on_hold_reason__s0={fetched.get('on_hold_reason__s0')!r}",
)

with SessionLocal() as db:
    stored = db.execute(
        text("SELECT custom_fields FROM leads WHERE lead_id = :id"), {"id": lead_id}
    ).scalar()
step(
    "and it is really in the JSONB column, not just echoed back",
    isinstance(stored, dict) and "on_hold_reason__s0" in stored,
    f"custom_fields={stored!r}",
)

# ------------------------------------------------- 4. per stage, not shared
print("\n4  hold it again at Stage 3 — two answers, neither overwriting")
print("-" * 46)

client.patch(
    f"/api/leads/{lead_id}",
    json={"project_stage": "3_PRESCRIPTION", "on_hold_reason__s3": "Awaiting board sign-off"},
)
again = client.get(f"/api/leads/{lead_id}").json()
step(
    "Stage 0 still says what Stage 0 said",
    again.get("on_hold_reason__s0") == "Client budget freeze until Q3",
    f"__s0={again.get('on_hold_reason__s0')!r}",
)
step(
    "Stage 3 says something different",
    again.get("on_hold_reason__s3") == "Awaiting board sign-off",
    f"__s3={again.get('on_hold_reason__s3')!r}",
)
step(
    "the Reasons panel on Details has both to show",
    again.get("on_hold_reason__s0") != again.get("on_hold_reason__s3"),
    "this is what the inline box structurally cannot show — it only ever "
    "holds the stage being edited",
)

# --------------------------------------------------------- 5. still refused
print("\n5  the rule did not get loose while widening it")
print("-" * 46)

# Two routes in, two deliberately different contracts — see resolve_write in
# app/custom_fields.py. A FLAT payload ignores what it does not recognise,
# because the same payload also carries `id`, `__labels` and computed values
# that were never fields; rejecting there would make every save fail. An
# EXPLICIT custom_fields object is a caller stating exactly what it means to
# store, so an unknown key there is an error, not noise.
client.patch(f"/api/leads/{lead_id}", json={"rfp_documnet__s3": "junk"})
after_typo = client.get(f"/api/leads/{lead_id}").json()
step(
    "a typo'd base name in a flat payload is ignored, and NOT stored",
    "rfp_documnet__s3" not in after_typo,
    "flat payloads drop what they do not recognise — the save succeeds, the "
    "junk does not land",
)

client.patch(f"/api/leads/{lead_id}", json={"on_hold_reason__sx": "junk"})
after_bad = client.get(f"/api/leads/{lead_id}").json()
step(
    "a non-numeric stage suffix is ignored too — __sx is not a stage",
    "on_hold_reason__sx" not in after_bad,
    "STAGE_SCOPED_KEY anchors on digits only, so notes__something is never "
    "mistaken for a per-stage value",
)

rejected = client.patch(
    f"/api/leads/{lead_id}", json={"custom_fields": {"rfp_documnet__s3": "junk"}}
)
step(
    "but an EXPLICIT custom_fields object rejects it rather than dropping it",
    rejected.status_code == 422,
    f"{rejected.status_code} — {rejected.text[:160]}",
)

with SessionLocal() as db:
    final = db.execute(
        text("SELECT custom_fields FROM leads WHERE lead_id = :id"), {"id": lead_id}
    ).scalar()
step(
    "after all of that, the JSONB holds the two real reasons and nothing else",
    isinstance(final, dict)
    and set(final) == {"on_hold_reason__s0", "on_hold_reason__s3"},
    f"custom_fields keys={sorted(final) if isinstance(final, dict) else final!r}",
)

# ----------------------------------------------------------------- teardown
with SessionLocal() as db:
    db.execute(text("DELETE FROM leads WHERE lead_id = :id"), {"id": lead_id})
    db.commit()
print(f"\n  teardown — {lead_id} deleted")

with SessionLocal() as db:
    anchored = db.scalars(
        select(FieldPlacement).where(
            FieldPlacement.anchor_field.isnot(None), FieldPlacement.status == "active"
        )
    ).all()
print(f"  register — {len(anchored)} anchored placements, unchanged by this run")

failed = [name for name, ok, _ in STEPS if not ok]
print("\n" + "=" * 74)
if failed:
    print(f"{len(STEPS) - len(failed)} passed, {len(failed)} FAILED\n")
    for name in failed:
        print(f"    {name}")
    sys.exit(1)
print(f"ALL {len(STEPS)} STEPS PASSED — one input, one place, one save.")
print("=" * 74)
