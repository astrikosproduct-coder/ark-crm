"""
/api/sales-targets — each BD Owner's monthly booking target (migration 0040).

    GET   /api/sales-targets                     anyone with a role
          ?fiscal_year=FY27   (default: the current one)
          ?bd_owner_id=USR-…  one owner
          ?history=true       SUPERSEDED rows too
    POST  /api/sales-targets                     ADMIN or DEVELOPER — a draft
    PATCH /api/sales-targets/{id}                ADMIN or DEVELOPER — a draft's amount
    POST  /api/sales-targets/{id}/lock           ADMIN or DEVELOPER
    POST  /api/sales-targets/{id}/revise         ADMIN or DEVELOPER — a locked one

Dashboard Phase 1, 28 Sep 2026. No screen yet: this exists so the permission
and the lock have something real to guard. The rules live in
app/sales_targets.py; the write routes are gated per route
(auth.require_target_editor) because the router also serves reads to everyone.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .. import fiscal
from .. import sales_targets as targets
from ..auth import require_target_editor
from ..clock import today_company
from ..database import get_db
from ..messages import already_exists, not_found, refusal
from ..models import SalesTarget, User
from ..schemas import SalesTargetCreate, SalesTargetEdit, SalesTargetList, SalesTargetOut, SalesTargetRevise

router = APIRouter(tags=["sales targets"])


def _names(db: Session) -> dict[str, str]:
    return {u.user_id: u.name for u in db.scalars(select(User))}


def _get_for_update(db: Session, target_id: str) -> SalesTarget:
    target = db.get(SalesTarget, target_id, with_for_update=True)
    if target is None:
        raise not_found("target")
    return target


def _apply(db: Session, change) -> SalesTarget:
    """
    Run one change and commit it. The database's own rules are the last word:
    two people saving the same owner-month at once, or revising one target
    twice, get past the checks in app/sales_targets.py and land here.
    """
    try:
        target = change()
        db.commit()
    except IntegrityError:
        db.rollback()
        raise already_exists()
    db.refresh(target)
    return target


@router.get("/sales-targets", response_model=SalesTargetList)
def list_targets(
    fiscal_year: str | None = None,
    bd_owner_id: str | None = None,
    history: bool = False,
    db: Session = Depends(get_db),
):
    label = fiscal_year or fiscal.label_of(today_company())
    try:
        fiscal.parse_label(label)
    except ValueError:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            refusal("FISCAL_YEAR_UNKNOWN", "That isn't a fiscal year.", ["Write it as FY27."]),
        )
    query = select(SalesTarget).where(SalesTarget.fiscal_year == label)
    if bd_owner_id:
        query = query.where(SalesTarget.bd_owner_id == bd_owner_id)
    if not history:
        query = query.where(SalesTarget.status != "SUPERSEDED")
    rows = list(db.scalars(query.order_by(SalesTarget.period_month, SalesTarget.bd_owner_id, SalesTarget.created_at)))
    names = _names(db)
    return {
        "fiscal_year": label,
        # Current rows only, whatever `history` says: a superseded number is
        # history, and adding it would count one owner-month twice.
        "total_usd": round(sum(float(r.target_amount_usd) for r in rows if r.status != "SUPERSEDED"), 2),
        "items": [targets.serialise(r, names) for r in rows],
    }


@router.post("/sales-targets", response_model=SalesTargetOut, status_code=status.HTTP_201_CREATED)
def create_target(
    payload: SalesTargetCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_target_editor),
):
    target = _apply(
        db,
        lambda: targets.create_target(
            db,
            bd_owner_id=payload.bd_owner_id,
            period_month=payload.period_month,
            amount=payload.target_amount_usd,
            actor=user.user_id,
        ),
    )
    return targets.serialise(target, _names(db))


@router.patch("/sales-targets/{target_id}", response_model=SalesTargetOut)
def edit_target(
    target_id: str,
    payload: SalesTargetEdit,
    db: Session = Depends(get_db),
    user: User = Depends(require_target_editor),
):
    target = _apply(
        db,
        lambda: targets.edit_draft(
            db, _get_for_update(db, target_id), amount=payload.target_amount_usd, actor=user.user_id
        ),
    )
    return targets.serialise(target, _names(db))


@router.post("/sales-targets/{target_id}/lock", response_model=SalesTargetOut)
def lock_target(
    target_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_target_editor),
):
    target = _apply(db, lambda: targets.lock(db, _get_for_update(db, target_id), actor=user.user_id))
    return targets.serialise(target, _names(db))


@router.post("/sales-targets/{target_id}/revise", response_model=SalesTargetOut, status_code=status.HTTP_201_CREATED)
def revise_target(
    target_id: str,
    payload: SalesTargetRevise,
    db: Session = Depends(get_db),
    user: User = Depends(require_target_editor),
):
    replacement = _apply(
        db,
        lambda: targets.revise(
            db,
            _get_for_update(db, target_id),
            amount=payload.target_amount_usd,
            note=payload.revision_note,
            actor=user.user_id,
        ),
    )
    return targets.serialise(replacement, _names(db))
