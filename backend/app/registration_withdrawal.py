"""
Withdrawing a deal registration — and what it does to the pursuit it protected.

A partner withdrawing is not the client cancelling the project, so the server
never guesses what happens to the lead. BD answers, in the same request:

    keep   keep pursuing, direct or with another partner — the pursuit stays
           open; Customer (Partner / SI) is released if it names this partner
    hold   On Hold, with the reason recorded at the stage it was given. Still
           counts toward pipeline, as every On Hold pursuit does (app/revenue.py)
    close  Closed Lost, reason code "Partner withdrew"

THE KNOCK-ON, SOLVED IN ONE TRANSACTION
---------------------------------------
Closing the PRIMARY pursuit of a pursuit group meets guard_close — the primary
may not close while a secondary is open. Two cases:

1. Another pursuit in the group is still open. BD names the new primary in the
   same request (new_primary). The primary moves first, then the close is
   written, so guard_close sees a secondary closing. The conflict's Primary
   Registration follows the new primary, so the conflict and the group never
   disagree about who counts.

2. No other pursuit is open — the other partner's lead has not been created
   yet. Nothing can be primary today. The conflict's other registration, if it
   is still live, becomes the Primary Registration and the group's primary
   pursuit is cleared, so when that lead IS created auto_join_from_conflict
   makes it primary and its value counts. Left alone it would join as a
   secondary behind a closed pursuit and never count at all.

A registration with no open pursuit that was a conflict's primary hands the
primary over the same way (case 2).

Every step writes its own History row with the withdrawal reason, and either
everything commits or nothing does: the one commit is the pursuit's own write
through its router, which runs the progression and pursuit rules unchanged.
"""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from .audit import record_audit
from .changes import diff, snapshot
from .clock import now_utc, today_company
from .models import DealRegistration, Lead, PicklistValue, PursuitGroup, RegistrationConflict, User
from .progression import PILOT_STATUS
from .pursuits import (
    STAGE_FIELD,
    _audit,
    _group_for_registration,
    _resolve_member,
    _touch,
    chain,
    change_primary,
    group_display_name,
    id_of,
    is_open,
    open_pursuits_in,
    restamp,
    root_of,
    stage_number,
    tip,
)
from .registration_matching import MIN_REASON, WITHDRAWN, account_names, is_live_status, registration_name
from .schemas import LeadUpdate, OpportunityUpdate

PURSUIT_ACTIONS = frozenset({"keep", "hold", "close"})

#: closed_lost_reason_code — added by partner_lifecycle_metadata.py.
PARTNER_WITHDRAWN = "PARTNER_WITHDRAWN"


def _pursuit(db: Session, reg: DealRegistration) -> tuple[Lead, list[tuple[str, Any]], tuple[str, Any]] | None:
    lead = db.scalars(
        select(Lead).where(Lead.partner_deal_registration == reg.registration_id).order_by(Lead.lead_id)
    ).first()
    if lead is None and reg.linked_lead:
        lead = db.get(Lead, reg.linked_lead)
    if lead is None:
        return None
    records = chain(db, lead.lead_id)
    live = tip(records)
    return (lead, records, live) if live is not None else None


def _awarded(records: list[tuple[str, Any]]) -> bool:
    """A Deal other than a paid pilot — the pursuit was won."""
    return any(module == "deals" and getattr(r, "lead_status", None) != PILOT_STATUS for module, r in records)


def _name_of(records: list[tuple[str, Any]], live: tuple[str, Any]) -> str | None:
    _, record = live
    first = records[0][1] if records else None
    return (
        getattr(record, "opportunity_name", None)
        or getattr(record, "deal_name", None)
        or getattr(first, "opportunity_name", None)
    )


def _member(db: Session, root: str, accounts: dict[str, str]) -> dict[str, Any] | None:
    records = chain(db, root)
    live = tip(records)
    if live is None:
        return None
    module, record = live
    first = records[0][1]
    return {
        "record_id": id_of(module, record),
        "name": _name_of(records, live),
        "partner_name": accounts.get(getattr(first, "customer_partner_si", None) or ""),
        "stage_number": stage_number(getattr(record, STAGE_FIELD[module], None)),
    }


def _handover_target(db: Session, reg: DealRegistration, group: PursuitGroup | None) -> DealRegistration | None:
    """The other registration of the conflict that made this one primary, if live."""
    if group is None or group.primary_registration != reg.registration_id or not group.source_conflict:
        return None
    conflict = db.get(RegistrationConflict, group.source_conflict)
    if conflict is None:
        return None
    other_id = conflict.registration_b if conflict.registration_a == reg.registration_id else conflict.registration_a
    other = db.get(DealRegistration, other_id) if other_id else None
    return other if other is not None and is_live_status(other.registration_status) else None


def _status_label(db: Session, key: str | None) -> str:
    """A registration status as the register labels it, not as its key reads."""
    label = db.scalar(
        select(PicklistValue.label)
        .where(PicklistValue.picklist_key == "partners__registration_status")
        .where(PicklistValue.key == key)
    )
    return label or str(key)


