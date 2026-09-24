"""
Carry-forward: seeding a new record's opening values from its parent.

    Opportunity                    Deal created                Deal afterwards
    one_time_revenue = 10 Cr  ->   one_time_revenue = 10 Cr -> may become 8.5 Cr

THE RULE, IN ONE SENTENCE
-------------------------
A placement with value_mode='carry_forward' is given its parent's value ONCE,
when the record is created, and the record owns it from then on.

That makes it the third of exactly three things a value can do, and the two it
is not are what define it:

    own            starts empty. Nothing is inherited, ever.
    read_through   never stored here at all; resolved from the parent on every
                   read, so it cannot drift and cannot be edited.
    carry_forward  stored here, seeded once. It CAN drift, and that is the
                   point — a Deal may renegotiate the number it was handed.

WHY THIS FILE EXISTS AT ALL (D5)
---------------------------------
Because metadata that describes behaviour nothing performs is worse than no
metadata: it reads as a guarantee and is a decoration. Before this, the
behaviour was hard-coded in the frontend — src/lib/spec/pipelineSeed.ts and the
convert dialogs copied EVERY key except the read-through ones — and nothing in
the register could say that a Deal inherits its ARR but not its stage. Now the
placement says it and this executes it.

WHERE THE VALUE COMES FROM
--------------------------
Not "the parent record", but the nearest ancestor that actually HOLDS the
value — app/metadata_resolver.py::value_source walks past a read-through
ancestor, because a read-through ancestor is not holding anything either.
end_client on a Deal therefore carries from the LEAD, not from the Opportunity
that merely reads it through. Getting this wrong would copy a blank.

WHAT IT WILL NOT DO
-------------------
It never overwrites a value the caller supplied. A conversion that explicitly
sets one_time_revenue means it; carry-forward fills what was left unsaid, which
is what "opening value" means. And it never touches a locked placement after
creation — value_locked is enforced on write, not here.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import inspect as sa_inspect
from sqlalchemy.orm import Session

from .metadata_resolver import carry_forward_plan, placements_of, value_source
from .changes import diff, snapshot
from .models import FieldPlacement

# Which business model and id column each pipeline module is stored in. Needed
# because the value being carried lives on a different table from the record
# being created, and the module key is what the metadata speaks in.
#
# Declared rather than derived: mapping a module key to an ORM class is a fact
# about this codebase's Python, not about the register, and there is no row
# anywhere that could tell us `deals` means `Deal`.
_TABLES: dict[str, tuple[str, str]] = {
    "leads": ("Lead", "lead_id"),
    "opportunities": ("Opportunity", "opportunity_id"),
    "deals": ("Deal", "deal_id"),
}


def attribute_for(model, api_name: str) -> str | None:
    """
    The ORM attribute holding an api_name's column, or None if there is none.

    NOT the same string. Two register api_names are not valid Python
    identifiers — `3rd_party_one_time` and `3rd_party_recurring_per_year` both
    lead with a digit — so their ORM attributes are third_party_one_time and
    third_party_recurring_per_year, with the real column name given explicitly
    to mapped_column(). The metadata speaks api_names; the model speaks
    attributes; this is the translation.

    Resolved through the mapper rather than by a naming rule, because a naming
    rule would be a second place the exception is written down. The mapper
    already knows which attribute owns which column.

    Getting this wrong is silent: setattr(deal, "3rd_party_one_time", 1000)
    succeeds, sets an attribute SQLAlchemy does not track, and the value is
    never written. A carried value would simply not arrive, with no error
    anywhere.
    """
    try:
        mapper = sa_inspect(model)
    except Exception:  # noqa: BLE001 - not a mapped class
        return None
    for prop in mapper.column_attrs:
        for column in prop.columns:
            if column.name == api_name or prop.key == api_name:
                return prop.key
    return None


def _model(module_key: str):
    from . import models

    entry = _TABLES.get(module_key)
    if entry is None:
        return None, None
    return getattr(models, entry[0], None), entry[1]


def effective_value(db: Session, module_key: str, record: Any, api_name: str) -> Any:
    """
    What a record's value for a field ACTUALLY is, following read-through.

    A record does not necessarily store its own answer. An Opportunity's
    end_client is read through to its Lead, so asking the Opportunity object
    for it returns nothing useful — the question has to be passed up the chain.

    Returns None when the chain is broken (no parent linked, or the parent row
    is gone). None is the honest answer: it means "nothing to carry", and the
    destination is left empty rather than filled with a guess.
    """
    if record is None:
        return None

    placements = placements_of(db, module_key)
    placement = placements.get(api_name)
    if placement is None:
        return None

    if placement.value_mode == "read_through":
        return _from_parent(db, module_key, record, api_name)

    if placement.storage == "custom_fields":
        return (getattr(record, "custom_fields", None) or {}).get(api_name)

    attribute = attribute_for(type(record), api_name)
    return getattr(record, attribute, None) if attribute else None


def parent_record(db: Session, module_key: str, record: Any) -> tuple[str | None, Any]:
    """
    (the module above this record, that record) — or (None, None).

    One link up, with ONE fallback: when the direct link is empty, the
    grandparent's link on this same record. A paid pilot's Deal has no
    Opportunity — it was created straight from its Lead — but it does carry
    parent_lead, the very link an Opportunity uses to name its Lead. Without
    the fallback everything a Deal shows "from the Lead" came back empty for
    those Deals; the list rows never had that gap, because app/revenue.py's
    root_lead_of already reads parent_lead first.
    """
    from .metadata_resolver import parent_of

    parent_module, parent_link = parent_of(db, module_key)
    if not parent_module or not parent_link:
        return None, None
    parent_id = getattr(record, parent_link, None)
    if not parent_id:
        grand_module, grand_link = parent_of(db, parent_module)
        grand_id = getattr(record, grand_link, None) if grand_link else None
        if not grand_module or not grand_id:
            return None, None
        parent_module, parent_id = grand_module, grand_id
    model, _ = _model(parent_module)
    if model is None:
        return None, None
    return parent_module, db.get(model, parent_id)


def _from_parent(db: Session, module_key: str, record: Any, api_name: str) -> Any:
    """Walk one link up and ask again."""
    parent_module, parent = parent_record(db, module_key, record)
    if parent is None:
        return None
    return effective_value(db, parent_module, parent, api_name)


def seed_values(
    db: Session,
    module_key: str,
    record: Any,
    *,
    supplied: set[str] | None = None,
) -> dict[str, Any]:
    """
    Fill a freshly created record's carry-forward fields from its ancestors.

    Call AFTER the caller's own values are applied and the parent link is set,
    and before the commit. Returns what it wrote, so a caller can log it or a
    test can assert on it.

    `supplied` is the set of api_names the request actually sent. Anything in
    it is left alone: an explicit value is a decision, and overwriting it with
    an inherited one would silently discard what the user typed.

    A field whose ancestor value is None is skipped rather than written as
    NULL — writing NULL is indistinguishable from carrying an empty value, and
    it would stamp "carried" onto a field that inherited nothing.
    """
    supplied = supplied or set()
    plan = carry_forward_plan(db, module_key)
    if not plan:
        return {}

    placements = placements_of(db, module_key)
    written: dict[str, Any] = {}
    custom: dict[str, Any] = {}

    for api_name, (source_module, source_api) in plan.items():
        # `supplied` arrives in the CALLER's vocabulary — Pydantic field names,
        # which are ORM attribute names — while the plan is in api_names. They
        # differ for the two fields whose api_name is not a valid identifier,
        # so both spellings are checked. Missing this would let an explicitly
        # sent 3rd-party figure be silently overwritten by the inherited one.
        attribute = attribute_for(type(record), api_name)
        if api_name in supplied or (attribute and attribute in supplied):
            continue

        value = _walk_to_source(db, module_key, record, source_api, source_module)
        if value is None:
            continue

        placement = placements[api_name]
        if placement.storage == "custom_fields":
            custom[api_name] = value
        else:
            if attribute is None:
                # The placement claims a typed column the business table does
                # not have yet — a known Round-7 gap, reported by the rebuild.
                # Skip rather than crash: the metadata is ahead of the table,
                # which is not this function's problem to solve, and certainly
                # not one to solve with DDL.
                continue
            setattr(record, attribute, value)
        written[api_name] = value

    if custom:
        # Reassigned, not mutated: SQLAlchemy does not track mutation inside a
        # plain JSONB dict, so an in-place update is silently lost.
        record.custom_fields = {**(getattr(record, "custom_fields", None) or {}), **custom}

    return written


def _walk_to_source(
    db: Session,
    module_key: str,
    record: Any,
    api_name: str,
    source_module: str,
) -> Any:
    """Follow parent links from `record` up to `source_module` and read there."""
    current_module, current = module_key, record
    while current_module != source_module:
        parent_module, parent = parent_record(db, current_module, current)
        if parent is None:
            return None
        current_module, current = parent_module, parent
    return effective_value(db, source_module, current, api_name)


#: Named transforms a mapping row may carry. Named so the screen can say what
#: happens, rather than a formula nobody can read.
TRANSFORMS = {
    "paid_poc_name": lambda value: f"{value} — Paid POC" if value else value,
}


def apply_mapping(db: Session, path: str, source: Any, target: Any) -> list[str]:
    """
    Copy one conversion path's rows from `source` onto a new `target`.

    For the paid pilot's Deal, whose source is the Lead itself: every row's
    source module is `leads`. Returns the target api_names written. The rows
    are locked (decided 24 Sep 2026, G2), so this copies exactly what it
    copied when the rule lived in code: Pilot Fee, the PO date, the name and
    Customer (Partner / SI).
    """
    from .metadata_resolver import conversion_rows

    written: list[str] = []
    for row in conversion_rows(db, path):
        value = effective_value(db, row.source_module, source, row.source_api_name)
        if row.transform:
            value = TRANSFORMS[row.transform](value)
        attribute = attribute_for(type(target), row.target_api_name)
        if attribute is None or value is None:
            continue
        setattr(target, attribute, value)
        written.append(row.target_api_name)
    return written


def locked_violations(
    db: Session, module_key: str, record: Any, before: dict[str, Any]
) -> list[FieldPlacement]:
    """
    Placements whose value THIS WRITE ACTUALLY CHANGED, but which may not change.

    Two kinds of placement are frozen once a record has them:

        value_locked      a carried value the record was given and may not move.
                          Carry-forward only — ck_field_placements_value_locked.
        editable = false  an own value the register marks not editable, e.g. a
                          Deal's Contract Value: set at conversion, never typed.

    Decided 16 Sep 2026: no commercial value changes after Commercial
    Evaluation, which reverses D1/D3's "a Deal may renegotiate what it
    inherits". Contract changes belong in Contract Variations (phase 2), not in
    editing the booked figures.

    COMPARED BY VALUE, after the payload is applied. This used to refuse any
    locked name merely PRESENT in the request — and every form save sends its
    whole section, so switching the lock on would have refused every save of
    that section, including the ones that changed nothing about the locked
    value. Re-sending an unchanged value is never a violation now.

    System fields (stamped by the server) and read-through fields (stored
    nowhere) are both editable=false and are neither of this rule's business.

    Call AFTER the scalars are applied and BEFORE commit. `before` is the
    router's own snapshot of the attributes the request sent; raising then
    writes nothing, because the session is never committed.
    """
    moved = {change["field"] for change in diff(before, snapshot(record, list(before)))}
    if not moved:
        return []

    frozen = []
    for api_name, placement in placements_of(db, module_key).items():
        attribute = attribute_for(type(record), api_name) or api_name
        if attribute not in moved:
            continue
        if placement.value_locked:
            frozen.append(placement)
        elif (
            placement.editable is False
            and placement.value_mode != "read_through"
            and placement.requirement != "System"
        ):
            frozen.append(placement)
    return frozen
