"""
PROGRESSION % AND PROBABILITY % — one table, one rule.

    record enters a stage  ->  takes that stage's pair from `stages`
    a person changes a number  ->  Override Justification for that stage

DECIDED 13 Sep 2026 (ARK business decision). The stage IS the rung: the
`stages` table carries one Progression % and one Probability % per stage,
multiples of 5, edited in Administration. Nothing else writes these two
numbers — no evidence ladder, no band midpoint. That ended a real bug: two
engines used to write the same pair and whichever ran last won.

    Progression moves on OUR work.   Probability moves on the CLIENT's decisions.

THE RULES, IN FULL
------------------
1. Create, or any stage move (forward, skip, reversal): both numbers and their
   defaults become the new stage's pair. Any override is cleared.
2. A person may change either number. A value that differs from the stage's
   default needs `probability_override_justification__s<stage>` — in the same
   request or already recorded for that stage — or the write is refused (422).
   Values must be 0-100 in steps of 5.
3. An override survives ordinary saves and ends at the next stage move.
4. Closed Lost: Probability is 0. Reopening restores the stage's value. Neither
   needs a justification — the status is the reason.
5. A POC/Pilot Deal (Deals status POC_PILOT_DEAL) is Probability 100: the pilot
   is sold. The status is refused on Leads and Opportunities.
6. A Lead whose pilot is marked Paid becomes a Deal: status POC/Pilot Deal at
   Stage 7 Close, contract value = pilot fee, and the Lead is Converted. One
   Deal per Lead, ever. What happens to the programme after the pilot is a
   phase-2 decision and deliberately not built.

Nothing here sends anything or acts on a timer (CLAUDE.md rule 6). Every change
it makes is written to the audit log in the same transaction as the save.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from .audit import record_audit
from .changes import diff, jsonable
from .messages import FORM_OUT_OF_DATE
from .models import Conversion, Deal, Lead, Stage

#: The two numbers, in the order they are reported.
PCT_FIELDS = ("progression_pct", "probability_pct")

#: The register's justification field. Stage-scoped 'sticky': written at the
#: stage it was given, never carried forward.
JUSTIFICATION_FIELD = "probability_override_justification"

#: Deals-only value on the shared status picklist.
PILOT_STATUS = "POC_PILOT_DEAL"
CLOSED_LOST = "CLOSED_LOST"
CONVERTED = "CONVERTED"

#: leads.pilot_commercial_model key that makes a pilot billable.
PAID = "PAID"

#: Where a paid pilot Deal sits.
PILOT_DEAL_STAGE = "7_CLOSE"

#: The column holding the stage, per module — modules.stage_field, inlined.
STAGE_FIELD = {"leads": "project_stage", "opportunities": "project_stage", "deals": "deal_stage"}

#: What every pipeline row serialises about the pair. One list, so the three
#: routers cannot serve different subsets of one fact.
PCT_OUT = (
    "progression_pct",
    "probability_pct",
    "progression_default_pct",
    "probability_default_pct",
    "is_overridden",
    "overridden_by",
    "overridden_date",
)

ZERO = Decimal("0")
ONE = Decimal("1")
_STEP = Decimal("5")


def current_stage(module: str, record: Any) -> int | None:
    """The leading integer of this record's stage column, or None."""
    return stage_number(getattr(record, STAGE_FIELD.get(module, ""), None))


def stage_number(value: Any) -> int | None:
    if value is None:
        return None
    match = re.match(r"^(\d+)", str(value))
    return int(match.group(1)) if match else None


def stage_pair(db: Session, stage: int | None) -> tuple[Decimal | None, Decimal | None]:
    """The stage's (progression, probability) as fractions, None where unset."""
    row = db.get(Stage, stage) if stage is not None else None
    if row is None:
        return None, None

    def frac(pct: int | None) -> Decimal | None:
        return None if pct is None else (Decimal(pct) / 100).quantize(Decimal("0.0001"))

    return frac(row.progression_pct), frac(row.probability_pct)


