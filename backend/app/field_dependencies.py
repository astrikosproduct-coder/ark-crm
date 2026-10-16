"""
Fields whose choices depend on another field — Region -> Country -> State.

Release 1.1 (decided 6 Oct 2026), Zoho's Map Dependency Fields: on a module, a
child picklist offers only the choices mapped to the value its parent holds.
Choose MEA and Country offers the MEA countries; choose UAE and State offers
the seven emirates. The maps are register metadata (field_dependencies), read
here from the PUBLISHED version, like the required-field check reads it.

Two rules, and the form follows the same two (src/lib/spec/dependencies.ts):

  offers_choices   a child with nothing to offer is never demanded: no Country
                   chosen yet, or a Country with no States. That is what makes
                   a Lead's State "required when the Country has states".
  check_choices    a save may not hold a child choice its parent does not
                   offer — a State outside its Country, a Country chosen with
                   no Region. Refused as DEPENDENT_CHOICE, naming the field.
                   Import goes through the same create logic, so a sheet row is
                   refused the same way.

A record saved before the map existed may hold a pair the map refuses — a Lead
whose free-text Country did not convert. Such a pair is refused only when the
save CHANGES it, so an unrelated edit to that record still saves.

SEVERAL CHOICES (Release 1.2, 15 Oct 2026; first built for Products on
phase-2). An Account works in several Segments, so its Segment -> Segment
Category -> Subsegment are multi-choice. The rules are the same two, read for a
list: a child offers the choices of EVERY parent choice held, and each child
choice must be one of them. `allowed` is the one place that is worked out; the
form's twin is allowedChoices.
"""

from __future__ import annotations

from typing import Any, Callable

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from .live_register import Published, published
from .messages import refusal

DEPENDENT_CHOICE = "DEPENDENT_CHOICE"


def _blank(value: Any) -> bool:
    return value is None or value == "" or value == []


def _value(record: Any, name: str) -> Any:
    """A column if the record has one, else its custom_fields value."""
    if hasattr(type(record), name):
        return getattr(record, name, None)
    return (getattr(record, "custom_fields", None) or {}).get(name)


def dependency(register: Published | None, module: str, child: str) -> dict[str, Any] | None:
    if register is None:
        return None
    return register.dependencies.get(module, {}).get(child)


def _choices(value: Any) -> list[str]:
    """A field's value as the choices it holds: one, several, or none."""
    if _blank(value):
        return []
    if isinstance(value, (list, tuple, set)):
        return [str(v) for v in value if not _blank(v)]
    return [str(value)]


def allowed(dep: dict[str, Any], parent_value: Any) -> list[str]:
    """The child choices on offer for what the parent holds — every choice of
    every parent choice, once each."""
    out: list[str] = []
    for parent in _choices(parent_value):
        for choice in dep["map"].get(parent, []):
            if choice not in out:
                out.append(choice)
    return out


def offers_choices(register: Published | None, module: str, child: str, value_of: Callable[[str], Any]) -> bool:
    """Does this field have anything to choose from, given its parent's value?

    True for a field no dependency governs. False when its parent is empty or
    maps to nothing — such a field is never demanded.
    """
    dep = dependency(register, module, child)
    if dep is None:
        return True
    return bool(allowed(dep, value_of(dep["parent"])))


def _label(register: Published, module: str, name: str) -> str:
    for f in register.fields_of(module):
        if f["api_name"] == name:
            return f.get("label") or name
    return name


def check_choices(db: Session, module: str, record: Any, *, record_id: str | None, creating: bool) -> None:
    """Refuse a child choice its parent does not offer. Call after values are applied."""
    register = published(db)
    deps = register.dependencies.get(module, {}) if register else {}
    if not deps:
        return

    saved = None
    if not creating and record_id:
        from .database import SessionLocal  # local: this module stays free of the engine at import

        with SessionLocal() as saved_db:
            row = saved_db.get(type(record), record_id)
            if row is not None:
                saved = {name: _value(row, name) for dep_child, dep in deps.items() for name in (dep_child, dep["parent"])}

    for child, dep in deps.items():
        child_value = _value(record, child)
        if _blank(child_value):
            continue
        parent_value = _value(record, dep["parent"])
        if saved is not None and (saved.get(child), saved.get(dep["parent"])) == (child_value, parent_value):
            continue  # unchanged by this save — see the module docstring
        child_label = _label(register, module, child)
        parent_label = _label(register, module, dep["parent"])
        on_offer = allowed(dep, parent_value)
        if _blank(parent_value):
            message = f"Choose a {parent_label} before the {child_label}."
            details = [f"The {child_label} list follows the {parent_label} chosen."]
        elif any(choice not in on_offer for choice in _choices(child_value)):
            message = f"That {child_label} isn't in the {parent_label} chosen."
            details = [f"Choose the {child_label} again from the list for that {parent_label}."]
        else:
            continue
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            refusal(
                DEPENDENT_CHOICE,
                message,
                details,
                fields=[{"api_name": child, "label": child_label, "parent": dep["parent"]}],
            ),
        )
