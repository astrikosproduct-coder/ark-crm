"""
Sales targets — the rules, in one place, for the API and the seed script alike.

    create   a DRAFT for one BD Owner and one month
    edit     a DRAFT's amount, in place
    lock     DRAFT -> LOCKED; from then on it never changes
    revise   a LOCKED target: it becomes SUPERSEDED and a new LOCKED row, linked
             by revision_of and carrying a note, takes its place

The database enforces the same rules (migration 0040's trigger and partial
unique index). These functions check first so a person gets a sentence rather
than a constraint name, and so every change is written to the audit trail
(module 'sales_targets') in the same transaction as the change itself.

Nothing here commits. The caller commits, once, after the whole change.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import fiscal
from .audit import record_audit
from .changes import jsonable
from .clock import now_utc
from .ids import next_reference_id
from .messages import picked_record_missing, refusal
from .models import SalesTarget, User, UserRole

MODULE = "sales_targets"

#: Targets are set for holders of this role, and only them.
BD_OWNER_ROLE = "BD_OWNER"


def _conflict(code: str, message: str, details: list[str]) -> HTTPException:
    return HTTPException(status.HTTP_409_CONFLICT, refusal(code, message, details))


def _refuse(code: str, message: str, details: list[str]) -> HTTPException:
    return HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, refusal(code, message, details))


def serialise(target: SalesTarget, names: dict[str, str]) -> dict[str, Any]:
    return {
        "id": target.target_id,
        "target_id": target.target_id,
        "fiscal_year": target.fiscal_year,
        "period_month": target.period_month,
        "bd_owner_id": target.bd_owner_id,
        "bd_owner_name": names.get(target.bd_owner_id),
        "target_amount_usd": float(target.target_amount_usd),
        "currency": target.currency,
        "status": target.status,
        "locked_at": target.locked_at,
        "locked_by": target.locked_by,
        "revision_of": target.revision_of,
        "revision_note": target.revision_note,
        "created_at": target.created_at,
        "created_by": target.created_by,
        "updated_at": target.updated_at,
        "updated_by": target.updated_by,
    }


def active_bd_owners(db: Session) -> list[User]:
    """Every active user holding the BD Owner role, by name."""
    return list(
        db.scalars(
            select(User)
            .join(UserRole, UserRole.user_id == User.user_id)
            .where(UserRole.role_id == BD_OWNER_ROLE, User.active.is_(True))
            .order_by(User.name)
        )
    )


def current_target(db: Session, bd_owner_id: str, period_month: date) -> SalesTarget | None:
    """The one row that is not SUPERSEDED for this owner and month, if any."""
    return db.scalar(
        select(SalesTarget).where(
            SalesTarget.bd_owner_id == bd_owner_id,
            SalesTarget.period_month == period_month,
            SalesTarget.status != "SUPERSEDED",
        )
    )


def _next_id(db: Session) -> str:
    highest = 0
    for existing in db.scalars(select(SalesTarget.target_id)):
        try:
            highest = max(highest, int(existing.split("-", 1)[1]))
        except (IndexError, ValueError):
            continue
    return next_reference_id(db, MODULE, "TGT", 5, highest)


def _owner_or_refuse(db: Session, bd_owner_id: str) -> User:
    owner = db.get(User, bd_owner_id)
    if owner is None:
        raise picked_record_missing("person")
    if not owner.active or not any(role.role_id == BD_OWNER_ROLE for role in owner.roles):
        raise _refuse(
            "TARGET_OWNER_NOT_BD",
            "Targets are set for active BD Owners only.",
            ["Pick a person who holds the BD Owner role."],
        )
    return owner


def create_target(db: Session, *, bd_owner_id: str, period_month: date, amount: Decimal, actor: str) -> SalesTarget:
    """A new DRAFT. The fiscal year is worked out from the month, never sent."""
    if period_month.day != 1:
        raise _refuse(
            "TARGET_MONTH_NOT_FIRST",
            "A target is set for a whole month.",
            ["Send the first day of the month."],
        )
    _owner_or_refuse(db, bd_owner_id)
    if current_target(db, bd_owner_id, period_month) is not None:
        raise _conflict(
            "TARGET_EXISTS",
            "This person already has a target for that month.",
            ["Change that target instead of adding a second one."],
        )

    stamp = now_utc()
    target = SalesTarget(
        target_id=_next_id(db),
        fiscal_year=fiscal.label_of(period_month),
        period_month=period_month,
        bd_owner_id=bd_owner_id,
        target_amount_usd=amount,
        currency="USD",
        status="DRAFT",
        created_at=stamp,
        created_by=actor,
        updated_at=stamp,
        updated_by=actor,
    )
    db.add(target)
    db.flush()
    record_audit(
        db,
        module=MODULE,
        record_id=target.target_id,
        action="created",
        actor=actor,
        changed_fields=["bd_owner_id", "period_month", "target_amount_usd"],
        changed=[
            {"field": "bd_owner_id", "from": None, "to": bd_owner_id},
            {"field": "period_month", "from": None, "to": jsonable(period_month)},
            {"field": "target_amount_usd", "from": None, "to": jsonable(amount)},
        ],
    )
    return target


def _refuse_unless_draft(target: SalesTarget) -> None:
    if target.status == "LOCKED":
        raise _conflict(
            "TARGET_LOCKED",
            "This target is locked.",
            ["Revise it to change it. The locked number stays on record beside the new one."],
        )
    if target.status == "SUPERSEDED":
        raise _conflict(
            "TARGET_SUPERSEDED",
            "A newer version of this target exists.",
            ["Open the current target and change that one."],
        )


def edit_draft(db: Session, target: SalesTarget, *, amount: Decimal, actor: str) -> SalesTarget:
    """A DRAFT's amount, changed in place. Anything else is refused."""
    _refuse_unless_draft(target)
    before = target.target_amount_usd
    if Decimal(before) == Decimal(amount):
        return target
    target.target_amount_usd = amount
    target.updated_at = now_utc()
    target.updated_by = actor
    record_audit(
        db,
        module=MODULE,
        record_id=target.target_id,
        action="updated",
        actor=actor,
        changed_fields=["target_amount_usd"],
        changed=[{"field": "target_amount_usd", "from": jsonable(before), "to": jsonable(amount)}],
    )
    return target


