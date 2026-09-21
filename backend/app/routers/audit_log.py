from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy import func, select
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
        "changed": a.changed,
        "timestamp": a.timestamp,
    }


#: A record's History tab asks for one record's rows and renders all of them.
#: The cap exists so that an unfiltered call — a curious operator hitting
#: /api/audit-log in a browser — cannot try to serialise the entire trail of
#: every record ever written, which is the one table here that only ever grows.
DEFAULT_LIMIT = 500
MAX_LIMIT = 2000


@router.get("/audit-log", response_model=list[AuditLogOut])
def list_audit_log(request: Request, response: Response, db: Session = Depends(get_db)):
    """
    The record-level CRUD trail, newest first, optionally filtered to one
    record or module. The History tab reads this with ?record_id=<id> and
    merges it with /transitions and /conversions into one timeline.

    No POST here: rows are written from inside the leads/opportunities/deals/
    accounts/contacts routers themselves — see app/audit.py::record_audit.

    Filtered and ordered in SQL rather than in Python, unlike the business list
    endpoints: those page over hundreds of rows, this one grows without bound
    by design, and one record's history must not cost a full-table read.
    """
    params = request.query_params

    query = select(AuditLog)
    record_id = params.get("record_id")
    if record_id:
        query = query.where(AuditLog.record_id == record_id)
    record_module = params.get("record_module")
    if record_module:
        query = query.where(AuditLog.record_module == record_module)

    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0

    limit = min(int(params.get("_limit") or DEFAULT_LIMIT), MAX_LIMIT)
    rows = db.scalars(query.order_by(AuditLog.timestamp.desc(), AuditLog.id.desc()).limit(limit))

    response.headers["X-Total-Count"] = str(total)
    return [_serialise(r) for r in rows]
