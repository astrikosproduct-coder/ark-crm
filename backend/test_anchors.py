"""
Phase A — field anchors: position as a property of the placement.

    python test_anchors.py

WHAT IS BEING PROVED
--------------------
    1   the anchor configuration  every anchored placement, A2's six reasons
        and Leads Stage 1's three, anchored and ruled
    2   the resolver              carries anchors into fields.json
    3   setting an anchor         works, and defaults its position sensibly
    4   the four refusals         self, cross-module, bad position, orphan
    5   cycles                    refused; chains are not
    6   database integrity        the CHECK constraints refuse what they must
    7   delete releases           dependents return to their own section
    8   rollback carries it       a snapshot restores WHERE a field drew, and
                                  stage_scoped / computed_expr with it
    9   per-stage values PERSIST   the bug A2 would otherwise have walked into

Assertions are made against PostgreSQL and against the resolver rather than
against the API's account of itself, same as test_placements.py: what is being
proved is where the authority lives.

THIS RUNS AGAINST THE REAL DATABASE, so every test that writes SNAPSHOTS THE
ROWS IT TOUCHES FIRST and puts them back in a finally — not to NULL, which
would quietly delete the A2 configuration the app now depends on, but to
whatever they held on the way in. An earlier version of this file reset to NULL
and would have unanchored Leads the first time it was run after A2.
"""

from __future__ import annotations

import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from sqlalchemy import func, select, text  # noqa: E402
from sqlalchemy.exc import IntegrityError  # noqa: E402
from fastapi import HTTPException  # noqa: E402

from app.database import SessionLocal, engine  # noqa: E402

engine.echo = False

from test_db import require_test_database  # noqa: E402

# This test writes. Refuse to run against the database the prototype is
# demonstrated from — the copy is made by run_tests.py. See test_db.py.
require_test_database()

from app import metadata_resolver as R  # noqa: E402
from app.models import FieldPlacement  # noqa: E402
from app.routers.metadata import _anchored_to, _apply_anchor  # noqa: E402

PASSED = 0
FAILED: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    global PASSED
    if condition:
        PASSED += 1
        print(f"  PASS  {name}")
    else:
        FAILED.append(f"{name}{(' — ' + detail) if detail else ''}")
        print(f"  FAIL  {name}{(' — ' + detail) if detail else ''}")


def head(title: str) -> None:
    print(f"\n{title}\n{'-' * len(title)}")


def refuses(fn) -> tuple[bool, str]:
    """Run fn, expecting an HTTPException. Returns (refused, message)."""
    try:
        fn()
    except HTTPException as exc:
        return True, str(exc.detail)
    return False, "no exception raised"


def placement(db, module: str, api_name: str) -> FieldPlacement | None:
    return db.scalar(
        select(FieldPlacement).where(
            FieldPlacement.module_key == module,
            FieldPlacement.api_name == api_name,
            FieldPlacement.status == "active",
        )
    )


db = SessionLocal()

# =====================================================================
# 1  the A2 configuration
# =====================================================================

head("1  every anchored placement is where Phase A put it")

