"""
What actually changed in a write, as before/after pairs.

WHY THE FIELD NAMES WERE NEVER ENOUGH
-------------------------------------
`audit_log.changed_fields` records WHICH fields a request carried. That answers
"was this record touched" and nothing else — and it is not even a list of
changes, because the record editor PUTs a whole section every time, so a save
that altered one field reports twenty. A manager asking "who dropped the
probability, and from what" could not be answered from it at all.

This module produces the missing half: `[{field, from, to}]`, computed by
snapshotting the record BEFORE the payload is applied and comparing after. Only
fields whose value genuinely moved appear, so a twenty-field PUT that altered
one yields one entry.

RAW VALUES, NOT LABELS
----------------------
'AMBER', not 'Amber'; 1480000, not '$1,480,000'; '2026-12-31', not
'31 Dec 2026'. The register's labels are editable in Administration, and a
timeline that stored them would silently rewrite its own history the first time
somebody renamed a picklist value. Formatting belongs at render time, where the
current label is looked up from the current register — see the History tab.

CHILD LISTS ARE RECORDED, NOT DIFFED
------------------------------------
Demo Attendees and Feature Gaps are rows, and a row-level diff ("attendee 2's
job title changed") is a much larger piece of work for much less value than the
scalar diffs above. They emit `{field, kind: 'list'}` and the timeline renders
"updated" — honest about what it knows, rather than inventing a from/to for a
collection.
"""

from datetime import date, datetime
from decimal import Decimal
from typing import Any

#: Fields never worth a timeline entry, because the entry would BE the noise:
#: the system stamps every one of them on every write, so including them would
#: put "Modified Date changed" above every real change forever.
IGNORED = frozenset(
    {
        "created_by",
        "created_date",
        "modified_by",
        "modified_date",
    }
)


def jsonable(value: Any) -> Any:
    """
    A value JSONB can hold, without losing what it meant.

    Decimal goes to float rather than str so the timeline can format it as
    money; datetime/date go to ISO strings, which is what the frontend's
    parseISO expects and what the column would have produced anyway.
    """
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, (list, tuple)):
        return [jsonable(v) for v in value]
    if isinstance(value, dict):
        return {str(k): jsonable(v) for k, v in value.items()}
    return str(value)


def snapshot(obj: Any, names) -> dict[str, Any]:
    """The current value of each named attribute, JSON-safe, for later comparison."""
    return {name: jsonable(getattr(obj, name, None)) for name in names}


def _moved(before: Any, after: Any) -> bool:
    """
    Did this value actually change?

    None and '' are treated as the same absence. A form that clears a text box
    sends '' where the column held NULL, and reporting that as a change would
    fill the timeline with edits nobody made.
    """
    if before in (None, "") and after in (None, ""):
        return False
    return before != after


def diff(before: dict[str, Any], after: dict[str, Any]) -> list[dict[str, Any]]:
    """
    Before/after pairs for every field that moved, sorted by field name.

    Keys absent from `after` are not reported as deletions: `after` is built
    from the same name list as `before`, so an absent key means the attribute
    could not be read, not that the value was removed.
    """
    changes = []
    for name, old in before.items():
        if name in IGNORED or name not in after:
            continue
        new = after[name]
        if _moved(old, new):
            changes.append({"field": name, "from": old, "to": new})
    return sorted(changes, key=lambda c: c["field"])


def custom_field_diff(
    before: dict[str, Any] | None, after: dict[str, Any] | None
) -> list[dict[str, Any]]:
    """
    The same, for the custom_fields JSONB — Administration-created fields and
    every per-stage value (`on_hold_reason__s3` and friends).

    Keys are compared over the UNION of both sides, unlike `diff` above: a
    custom field genuinely can appear for the first time in a write, because
    the key only exists once somebody fills it in.
    """
    old_map = before or {}
    new_map = after or {}
    changes = []
    for name in sorted(set(old_map) | set(new_map)):
        if name in IGNORED:
            continue
        old = jsonable(old_map.get(name))
        new = jsonable(new_map.get(name))
        if _moved(old, new):
            changes.append({"field": name, "from": old, "to": new})
    return changes


def child_snapshot(rows: Any, columns: tuple[str, ...]) -> list[dict[str, Any]]:
    """
    A child list's rows, in order, as plain comparable values.

    Row order is part of the value: the register's child lists are ordered
    (`row_order`), and reordering the payment milestones IS a change to the
    schedule even when every row keeps its contents.
    """
    return [{name: jsonable(getattr(row, name, None)) for name in columns} for row in rows or []]


def list_change(field: str) -> dict[str, Any]:
    """A child list was rewritten. See the module docstring for why it is not diffed."""
    return {"field": field, "kind": "list"}


def list_changes(
    before: dict[str, list[dict[str, Any]]], after: dict[str, list[dict[str, Any]]]
) -> list[dict[str, Any]]:
    """
    An entry for each child list whose ROWS actually moved.

    This used to report any list merely PRESENT in the request, which is not the
    same thing and was wrong in the most visible possible way: the record editor
    PUTs a whole section, child lists included, so opening a Stage 1 lead and
    editing one unrelated text box logged "Demo Attendees updated" every single
    time. The History tab filled with changes nobody had made, which is worse
    than showing nothing — a trail that cries wolf stops being read.

    Compared rather than trusted, exactly like the scalar diff above.
    """
    return [
        list_change(name)
        for name in sorted(before)
        if name in after and before[name] != after[name]
    ]
