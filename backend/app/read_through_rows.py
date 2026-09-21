"""
Read-through identity on LIST rows — Opportunities and Deals.

An Opportunity stores none of its identity: opportunity_name, end_client, the
owners, segment and 20-odd more are `value_mode='read_through'` placements,
resolved from the Lead at the root of the chain (models.py, VALUE_MODES). The
record page resolves them in the browser. A list could not: the server filters,
searches and sorts over the row it serialised, and that row had no End Client
and no owner — so "Opportunities owned by Sara" matched nothing, and every
list cell fetched its parent Lead separately.

This copies each read-through value from the root Lead's own serialised row
onto the list row, with its lookup label. Only on the LIST endpoints: a record
read stays exactly what the record stores, so nothing here can be mistaken for
an editable value and written back.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import FieldPlacement, Lead
from .revenue import revenue_context, root_lead_of


def read_through_names(db: Session, module: str) -> list[str]:
    return sorted(
        set(
            db.scalars(
                select(FieldPlacement.api_name).where(
                    FieldPlacement.module_key == module,
                    FieldPlacement.value_mode == "read_through",
                    FieldPlacement.status == "active",
                )
            )
        )
    )


def attach_read_through(db: Session, module: str, pairs: list[tuple[Any, dict]]) -> None:
    """Fill each row's read-through fields from its root Lead. Own values are never overwritten."""
    names = read_through_names(db, module)
    if not names or not pairs:
        return

    from .routers.leads import _label_maps as lead_label_maps
    from .routers.leads import _serialise as serialise_lead

    ctx = revenue_context(db)
    roots = {root_lead_of(ctx, module, record) for record, _ in pairs} - {None}
    if not roots:
        return
    labels = lead_label_maps(db)
    lead_rows = {lead.lead_id: serialise_lead(lead, labels) for lead in db.scalars(select(Lead).where(Lead.lead_id.in_(roots)))}

    for record, row in pairs:
        source = lead_rows.get(root_lead_of(ctx, module, record) or "")
        if source is None:
            continue
        source_labels = source.get("__labels") or {}
        for name in names:
            if row.get(name) not in (None, "", []):
                continue
            if name in source:
                row[name] = source[name]
            if name in source_labels:
                row.setdefault("__labels", {})[name] = source_labels[name]
