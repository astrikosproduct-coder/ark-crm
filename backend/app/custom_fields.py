"""
Values for Administration-created fields: the read and write half of the
`custom_fields` JSONB store.

    Admin creates a field   -> field_metadata row, storage='custom_fields'
    User enters a value     -> business_table.custom_fields['<api_name>']
    No ALTER TABLE, ever.

Register fields are not involved. They have typed columns, keep them, and are
written by each router's own *_SCALARS loop exactly as before. This module only
ever touches keys that field_metadata explicitly marks as custom-stored.

THE RULE THAT MAKES THIS SAFE
------------------------------
A key is written to custom_fields only if field_metadata says so — an ACTIVE
row, for this table's module, with storage='custom_fields'. Anything else is
ignored on a flat payload, and rejected outright when the caller used the
explicit `custom_fields` object.

The failure this prevents is specific: without it, "the API did not recognise
this key" becomes "so it must be a custom field", and a typo (`rfp_documnet`)
becomes a permanent JSON key holding a value nobody will ever see on a form
again. Unknown keys are not data.

THE SECOND KIND OF KEY: PER-STAGE VALUES
-----------------------------------------
`<api_name>__s<stage>` — `on_hold_reason__s3`, `probability_pct__s1`.

Some fields are answered once per STAGE rather than once per record, because
one value per record cannot express what the pipeline actually does: a lead put
on hold at Stage 1 and again at Stage 3 has two different reasons, and the
probability it was given at Demo is not the probability it has at Close. The
frontend has recorded these under a suffixed key since the mechanism was built
(see frontend/src/lib/stageScope.ts).

The register has no column for them and is never going to: adding
`on_hold_reason__s0` … `__s9` as twenty columns per field is not a schema, it is
a spreadsheet. So they live in the same JSONB store, which is exactly what a
JSONB store is for — a value the register cannot type.

THEY WERE BEING SILENTLY DROPPED. Leads, Opportunities and Deals all moved onto
PostgreSQL, and from that moment every per-stage value a user typed went into a
PUT, failed the `key in defs` test below, and was discarded without an error.
The box kept its value until the page was reloaded and then it was simply gone.
This is the fix, and it is the same rule as above rather than an exception to
it: a per-stage key is accepted only when its BASE NAME is an active placement
on this module. `on_hold_reason__s3` is storable because `on_hold_reason` is a
field; `rfp_documnet__s3` is not, and neither is `on_hold_reason__sx`.
"""

from __future__ import annotations

import re
from typing import Any, Iterable

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from .metadata_resolver import module_field_names, placements_of
from .models import FieldPlacement

# `<api_name>__s<stage>`. Anchored at both ends, digits only for the stage, so
# `notes__something` is not mistaken for a per-stage value.
STAGE_SCOPED_KEY = re.compile(r"^(?P<base>[A-Za-z0-9_]+)__s(?P<stage>\d+)$")


def stage_scoped_base(key: str) -> str | None:
    """The api_name a per-stage key belongs to, or None if it is not one."""
    match = STAGE_SCOPED_KEY.match(key)
    return match.group("base") if match else None


def custom_field_defs(
    db: Session, table: str, *, include_deleted: bool = False
) -> dict[str, FieldPlacement]:
    """
    The admin-created fields whose values belong on `table`, keyed by api_name.

    ONE QUERY, NO INFERENCE: the placements on this module that say their values
    live in custom_fields. A placement's module_key IS the business table, so
    there is nothing left to work out.

    This used to walk the module parent chain — source_modules_for() — to decide
    that "opportunities may also take fields from leads". That walk existed only
    because placement was computed in the browser and the backend had to
    reconstruct the answer: an admin adding a field to a Stage 5 section created
    a `leads` row that rendered on the Opportunity form. It was right, and it was
    right for a reason nothing in the database recorded.

    It is also now MORE accurate, not just simpler. The old chain returned every
    custom field on `leads` for a query about `opportunities`, including ones
    that render only on Leads — a Stage 0 field would have been writable on an
    Opportunity that never shows it. A placement query cannot make that mistake.

    Active only unless asked otherwise. A deleted field is excluded from writes —
    nobody can enter a value for a field that is not on a form — while its
    already-stored values stay exactly where they are.
    """
    return placements_of(
        db, table, storage="custom_fields", include_deleted=include_deleted
    )


