"""
When a record entered the stage it is in now.

WHY THIS IS A TABLE LOOKUP AND NOT A COLUMN
-------------------------------------------
CLAUDE.md: "Stages are states, not steps." A pursuit may skip 1 -> 4 and may be
moved back 5 -> 3, each with a recorded reason, so "when did this reach Stage 3"
has no single answer — a lead that went 3 -> 5 -> 3 entered Stage 3 twice and
the age of its CURRENT stay starts at the second one. A `stage_entered_date`
column could only ever hold one of the two, and would hold the wrong one for
every record that has ever moved backwards.

`stage_transitions` already carries one row per move with its timestamp, so the
answer is derivable and does not need storing. models.Lead.days_in_current_stage
approximated it from `modified_date` until 12 Sep 2026 with a docstring saying
to revisit once that table existed — it exists, this is the revisit. The
approximation was wrong in both directions: editing a Stage 3 lead's remarks
reset its stage age to 0, and a lead that sat untouched for a month read the
same number whether it had entered the stage that month or a year earlier.

ONE QUERY PER PAGE, NOT ONE PER RECORD
--------------------------------------
Resolved for a whole page of records at once and handed to `_serialise` as a
map, the same shape and for the same reason as the display-name joins beside it
in each router's `_label_maps`. A property on the model would have to reach for
`object_session(self)` and fire a query per row — forty on a list screen.

FALLING BACK TO created_date IS A REAL ANSWER, NOT A PLACEHOLDER
----------------------------------------------------------------
A record that has never transitioned has been in its stage since it was
created, which is exactly what the fallback says. It also covers the records
that predate the transitions table, and a lead created directly INTO Stage 4
(legal — the create form asks for a stage), which never generated a transition
row because nothing moved.

It also covers the deal_stage value that carries no stage number at all —
CLOSED. `to_stage` is an integer, so no transition row can target it; there is
no numbered stage for such a deal to have entered, and "since it was created"
is the only true answer available.
"""

from collections.abc import Mapping
from datetime import datetime
import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import StageTransition

def stage_number(value: object) -> int | None:
    """
    The leading integer of a stage value.

    project_stage is a picklist keyed "4_RFP_RFI", deal_stage "8_PROJECT_SUCCESS",
    and a record straight off a create can hold the bare number. All three
    resolve here — the same parse src/lib/spec/resolvers.ts does in the browser.
    """
    if value is None:
        return None
    if isinstance(value, int):
        return value
    match = re.match(r"^(\d+)", str(value))
    return int(match.group(1)) if match else None


def stage_entry_dates(
    db: Session,
    module: str,
    records: Mapping[str, object],
) -> dict[str, datetime]:
    """
    record_id -> the instant it entered the stage it is in now.

    `records` maps each record's id to its own stage value, in whatever form
    that module's column holds it. A record whose stage was never transitioned
    INTO is absent from the result, and the caller falls back to created_date.
    """
    wanted = {
        record_id: stage_number(stage) for record_id, stage in records.items()
    }
    wanted = {k: v for k, v in wanted.items() if v is not None}
    if not wanted:
        return {}

    rows = db.execute(
        select(
            StageTransition.record_id,
            StageTransition.to_stage,
            StageTransition.timestamp,
        )
        .where(
            StageTransition.module == module,
            StageTransition.record_id.in_(wanted.keys()),
        )
        # Ascending, so the LAST matching row of a record wins — the most
        # recent entry into the stage it is in now, which is the one whose age
        # is being asked for. A 3 -> 5 -> 3 record takes the second 3.
        .order_by(StageTransition.timestamp)
    )

    entered: dict[str, datetime] = {}
    for record_id, to_stage, timestamp in rows:
        if to_stage == wanted.get(record_id):
            entered[record_id] = timestamp
    return entered
