"""
THE authoritative resolution model.

One question, one answer, one place:

    "Which fields does module X have, and how does each one's value behave?"

    -> SELECT ... FROM field_placements
       JOIN field_definitions ... WHERE module_key = X AND status = 'active'

That is the whole resolver. There is no projection here, and there must never
be one: placement is a row, decided in Administration and stored, not derived
at read time from capture stages and section names.

WHAT THIS REPLACED
------------------
src/lib/spec/moduleSplit.ts re-homed a Stage 5 Leads field onto Opportunities,
added the shared / own-instance / read-through copies, relabelled them and
renumbered the sections — 377 lines of projection, running in the browser,
reading a hand-authored JSON that nothing verified. The backend's share of the
same knowledge was app/module_split.py::source_modules_for(), a parent-chain
walk whose only job was to reverse-engineer what the browser had decided.

Both are gone. Administration and the CRM now read the same rows, so the screen
an administrator uses cannot disagree with the screen a user sees: there is
only one table for them to disagree from.

WHAT IS STILL DERIVED, AND WHY THAT IS DIFFERENT
-------------------------------------------------
Two things are computed here rather than stored, because storing them would
duplicate a fact `modules` already owns and duplicated facts drift:

    the parent chain          modules.parent_module / parent_link
    a carried value's SOURCE  the nearest ancestor that owns the value

Neither decides WHERE a field appears. They answer "where does this placement's
value come from", which is a different question with a single existing source.
"""

from __future__ import annotations

from typing import Any, Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import FieldDefinition, FieldPlacement, Module, Section

# The keys spec/fields.json carries for every field, in the order build_spec.py
# wrote them. Unchanged from the register's own 24 — a regenerated file is still
# indistinguishable from a workbook-generated one at this level.
#
# `module`, `section` and `order` now come from the PLACEMENT rather than from
# the definition, which is the entire point: one_time_revenue is `STAGE 4 — RFP
# / RFI` #23 on Opportunities and `ON CONVERSION` #15 on Deals, and there was
# never one answer for it to have.
FIELD_JSON_KEYS: tuple[str, ...] = (
    "module",
    "section",
    "order",
    "api_name",
    "label",
    "type",
    "max_length",
    "picklist",
    "lookup_target",
    "lookup_filter",
    "values_note",
    "capture_stage",
    "capture_any_stage",
    "mandatory_from",
    "blocks_transition",
    "requirement",
    "origin",
    "source_ref",
    "description",
    "use_case",
    "required_on_skip",
    "required_on_create",
    "visibility_condition",
    "condition",
    "computed_formula",
)

# Keys the frontend needs that the register never had. They used to be computed
# by moduleSplit.ts at load time; they are read off the placement now.
#
#   value_mode          own | read_through | carry_forward
#   value_locked        may a carried value diverge afterwards
#   editable            read-only on this module
#   read_through_from   the module the value resolves from   (read_through only)
#   read_through_via    the lookup on THIS record holding that record's id
#   register_module     which sheet the concept was filed on, so that sidecar
#                       keys written as `leads.rfp_received_date` still resolve
#                       after the field's placement moved to Opportunities
#   register_order      that sheet's own numbering, for Spec Health
#   anchor_field        the api_name this placement draws NEXT TO, or null for
#                       "draw in my own section, in sort_order". Section says
#                       what kind of field it is; this says where it goes.
#   anchor_position     'after' | 'beside', null when there is no anchor
#   layout_span         'full' | 'half' | null for the field type's own width
#   stage_scoped        'none' | 'carry_forward' | 'sticky' — one value per
#                       record, or one per stage under `<api_name>__s<n>`
#   computed_expr       the expression the engine evaluates, as distinct from
#                       computed_formula, which is the register's English
#                       sentence about the same rule and is shown beside it
#   min_value           inclusive bounds on a number field (0023), null when
#   max_value           unbounded on that side
RESOLVED_KEYS: tuple[str, ...] = (
    "value_mode",
    "value_locked",
    "editable",
    "read_through_from",
    "read_through_via",
    "register_module",
    "register_order",
    "anchor_field",
    "anchor_position",
    "layout_span",
    "stage_scoped",
    "computed_expr",
    "min_value",
    "max_value",
)


# ------------------------------------------------------------ structure


def parent_chain(db: Session, module_key: str) -> list[str]:
    """
    Ancestors of a pipeline module, nearest first. Deals -> [opportunities, leads].

    Read off modules.parent_module, which is where module parentage is written
    down. Cycle-guarded rather than trusted: a self-referential parent would
    otherwise hang every record load rather than failing.
    """
    chain: list[str] = []
    seen = {module_key}
    current = module_key
    while True:
        module = db.get(Module, current)
        if module is None or not module.parent_module:
            return chain
        if module.parent_module in seen:
            return chain
        chain.append(module.parent_module)
        seen.add(module.parent_module)
        current = module.parent_module