def resolve_write(
    db: Session,
    table: str,
    *,
    explicit: dict[str, Any] | None,
    extras: dict[str, Any] | None,
) -> dict[str, Any]:
    """
    The custom-field values a request is asking to write.

    Two ways a caller can send them, and they are treated differently on
    purpose:

    `explicit` — a `custom_fields` object in the body. The caller is asserting
        that every key in it is an admin-created field, so a key that is not one
        is an error (422) rather than something to quietly drop. This is the
        form new code should use.

    `extras` — keys sitting flat alongside the register fields, which is what
        the prototype's form engine already sends (`toPayload` returns one flat
        object). Only keys that field_metadata marks custom-stored are taken;
        everything else is ignored, exactly as it is today. It has to be
        ignored rather than rejected, because that same flat payload also
        carries `id`, `__labels` and computed values that were never fields.

    Per-stage keys (`<api_name>__s<stage>`) are accepted through either route,
    on the same terms: the BASE name must be an active placement on this module.
    See the module docstring for why they belong here and what breaks without it.

    Returns only the keys that should be written. An empty dict means the
    request asked for no custom-field change at all — which is not the same as
    asking to clear them, and the caller must not treat it as such.
    """
    defs = custom_field_defs(db, table)
    # Lazily, because most requests carry no per-stage key and this is one more
    # query on the hot save path.
    live: set[str] | None = None

    def storable(key: str) -> bool:
        nonlocal live
        if key in defs:
            return True
        base = stage_scoped_base(key)
        if base is None:
            return False
        if live is None:
            live = module_field_names(db, table)
        return base in live

    out: dict[str, Any] = {}

    if explicit:
        unknown = [key for key in explicit if not storable(key)]
        if unknown:
            deleted = custom_field_defs(db, table, include_deleted=True)
            hints = []
            for key in unknown:
                base = stage_scoped_base(key)
                if key in deleted:
                    hints.append(f"{key!r} is a deleted field — restore it first")
                elif base is not None:
                    hints.append(
                        f"{key!r} records a per-stage value for {base!r}, which "
                        f"is not a field on {table}"
                    )
                else:
                    hints.append(f"{key!r} is not a field on {table}")
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                {
                    "message": (
                        "custom_fields may only carry fields created through "
                        "Administration, or a per-stage value of a field this "
                        "module has. Nothing was written."
                    ),
                    "rejected": hints,
                },
            )
        out.update(explicit)

    for key, value in (extras or {}).items():
        if storable(key):
            out[key] = value

    return out


def apply_write(record: Any, values: dict[str, Any]) -> None:
    """
    Merge values into a record's custom_fields.

    A MERGE, not a replacement: a PATCH carrying one admin field must not blank
    the others, the same rule every router's *_SCALARS loop already follows for
    typed columns.

    Reassigned rather than mutated in place, because SQLAlchemy does not track
    mutation inside a plain JSONB dict — updating the dict without rebinding the
    attribute leaves the change uncommitted and silently lost.
    """
    if not values:
        return
    record.custom_fields = {**(record.custom_fields or {}), **values}


def merge_into_row(row: dict[str, Any], record: Any) -> dict[str, Any]:
    """
    Put a record's custom-field values into the flat dict the API returns.

    Flat, because that is the shape the form engine reads: it looks up
    `values[field.api_name]` and knows nothing about where the value was stored.
    An admin-created field therefore reads back exactly like a register one.

    A stored key NEVER overwrites a typed column already in the row. That
    protects register fields from a custom field that happens to share a name —
    the typed column is the register's, and it wins.

    Values for DELETED fields are returned too. They render nowhere, because the
    frontend only knows the fields in the published fields.json; carrying them
    is what makes a restore show the old value immediately instead of needing
    the record to be saved again.
    """
    for key, value in (getattr(record, "custom_fields", None) or {}).items():
        if key not in row:
            row[key] = value
    return row


def extras_of(payload: Any) -> dict[str, Any]:
    """
    The keys a request sent that the Pydantic model does not declare.

    The Create/Update schemas allow extras so that the form engine's flat
    payload survives; resolve_write is what decides which of them are real.
    """
    return dict(getattr(payload, "model_extra", None) or {})


def sent_names(payload: Any, declared: Iterable[str]) -> set[str]:
    """
    Field names the caller actually sent, restricted to declared model fields.

    Routers use `set(payload.model_dump(exclude_unset=True))` to decide what to
    write. With extras allowed that set now also contains undeclared keys, which
    must never be handed to setattr — this keeps the old meaning.
    """
    sent = set(payload.model_dump(exclude_unset=True))
    return sent & set(declared)