def lock(db: Session, target: SalesTarget, *, actor: str) -> SalesTarget:
    """DRAFT -> LOCKED, stamped with who and when."""
    _refuse_unless_draft(target)
    stamp = now_utc()
    target.status = "LOCKED"
    target.locked_at = stamp
    target.locked_by = actor
    target.updated_at = stamp
    target.updated_by = actor
    record_audit(
        db,
        module=MODULE,
        record_id=target.target_id,
        action="locked",
        actor=actor,
        changed_fields=["status"],
        changed=[{"field": "status", "from": "DRAFT", "to": "LOCKED"}],
    )
    return target


def revise(db: Session, target: SalesTarget, *, amount: Decimal, note: str, actor: str) -> SalesTarget:
    """
    A LOCKED target's replacement. The original becomes SUPERSEDED — its number
    untouched — and the new row, LOCKED at once, points back at it.

    The new row is locked straight away: a locked number is changed only by a
    noted, deliberate revision, and a revision that could then drift as a draft
    would undo the point of locking.
    """
    if target.status == "DRAFT":
        raise _conflict(
            "TARGET_NOT_LOCKED",
            "This target is still a draft.",
            ["Edit the draft directly. Only a locked target needs a revision."],
        )
    if target.status == "SUPERSEDED":
        raise _conflict(
            "TARGET_SUPERSEDED",
            "A newer version of this target exists.",
            ["Revise the current target instead."],
        )
    note = (note or "").strip()
    if not note:
        raise _refuse(
            "TARGET_REVISION_NOTE_MISSING",
            "Say why the target is changing.",
            ["The reason is kept beside the new number."],
        )

    stamp = now_utc()
    target.status = "SUPERSEDED"
    target.updated_at = stamp
    target.updated_by = actor
    # The partial unique index must see the original leave before the
    # replacement arrives, and so must the trigger that checks the link.
    db.flush()
    record_audit(
        db,
        module=MODULE,
        record_id=target.target_id,
        action="superseded",
        actor=actor,
        changed_fields=["status"],
        changed=[{"field": "status", "from": "LOCKED", "to": "SUPERSEDED"}],
    )

    replacement = SalesTarget(
        target_id=_next_id(db),
        fiscal_year=target.fiscal_year,
        period_month=target.period_month,
        bd_owner_id=target.bd_owner_id,
        target_amount_usd=amount,
        currency="USD",
        status="LOCKED",
        locked_at=stamp,
        locked_by=actor,
        revision_of=target.target_id,
        revision_note=note,
        created_at=stamp,
        created_by=actor,
        updated_at=stamp,
        updated_by=actor,
    )
    db.add(replacement)
    db.flush()
    record_audit(
        db,
        module=MODULE,
        record_id=replacement.target_id,
        action="revised",
        actor=actor,
        changed_fields=["target_amount_usd", "revision_of", "revision_note"],
        changed=[
            {"field": "target_amount_usd", "from": jsonable(target.target_amount_usd), "to": jsonable(amount)},
            {"field": "revision_of", "from": None, "to": target.target_id},
            {"field": "revision_note", "from": None, "to": note},
        ],
    )
    return replacement


def seed_year(db: Session, label: str, *, actor: str) -> tuple[list[SalesTarget], int]:
    """
    Twelve DRAFT rows at 0 for every active BD Owner in the fiscal year `label`,
    skipping any owner-month that already has a target. Safe to run again: a
    BD Owner added mid-year gets their rows, and nobody gets a second set.

    Returns (rows created, owner-months skipped).
    """
    months = fiscal.months_of(label)
    created: list[SalesTarget] = []
    skipped = 0
    for owner in active_bd_owners(db):
        for month in months:
            if current_target(db, owner.user_id, month) is not None:
                skipped += 1
                continue
            created.append(
                create_target(db, bd_owner_id=owner.user_id, period_month=month, amount=Decimal("0"), actor=actor)
            )
    return created, skipped
