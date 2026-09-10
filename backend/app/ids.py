from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import IdSequence


def next_reference_id(db: Session, name: str, prefix: str, pad: int, highest_seen: int) -> str:
    """
    Allocate the next never-before-used reference id, e.g. ACC-020.

    WHY THIS IS NOT `max(existing) + 1`
    -----------------------------------
    It used to be, and that reuses ids. Delete the newest account and the next
    create is handed the same id back. Any record still pointing at the deleted
    one — a Lead's End Client, a Contact's Account — then silently attaches
    itself to a brand-new, unrelated organisation. A reviewer creates an account,
    opens it, and finds it already "referenced" by leads it has never met.

    So the counter is a HIGH-WATER MARK that only ever increases. It is stored,
    not derived, which is the whole point: deleting a row cannot lower it.

    `highest_seen` seeds the counter the first time it is used, and guards
    against a row inserted by hand or by a migration behind the API's back.

    The row is locked for update, so two concurrent creates cannot be handed the
    same number.
    """
    row = db.scalar(select(IdSequence).where(IdSequence.name == name).with_for_update())

    if row is None:
        row = IdSequence(name=name, prefix=prefix, pad=pad, last_value=highest_seen)
        db.add(row)
        db.flush()

    row.last_value = max(row.last_value, highest_seen) + 1
    db.flush()

    return f"{prefix}-{row.last_value:0{pad}d}"
