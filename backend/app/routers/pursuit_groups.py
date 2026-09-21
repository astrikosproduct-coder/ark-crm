"""
/api/pursuit-groups — reading a group, and the three things a person does to
one: group pursuits, change which is primary, remove a pursuit.

Every rule lives in app/pursuits.py; this file is the HTTP shape of it. Any
signed-in user with a role may call every endpoint (PROTECTED in app/main.py)
— see the note on role binding in app/pursuits.py.
"""

from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth import current_user
from ..messages import not_found
from ..database import get_db
from ..models import PursuitGroup, User
from ..pursuits import (
    add_member,
    change_primary,
    chain,
    create_group,
    record_by_id,
    remove_member,
    root_of,
    serialise_group,
    tip,
)
from ..schemas import (
    PursuitGroupAddMember,
    PursuitGroupChangePrimary,
    PursuitGroupCreate,
    PursuitGroupOut,
    PursuitGroupRemoveMember,
)

router = APIRouter(tags=["pursuit-groups"])


def _get_or_404(db: Session, group_id: str) -> PursuitGroup:
    group = db.get(PursuitGroup, group_id)
    if group is None:
        raise not_found("pursuit group")
    return group


@router.get("/pursuit-groups", response_model=list[PursuitGroupOut])
def list_groups(request: Request, response: Response, db: Session = Depends(get_db)):
    """Every group, or — with ?record_id= — the one that record's pursuit is in
    (an empty list when it is in none)."""
    record_id = request.query_params.get("record_id")
    if record_id:
        module, record = record_by_id(db, record_id)
        live = tip(chain(db, root_of(db, module, record)))
        group_id = live[1].pursuit_group if live else None
        groups = [db.get(PursuitGroup, group_id)] if group_id else []
    else:
        groups = list(db.scalars(select(PursuitGroup)))
    groups = [g for g in groups if g is not None]
    end_client = request.query_params.get("end_client")
    if end_client:
        groups = [g for g in groups if g.end_client == end_client]
    response.headers["X-Total-Count"] = str(len(groups))
    return [serialise_group(db, g) for g in groups]


@router.get("/pursuit-groups/{group_id}", response_model=PursuitGroupOut)
def get_group(group_id: str, db: Session = Depends(get_db)):
    return serialise_group(db, _get_or_404(db, group_id))


@router.post("/pursuit-groups", response_model=PursuitGroupOut, status_code=status.HTTP_201_CREATED)
def post_group(
    payload: PursuitGroupCreate,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    group = create_group(
        db, members=payload.members, primary=payload.primary, actor=user.user_id, reason=payload.reason
    )
    db.commit()
    return serialise_group(db, group)


@router.post("/pursuit-groups/{group_id}/members", response_model=PursuitGroupOut)
def post_member(
    group_id: str,
    payload: PursuitGroupAddMember,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    group = _get_or_404(db, group_id)
    add_member(db, group, payload.record_id, actor=user.user_id, reason=payload.reason)
    db.commit()
    return serialise_group(db, group)


@router.post("/pursuit-groups/{group_id}/primary", response_model=PursuitGroupOut)
def post_primary(
    group_id: str,
    payload: PursuitGroupChangePrimary,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    group = _get_or_404(db, group_id)
    change_primary(db, group, payload.record_id, actor=user.user_id, reason=payload.reason)
    db.commit()
    return serialise_group(db, group)


@router.post("/pursuit-groups/{group_id}/members/{record_id}/remove")
def post_remove_member(
    group_id: str,
    record_id: str,
    payload: PursuitGroupRemoveMember,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    """
    POST, not DELETE: removing carries a reason, and a DELETE body is something
    proxies and clients are entitled to drop. Returns the group, or
    {"dissolved": true} when one pursuit was left and the group went with it.
    """
    group = _get_or_404(db, group_id)
    remove_member(
        db,
        group,
        record_id,
        actor=user.user_id,
        reason=payload.reason,
        new_primary=payload.new_primary,
    )
    db.commit()
    if db.get(PursuitGroup, group_id) is None:
        return {"dissolved": True, "group_id": group_id}
    return serialise_group(db, group)