def as_fraction(value: Any) -> Decimal | None:
    """
    A percentage off the wire, as the fraction the column holds. The UI sends
    fractions (0.4); a value above 1 cannot be one and is read as a whole
    percent, so an integration posting `40` means 40% and not 4000%.
    """
    if value is None or value == "":
        return None
    try:
        number = Decimal(str(value))
    except Exception:
        return None
    return (number / 100 if number > 1 else number).quantize(Decimal("0.0001"))


def _same(a: Decimal | None, b: Decimal | None) -> bool:
    if a is None or b is None:
        return a is b
    return Decimal(a) == Decimal(b)


# =========================================================================
# BEFORE THE WRITE
# =========================================================================


@dataclass
class Plan:
    """Everything decided about the pair before a single value is applied."""

    creating: bool
    previous_stage: int | None
    new_stage: int | None
    previous_status: str | None
    #: The record's pair and defaults before this request.
    before: dict[str, Any]
    #: Fields a PERSON set in this request to a new value: name -> fraction.
    typed: dict[str, Decimal] = field(default_factory=dict)
    #: Of those, the ones that disagree with the stage's default.
    overriding: set[str] = field(default_factory=set)


def plan_write(
    db: Session,
    module: str,
    record: Any,
    payload: Any,
    sent: set[str],
    *,
    creating: bool = False,
) -> Plan:
    """
    Validate a create or update and decide what the pair will be. Raises 422;
    writes nothing. Call BEFORE the payload is applied to `record`.
    """
    stage_field = STAGE_FIELD[module]
    previous_stage = None if creating else current_stage(module, record)
    new_stage = (
        stage_number(getattr(payload, stage_field, None))
        if stage_field in sent
        else previous_stage
    )

    from .custom_fields import extras_of, stage_scoped_base  # local: avoids a module-load cycle

    stray = sorted(
        key
        for key in (*extras_of(payload), *(getattr(payload, "custom_fields", None) or {}))
        if stage_scoped_base(key) in PCT_FIELDS
    )
    if stray:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            {"code": "FORM_OUT_OF_DATE", "message": FORM_OUT_OF_DATE, "rejected": stray},
        )

    new_status = getattr(payload, "lead_status", None) if "lead_status" in sent else None
    if module != "deals" and new_status == PILOT_STATUS:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            {
                "code": "PILOT_STATUS_NOT_PICKABLE",
                "message": '"POC/Pilot Deal" can\'t be picked here.',
                "details": ["Mark the pilot as Paid instead. That creates the Deal."],
            },
        )

    before = {
        name: (None if creating else getattr(record, name, None))
        for name in (*PCT_FIELDS, "progression_default_pct", "probability_default_pct")
    }
    plan = Plan(
        creating=creating,
        previous_stage=previous_stage,
        new_stage=new_stage,
        previous_status=None if creating else getattr(record, "lead_status", None),
        before=before,
    )

    stage_moved = creating or new_stage != previous_stage
    status_now = new_status if "lead_status" in sent else plan.previous_status
    pair = dict(zip(PCT_FIELDS, stage_pair(db, new_stage)))
    usual: dict[str, Any] = {}
    for name in PCT_FIELDS:
        if name not in sent:
            continue
        value = as_fraction(getattr(payload, name, None))
        if value is None or _same(value, before[name]):
            continue  # untouched, or a form re-sending what is already there
        if value < ZERO or value > ONE or (value * 100) % _STEP != 0:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                {
                    "code": "PERCENT_NOT_A_STEP",
                    "message": f"{_label(name)} must be a multiple of 5 between 0 and 100 (you entered {value * 100:g}).",
                },
            )
        plan.typed[name] = value
        default = _default_for(
            module,
            name,
            stage_moved=stage_moved,
            pair_value=pair[name],
            stored_default=before[_default_name(name)],
            status_now=status_now,
            previous_status=plan.previous_status,
        )
        if not _same(value, default):
            plan.overriding.add(name)
            usual[name] = default

    if plan.overriding:
        key = f"{JUSTIFICATION_FIELD}__s{new_stage}" if new_stage is not None else JUSTIFICATION_FIELD
        if not _justified(record, payload, key, creating):
            changed = [n for n in PCT_FIELDS if n in plan.overriding]
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                {
                    "code": "OVERRIDE_JUSTIFICATION_REQUIRED",
                    "message": (
                        f"{' and '.join(_label(n) for n in changed)} "
                        f"{'differs' if len(changed) == 1 else 'differ'} from the stage's usual value."
                    ),
                    "details": [
                        *(
                            f"{_label(n)}: usually {_pct(usual[n])}"
                            for n in changed
                            if usual.get(n) is not None
                        ),
                        "Add an Override Justification before saving.",
                    ],
                    "fields": [key],
                },
            )
    return plan


