"""
REQUIRED FIELDS, ENFORCED — on every save and every stage move.

Decided 21 Sep 2026, for go-live. Until then a Mandatory field only drew a red
asterisk: a record saved and moved stage with any of them empty. The rules are
the published register's (app/live_register.py), so a field made optional in
Administration and published stops being demanded here at once — there is no
switch to turn enforcement off, and there must not be one.

WHEN A FIELD IS DUE
-------------------
Every field names the stage its answer belongs to: `mandatory_from`, else the
first number of `blocks_transition` ("3 → 4"), else `capture_stage`. A field
with none of them (Accounts, Contacts) is due always.

    Save at stage S          every field due at S or an earlier stage
    Move forward F -> T      every field due at F or earlier; T's own fields
                             are asked for once the record is there, because
                             the form does not show them before
    Move back, On Hold,      never blocked by a stage's fields — only the
    Closed Lost              reason the status itself asks for (On Hold
                             Reason, Closed Lost Reason)
    Converted                nothing: the record is read-only

EXCEPTIONS, each decided by the business
----------------------------------------
* A SKIPPED stage's fields are not demanded (21 Sep 2026). "Skipped" means the
  record never stood at that stage — read from its stage history, so a stage
  it later goes back to and leaves normally is demanded from then on.
* Stages below the module's own range belong to the parent record's journey,
  which was checked when the parent converted.
* A POC/Pilot Deal is exempt through Stage 7 Close (21 Sep 2026): it is born
  there from a paid pilot, and only its PO date is asked for, on the Lead.
* A record created by conversion is exempt on that create — the conversion is
  a move, and the source record's side of it is what is checked
  (`check_leaving`, called from app/conversion.py).

WHAT COUNTS
-----------
Mandatory always; Conditional when its condition holds. A field is skipped
when it is hidden (its visibility condition is false), read from the parent,
not editable, a formula, or locked in phase 1 — the same list the form uses to
draw the asterisk (src/lib/spec/validation.ts), so screen and server agree.
A condition this evaluator cannot read is never used to DEMAND a field: the
server refusing on a rule it misunderstood would block a save the form allows.

TESTS
-----
`ENFORCED` is a module constant, not configuration: the older test scripts
create records with a handful of fields and switch it off in test_support.py.
test_required_fields.py switches it back on. Nothing in production can.
"""

from __future__ import annotations

import json
import re
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from .live_register import Published, published
from .messages import refusal
from .metadata_spec import SPEC_DIR
from .models import StageTransition
from .spreadsheets.conditions import ConditionError, evaluate

#: Off only in the older test scripts — see the docstring.
ENFORCED = True

#: Stored in the stage column, read as a number.
STAGE_FIELD = {"leads": "project_stage", "opportunities": "project_stage", "deals": "deal_stage"}

#: Child lists, by register api_name -> relationship on the record.
CHILD_LISTS = {
    "leads": {"demo_attendees": "demo_attendees", "feature_gaps_logged": "feature_gaps"},
    "opportunities": {"payment_milestones": "payment_milestones"},
    "deals": {"bid_commitments_register": "bid_commitments", "expansion_use_cases": "expansion_use_cases"},
}

#: Statuses, as stored.
CLOSED_LOST = "CLOSED_LOST"
ON_HOLD = "ON_HOLD"
CONVERTED = "CONVERTED"
PILOT = "POC_PILOT_DEAL"
PILOT_EXEMPT_THROUGH = 7

NEVER_DEMANDED = {"System", "Computed", "Advisory", "Optional"}

#: Marked Mandatory in the register but never typed by a person: the stage is
#: moved by the Update Stage dialog, the status defaults to Open, and the two
#: percentages follow the stage (app/progression.py). The stage field is added
#: per module below.
SYSTEM_SET = {"lead_status", "progression_pct", "probability_pct"}


