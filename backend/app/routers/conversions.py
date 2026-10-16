import re

from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth import current_user
from ..clock import now_utc
from ..database import get_db
from ..ids import next_reference_id
from ..models import Conversion, Deal, Lead, Opportunity, User
from ..schemas import ConversionCreate, ConversionOut

router = APIRouter(tags=["conversions"])

CONVERSION_ID_PATTERN = re.compile(r"^CONV-(\d+)$")


def _next_conversion_id(db: Session) -> str:
    """From a stored high-water mark, never max(existing) — see app/ids.py."""
    highest = 0
    for existing in db.scalars(select(Conversion.reference_id)):
        match = CONVERSION_ID_PATTERN.match(existing or "")
        if match:
            highest = max(highest, int(match.group(1)))
    return next_reference_id(db, "conversions", "CONV", 4, highest)


#: How a pipeline record is named, per module.
_NAMED = {
    "leads": (Lead, "opportunity_name"),
    "opportunities": (Opportunity, "opportunity_name"),
    "deals": (Deal, "deal_name"),
}


def _name_of(db: Session, module: str, record_id: str | None) -> str | None:
    model, column = _NAMED.get(module, (None, None))
    record = db.get(model, record_id) if model is not None and record_id else None
    return getattr(record, column, None) if record is not None else None


def _serialise(db: Session, c: Conversion) -> dict:
    """
    History shows no record ids (decided 14 Oct 2026): each side is served by
    name, and a number in a note written before then ("LEAD-00005 moved
    directly…") reads as that record's name.
    """
    source_name = _name_of(db, c.source_module, c.source_id)
    target_name = _name_of(db, c.target_module, c.target_id)
    note = c.note
    for record_id, name in ((c.source_id, source_name), (c.target_id, target_name)):
        if note and record_id:
            note = note.replace(record_id, name or "the record")
    return {
        "id": c.reference_id,
        "source_module": c.source_module,
        "source_id": c.source_id,
        "source_name": source_name,
        "target_module": c.target_module,
        "target_id": c.target_id,
        "target_name": target_name,
        "actor": c.actor,
        "timestamp": c.timestamp,
        "copied_fields": c.copied_fields,
        "note": note,
    }


@router.get("/conversions", response_model=list[ConversionOut])
def list_conversions(request: Request, response: Response, db: Session = Depends(get_db)):
    """Every recorded conversion, optionally filtered to one source or target record."""
    rows = list(db.scalars(select(Conversion)))

    params = request.query_params
    source_id = params.get("source_id")
    if source_id:
        rows = [r for r in rows if r.source_id == source_id]
    target_id = params.get("target_id")
    if target_id:
        rows = [r for r in rows if r.target_id == target_id]

    response.headers["X-Total-Count"] = str(len(rows))
    return [_serialise(db, r) for r in rows]


@router.post("/conversions", response_model=ConversionOut, status_code=status.HTTP_201_CREATED)
def create_conversion(
    payload: ConversionCreate,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    """
    Written right after the target record (the new Opportunity or Deal) is
    created — see LeadAdvanceDialog.tsx's moveToOpportunity and
    opportunities/ConvertToDealDialog.tsx. Never rejects on an unrecognised
    module/id: this is an audit trail of a conversion that already happened,
    not a gate on whether it may.

    `actor` and `timestamp` in the body are IGNORED, for the same reason they
    are on /transitions — see that router.
    """
    conversion = Conversion(
        reference_id=_next_conversion_id(db),
        source_module=payload.source_module,
        source_id=payload.source_id,
        target_module=payload.target_module,
        target_id=payload.target_id,
        copied_fields=payload.copied_fields,
        note=payload.note,
        actor=user.user_id,
        timestamp=now_utc(),
    )
    db.add(conversion)
    db.commit()
    db.refresh(conversion)
    return _serialise(db, conversion)