def preview(db: Session, reg: DealRegistration) -> dict[str, Any]:
    """What the Withdraw dialog needs to ask the right question, by name."""
    accounts = account_names(db)
    out: dict[str, Any] = {"can_withdraw": True, "blocked_reason": None, "pursuit": None, "primary_handover": None}

    if reg.registration_status == WITHDRAWN:
        out.update(can_withdraw=False, blocked_reason="This registration has already been withdrawn.")
    elif not is_live_status(reg.registration_status):
        out.update(
            can_withdraw=False,
            blocked_reason=(
                f"This registration is {_status_label(db, reg.registration_status)}, so there is nothing to withdraw."
            ),
        )

    group = None
    found = _pursuit(db, reg)
    if found is not None:
        lead, records, live = found
        if _awarded(records):
            out.update(
                can_withdraw=False,
                blocked_reason=(
                    "The pursuit on this registration has been won, so it can't be withdrawn. "
                    "If the partner is leaving, change the delivery partner on the Deal."
                ),
            )
        module, record = live
        group = db.get(PursuitGroup, record.pursuit_group) if record.pursuit_group else None
        root = root_of(db, module, record)
        others = []
        if group is not None:
            for entry in open_pursuits_in(db, group.group_id):
                if entry["pursuit"] != root:
                    member = _member(db, entry["pursuit"], accounts)
                    if member:
                        others.append(member)
        out["pursuit"] = {
            "record_id": id_of(module, record),
            "module": module,
            "name": _name_of(records, live),
            "stage_number": stage_number(getattr(record, STAGE_FIELD[module], None)),
            "status": record.lead_status,
            "is_open": is_open(record),
            "is_primary": bool(group is not None and record.is_primary_pursuit),
            "group_name": group_display_name(db, group) if group is not None else None,
            "other_open": others,
        }

    if group is None:
        group = _group_for_registration(db, reg.registration_id)
    target = _handover_target(db, reg, group)
    if target is not None:
        out["primary_handover"] = {"registration_id": target.registration_id, "name": registration_name(target, accounts)}
    return out


def _set_primary_registration(
    db: Session, group: PursuitGroup, conflict: RegistrationConflict, target: str, actor: str
) -> str | None:
    old = conflict.primary_registration
    if old == target:
        return old
    conflict.primary_registration = target
    conflict.modified_by = actor
    conflict.modified_date = now_utc()
    record_audit(
        db,
        module="conflicts",
        record_id=conflict.conflict_id,
        action="updated",
        actor=actor,
        changed_fields=["primary_registration"],
        changed=[{"field": "primary_registration", "from": old, "to": target}],
    )
    group.primary_registration = target
    return old


def _follow_primary_registration(db: Session, group: PursuitGroup, root: str, actor: str) -> None:
    """After change_primary: the conflict names the registration that now counts."""
    if not group.source_conflict or not root.startswith("LEAD-"):
        return
    lead = db.get(Lead, root)
    conflict = db.get(RegistrationConflict, group.source_conflict)
    if lead is None or conflict is None:
        return
    target = lead.partner_deal_registration
    if target in {conflict.registration_a, conflict.registration_b} and target != conflict.primary_registration:
        _set_primary_registration(db, group, conflict, target, actor)


def _hand_over_primary(db: Session, reg: DealRegistration, group: PursuitGroup | None, actor: str, why: str) -> None:
    """Case 2 of the module docstring."""
    target = _handover_target(db, reg, group)
    if target is None or group is None:
        return
    conflict = db.get(RegistrationConflict, group.source_conflict)
    old_registration = _set_primary_registration(db, group, conflict, target.registration_id, actor)

    target_root = None
    for entry in open_pursuits_in(db, group.group_id):
        member_lead = db.get(Lead, entry["pursuit"]) if entry["pursuit"].startswith("LEAD-") else None
        if member_lead is not None and member_lead.partner_deal_registration == target.registration_id:
            target_root = entry["pursuit"]
            break

    old_primary = group.primary_pursuit
    group.primary_pursuit = target_root
    restamp(db, group)
    _touch(group, actor)
    _audit(
        db,
        group.group_id,
        actor,
        "primary_registration_changed",
        why,
        primary_registration=(old_registration, target.registration_id),
        primary_pursuit=(old_primary, target_root),
    )


def _release_partner(db: Session, lead: Lead, reg: DealRegistration, actor: str) -> None:
    """"Keep pursuing": the withdrawn partner stops being the Customer (Partner / SI).
    Deal Source stays Partner-sourced — that is how the pursuit arrived."""
    if not lead.customer_partner_si or lead.customer_partner_si != reg.partner:
        return
    old = lead.customer_partner_si
    lead.customer_partner_si = None
    lead.modified_by = actor
    lead.modified_date = now_utc()
    record_audit(
        db,
        module="leads",
        record_id=lead.lead_id,
        action="updated",
        actor=actor,
        changed_fields=["customer_partner_si"],
        changed=[{"field": "customer_partner_si", "from": old, "to": None}],
    )


