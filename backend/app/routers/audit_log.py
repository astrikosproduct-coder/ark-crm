from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import AuditLog
from ..schemas import AuditLogOut

router = APIRouter(tags=["audit-log"])


def _serialise(a: AuditLog) -> dict:
    return {
        "id": a.reference_id,
        "record_module": a.record_module,
        "record_id": a.record_id,
        "action": a.action,
        "actor": a.actor,
        "changed_fields": a.changed_fields,
        "timestamp": a.timestamp,
    }


@router.get("/audit-log", response_model=list[AuditLogOut])
def list_audit_log(request: Request, response: Response, db: Session = Depends(get_db)):
    """
    The record-level CRUD trail, optionally filtered to one record or module.
    No POST here: rows are written from inside the leads/opportunities/deals/
    accounts/contacts routers themselves — see app/audit.py::record_audit.
    """
    rows = list(db.scalars(select(AuditLog)))

    params = request.query_params
    record_id = params.get("record_id")
    if record_id:
        rows = [r for r in rows if r.record_id == record_id]
    record_module = params.get("record_module")
    if record_module:
        rows = [r for r in rows if r.record_module == record_module]

    rows.sort(key=lambda r: r.timestamp, reverse=True)

    response.headers["X-Total-Count"] = str(len(rows))
    return [_serialise(r) for r in rows]
