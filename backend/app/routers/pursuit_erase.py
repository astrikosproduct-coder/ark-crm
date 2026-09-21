"""
Deleting a pursuit for good — every record of the chain, in one transaction.
See app/pursuit_erasure.py for what goes and what is only unlinked.

    GET  /api/pursuits/{record_id}/erase    what would be deleted
    POST /api/pursuits/{record_id}/erase    delete it; body {"confirm": "<pursuit name>"}

Open to every role (decided 21 Sep 2026), like every other business action in
V1 — mounted with PROTECTED, so a signed-in user with no role still gets
nothing. What guards it is the confirmation: the pursuit's name, typed.
"""

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..auth import current_user
from ..database import get_db
from ..models import User
from ..pursuit_erasure import erase, plan

router = APIRouter(tags=["pursuits"])


class EraseRequest(BaseModel):
    confirm: str = Field(max_length=500)


@router.get("/pursuits/{record_id}/erase")
def erase_plan(record_id: str, db: Session = Depends(get_db)):
    return plan(db, record_id)


@router.post("/pursuits/{record_id}/erase")
def erase_pursuit(
    record_id: str,
    payload: EraseRequest,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    info = erase(db, record_id, confirm=payload.confirm, actor=user.user_id)
    return {"deleted": [r["id"] for r in info["records"]]}