def parent_of(db: Session, module_key: str) -> tuple[str | None, str | None]:
    """(parent module, the lookup field on this record holding its id)."""
    module = db.get(Module, module_key)
    if module is None:
        return (None, None)
    return (module.parent_module, module.parent_link)


def value_source(db: Session, module_key: str, api_name: str) -> str | None:
    """
    Which module a read-through or carried value actually comes from.

    Walks the parent chain to the nearest ancestor that HOLDS the value — one
    whose placement is `own` or `carry_forward`. A read-through ancestor is
    skipped rather than treated as the source, because it does not hold
    anything either: a Deal reading End Client through Opportunities, which
    itself reads it through Leads, gets the value from LEADS.

    Not stored on the placement, because it is entirely determined by the
    parent chain plus the modes, both of which are already rows. Storing it
    would be a second copy of a fact that can only ever be answered one way.
    """
    for ancestor in parent_chain(db, module_key):
        placement = db.scalar(
            select(FieldPlacement).where(
                FieldPlacement.module_key == ancestor,
                FieldPlacement.api_name == api_name,
                FieldPlacement.status == "active",
            )
        )
        if placement is not None and placement.value_mode in ("own", "carry_forward"):
            return ancestor
    return None


# ------------------------------------------------------------- resolving


def _rows(
    db: Session,
    module_key: str | None,
    *,
    status: str = "active",
) -> list[tuple[FieldPlacement, FieldDefinition, str]]:
    """Placements joined to their definition and section label, in form order."""
    query = (
        select(FieldPlacement, FieldDefinition, Section.label)
        .join(FieldDefinition, FieldDefinition.id == FieldPlacement.definition_id)
        .join(Section, Section.id == FieldPlacement.section_id)
    )
    if status != "all":
        # A placement is only live if its DEFINITION is live too. A definition
        # deleted everywhere leaves its placements deleted by cascade, so this
        # is belt and braces — but it is also what makes a half-applied cascade
        # fail closed rather than leaking a field back onto a form.
        query = query.where(
            FieldPlacement.status == status, FieldDefinition.status == status
        )
    if module_key:
        query = query.where(FieldPlacement.module_key == module_key)

    # Section order, then id, break a sort_order tie. Eleven active placements
    # share a sort_order with another (the HEADER key facts were numbered 10,
    # 20, 30… into modules already numbered 1, 2, 3…), and without a
    # tie-breaker PostgreSQL returned tied rows in whatever physical order an
    # UPDATE last left them — so two publishes of an unchanged register could
    # write different fields.json files, and even swap which section a module
    # draws first.
    return [
        (p, d, label)
        for p, d, label in db.execute(
            query.order_by(
                FieldPlacement.module_key,
                FieldPlacement.sort_order,
                Section.sort_order,
                FieldPlacement.id,
            )
        ).all()
    ]


def label_of(placement: FieldPlacement, definition: FieldDefinition) -> str:
    """
    What this module calls the field.

    The definition's label unless this placement overrides it. Five placements
    do: the register calls project_stage "Lead Stage", which is simply the
    wrong word on an Opportunity, and lead_status is "Deal Status" on a Deal.
    The api_name stays the same in every case, so one condition, one picklist
    and one seed normalisation still cover all three modules.
    """
    return placement.label_override or definition.label


def field_row(
    db: Session,
    placement: FieldPlacement,
    definition: FieldDefinition,
    section_label: str,
    *,
    source_cache: dict[tuple[str, str], str | None] | None = None,
) -> dict[str, Any]:
    """One resolved field, in the shape spec/fields.json carries."""
    if placement.value_mode == "read_through":
        cache_key = (placement.module_key, placement.api_name)
        if source_cache is not None and cache_key in source_cache:
            source = source_cache[cache_key]
        else:
            source = value_source(db, placement.module_key, placement.api_name)
            if source_cache is not None:
                source_cache[cache_key] = source
        _, via = parent_of(db, placement.module_key)
    else:
        source, via = None, None

    return {
        "module": placement.module_key,
        "section": section_label,
        "order": placement.sort_order,
        "api_name": placement.api_name,
        "label": label_of(placement, definition),
        "type": definition.field_type,
        "max_length": definition.max_length,
        "picklist": definition.picklist_key,
        "lookup_target": definition.lookup_target,
        "lookup_filter": definition.lookup_filter,
        "values_note": definition.values_note,
        "capture_stage": placement.capture_stage,
        "capture_any_stage": placement.capture_any_stage,
        "mandatory_from": placement.mandatory_from,
        "blocks_transition": placement.blocks_transition,
        "requirement": placement.requirement,
        "origin": definition.origin,
        "source_ref": definition.source_ref,
        "description": definition.description,
        "use_case": definition.use_case,
        "required_on_skip": placement.required_on_skip,
        "required_on_create": bool(placement.required_on_create),
        "visibility_condition": placement.visibility_condition,
        "condition": placement.condition,
        "computed_formula": definition.computed_formula,
        # ---- resolved keys, see RESOLVED_KEYS
        "value_mode": placement.value_mode,
        "value_locked": placement.value_locked,
        "editable": placement.editable,
        "read_through_from": source,
        "read_through_via": via,
        "register_module": definition.origin_module,
        "register_order": placement.sort_order,
        "anchor_field": placement.anchor_field,
        "anchor_position": placement.anchor_position,
        "layout_span": placement.layout_span,
        "min_value": definition.min_value,
        "max_value": definition.max_value,
        "stage_scoped": placement.stage_scoped,
        "computed_expr": definition.computed_expr,
    }


