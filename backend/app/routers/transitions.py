import re

from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..ids import next_reference_id
from ..models import StageTransition
from ..schemas import TransitionCreate, TransitionOut

router = APIRouter(tags=["transitions"])

TRANSITION_ID_PATTERN = re.compile(r"^TRN-(\d+)$")


def _next_transition_id(db: Session) -> str:
    """From a stored high-water mark, never max(existing) — see app/ids.py."""
    highest = 0
    for existing in db.scalars(select(StageTransition.reference_id)):
        match = TRANSITION_ID_PATTERN.match(existing or "")
        if match:
            highest = max(highest, int(match.group(1)))
    return next_reference_id(db, "transitions", "TRN", 4, highest)


def _serialise(t: StageTransition) -> dict:
    return {
        "id": t.reference_id,
        "module": t.module,
        "record_id": t.record_id,
        "from": t.from_stage,
        "to": t.to_stage,
        "reason": t.reason,
        "is_skip": t.is_skip,
        "is_reversal": t.is_reversal,
        "actor": t.actor,
        "timestamp": t.timestamp,
    }


@router.get("/transitions", response_model=list[TransitionOut])
def list_transitions(request: Request, response: Response, db: Session = Depends(get_db)):
    """
    Every recorded stage move, optionally filtered to one record or module —
    PipelineRecordPage.tsx reads this with ?record_id=<id> for StageHistoryTab.
    """
    rows = list(db.scalars(select(StageTransition)))

    params = request.query_params
    record_id = params.get("record_id")
    if record_id:
        rows = [r for r in rows if r.record_id == record_id]
    module = params.get("module")
    if module:
        rows = [r for r in rows if r.module == module]

    response.headers["X-Total-Count"] = str(len(rows))
    return [_serialise(r) for r in rows]


@router.post("/transitions", response_model=TransitionOut, status_code=status.HTTP_201_CREATED)
def create_transition(payload: TransitionCreate, db: Session = Depends(get_db)):
    """
    The one place a stage move is recorded — see AdvanceStageDialog.tsx,
    LeadAdvanceDialog.tsx and DealDetailPage.tsx's expansion-lead creation,
    all of which POST here right after the record's own stage field is
    written. Never rejects on an unrecognised module/record_id: this is an
    audit trail, not a foreign key, and refusing to log a move that already
    happened would hide the very thing this table exists to show.
    """
    transition = StageTransition(
        reference_id=_next_transition_id(db),
        module=payload.module,
        record_id=payload.record_id,
        from_stage=payload.from_stage,
        to_stage=payload.to_stage,
        reason=payload.reason,
        is_skip=payload.is_skip,
        is_reversal=payload.is_reversal,
        actor=payload.actor,
        timestamp=payload.timestamp,
    )
    db.add(transition)
    db.commit()
    db.refresh(transition)
    return _serialise(transition)