def _default_name(name: str) -> str:
    return f"{name.removesuffix('_pct')}_default_pct"


def _default_for(
    module: str,
    name: str,
    *,
    stage_moved: bool,
    pair_value: Decimal | None,
    stored_default: Decimal | None,
    status_now: str | None,
    previous_status: str | None,
) -> Decimal | None:
    """
    What `name` should be when nobody argues with it. The status rules come
    first (Closed Lost 0, a pilot Deal 100); then a stage move, or a record
    that never had a default, takes the stage's value; otherwise the default
    the record already carries stands — so retuning a stage in Administration
    changes records as they ENTER it, never records already sitting in it.
    """
    if name == "probability_pct":
        if status_now == CLOSED_LOST:
            return ZERO
        if module == "deals" and status_now == PILOT_STATUS:
            return ONE
        if previous_status in (CLOSED_LOST, PILOT_STATUS) and status_now != previous_status:
            return pair_value if pair_value is not None else stored_default
    if stage_moved or stored_default is None:
        return pair_value if pair_value is not None else stored_default
    return stored_default


def _pct(value: Any) -> str:
    return f"{(Decimal(str(value)) * 100).normalize():f}%"


def _label(name: str) -> str:
    return "Progression %" if name == "progression_pct" else "Probability %"


def _justified(record: Any, payload: Any, key: str, creating: bool) -> bool:
    from .custom_fields import extras_of  # local: avoids a module-load cycle

    for source in (extras_of(payload), getattr(payload, "custom_fields", None) or {}):
        value = source.get(key)
        if isinstance(value, str) and value.strip():
            return True
    if creating:
        return False
    stored = (getattr(record, "custom_fields", None) or {}).get(key)
    return isinstance(stored, str) and bool(stored.strip())


# =========================================================================
# AFTER THE WRITE
# =========================================================================


def after_write(db: Session, module: str, record: Any, plan: Plan, *, actor: str | None) -> None:
    """
    Settle the pair on a record whose payload has been applied, before the
    router commits. Mutates `record`; commits nothing.
    """
    stage_moved = plan.creating or plan.new_stage != plan.previous_stage
    pair = dict(zip(PCT_FIELDS, stage_pair(db, plan.new_stage)))
    status_now = getattr(record, "lead_status", None)
    status_changed = not plan.creating and status_now != plan.previous_status

    for name in PCT_FIELDS:
        default_name = _default_name(name)
        old_value, old_default = plan.before[name], plan.before[default_name]
        default = _default_for(
            module,
            name,
            stage_moved=stage_moved,
            pair_value=pair[name],
            stored_default=old_default,
            status_now=status_now,
            previous_status=plan.previous_status,
        )

        standing_override = old_value is not None and not _same(old_value, old_default)
        if name in plan.typed:
            value = plan.typed[name]
        elif standing_override and not stage_moved and not status_changed:
            value = old_value  # an override outlives an ordinary save
        else:
            value = default

        setattr(record, default_name, default)
        setattr(record, name, value)

    if stage_moved and not plan.creating:
        record_audit(
            db,
            module=module,
            record_id=_id_of(record),
            action="stage_pct",
            actor=actor,
            changed_fields=[
                f"stage:{plan.previous_stage if plan.previous_stage is not None else '-'}->{plan.new_stage}",
                *PCT_FIELDS,
            ],
            changed=diff(
                {n: jsonable(plan.before[n]) for n in PCT_FIELDS},
                {n: jsonable(getattr(record, n)) for n in PCT_FIELDS},
            ),
        )

    _sync_override(db, module, record, newly=bool(plan.overriding), actor=actor)

    if module == "leads":
        spin_off_pilot_deal(db, record, actor=actor)