def _sidecar() -> tuple[set[str], set[str], set[str]]:
    """
    Three lists from the hand-kept sidecar (spec/extensions.json) that the form
    also reads: phase-1-locked fields (module.api_name), history-only reasons,
    and fields that exist only as a COLUMN of an inline child table — entered
    per row, never on the record (src/lib/spec/childSpec.ts).
    """
    try:
        data = json.loads((SPEC_DIR / "extensions.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return set(), set(), set()
    fields = data.get("fields") or {}
    locked = {key for key, ext in fields.items() if isinstance(ext, dict) and ext.get("phase1_locked")}
    history = set(((data.get("stage_scoped") or {}).get("history_only") or {}).get("fields") or [])
    columns: set[str] = set()
    for ext in fields.values():
        spec = ext.get("child_spec") if isinstance(ext, dict) else None
        if not spec or spec.get("child_module"):
            continue
        for entry in spec.get("columns") or []:
            if isinstance(entry, str):
                columns.add(entry.split(".")[-1])
    return locked, history, columns


PHASE1_LOCKED, HISTORY_ONLY, CHILD_COLUMNS = _sidecar()


def stage_number(value: Any) -> int | None:
    if value is None:
        return None
    match = re.match(r"^(\d+)", str(value))
    return int(match.group(1)) if match else None


def due_stage(field: dict[str, Any]) -> int | None:
    """The stage a field's answer belongs to, or None for a field of no stage."""
    if field.get("mandatory_from") is not None:
        return int(field["mandatory_from"])
    blocks = stage_number(field.get("blocks_transition"))
    if blocks is not None:
        return blocks
    if field.get("capture_stage") is not None:
        return int(field["capture_stage"])
    return None


def _blank(value: Any) -> bool:
    return value is None or value == "" or (isinstance(value, (list, tuple, set, dict)) and len(value) == 0)


class _Record:
    """Reads a record's values the way the form does."""

    def __init__(self, module: str, record: Any, register: Published, stage: int | None):
        self.module = module
        self.record = record
        self.register = register
        self.stage = stage
        self.custom = dict(getattr(record, "custom_fields", None) or {})
        self.picklist_of = {f["api_name"]: f.get("picklist") for f in register.fields_of(module)}

    def raw(self, name: str) -> Any:
        if self.module == "accounts" and name == "account_type":
            return sorted(t.account_type for t in getattr(self.record, "types", []) or [])
        relation = CHILD_LISTS.get(self.module, {}).get(name)
        if relation is not None:
            return list(getattr(self.record, relation, None) or [])
        if name in type(self.record).__dict__ or hasattr(type(self.record), name):
            return getattr(self.record, name, None)
        return self.custom.get(name)

    def value(self, field: dict[str, Any]) -> Any:
        name = field["api_name"]
        scoped = field.get("stage_scoped") or "none"
        if scoped == "sticky" and self.stage is not None:
            return self.custom.get(f"{name}__s{self.stage}")
        if scoped == "carry_forward":
            base = self.raw(name)
            if not _blank(base):
                return base
            for s in range((self.stage or 0), -1, -1):
                earlier = self.custom.get(f"{name}__s{s}")
                if not _blank(earlier):
                    return earlier
            return None
        return self.raw(name)

    def holds(self, expr: str) -> bool | None:
        """The condition's truth, or None when it cannot be read here."""
        try:
            return evaluate(
                expr,
                value_of=self.raw,
                label_of=lambda name, key: self.register.label(self.picklist_of.get(name), key),
            )
        except (ConditionError, TypeError, ValueError):
            return None


def _applies(field: dict[str, Any], module: str) -> bool:
    """Could this field ever be demanded of the person saving?"""
    if field.get("requirement") in NEVER_DEMANDED or field.get("requirement") not in ("Mandatory", "Conditional"):
        return False
    if field.get("value_mode") == "read_through" or field.get("editable") is False or field.get("value_locked"):
        return False
    if field.get("computed_formula") or field.get("type") == "computed":
        return False
    name = field["api_name"]
    if name in SYSTEM_SET or name == STAGE_FIELD.get(module):
        return False
    return f"{module}.{name}" not in PHASE1_LOCKED and name not in HISTORY_ONLY and name not in CHILD_COLUMNS


def _demanded(field: dict[str, Any], rec: _Record) -> bool:
    """Visible, and required by its own rule. Unreadable rules never demand."""
    visibility = field.get("visibility_condition")
    if visibility:
        names = set(re.findall(r"[A-Za-z_]\w*", visibility))
        # "Shown once filled in" — a value never hides itself.
        if field["api_name"] not in names and rec.holds(visibility) is not True:
            return False
    if field.get("requirement") == "Mandatory":
        return True
    condition = field.get("condition")
    return bool(condition) and rec.holds(condition) is True


def _visited(db: Session, module: str, record_id: str | None, *also: int | None) -> set[int]:
    stages = {s for s in also if s is not None}
    if record_id:
        for t in db.scalars(
            select(StageTransition).where(StageTransition.module == module, StageTransition.record_id == record_id)
        ):
            stages.update((t.from_stage, t.to_stage))
    return stages


def missing_fields(
    db: Session,
    module: str,
    record: Any,
    *,
    record_id: str | None,
    stage: int | None,
    up_to: int | None,
    visited: set[int] | None = None,
    status_only: bool = False,
) -> list[dict[str, Any]]:
    """
    The fields that must be filled and are not.

    `stage` is where the record stands (it decides which per-stage answer is
    read); `up_to` is the last stage whose fields are due. `status_only` keeps
    only fields whose rule reads the status — the reason for On Hold or
    Closed Lost.
    """
    register = published(db)
    if register is None:
        return []
    rec = _Record(module, record, register, stage)
    span = register.stage_range(module)
    first = span[0] if span else None
    if visited is None:
        visited = _visited(db, module, record_id, stage)
    exempt_through = PILOT_EXEMPT_THROUGH if module == "deals" and getattr(record, "lead_status", None) == PILOT else None

    out: list[dict[str, Any]] = []
    for field in register.fields_of(module):
        if not _applies(field, module):
            continue
        if status_only and "lead_status" not in (field.get("condition") or ""):
            continue
        due = due_stage(field)
        if due is not None and up_to is not None:
            if due > up_to:
                continue
            if first is not None and due < first:
                continue
            if due not in visited and due != up_to:
                continue
            if exempt_through is not None and due <= exempt_through:
                continue
        if not _demanded(field, rec):
            continue
        if _blank(rec.value(field)):
            out.append(field)
    return out


def _refuse(fields: list[dict[str, Any]], message: str) -> HTTPException:
    shown = [f["label"] for f in fields[:8]]
    details = [f"Fill in: {', '.join(shown)}{'.' if len(fields) <= 8 else ''}"]
    if len(fields) > 8:
        details[0] += f", and {len(fields) - 8} more."
    details.append("Required fields are marked with a red asterisk.")
    return HTTPException(
        status.HTTP_422_UNPROCESSABLE_ENTITY,
        refusal(
            "REQUIRED_FIELDS_MISSING",
            message,
            details,
            fields=[{"api_name": f["api_name"], "label": f["label"], "section": f.get("section")} for f in fields],
        ),
    )


def check_save(
    db: Session,
    module: str,
    record: Any,
    *,
    record_id: str | None,
    creating: bool,
    previous_stage: int | None = None,
    converting: bool = False,
) -> None:
    """
    Refuse this save (422 REQUIRED_FIELDS_MISSING) if it leaves a due field
    empty. Call after every value is applied, before the commit.
    """
    if not ENFORCED or (creating and converting):
        return
    if module in STAGE_FIELD:
        db.flush()
        rels = list(CHILD_LISTS.get(module, {}).values())
        if rels:
            db.expire(record, rels)
        status_now = getattr(record, "lead_status", None)
        if status_now == CONVERTED:
            return
        stage = stage_number(getattr(record, STAGE_FIELD[module], None))
        status_only = status_now in (CLOSED_LOST, ON_HOLD)
        moving_back = previous_stage is not None and stage is not None and stage < previous_stage
        moving_on = (
            not creating and previous_stage is not None and stage is not None and stage > previous_stage
        )
        if moving_back:
            status_only = True
        if moving_on:
            # The move itself: the stage being LEFT is what must be complete.
            visited = _visited(db, module, record_id, previous_stage)
            missing = missing_fields(
                db, module, record, record_id=record_id, stage=previous_stage,
                up_to=previous_stage, visited=visited, status_only=status_only,
            )
            if missing:
                raise _refuse(missing, f"Fill in Stage {previous_stage}'s required fields before moving on.")
            # And the status's own reason, read at the stage it was given.
            missing = missing_fields(
                db, module, record, record_id=record_id, stage=stage, up_to=stage,
                visited=visited | {stage}, status_only=True,
            )
        else:
            visited = {stage} if creating else None
            missing = missing_fields(
                db, module, record, record_id=record_id, stage=stage, up_to=stage,
                visited=visited, status_only=status_only,
            )
        if missing:
            raise _refuse(missing, "Some required fields are empty.")
        return

    missing = missing_fields(db, module, record, record_id=record_id, stage=None, up_to=None)
    if missing:
        raise _refuse(missing, "Some required fields are empty.")


def check_leaving(db: Session, module: str, record: Any, *, record_id: str) -> None:
    """
    A conversion moves the source out of its stage: that stage's fields, and
    every earlier one it stood at, must be complete. Called by
    app/conversion.py before the new record is created.
    """
    if not ENFORCED:
        return
    stage = stage_number(getattr(record, STAGE_FIELD[module], None))
    missing = missing_fields(db, module, record, record_id=record_id, stage=stage, up_to=stage)
    if missing:
        raise _refuse(missing, f"Fill in Stage {stage}'s required fields before moving on.")