def resolved_fields(
    db: Session, module_key: str | None = None, *, status: str = "active"
) -> list[dict[str, Any]]:
    """
    Every field of a module — or of every module — as the frontend reads them.

    This is what Administration lists and what spec/fields.json is generated
    from. Both call it, which is what stops them disagreeing.
    """
    cache: dict[tuple[str, str], str | None] = {}
    return [
        field_row(db, p, d, label, source_cache=cache)
        for p, d, label in _rows(db, module_key, status=status)
    ]


def module_field_names(db: Session, module_key: str) -> set[str]:
    """The api_names a module has. Used to check that a condition can compile."""
    return set(
        db.scalars(
            select(FieldPlacement.api_name).where(
                FieldPlacement.module_key == module_key,
                FieldPlacement.status == "active",
            )
        )
    )


# ------------------------------------------------------- value behaviour


def placements_of(
    db: Session,
    module_key: str,
    *,
    value_mode: str | None = None,
    storage: str | None = None,
    include_deleted: bool = False,
) -> dict[str, FieldPlacement]:
    """
    A module's placements keyed by api_name, optionally filtered.

    The one query the custom-field writer and the carry-forward seeder both go
    through, so "which fields does this table have" has a single answer for
    reads, writes and forms alike.
    """
    query = select(FieldPlacement).where(FieldPlacement.module_key == module_key)
    if not include_deleted:
        query = query.where(FieldPlacement.status == "active")
    if value_mode:
        query = query.where(FieldPlacement.value_mode == value_mode)
    if storage:
        query = query.where(FieldPlacement.storage == storage)
    return {p.api_name: p for p in db.scalars(query)}


def carry_forward_plan(db: Session, module_key: str) -> dict[str, str]:
    """
    What a new record on this module inherits, and from where.

    api_name -> the module its opening value is copied from. Empty for Leads,
    which has no parent to inherit from.

    Called once when a record is created. See app/carry_forward.py, which is
    what actually copies the values — this only says what and from where, so
    the rule stays readable and testable without a record in hand.
    """
    plan: dict[str, str] = {}
    for api_name in placements_of(db, module_key, value_mode="carry_forward"):
        source = value_source(db, module_key, api_name)
        if source:
            plan[api_name] = source
    return plan


def read_through_plan(db: Session, module_key: str) -> dict[str, str]:
    """api_name -> the module its value is resolved from, every time it is read."""
    plan: dict[str, str] = {}
    for api_name in placements_of(db, module_key, value_mode="read_through"):
        source = value_source(db, module_key, api_name)
        if source:
            plan[api_name] = source
    return plan


def modules_of(db: Session, definition_id: int, *, include_deleted: bool = False) -> list[str]:
    """
    Every module a definition appears on.

    What Administration means by "Used in 3 modules", and what the rename
    dialog names before it changes a label everywhere.
    """
    query = select(FieldPlacement.module_key).where(
        FieldPlacement.definition_id == definition_id
    )
    if not include_deleted:
        query = query.where(FieldPlacement.status == "active")
    return sorted(db.scalars(query))


def definition_for(
    db: Session, module_key: str, api_name: str
) -> tuple[FieldDefinition | None, FieldPlacement | None]:
    """The canonical definition behind a field as one module sees it."""
    placement = db.scalar(
        select(FieldPlacement).where(
            FieldPlacement.module_key == module_key,
            FieldPlacement.api_name == api_name,
            FieldPlacement.status == "active",
        )
    )
    if placement is None:
        return (None, None)
    return (db.get(FieldDefinition, placement.definition_id), placement)


def iter_modules(db: Session) -> Iterable[Module]:
    return db.scalars(select(Module).order_by(Module.sort_order, Module.module_key))
