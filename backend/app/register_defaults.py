"""
A new record's starting values, from the published register.

Setup rebuild, 4d (5 Oct 2026). A Pick List field can carry a default value
(`field_placements.default_value`, migration 0042) — Zoho's "Select default
value". The create forms show it already chosen (lib/spec defaultValuesOf);
this fills the same value on the server for a record created any other way —
an import row, a Lead made from a deal registration or off a Deal — so the two
can never disagree. Before this, a new Lead's Currency was USD in two places
of code (LeadCreatePage and create_lead); it is a register default now, and
changing it in Setup and publishing changes both.

Only a blank is filled: a value the person or the import gave always wins. The
PUBLISHED register is read, never the draft, as everywhere at runtime.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from .live_register import published


def _blank(value: Any) -> bool:
    return value is None or (isinstance(value, str) and value.strip() == "")


def apply_defaults(db: Session, module: str, record: Any) -> None:
    """Fill each blank field of `record` that has a default on `module`."""
    register = published(db)
    if register is None:
        return
    columns = set(record.__table__.columns.keys())
    store = dict(getattr(record, "custom_fields", None) or {})
    changed = False
    for field in register.fields_of(module):
        default = field.get("default_value")
        if default is None or field.get("value_mode") == "read_through":
            continue
        name = field["api_name"]
        if name in columns and name != "custom_fields":
            if _blank(getattr(record, name)):
                setattr(record, name, default)
        elif _blank(store.get(name)):
            store[name] = default
            changed = True
    if changed:
        # Rebound, not mutated: SQLAlchemy does not see changes inside a dict.
        record.custom_fields = store
