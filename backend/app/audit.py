from typing import Any

from sqlalchemy.orm import Session

from .clock import now_utc
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
    changed: list[dict[str, Any]] | None = None,
) -> None:
    """
    Appends one audit_log row to the current session, WITHOUT committing — the
    caller's own db.commit() persists it atomically with the business write it
    describes. Call this AFTER the record's id is known (so on create, after
    _next_*_id has run) and BEFORE that commit.

    record_id is a plain string, not a foreign key: `module` says which of
    leads/opportunities/deals/accounts/contacts it names, and no single FK can
    point at five different tables. See models.AuditLog.

    `actor` MUST come from the Entra session — `Depends(current_user).user_id`
    — and never from the request body. Until Sep 2026 it was read off the
    record's own `modified_by`, which the browser sent: the audit trail's idea
    of who did something was whatever the person doing it claimed. Every call
    site now passes the signed-in user, which is the only value a client cannot
    choose.

    `changed_fields` is what the request CARRIED; `changed` is what actually
    MOVED, as {field, from, to} — see app/changes.py. Both are kept: the first
    answers "was this touched", the second is what the History timeline renders.
    """
    db.add(
        AuditLog(
            reference_id=next_reference_id(db, "audit_log", "AUD", 5, 0),
            record_module=module,
            record_id=record_id,
            action=action,
            actor=actor,
            changed_fields=changed_fields,
            changed=changed,
            # Server clock, always UTC — never a timestamp from the payload.
            timestamp=now_utc(),
        )
    )