def _sync_override(db: Session, module: str, record: Any, *, newly: bool, actor: str | None) -> None:
    """is_overridden is derived from the record's own values on every write."""
    overridden = any(
        getattr(record, name) is not None
        and not _same(getattr(record, name), getattr(record, _default_name(name)))
        for name in PCT_FIELDS
    )
    record.is_overridden = overridden
    if not overridden:
        record.overridden_by = None
        record.overridden_date = None
    elif newly:
        record.overridden_by = actor
        record.overridden_date = datetime.now(timezone.utc)
        record_audit(
            db,
            module=module,
            record_id=_id_of(record),
            action="overridden",
            actor=actor,
            changed_fields=[n for n in PCT_FIELDS],
        )


# =========================================================================
# PAID POC / PILOT
# =========================================================================


def spin_off_pilot_deal(db: Session, lead: Lead, *, actor: str | None) -> Deal | None:
    """
    A Lead whose pilot is Paid becomes a POC/Pilot Deal, and the Lead is
    Converted. One Deal per Lead, ever: an existing pilot Deal from this Lead
    is the answer, so saving the Lead again never creates a second.
    """
    if (lead.pilot_commercial_model or "").upper() != PAID or lead.lead_status == CONVERTED:
        return None
    existing = db.scalar(
        select(Deal).where(Deal.parent_lead == lead.lead_id, Deal.lead_status == PILOT_STATUS)
    )
    if existing is not None:
        return None

    from .ids import next_reference_id  # local: ids imports models

    highest = 0
    for reference in db.scalars(select(Deal.deal_id)):
        match = re.match(r"^DEAL-(\d+)$", reference or "")
        if match:
            highest = max(highest, int(match.group(1)))
    deal_id = next_reference_id(db, "deals", "DEAL", 5, highest)

    progression, _ = stage_pair(db, stage_number(PILOT_DEAL_STAGE))
    deal = Deal(
        deal_id=deal_id,
        deal_name=f"{lead.opportunity_name} — Paid POC",
        deal_stage=PILOT_DEAL_STAGE,
        lead_status=PILOT_STATUS,
        parent_lead=lead.lead_id,
        contract_value=lead.pilot_fee,
        # The Won date: asked for on the Lead when the pilot is marked Paid
        # (decided 21 Sep 2026), never defaulted to the day of the click.
        po_received_date=lead.pilot_po_received_date,
        end_client=lead.end_client,
        customer_partner_si=lead.customer_partner_si,
        progression_pct=progression,
        progression_default_pct=progression,
        probability_pct=ONE,
        probability_default_pct=ONE,
        is_overridden=False,
    )
    db.add(deal)
    db.flush()

    copied = ["deal_name", "contract_value", "po_received_date", "end_client", "customer_partner_si"]
    record_audit(
        db,
        module="deals",
        record_id=deal_id,
        action="created",
        actor=actor,
        changed_fields=[f"from {lead.lead_id} — paid POC/pilot", *copied],
    )

    was = lead.lead_status
    lead.lead_status = CONVERTED
    record_audit(
        db,
        module="leads",
        record_id=lead.lead_id,
        action="updated",
        actor=actor,
        changed_fields=["lead_status"],
        changed=diff({"lead_status": was}, {"lead_status": CONVERTED}),
    )

    from .routers.conversions import _next_conversion_id  # local: routers import this module

    db.add(
        Conversion(
            reference_id=_next_conversion_id(db),
            source_module="leads",
            source_id=lead.lead_id,
            target_module="deals",
            target_id=deal_id,
            copied_fields=copied,
            note="Paid POC/pilot became a POC/Pilot Deal",
            actor=actor,
            timestamp=datetime.now(timezone.utc),
        )
    )
    return deal


# =========================================================================
# READING
# =========================================================================


def serialise_pct(record: Any) -> dict:
    """
    The pair half of a record's JSON. FRACTIONS GO OUT AS FRACTIONS — 0.4 is
    40% in the column, on the wire and in the chips' arithmetic alike.
    """
    row: dict[str, Any] = {}
    for name in PCT_OUT:
        value = getattr(record, name, None)
        row[name] = float(value) if isinstance(value, Decimal) else value
    return row


def _id_of(record: Any) -> str:
    for name in ("lead_id", "opportunity_id", "deal_id"):
        value = getattr(record, name, None)
        if value:
            return value
    return ""