def _write_status(db: Session, module: str, record_id: str, payload: dict[str, Any], user: User) -> None:
    """Through the record's own router, so progression (Closed Lost -> Probability
    0) and the pursuit rules run exactly as they do for a typed save. Commits."""
    # Imported here: the routers import app modules, and this module is one.
    from .routers import leads as leads_router
    from .routers import opportunities as opportunities_router

    if module == "leads":
        leads_router._write(db, record_id, LeadUpdate.model_validate(payload), set(payload), user)
    elif module == "opportunities":
        opportunities_router._write(db, record_id, OpportunityUpdate.model_validate(payload), set(payload), user)
    else:  # pragma: no cover — preview() refuses once a Deal exists
        raise HTTPException(status.HTTP_409_CONFLICT, {"code": "CANNOT_WITHDRAW", "message": "This registration already became a Deal, so it can't be withdrawn."})


def withdraw(
    db: Session,
    reg: DealRegistration,
    *,
    reason: str | None,
    action: str | None,
    new_primary: str | None,
    user: User,
) -> None:
    actor = user.user_id
    reason = (reason or "").strip()
    if len(reason) < MIN_REASON:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            {"code": "WITHDRAWAL_REASON_REQUIRED", "message": "Say why the partner withdrew."},
        )

    info = preview(db, reg)
    if not info["can_withdraw"]:
        raise HTTPException(status.HTTP_409_CONFLICT, {"code": "CANNOT_WITHDRAW", "message": info["blocked_reason"]})

    why = f"{registration_name(reg, account_names(db))} was withdrawn: {reason}"

    tracked = ["registration_status", "withdrawn_date", "withdrawal_reason"]
    before = snapshot(reg, tracked)
    reg.registration_status = WITHDRAWN
    reg.withdrawn_date = today_company()
    reg.withdrawal_reason = reason
    reg.modified_by = actor
    reg.modified_date = now_utc()
    record_audit(
        db,
        module="registrations",
        record_id=reg.registration_id,
        action="updated",
        actor=actor,
        changed_fields=tracked,
        changed=diff(before, snapshot(reg, tracked)),
    )

    status_write: tuple[str, str, dict[str, Any]] | None = None
    hand_over = True
    found = _pursuit(db, reg)

    if found is not None and is_open(found[2][1]):
        if action not in PURSUIT_ACTIONS:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                {
                    "code": "PURSUIT_ACTION_REQUIRED",
                    "message": "Choose what happens to the pursuit: keep pursuing, put on hold, or close as lost.",
                },
            )
        lead, _records, (module, record) = found
        stage = stage_number(getattr(record, STAGE_FIELD[module], None))
        record_id = id_of(module, record)

        if action == "keep":
            hand_over = False
            _release_partner(db, lead, reg, actor)
        elif action == "hold":
            hand_over = False
            payload: dict[str, Any] = {"lead_status": "ON_HOLD"}
            if stage is not None:
                payload[f"on_hold_reason__s{stage}"] = f"Partner withdrew the deal registration: {reason}"
            status_write = (module, record_id, payload)
        else:
            payload = {"lead_status": "CLOSED_LOST"}
            if stage is not None:
                payload[f"closed_lost_reason_code__s{stage}"] = PARTNER_WITHDRAWN
            status_write = (module, record_id, payload)

            if record.pursuit_group and record.is_primary_pursuit:
                group = db.get(PursuitGroup, record.pursuit_group)
                root = root_of(db, module, record)
                others = [o for o in open_pursuits_in(db, group.group_id) if o["pursuit"] != root]
                if others:
                    if not new_primary:
                        raise HTTPException(
                            status.HTTP_409_CONFLICT,
                            {
                                "code": "NEW_PRIMARY_REQUIRED",
                                "message": "This pursuit counts in the pipeline, and another of the same project is still open.",
                                "details": ["Choose which one should count instead."],
                                "options": [o["record_id"] for o in others],
                            },
                        )
                    chosen = _resolve_member(db, new_primary)[0]
                    if chosen not in {o["pursuit"] for o in others}:
                        raise HTTPException(
                            status.HTTP_422_UNPROCESSABLE_ENTITY,
                            {
                                "code": "NOT_AN_OPEN_PURSUIT",
                                "message": "The new primary must be another open pursuit of the same project.",
                            },
                        )
                    change_primary(db, group, chosen, actor=actor, reason=why)
                    _follow_primary_registration(db, group, chosen, actor)
                    hand_over = False

    if hand_over:
        _hand_over_primary(db, reg, _group_for_registration(db, reg.registration_id), actor, why)

    if status_write is not None:
        _write_status(db, *status_write, user=user)
    else:
        db.commit()