# (module, api_name) -> (anchor, span, section it stays filed under)
#
# Two groups, asserted together because what matters is the WHOLE anchored
# set: a count that only knows about one group cannot tell a new anchor apart
# from a drifted one.
#
#   the six reason placements          (A2, anchor_reasons.py)
#   Leads Stage 1's three conditionals (A3, anchor_stage1.py)
#
# Both scripts are deleted as of B3. They existed because Administration had no
# anchor control and the only way to set one was to write it; the field editor
# has one now, which is what they each said should end them. This list is the
# record of what they configured, and the assertion that it is still there.
#
# The Stage 1 three are the case that proves the model generalises: they are
# ordinary register fields in an ordinary STAGE section, not CROSS-CUTTING
# strays, and they were anchored because sort_order had already let one of
# them drift ABOVE the field that reveals it.
ANCHORED = {
    ("leads", "on_hold_reason"): ("lead_status", "full", "CROSS-CUTTING"),
    ("leads", "closed_lost_reason_code"): ("lead_status", "half", "CROSS-CUTTING"),
    ("opportunities", "on_hold_reason"): ("lead_status", "full", "CROSS-CUTTING"),
    ("opportunities", "closed_lost_reason_code"): ("lead_status", "half", "CROSS-CUTTING"),
    ("deals", "on_hold_reason"): ("lead_status", "full", "CROSS-CUTTING"),
    ("deals", "closed_lost_reason_code"): ("lead_status", "half", "CROSS-CUTTING"),
    ("leads", "data_site_access_confirmation_document"): (
        "agreed_next_step",
        "full",
        "STAGE 1 — DEMO PRESENTATION",
    ),
    ("leads", "pilot_commercial_model"): (
        "agreed_next_step",
        "half",
        "STAGE 1 — DEMO PRESENTATION",
    ),
    ("leads", "pilot_fee"): (
        "agreed_next_step",
        "half",
        "STAGE 1 — DEMO PRESENTATION",
    ),
}

total_anchored = db.scalar(
    select(func.count()).select_from(FieldPlacement).where(
        FieldPlacement.anchor_field.isnot(None), FieldPlacement.status == "active"
    )
)
check(
    f"exactly {len(ANCHORED)} active placements are anchored, and no others drifted",
    total_anchored == len(ANCHORED),
    f"{total_anchored} anchored",
)

for (module, api_name), (anchor, span, section_label) in ANCHORED.items():
    p = placement(db, module, api_name)
    if p is None:
        check(f"{module}.{api_name} exists", False, "no active placement")
        continue
    check(
        f"{module}.{api_name} — anchored to {anchor}, after, span {span}",
        p.anchor_field == anchor
        and p.anchor_position == "after"
        and p.layout_span == span,
        f"{p.anchor_field}/{p.anchor_position}/{p.layout_span}",
    )
    # The gap the plan missed. A Conditional row carrying only a
    # visibility_condition appears and then lets the user save straight past
    # it, because requirementOf reads `condition`, not visibility_condition.
    # The six reasons had to be given one; the Stage 1 three already had one,
    # and are the only rows in the register that did.
    check(
        f"{module}.{api_name} — states the condition that DEMANDS it",
        bool(p.condition) and anchor in (p.condition or ""),
        repr(p.condition),
    )
    # Section says what KIND of field this is; anchor says where it draws.
    # The reasons stay CROSS-CUTTING while rendering next to a status field
    # in another section — that disagreement is the whole design.
    check(
        f"{module}.{api_name} — still filed under {section_label}",
        p.section.label == section_label,
        p.section.label,
    )

# =====================================================================
# 2  the resolver carries them
# =====================================================================

head("2  the resolver carries anchors into fields.json")

check(
    "anchor keys are declared in RESOLVED_KEYS",
    {"anchor_field", "anchor_position", "layout_span"} <= set(R.RESOLVED_KEYS),
    str(R.RESOLVED_KEYS),
)

rows = R.resolved_fields(db, "leads")
check(
    "every resolved field row carries all three keys",
    all(
        k in r for r in rows for k in ("anchor_field", "anchor_position", "layout_span")
    ),
)
reason_row = next(r for r in rows if r["api_name"] == "on_hold_reason")
check(
    "the anchored reason resolves with its anchor",
    reason_row["anchor_field"] == "lead_status"
    and reason_row["anchor_position"] == "after"
    and reason_row["layout_span"] == "full",
    str(reason_row["anchor_field"]),
)
check(
    "and still reports CROSS-CUTTING as its section — the register is untouched",
    reason_row["section"] == "CROSS-CUTTING",
    reason_row["section"],
)
plain_row = next(r for r in rows if r["api_name"] == "lead_status")
check(
    "an unanchored field resolves to null, not to a missing key",
    plain_row["anchor_field"] is None and plain_row["anchor_position"] is None,
    str(plain_row["anchor_field"]),
)

