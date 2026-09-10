from datetime import datetime, timezone

from sqlalchemy.orm import Session

from .ids import next_reference_id
from .models import AuditLog


def record_audit(
    db: Session,
    *,
    module: str,
    record_id: str,
    action: str,
    actor: str | None = None,
    changed_fields: list[str] | None = None,
) -> None:
    """
    Appends one audit_log row to the current session, WITHOUT committing — the
    caller's own db.commit() persists it atomically with the business write it
    describes. Call this AFTER the record's id is known (so on create, after
    _next_*_id has run) and BEFORE that commit.

    record_id is a plain string, not a foreign key: `module` says which of
    leads/opportunities/deals/accounts/contacts it names, and no single FK can
    point at five different tables. See models.AuditLog.
    """
    db.add(
        AuditLog(
            reference_id=next_reference_id(db, "audit_log", "AUD", 5, 0),
            record_module=module,
            record_id=record_id,
            action=action,
            actor=actor,
            changed_fields=changed_fields,
            timestamp=datetime.now(timezone.utc),
        )
    )
