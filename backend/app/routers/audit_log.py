import re

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import AuditLog, RegistrationConflict
from ..schemas import AuditLogOut

router = APIRouter(tags=["audit-log"])


#: "Conflict CONF-0002 decided: both pursued." — the wording pursuit groups
#: wrote before History stopped showing record ids (14 Oct 2026).
_CONFLICT_NUMBER = re.compile(r"Conflict (CONF-\d+)")


def _conflict_names(db: Session, rows: list[AuditLog]) -> dict[str, str]:
    """Every conflict number these rows' reasons mention, by its partners' names."""
    wanted = {
        m.group(1)
        for a in rows
        for e in (a.changed or [])
        if isinstance(e, dict) and e.get("field") == "__reason"
        for m in _CONFLICT_NUMBER.finditer(str(e.get("to") or ""))
    }
    if not wanted:
        return {}
    from ..registration_matching import account_names, conflict_name, partner_names_of_registrations

    partner_of = partner_names_of_registrations(db, account_names(db))
    return {
        c.conflict_id: conflict_name(c, partner_of)
        for c in db.scalars(select(RegistrationConflict).where(RegistrationConflict.conflict_id.in_(wanted)))
    }


def _serialise(a: AuditLog, conflicts: dict[str, str] | None = None) -> dict:
    changed = a.changed
    if conflicts and changed:
        changed = [
            {**e, "to": _CONFLICT_NUMBER.sub(lambda m: conflicts.get(m.group(1), "A conflict"), str(e["to"]))}
            if isinstance(e, dict) and e.get("field") == "__reason" and e.get("to")
            else e
            for e in changed
        ]
    return {
        "id": a.reference_id,
        "record_module": a.record_module,
        "record_id": a.record_id,
        "action": a.action,
        "actor": a.actor,
        "changed_fields": a.changed_fields,
        "changed": changed,
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
    rows = list(db.scalars(query.order_by(AuditLog.timestamp.desc(), AuditLog.id.desc()).limit(limit)))
    conflicts = _conflict_names(db, rows)

    response.headers["X-Total-Count"] = str(total)
    return [_serialise(r, conflicts) for r in rows]
