"""
/api/feedback — what users tell the people building ARK CRM.

    POST  /api/feedback            anyone with a role        (PROTECTED)
    GET   /api/feedback            DEVELOPER only            (require_developer)
    PATCH /api/feedback/{id}       DEVELOPER only — New / Read / Done

UX roadmap item 2, 17 Sep 2026. The read side is gated per route rather than
on the router, because the same router must accept a POST from everyone.

Who wrote it and when, and who marked it read, are the server's to stamp. The
category and status are picklist keys (`feedback__category`,
`feedback__status`, migration 0032), checked against the active values so a
stale page cannot store a key the picklist no longer offers.
"""

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth import current_user, require_developer
from ..clock import now_utc
from ..database import get_db
from ..ids import next_reference_id
from ..messages import not_found, refusal
from ..models import Feedback, PicklistValue, User
from ..schemas import FeedbackCreate, FeedbackOut, FeedbackStatusUpdate

router = APIRouter(tags=["feedback"])


def _active_keys(db: Session, picklist_key: str) -> set[str]:
    return set(
        db.scalars(
            select(PicklistValue.key).where(PicklistValue.picklist_key == picklist_key, PicklistValue.active.is_(True))
        )
    )


def _serialise(item: Feedback, names: dict[str, str]) -> dict:
    return {
        "id": item.feedback_id,
        "feedback_id": item.feedback_id,
        "category": item.category,
        "message": item.message,
        "page_path": item.page_path,
        "record_ref": item.record_ref,
        "status": item.status,
        "created_by": item.created_by,
        "created_by_name": names.get(item.created_by),
        "created_at": item.created_at,
        "read_by": item.read_by,
        "read_at": item.read_at,
    }


def _names(db: Session) -> dict[str, str]:
    return {u.user_id: u.name for u in db.scalars(select(User))}


@router.post("/feedback", response_model=FeedbackOut, status_code=status.HTTP_201_CREATED)
def create_feedback(
    payload: FeedbackCreate,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    message = payload.message.strip()
    if not message:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            refusal("FEEDBACK_EMPTY", "Write a few words before sending."),
        )
    if payload.category not in _active_keys(db, "feedback__category"):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            refusal("FEEDBACK_CATEGORY_UNKNOWN", "Pick what kind of feedback this is.", ["Reload the page if the list looks wrong."]),
        )

    highest = 0
    for existing in db.scalars(select(Feedback.feedback_id)):
        try:
            highest = max(highest, int(existing.split("-", 1)[1]))
        except (IndexError, ValueError):
            continue
    stamp = now_utc()
    item = Feedback(
        feedback_id=next_reference_id(db, "feedback", "FB", 5, highest),
        category=payload.category,
        message=message,
        page_path=(payload.page_path or None),
        record_ref=(payload.record_ref or None),
        status="NEW",
        created_by=user.user_id,
        created_at=stamp,
        updated_at=stamp,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return _serialise(item, {user.user_id: user.name})


@router.get("/feedback", response_model=list[FeedbackOut])
def list_feedback(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    _: User = Depends(require_developer),
):
    """Newest first. `?status=NEW` (repeatable) and `?category=` narrow it; the unread count rides on X-New-Count."""
    params = request.query_params
    query = select(Feedback).order_by(Feedback.created_at.desc())
    if params.getlist("status"):
        query = query.where(Feedback.status.in_(params.getlist("status")))
    if params.getlist("category"):
        query = query.where(Feedback.category.in_(params.getlist("category")))
    items = list(db.scalars(query))
    response.headers["X-New-Count"] = str(
        len(list(db.scalars(select(Feedback.feedback_id).where(Feedback.status == "NEW"))))
    )
    names = _names(db)
    return [_serialise(item, names) for item in items]


@router.patch("/feedback/{feedback_id}", response_model=FeedbackOut)
def update_feedback_status(
    feedback_id: str,
    payload: FeedbackStatusUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_developer),
):
    item = db.get(Feedback, feedback_id)
    if item is None:
        raise not_found("feedback")
    if payload.status not in _active_keys(db, "feedback__status"):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            refusal("FEEDBACK_STATUS_UNKNOWN", "That status isn't offered any more.", ["Reload the page and try again."]),
        )
    if payload.status != item.status:
        item.status = payload.status
        # Who first read it stays recorded; moving it back to New clears it.
        if payload.status == "NEW":
            item.read_by, item.read_at = None, None
        elif item.read_by is None:
            item.read_by, item.read_at = user.user_id, now_utc()
        item.updated_at = now_utc()
        db.commit()
        db.refresh(item)
    return _serialise(item, _names(db))