# =====================================================================
# 3-8  the live tests, every touched row snapshotted and put back
# =====================================================================

TOUCHED = [
    ("leads", "on_hold_reason"),
    ("leads", "closed_lost_reason_code"),
    ("leads", "stage_skip_reason"),
]

before: dict[int, tuple] = {}
for module, api_name in TOUCHED:
    p = placement(db, module, api_name)
    if p is not None:
        before[p.id] = (p.anchor_field, p.anchor_position, p.layout_span, p.condition)


def restore() -> None:
    """Put every touched row back to what it held on the way in."""
    for pid, (anchor, position, span, condition) in before.items():
        p = db.get(FieldPlacement, pid)
        if p is None:
            continue
        p.anchor_field = anchor
        p.anchor_position = position
        p.layout_span = span
        p.condition = condition
    db.commit()


try:
    reason = placement(db, "leads", "on_hold_reason")
    lost = placement(db, "leads", "closed_lost_reason_code")
    skip = placement(db, "leads", "stage_skip_reason")
    assert reason and lost and skip, "the three CROSS-CUTTING reasons must exist on leads"

    head("3  setting and clearing an anchor")

    _apply_anchor(db, reason, {"anchor_field": None})
    db.commit()
    check(
        "anchor_field: null clears both columns",
        reason.anchor_field is None and reason.anchor_position is None,
    )

    _apply_anchor(db, reason, {"anchor_field": "lead_status"})
    db.commit()
    check(
        "position defaults to 'after' — beneath the question that revealed it",
        reason.anchor_position == "after",
        str(reason.anchor_position),
    )

    _apply_anchor(db, reason, {"anchor_field": "lead_status", "anchor_position": "beside"})
    db.commit()
    check("position can be changed to 'beside'", reason.anchor_position == "beside")

    head("4  the four refusals")

    refused, msg = refuses(
        lambda: _apply_anchor(db, reason, {"anchor_field": "on_hold_reason"})
    )
    check("a field cannot be anchored to itself", refused, msg)

    refused, msg = refuses(
        lambda: _apply_anchor(db, reason, {"anchor_field": "not_a_field_anywhere"})
    )
    check("an anchor must name a field this module actually has", refused, msg)

    refused, msg = refuses(
        lambda: _apply_anchor(
            db, reason, {"anchor_field": "lead_status", "anchor_position": "above"}
        )
    )
    check("anchor_position is restricted to after/beside", refused, msg)

    # Only when there is no anchor to position AGAINST. Sending a bare
    # anchor_position for a field that is already anchored is a legitimate
    # edit — "keep the anchor, move it beside instead of under" — and is the
    # one the Phase-B ··· menu will send.
    _apply_anchor(db, reason, {"anchor_field": None})
    refused, msg = refuses(lambda: _apply_anchor(db, reason, {"anchor_position": "after"}))
    check("a position with no anchor at all is refused, not silently kept", refused, msg)

    _apply_anchor(db, reason, {"anchor_field": "lead_status"})
    _apply_anchor(db, reason, {"anchor_position": "beside"})
    check(
        "but a bare position on an ALREADY anchored field just moves it",
        reason.anchor_field == "lead_status" and reason.anchor_position == "beside",
        f"{reason.anchor_field}/{reason.anchor_position}",
    )

    db.rollback()

    head("5  cycles are refused, chains are not")

    _apply_anchor(db, reason, {"anchor_field": "lead_status"})
    _apply_anchor(db, lost, {"anchor_field": "on_hold_reason"})
    db.commit()
    check(
        "a chain is legal — closed_lost under on_hold under lead_status",
        lost.anchor_field == "on_hold_reason" and reason.anchor_field == "lead_status",
    )

    refused, msg = refuses(
        lambda: _apply_anchor(db, reason, {"anchor_field": "closed_lost_reason_code"})
    )
    check("closing the chain into a loop is refused", refused, msg)
    db.rollback()

    head("6  the database refuses what the API is not the only guard for")

    for sql, constraint, name in (
        (
            "UPDATE field_placements SET anchor_field = 'lead_status', "
            "anchor_position = NULL WHERE id = :id",
            "ck_field_placements_anchor_pair",
            "an anchor with no position",
        ),
        (
            "UPDATE field_placements SET anchor_field = api_name, "
            "anchor_position = 'after' WHERE id = :id",
            "ck_field_placements_anchor_self",
            "a self-anchor",
        ),
        (
            "UPDATE field_placements SET layout_span = 'third' WHERE id = :id",
            "ck_field_placements_layout_span",
            "an unknown layout_span",
        ),
    ):
        with SessionLocal() as raw:
            try:
                raw.execute(text(sql), {"id": skip.id})
                raw.commit()
                check(f"CHECK refuses {name}", False, "the UPDATE succeeded")
            except IntegrityError as exc:
                raw.rollback()
                check(
                    f"CHECK refuses {name}",
                    constraint in str(exc.orig),
                    str(exc.orig)[:120],
                )

    head("7  removing an anchor releases what hung off it")

    _apply_anchor(db, reason, {"anchor_field": "lead_status"})
    _apply_anchor(db, lost, {"anchor_field": "lead_status"})
    db.commit()

    status_placement = placement(db, "leads", "lead_status")
    dependents = _anchored_to(db, status_placement)
    check(
        "both reasons are found hanging off lead_status",
        {p.api_name for p in dependents}
        == {"on_hold_reason", "closed_lost_reason_code"},
        str(sorted(p.api_name for p in dependents)),
    )

    # What delete_placement does, without deleting a real field off a real
    # module: release the dependents rather than take them down with it.
    for dependent in dependents:
        dependent.anchor_field = None
        dependent.anchor_position = None
    db.commit()
    check(
        "released dependents return to their own section, they are not deleted",
        reason.anchor_field is None
        and lost.anchor_field is None
        and reason.status == "active"
        and lost.status == "active",
    )

    head("8  a published snapshot carries WHERE a field drew")

    from app.metadata_spec import build_snapshot  # noqa: E402

    _apply_anchor(db, reason, {"anchor_field": "lead_status"})
    reason.layout_span = "full"
    db.commit()

    snapshot = build_snapshot(db)
    snap_row = next(
        r
        for r in snapshot["fields"]
        if r["module"] == "leads" and r["api_name"] == "on_hold_reason"
    )
    check(
        "the snapshot's field row carries the anchor and the span",
        snap_row["anchor_field"] == "lead_status"
        and snap_row["anchor_position"] == "after"
        and snap_row["layout_span"] == "full",
        str(
            (
                snap_row.get("anchor_field"),
                snap_row.get("anchor_position"),
                snap_row.get("layout_span"),
            )
        ),
    )

    # B2's two columns have to travel the same way, and the round trip is
    # asserted rather than the snapshot alone: build_snapshot reading a column
    # proves nothing if restore_snapshot never writes it back. It did not, for
    # exactly as long as it took to write this check — a rollback would have
    # turned every On Hold Reason back into one value the second hold
    # overwrites, and dropped all 28 expressions, silently.
    check(
        "the snapshot carries stage_scoped and computed_expr",
        snap_row.get("stage_scoped") == "sticky"
        and "computed_expr" in snap_row,
        str((snap_row.get("stage_scoped"), snap_row.get("computed_expr"))),
    )

    from app.metadata_spec import restore_snapshot  # noqa: E402

    reason.stage_scoped = "none"
    db.commit()
    restore_snapshot(db, snapshot)
    db.commit()
    db.refresh(reason)
    check(
        "restoring it puts stage_scoped back",
        reason.stage_scoped == "sticky",
        reason.stage_scoped,
    )

    # And the absence case, which is the one a rollback to any snapshot
    # published before 0015 actually hits. Those rows carry no such key, and
    # the answer is NOT "nothing was per-stage" — it was in extensions.json,
    # which a rollback does not revert. Preserve, do not null.
    for row in snapshot["fields"]:
        row.pop("stage_scoped", None)
        row.pop("computed_expr", None)
    restore_snapshot(db, snapshot)
    db.commit()
    db.refresh(reason)
    check(
        "a pre-0015 snapshot leaves stage_scoped alone rather than clearing it",
        reason.stage_scoped == "sticky",
        reason.stage_scoped,
    )

    # =================================================================
    # 9  per-stage values survive a save
    # =================================================================

    head("9  a per-stage answer actually persists")

    from app.custom_fields import resolve_write, stage_scoped_base  # noqa: E402

    check(
        "the key shape is recognised, and only the real shape",
        stage_scoped_base("on_hold_reason__s3") == "on_hold_reason"
        and stage_scoped_base("probability_pct__s10") == "probability_pct"
        and stage_scoped_base("notes__something") is None
        and stage_scoped_base("on_hold_reason__sx") is None,
    )

    # THE BUG THIS CLOSES. Leads, Opportunities and Deals are all on PostgreSQL,
    # and until now a flat payload's `on_hold_reason__s0` failed the
    # `key in custom_field_defs` test and was discarded with no error at all.
    # A2 puts a box on screen that writes exactly that key, so without this the
    # journey would be: type the reason, save, watch it vanish on reload.
    written = resolve_write(
        db,
        "leads",
        explicit=None,
        extras={
            "on_hold_reason__s0": "Client budget freeze until Q3",
            "probability_pct__s3": 45,
        },
    )
    check(
        "a per-stage value of a real field is kept",
        written.get("on_hold_reason__s0") == "Client budget freeze until Q3"
        and written.get("probability_pct__s3") == 45,
        str(written),
    )

    junk = resolve_write(
        db,
        "leads",
        explicit=None,
        extras={
            "rfp_documnet__s3": "typo",
            "on_hold_reason__sx": "not a stage",
            "id": "LEAD-00118",
            "__labels": {},
        },
    )
    check(
        "a typo, a malformed stage and the payload's own plumbing are all ignored",
        junk == {},
        str(junk),
    )

    refused, msg = refuses(
        lambda: resolve_write(
            db, "leads", explicit={"rfp_documnet__s3": "typo"}, extras=None
        )
    )
    check(
        "an EXPLICIT custom_fields object still rejects rather than drops",
        refused,
        msg[:140],
    )
    check(
        "and the message names the field the key claims a stage of",
        "rfp_documnet" in msg,
        msg[:140],
    )

finally:
    restore()
    still = db.scalar(
        select(func.count()).select_from(FieldPlacement).where(
            FieldPlacement.anchor_field.isnot(None), FieldPlacement.status == "active"
        )
    )
    ok = still == len(ANCHORED)
    print(f"\n  restore — {still} anchored placement(s), expected {len(ANCHORED)}")
    if not ok:
        FAILED.append(
            f"the anchor configuration was not restored — {still} anchored, "
            f"expected {len(ANCHORED)}. The scripts that used to set these are "
            f"gone (B3): roll back to the last good published version in "
            f"Administration, or set the anchors in the field editor — "
            f"'Anchor to' names the field each one draws beneath."
        )
    db.close()

print("\n" + "=" * 74)
if FAILED:
    print(f"{PASSED} passed, {len(FAILED)} FAILED\n")
    for line in FAILED:
        print(f"    {line}")
    sys.exit(1)
print(f"{PASSED} passed. Anchors are wired end to end and all {len(ANCHORED)} are in place.")
