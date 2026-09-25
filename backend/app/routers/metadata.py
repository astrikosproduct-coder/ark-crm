"""
The Administration metadata API — /api/admin/metadata/*.

Mounted under /api/admin deliberately, and not on a path of its own: managing
the register is administration, and it carries the same DEVELOPER-only gate
(app/auth.py::require_administration).

WHAT THE WRITE ENDPOINTS ARE EDITING
-------------------------------------
The live draft: the six metadata tables themselves. There is no separate draft
store and no draft copy of a row. An edit lands immediately, and it changes
nothing a user can see, because the CRM reads spec/*.json — which is only
rewritten by POST /publish. That is what makes "draft" real rather than
ceremonial: an admin can leave a half-finished change sitting for a week and
no screen moves until somebody publishes it.

THREE THINGS THIS API WILL NOT DO
----------------------------------
1. DROP a column, or touch one byte of business data. Deleting a field is
   status='deleted' and nothing else; the values stay exactly where they are
   and come back when the field is restored. See models.FieldDefinition.
2. Rename an api_name or a picklist value key. Both are the keys stored data is
   written under, so a rename in the metadata would orphan every existing value
   while looking like it worked. Labels are editable instead.
3. Modify a published version. Rollback republishes an old snapshot as a NEW
   version rather than rewinding history — see _guard_immutable.
"""

import re
from datetime import datetime, timezone

from fastapi import APIRouter, Body, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..database import get_db
from ..metadata_spec import (
    FIELD_TYPES,
    REQUIREMENTS,
    SPEC_DIR,
    build_snapshot,
    diff_snapshots,
    orphaned_sidecar_refs,
    restore_snapshot,
    spec_documents,
    validate_snapshot,
    write_spec_documents,
)
from .. import metadata_resolver
from ..messages import refusal
from ..models import (
    ANCHOR_POSITIONS,
    ConversionMapping,
    LAYOUT_SPANS,
    STAGE_SCOPED_MODES,
    STORAGE_MODES,
    VALUE_MODES,
    FieldDefinition,
    FieldPlacement,
    MetadataVersion,
    Module,
    Picklist,
    PicklistValue,
    Section,
    Stage,
    User,
)
from ..schemas_metadata import (
    ConversionMappingOut,
    DraftStatus,
    FieldCreate,
    FieldDetailOut,
    FieldOut,
    FieldUpdate,
    MetadataVersionDetail,
    MetadataVersionOut,
    ModuleCreate,
    ModuleOut,
    ModuleUpdate,
    PlacementCreate,
    PlacementUpdate,
    PicklistCreate,
    PicklistOut,
    PicklistReorderRequest,
    PicklistUpdate,
    PicklistValueCreate,
    PicklistValueOut,
    PicklistValueUpdate,
    PublishRequest,
    PublishResult,
    ReorderRequest,
    RequiredUpdate,
    RollbackRequest,
    SectionCreate,
    SectionOut,
    SectionUpdate,
    StageCreate,
    StageOut,
    StageUpdate,
    ValidationOut,
)

router = APIRouter(tags=["metadata"])


# ------------------------------------------------------------------ helpers


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _check_user(db: Session, user_id: str | None) -> str | None:
    """
    An acting user, if one was named, and only if it is real.

    There is no authentication, so the caller states who it is. An unknown id
    is rejected rather than stored: a wrong name in an audit column is worse
    than an empty one, because it reads as evidence.
    """
    if user_id is None:
        return None
    if db.get(User, user_id) is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"No user {user_id}")
    return user_id


def _next_sort_order(db: Session, model, filters) -> int:
    highest = db.scalar(select(func.max(model.sort_order)).where(*filters)) or 0
    return highest + 1


def _module_or_404(db: Session, module_key: str) -> Module:
    module = db.get(Module, module_key)
    if module is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"No module {module_key}")
    return module


def _section_or_404(db: Session, section_id: int) -> Section:
    section = db.get(Section, section_id)
    if section is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"No section {section_id}")
    return section


def _picklist_or_404(db: Session, picklist_key: str) -> Picklist:
    picklist = db.get(Picklist, picklist_key)
    if picklist is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"No picklist {picklist_key}")
    return picklist


def _value_or_404(db: Session, value_id: int) -> PicklistValue:
    value = db.get(PicklistValue, value_id)
    if value is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"No picklist value {value_id}")
    return value


def _stage_or_404(db: Session, stage: int) -> Stage:
    row = db.get(Stage, stage)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"No stage {stage}")
    return row


def _section_labels(db: Session) -> dict[int, str]:
    return {s.id: s.label for s in db.scalars(select(Section))}


def _validation_out(snapshot: dict) -> ValidationOut:
    result = validate_snapshot(snapshot)
    return ValidationOut(
        ok=result.ok,
        errors=result.errors,
        warnings=result.warnings,
        orphaned_sidecar_refs=orphaned_sidecar_refs(snapshot),
    )


STAGE_SECTION = re.compile(r"^STAGE (\d+)")

# Metadata v2 (24 Sep 2026): there is no shared scope any more. Every field is
# owned by exactly one module and is unique within it, as in Zoho — the shared
# `pipeline` namespace Leads, Opportunities and Deals had was dissolved by
# metadata_v2.py. A field may still be SHOWN on a descendant module, live
# "from the Lead" (value_mode='read_through'), but it is owned once.


def _stage_of_section(label: str) -> int | None:
    """
    The stage number a section name declares, or None.

    Matches `STAGE 4 — RFP / RFI` and deliberately NOT `STAGE DEFINITION
    (configuration)` or `STAGE CRITERIA (configuration)`, which are
    Administration sections describing stage config rather than pipeline stages.
    The digit is what separates them.
    """
    match = STAGE_SECTION.match(label or "")
    return int(match.group(1)) if match else None


def _derive_capture_stage(
    db: Session, section: Section, module_key: str, supplied: int | None
) -> int | None:
    """
    Fill in capture_stage from the section a field is being put in.

    Without this, a field created in `STAGE 4 — RFP / RFI` with the box left
    blank renders on NO screen: the stage tab selects by
    `capture_stage === stage`, and the Details tab excludes every STAGE section.
    The field looks correct in Administration and is invisible in the CRM, which
    is the worst kind of wrong.

    Only fills a blank, and only on a pipeline module. An explicitly supplied
    value is never overridden — if an admin means to disagree with the section,
    publish validation reports the disagreement rather than this quietly
    resolving it.

    Sound because the register agrees with itself: across all 133 rows in a
    numbered STAGE section, capture_stage equals the section number in every
    case.
    """
    if supplied is not None:
        return supplied
    module = db.get(Module, module_key)
    if module is None or not module.is_pipeline:
        return None
    return _stage_of_section(section.label)


def _guard_immutable(version: MetadataVersion) -> None:
    """
    A published version is a historical fact and facts are not edited.

    Nothing routes here today — no endpoint offers an update or a delete of a
    version — so this exists to make that a decision rather than an oversight,
    and to fail loudly if somebody adds one later.
    """
    if version.status == "published":
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Version {version.version_no} is published and immutable. "
            f"To go back to it, roll back — which republishes it as a new "
            f"version and leaves the history intact.",
        )


def _latest_version(db: Session) -> MetadataVersion | None:
    return db.scalar(
        select(MetadataVersion)
        .where(MetadataVersion.status == "published")
        .order_by(MetadataVersion.version_no.desc())
        .limit(1)
    )


# ------------------------------------------------------------------ modules


@router.get("/modules", response_model=list[ModuleOut])
def list_modules(
    include_inactive: bool = Query(default=True),
    include_hidden: bool = Query(default=False),
    db: Session = Depends(get_db),
):
    """
    Hidden modules (not built yet, or not modules at all) are left out unless
    asked for: Administration offers only what someone can act on. Metadata v2.
    """
    counts = dict(
        db.execute(
            select(FieldPlacement.module_key, func.count())
            .where(FieldPlacement.status == "active")
            .group_by(FieldPlacement.module_key)
        ).all()
    )
    deleted = dict(
        db.execute(
            select(FieldPlacement.module_key, func.count())
            .where(FieldPlacement.status == "deleted")
            .group_by(FieldPlacement.module_key)
        ).all()
    )
    sections = dict(
        db.execute(
            select(Section.module_key, func.count()).group_by(Section.module_key)
        ).all()
    )

    query = select(Module).order_by(Module.sort_order, Module.module_key)
    if not include_inactive:
        query = query.where(Module.active.is_(True))
    if not include_hidden:
        query = query.where(Module.hidden.is_(False))

    return [
        ModuleOut(
            module_key=m.module_key,
            label=m.label,
            sort_order=m.sort_order,
            active=m.active,
            hidden=m.hidden,
            setup_parent=m.setup_parent,
            field_count=counts.get(m.module_key, 0),
            deleted_field_count=deleted.get(m.module_key, 0),
            section_count=sections.get(m.module_key, 0),
        )
        for m in db.scalars(query)
    ]


@router.post("/modules", response_model=ModuleOut, status_code=status.HTTP_201_CREATED)
def create_module(payload: ModuleCreate, db: Session = Depends(get_db)):
    if db.get(Module, payload.module_key) is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT, f"Module {payload.module_key} already exists"
        )
    module = Module(
        module_key=payload.module_key,
        label=payload.label,
        sort_order=payload.sort_order
        if payload.sort_order is not None
        else _next_sort_order(db, Module, []),
        active=payload.active,
    )
    db.add(module)
    db.commit()
    db.refresh(module)
    return ModuleOut.model_validate(module)


@router.patch("/modules/{module_key}", response_model=ModuleOut)
def update_module(
    module_key: str, payload: ModuleUpdate, db: Session = Depends(get_db)
):
    """
    Label, order and active only.

    module_key is not editable: it is written into all 566 field rows, into
    every sidecar key in extensions.json, into list_views and into
    module_split.json. Renaming it here would leave every one of those pointing
    at a module that no longer exists.
    """
    module = _module_or_404(db, module_key)
    for name, value in payload.model_dump(exclude_unset=True).items():
        setattr(module, name, value)
    db.commit()
    db.refresh(module)
    return ModuleOut.model_validate(module)


# ----------------------------------------------------------------- sections


@router.get("/sections", response_model=list[SectionOut])
def list_sections(
    module: str | None = Query(default=None),
    db: Session = Depends(get_db),
):
    counts = dict(
        db.execute(
            select(FieldPlacement.section_id, func.count())
            .where(FieldPlacement.status == "active")
            .group_by(FieldPlacement.section_id)
        ).all()
    )
    deleted = dict(
        db.execute(
            select(FieldPlacement.section_id, func.count())
            .where(FieldPlacement.status == "deleted")
            .group_by(FieldPlacement.section_id)
        ).all()
    )

    query = select(Section).order_by(Section.module_key, Section.sort_order)
    if module:
        query = query.where(Section.module_key == module)

    return [
        SectionOut(
            id=s.id,
            module_key=s.module_key,
            label=s.label,
            sort_order=s.sort_order,
            active=s.active,
            field_count=counts.get(s.id, 0),
            deleted_field_count=deleted.get(s.id, 0),
        )
        for s in db.scalars(query)
    ]


@router.post("/sections", response_model=SectionOut, status_code=status.HTTP_201_CREATED)
def create_section(payload: SectionCreate, db: Session = Depends(get_db)):
    _module_or_404(db, payload.module_key)
    clash = db.scalar(
        select(Section).where(
            Section.module_key == payload.module_key, Section.label == payload.label
        )
    )
    if clash is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"{payload.module_key} already has a section called {payload.label!r}",
        )

    section = Section(
        module_key=payload.module_key,
        label=payload.label,
        sort_order=payload.sort_order
        if payload.sort_order is not None
        else _next_sort_order(db, Section, [Section.module_key == payload.module_key]),
        active=payload.active,
    )
    db.add(section)
    db.commit()
    db.refresh(section)
    return SectionOut.model_validate(section)


@router.patch("/sections/{section_id}", response_model=SectionOut)
def update_section(
    section_id: int, payload: SectionUpdate, db: Session = Depends(get_db)
):
    """
    Rename, reorder, activate/deactivate.

    A rename is safe here in a way that renaming an api_name is not: a section
    label is part of a field's qref, but a qref is derived at load time from
    whatever the section is currently called — no record stores it. The fields
    move with the section because they point at its id, not its name.

    A sidecar key written in the QUALIFIED form (module.SECTION.api_name) does
    name the label, so a rename can orphan one. That is reported by
    orphaned_sidecar_refs and shown before publish, rather than being prevented.
    """
    section = _section_or_404(db, section_id)
    data = payload.model_dump(exclude_unset=True)

    if "label" in data and data["label"] != section.label:
        clash = db.scalar(
            select(Section).where(
                Section.module_key == section.module_key,
                Section.label == data["label"],
                Section.id != section.id,
            )
        )
        if clash is not None:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                f"{section.module_key} already has a section called {data['label']!r}",
            )

    for name, value in data.items():
        setattr(section, name, value)
    db.commit()
    db.refresh(section)
    return SectionOut.model_validate(section)


@router.post("/sections/reorder", response_model=list[SectionOut])
def reorder_sections(payload: ReorderRequest, db: Session = Depends(get_db)):
    sections = {s.id: s for s in db.scalars(select(Section).where(Section.id.in_(payload.ids)))}
    missing = [i for i in payload.ids if i not in sections]
    if missing:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, f"Unknown section id(s): {missing}"
        )

    modules = {s.module_key for s in sections.values()}
    if len(modules) > 1:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "Sections from more than one module cannot be reordered together",
        )

    for position, section_id in enumerate(payload.ids, start=1):
        sections[section_id].sort_order = position
    db.commit()

    return list_sections(module=modules.pop() if modules else None, db=db)


# ------------------------------------------------------------------- fields
#
# A "field" on these endpoints is a PLACEMENT: one field as one module shows
# it. That is what an administrator is looking at when they open
# Administration -> Opportunities -> Fields, and it is the same row the CRM
# renders, so the two screens cannot describe different products.
#
# The canonical definition sits behind it and is edited through the same
# endpoints, with the split stated explicitly on every response:
#
#     definition_id / definition_*   changing it changes every module
#     placement_id  / everything else changing it changes this module only
#
# `id` is the PLACEMENT id, because that is the thing the list is a list of.
# Definition-level routes take the definition id and say so in the path.


def _placement_or_404(db: Session, placement_id: int) -> FieldPlacement:
    placement = db.get(FieldPlacement, placement_id)
    if placement is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, f"No field placement {placement_id}"
        )
    return placement


def _definition_or_404(db: Session, definition_id: int) -> FieldDefinition:
    definition = db.get(FieldDefinition, definition_id)
    if definition is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, f"No field definition {definition_id}"
        )
    return definition


@router.get("/fields", response_model=list[FieldOut])
def list_fields(
    module: str | None = Query(default=None),
    section_id: int | None = Query(default=None),
    field_status: str = Query(default="active", alias="status"),
    q: str | None = Query(default=None),
    db: Session = Depends(get_db),
):
    """
    The fields of a module — every field that module actually shows.

    This is the endpoint the whole redesign is for. It used to filter
    field_metadata.module_key, which recorded which SHEET OF THE WORKBOOK a row
    was typed on; the register files the entire Stage 0-7 pipeline on `leads`,
    so this returned 0 rows for Opportunities while the CRM rendered 105. It now
    filters field_placements.module_key, which records where the user sees it.

    `status` defaults to 'active', so the ordinary screens never have to
    remember to exclude deleted fields. 'deleted' is what the Deleted tab asks
    for, and 'all' is for the rare case of wanting both.
    """
    if field_status not in ("active", "deleted", "all"):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "status must be one of: active, deleted, all",
        )

    query = (
        select(FieldPlacement, FieldDefinition, Section.label)
        .join(FieldDefinition, FieldDefinition.id == FieldPlacement.definition_id)
        .join(Section, Section.id == FieldPlacement.section_id)
    )
    if field_status != "all":
        query = query.where(FieldPlacement.status == field_status)
        # A placement of a deleted definition is not 'active' on any screen,
        # whatever its own row says. Asking for active fields must not return a
        # field whose concept has been deleted everywhere.
        if field_status == "active":
            query = query.where(FieldDefinition.status == "active")
    if module:
        query = query.where(FieldPlacement.module_key == module)
    if section_id is not None:
        query = query.where(FieldPlacement.section_id == section_id)
    if q:
        pattern = f"%{q.lower()}%"
        query = query.where(
            func.lower(FieldPlacement.api_name).like(pattern)
            | func.lower(FieldDefinition.label).like(pattern)
            | func.lower(func.coalesce(FieldPlacement.label_override, "")).like(pattern)
        )

    rows = db.execute(
        query.order_by(FieldPlacement.module_key, FieldPlacement.sort_order)
    ).all()
    counts = _placement_counts(db)
    return [
        FieldOut(**_serialise_placement(db, p, d, label, counts)) for p, d, label in rows
    ]


@router.get("/fields/{definition_id}", response_model=FieldDetailOut)
def get_field(definition_id: int, db: Session = Depends(get_db)):
    """
    One canonical field and every module it appears on.

    What the edit dialog loads: the definition's own properties, plus a
    placement row per module so the screen can say "changes here apply to
    Opportunities and Deals" by naming them rather than counting them.
    """
    definition = _definition_or_404(db, definition_id)
    labels = _section_labels(db)
    counts = _placement_counts(db)
    return FieldDetailOut(
        **_serialise_definition(definition),
        placements=[
            FieldOut(
                **_serialise_placement(
                    db, p, definition, labels.get(p.section_id, ""), counts
                )
            )
            for p in sorted(definition.placements, key=lambda p: p.module_key)
        ],
    )


def _placement_counts(db: Session) -> dict[int, int]:
    """How many modules each definition is live on. Drives 'Used in 3 modules'."""
    return {
        definition_id: n
        for definition_id, n in db.execute(
            select(FieldPlacement.definition_id, func.count())
            .where(FieldPlacement.status == "active")
            .group_by(FieldPlacement.definition_id)
        )
    }


def _serialise_definition(definition: FieldDefinition) -> dict:
    return {
        "definition_id": definition.id,
        "scope_key": definition.scope_key,
        "api_name": definition.api_name,
        "definition_label": definition.label,
        "field_type": definition.field_type,
        "max_length": definition.max_length,
        "min_value": definition.min_value,
        "max_value": definition.max_value,
        "picklist_key": definition.picklist_key,
        "lookup_target": definition.lookup_target,
        "lookup_filter": definition.lookup_filter,
        "computed_formula": definition.computed_formula,
        "computed_expr": definition.computed_expr,
        "values_note": definition.values_note,
        "description": definition.description,
        "use_case": definition.use_case,
        "origin": definition.origin,
        "source_ref": definition.source_ref,
        "origin_module": definition.origin_module,
        "definition_status": definition.status,
        "has_extension": definition.extension is not None,
    }


def _serialise_placement(
    db: Session,
    placement: FieldPlacement,
    definition: FieldDefinition,
    section_label: str,
    counts: dict[int, int] | None = None,
) -> dict:
    counts = counts if counts is not None else _placement_counts(db)
    source = (
        metadata_resolver.value_source(db, placement.module_key, placement.api_name)
        if placement.value_mode in ("read_through", "carry_forward")
        else None
    )
    return {
        **_serialise_definition(definition),
        # `id` is the PLACEMENT. The list this appears in is a list of fields
        # as one module shows them, and that is the thing being reordered,
        # removed and restored.
        "id": placement.id,
        "placement_id": placement.id,
        "module_key": placement.module_key,
        "scope_key": placement.scope_key,
        "section_id": placement.section_id,
        "section_label": section_label,
        "sort_order": placement.sort_order,
        "label_override": placement.label_override,
        # What this module actually calls it — the override if there is one.
        "label": placement.label_override or definition.label,
        "capture_stage": placement.capture_stage,
        "capture_any_stage": placement.capture_any_stage,
        "mandatory_from": placement.mandatory_from,
        "blocks_transition": placement.blocks_transition,
        "requirement": placement.requirement,
        "required": placement.requirement == "Mandatory",
        "required_on_skip": placement.required_on_skip,
        "required_on_create": bool(placement.required_on_create),
        "visibility_condition": placement.visibility_condition,
        "condition": placement.condition,
        "value_mode": placement.value_mode,
        "value_locked": placement.value_locked,
        "editable": placement.editable,
        "value_source_module": source,
        "storage": placement.storage,
        "status": placement.status,
        "deleted_at": placement.deleted_at,
        "deleted_by": placement.deleted_by,
        "deleted_by_cascade": placement.deleted_by_cascade,
        "provenance": placement.provenance,
        "anchor_field": placement.anchor_field,
        "anchor_position": placement.anchor_position,
        "layout_span": placement.layout_span,
        "stage_scoped": placement.stage_scoped,
        # Every module this field is live on, so the screen can warn before a
        # definition-level edit without a second request per row.
        "module_count": counts.get(definition.id, 0),
        "created_at": placement.created_at,
        "updated_at": placement.updated_at,
    }


def _check_field_definition(
    db: Session,
    field_type: str | None,
    requirement: str | None,
    picklist_key: str | None,
) -> None:
    if field_type is not None and field_type not in FIELD_TYPES:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"type must be one of: {', '.join(sorted(FIELD_TYPES))}",
        )
    if requirement is not None and requirement not in REQUIREMENTS:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"requirement must be one of: {', '.join(REQUIREMENTS)}",
        )
    if picklist_key and db.get(Picklist, picklist_key) is None:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"No picklist {picklist_key}",
        )


def _scope_for(db: Session, module_key: str) -> tuple[str, str]:
    """
    (definition scope, placement scope) for a field being created on a module.

    Both are the module itself: a field belongs to the module it is created on
    and to no other (metadata v2).
    """
    return module_key, module_key


def _check_local_picklist(
    db: Session, picklist_key: str | None, definition_id: int | None = None
) -> None:
    """
    A local list serves one field. A second field wanting it must use a global
    list — Zoho's rule, and what stops a change to one field's choices from
    quietly changing another's.
    """
    if not picklist_key:
        return
    picklist = db.get(Picklist, picklist_key)
    if picklist is None or picklist.is_global:
        return
    other = db.scalar(
        select(FieldDefinition).where(
            FieldDefinition.picklist_key == picklist_key,
            FieldDefinition.status == "active",
            FieldDefinition.id != (definition_id or 0),
        )
    )
    if other is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            refusal(
                "PICKLIST_IS_LOCAL",
                f"The {picklist.label or picklist_key} list belongs to another field.",
                [
                    f"It is used by {other.label}.",
                    "Make the list global to share it, or create a new list for this field.",
                ],
            ),
        )


@router.post("/fields", response_model=FieldOut, status_code=status.HTTP_201_CREATED)
def create_field(payload: FieldCreate, db: Session = Depends(get_db)):
    """
    Create a field: one canonical definition, and its first placement.

    Never two definitions. If the same field is later wanted on another module,
    that is POST /fields/{id}/placements — a second PLACEMENT — which is the
    action the old model could not express at all.
    """
    _module_or_404(db, payload.module_key)
    section = _section_or_404(db, payload.section_id)
    if section.module_key != payload.module_key:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"Section {section.id} belongs to {section.module_key}, "
            f"not {payload.module_key}",
        )
    _check_field_definition(
        db, payload.field_type, payload.requirement, payload.picklist_key
    )
    _check_local_picklist(db, payload.picklist_key)

    definition_scope, placement_scope = _scope_for(db, payload.module_key)

    existing = db.scalar(
        select(FieldDefinition).where(
            FieldDefinition.scope_key == definition_scope,
            FieldDefinition.api_name == payload.api_name,
        )
    )
    if existing is not None:
        if existing.status == "deleted":
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                f"{payload.api_name!r} already exists here and is deleted. "
                f"Restore it (POST /fields/{existing.id}/restore) rather than "
                f"creating a second one — two rows would race to own one column "
                f"of business data.",
            )
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            refusal(
                "FIELD_EXISTS",
                f"This module already has a field named {payload.api_name}.",
                ["Pick a different name, or edit the field that is already there."],
            ),
        )

    data = payload.model_dump(exclude_unset=True)
    capture_stage = _derive_capture_stage(
        db, section, payload.module_key, data.get("capture_stage")
    )

    definition = FieldDefinition(
        scope_key=definition_scope,
        api_name=payload.api_name,
        label=payload.label,
        field_type=payload.field_type,
        max_length=data.get("max_length"),
        min_value=data.get("min_value"),
        max_value=data.get("max_value"),
        picklist_key=data.get("picklist_key"),
        lookup_target=data.get("lookup_target"),
        lookup_filter=data.get("lookup_filter"),
        computed_formula=data.get("computed_formula"),
        computed_expr=data.get("computed_expr"),
        values_note=data.get("values_note"),
        description=data.get("description") or "",
        use_case=data.get("use_case") or "",
        origin=data.get("origin") or "Administration",
        source_ref=data.get("source_ref"),
        origin_module=payload.module_key,
        status="active",
    )
    db.add(definition)
    db.flush()

    placement = FieldPlacement(
        definition_id=definition.id,
        api_name=definition.api_name,
        module_key=payload.module_key,
        scope_key=placement_scope,
        section_id=section.id,
        sort_order=data.get("sort_order")
        or _next_sort_order(
            db, FieldPlacement, [FieldPlacement.module_key == payload.module_key]
        ),
        capture_stage=capture_stage,
        capture_any_stage=bool(data.get("capture_any_stage", False)),
        mandatory_from=data.get("mandatory_from"),
        blocks_transition=data.get("blocks_transition"),
        requirement=payload.requirement,
        required_on_skip=data.get("required_on_skip"),
        required_on_create=bool(data.get("required_on_create") or False),
        visibility_condition=data.get("visibility_condition"),
        condition=data.get("condition"),
        # A field created here has no typed column and is never getting one —
        # that would be the ALTER TABLE from an admin screen the architecture
        # refuses. Its values live in the module's custom_fields JSONB.
        value_mode="own",
        editable=True,
        storage="custom_fields",
        status="active",
        provenance="admin",
    )
    db.add(placement)
    db.commit()
    db.refresh(placement)
    return FieldOut(**_serialise_placement(db, placement, definition, section.label))


@router.post(
    "/fields/{definition_id}/placements",
    response_model=FieldOut,
    status_code=status.HTTP_201_CREATED,
)
def add_placement(
    definition_id: int, payload: PlacementCreate, db: Session = Depends(get_db)
):
    """
    Show a field live on a module further down the pipeline — "From the Lead".

    Metadata v2: a field is OWNED by one module. The only other place it may
    appear is a descendant module that shows the owner's value live and stores
    nothing (value_mode='read_through'). A module that needs its own value
    creates its own field, and a Conversion Mapping copies into it.
    """
    definition = _definition_or_404(db, definition_id)
    _module_or_404(db, payload.module_key)
    section = _section_or_404(db, payload.section_id)
    if section.module_key != payload.module_key:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"Section {section.id} belongs to {section.module_key}, "
            f"not {payload.module_key}",
        )

    _, placement_scope = _scope_for(db, payload.module_key)
    owner = definition.scope_key
    if (payload.value_mode or "own") != "read_through" or owner not in metadata_resolver.parent_chain(
        db, payload.module_key
    ):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            refusal(
                "FIELD_OWNED_ELSEWHERE",
                f"{definition.label} belongs to another module.",
                [
                    "It can only be shown, read-only, on a module further down the pipeline.",
                    "For a value of its own, create a field here and map it in Conversion Mapping.",
                ],
            ),
        )

    existing = db.scalar(
        select(FieldPlacement).where(
            FieldPlacement.definition_id == definition_id,
            FieldPlacement.module_key == payload.module_key,
        )
    )
    if existing is not None:
        if existing.status == "deleted":
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                f"{definition.api_name!r} was removed from {payload.module_key} "
                f"and can be restored "
                f"(POST /placements/{existing.id}/restore).",
            )
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"{definition.api_name!r} is already shown on {payload.module_key}",
        )

    value_mode = payload.value_mode or "own"
    if value_mode not in VALUE_MODES:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"value_mode must be one of: {', '.join(VALUE_MODES)}",
        )
    if value_mode in ("read_through", "carry_forward"):
        source = metadata_resolver.value_source(
            db, payload.module_key, definition.api_name
        )
        if source is None:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                f"{payload.module_key} has no ancestor that holds "
                f"{definition.api_name!r}, so there is nothing for it to "
                f"{'read through' if value_mode == 'read_through' else 'carry forward'}. "
                f"Use value_mode 'own'.",
            )

    placement = FieldPlacement(
        definition_id=definition.id,
        api_name=definition.api_name,
        module_key=payload.module_key,
        scope_key=placement_scope,
        section_id=section.id,
        sort_order=payload.sort_order
        or _next_sort_order(
            db, FieldPlacement, [FieldPlacement.module_key == payload.module_key]
        ),
        label_override=payload.label_override,
        capture_stage=_derive_capture_stage(
            db, section, payload.module_key, payload.capture_stage
        ),
        requirement=payload.requirement or "Optional",
        value_mode=value_mode,
        value_locked=bool(payload.value_locked) if value_mode == "carry_forward" else False,
        editable=value_mode != "read_through",
        # read_through stores nothing. Everything else keeps its values where
        # the caller says, defaulting to the JSONB store — a field being added
        # to a new module has no typed column there and is not getting one.
        storage=None if value_mode == "read_through" else (payload.storage or "custom_fields"),
        status="active",
        provenance="admin",
    )
    # Validated after construction rather than inline: the check needs the
    # placement's own module and value_mode, and refusing here means the
    # row is never committed.
    if payload.stage_scoped is not None:
        _apply_stage_scoped(db, placement, payload.stage_scoped)
    db.add(placement)
    db.commit()
    db.refresh(placement)
    return FieldOut(**_serialise_placement(db, placement, definition, section.label))


@router.patch("/fields/{definition_id}", response_model=FieldDetailOut)
def update_field(
    definition_id: int, payload: FieldUpdate, db: Session = Depends(get_db)
):
    """
    Edit a field. It belongs to one module (metadata v2), so this changes that
    module — and the read-only "From the Lead" copies further down the
    pipeline, which show the same field. Renaming One-Time Revenue on Deals no
    longer renames it on Opportunities: they are two fields.

    A module that needs a different word sets label_override on ITS placement
    (PATCH /placements/{id}) instead. api_name stays absent: it is the key
    every record, condition, formula and custom_fields entry is written under,
    so renaming it would orphan all of that while looking like it worked — the
    same rule PicklistValue.key already states.
    """
    definition = _definition_or_404(db, definition_id)
    data = payload.model_dump(exclude_unset=True)
    _check_field_definition(
        db, data.get("field_type"), data.get("requirement"), data.get("picklist_key")
    )
    if "picklist_key" in data:
        _check_local_picklist(db, data["picklist_key"], definition.id)

    # Definition-level properties: the shape of the value, and its documentation.
    for attr in (
        "label",
        "field_type",
        "max_length",
        "min_value",
        "max_value",
        "picklist_key",
        "lookup_target",
        "lookup_filter",
        "computed_formula",
        "computed_expr",
        "values_note",
        "description",
        "use_case",
        "origin",
        "source_ref",
    ):
        if attr in data:
            setattr(definition, attr, data[attr])

    # Placement-level properties sent to this endpoint are applied to the
    # placement the caller named, and refused otherwise — silently applying a
    # per-module value to every module is exactly the confusion being removed.
    placement_keys = {
        "section_id",
        "sort_order",
        "requirement",
        "capture_stage",
        "capture_any_stage",
        "mandatory_from",
        "blocks_transition",
        "required_on_skip",
        "required_on_create",
        "visibility_condition",
        "condition",
    }
    sent_placement_keys = placement_keys & set(data)
    if sent_placement_keys:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            {
                "message": (
                    "These belong to one module's placement, not to the field "
                    "itself, and would otherwise change every module at once."
                ),
                "fields": sorted(sent_placement_keys),
                "use": "PATCH /api/admin/metadata/placements/{placement_id}",
            },
        )

    db.commit()
    db.refresh(definition)
    return get_field(definition_id, db)


@router.patch("/placements/{placement_id}", response_model=FieldOut)
def update_placement(
    placement_id: int, payload: PlacementUpdate, db: Session = Depends(get_db)
):
    """
    Edit one module's placement. Nothing on any other module moves.

    Section, order, stage gating, conditions, the label this module uses, and
    the value behaviour — every property that measurement showed genuinely
    differs between modules.
    """
    placement = _placement_or_404(db, placement_id)
    definition = db.get(FieldDefinition, placement.definition_id)
    data = payload.model_dump(exclude_unset=True)

    if data.get("requirement") is not None and data["requirement"] not in REQUIREMENTS:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"requirement must be one of: {', '.join(REQUIREMENTS)}",
        )

    if "section_id" in data and data["section_id"] is not None:
        section = _section_or_404(db, data["section_id"])
        if section.module_key != placement.module_key:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                f"Section {section.id} belongs to {section.module_key}, not "
                f"{placement.module_key}. To show this field on "
                f"{section.module_key} too, add a placement there instead of "
                f"moving this one.",
            )
        placement.section_id = section.id
        # A field moved into a numbered STAGE section with no stage of its own
        # would render on no screen at all. Fill the blank the same way create
        # does, and never override a value the caller stated.
        placement.capture_stage = _derive_capture_stage(
            db, section, placement.module_key, data.get("capture_stage", placement.capture_stage)
        )

    if "layout_span" in data:
        if data["layout_span"] is not None and data["layout_span"] not in LAYOUT_SPANS:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                f"layout_span must be one of: {', '.join(LAYOUT_SPANS)}, or null "
                f"for the field type's own width.",
            )
        placement.layout_span = data["layout_span"]

    if "anchor_field" in data or "anchor_position" in data:
        _apply_anchor(db, placement, data)

    for attr in (
        "sort_order",
        "label_override",
        "capture_stage",
        "capture_any_stage",
        "mandatory_from",
        "blocks_transition",
        "requirement",
        "required_on_skip",
        "required_on_create",
        "visibility_condition",
        "condition",
    ):
        if attr in data:
            setattr(placement, attr, data[attr])

    if "value_mode" in data and data["value_mode"] is not None:
        _apply_value_mode(db, placement, definition, data)
    elif "value_locked" in data:
        if placement.value_mode != "carry_forward":
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                f"value_locked only means something for a carried value. "
                f"{placement.api_name!r} on {placement.module_key} is "
                f"{placement.value_mode!r}.",
            )
        placement.value_locked = bool(data["value_locked"])

    if "storage" in data and data["storage"] is not None:
        if placement.value_mode == "read_through":
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                "A read-through placement stores nothing. Change value_mode first.",
            )
        if data["storage"] not in STORAGE_MODES:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                f"storage must be one of: {', '.join(STORAGE_MODES)}",
            )
        placement.storage = data["storage"]

    if "stage_scoped" in data and data["stage_scoped"] is not None:
        _apply_stage_scoped(db, placement, str(data["stage_scoped"]))

    db.commit()
    db.refresh(placement)
    return FieldOut(
        **_serialise_placement(db, placement, definition, placement.section.label)
    )


def _apply_stage_scoped(db: Session, placement: FieldPlacement, mode: str) -> None:
    """
    Record this field once per record, or once per stage.

    THE TWO CHECKS A CHECK CONSTRAINT CANNOT MAKE, for the same reason the
    anchor checks live here: both need a join the constraint cannot reach.

      1. the module actually HAS stages. `stage_scoped` on Accounts describes
         values keyed `__s<n>` on a record that is never on a stage — not
         corrupt, but a promise nothing can keep, and an admin who sets it
         would see no change and no reason why.
      2. the placement stores something. A read_through placement holds no
         value of its own at all, so it has no per-stage values either; the
         answer it shows comes from the ancestor that owns it.

    Nothing is validated about the field's TYPE. A per-stage checkbox is odd
    but not wrong, and the register is full of judgements this layer should not
    be making for an admin.
    """
    if mode not in STAGE_SCOPED_MODES:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"stage_scoped must be one of: {', '.join(STAGE_SCOPED_MODES)}",
        )

    if mode != "none":
        module = db.get(Module, placement.module_key)
        if module is None or not module.is_pipeline:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                f"{placement.module_key} has no stages, so a value cannot be "
                f"recorded per stage on it. Only pipeline modules can.",
            )
        if placement.value_mode == "read_through":
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                f"{placement.api_name!r} on {placement.module_key} is "
                f"read-through and stores nothing of its own, per stage or "
                f"otherwise. Change value_mode first.",
            )

    placement.stage_scoped = mode


def _apply_anchor(db: Session, placement: FieldPlacement, data: dict) -> None:
    """
    Move a placement next to another field, or return it to its own section.

    THE TWO CHECKS A CHECK CONSTRAINT CANNOT MAKE. The migration explains why
    neither is a foreign key; both are made here, at the only endpoint that
    sets an anchor.

      1. the anchor is an ACTIVE placement on the same module and shape. A
         field cannot draw next to something that is not on the screen, and a
         cross-module anchor would name a field this form has never heard of.
      2. the anchor chain does not loop. A anchored to B anchored to A renders
         neither, and the walk below is the only place that can see it — the
         self-anchor CHECK catches the one-hop case and nothing longer.

    Chains themselves are fine and deliberately allowed: C under B under A is
    three fields stacked in the order they are asked for.
    """
    anchor = data.get("anchor_field", placement.anchor_field)

    if anchor is None:
        # Clearing the anchor clears the position with it — the pair check
        # refuses one without the other, and a stale 'after' pointing at
        # nothing is not information worth keeping.
        if data.get("anchor_position") is not None:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                "anchor_position needs an anchor_field. Send both, or send "
                "anchor_field: null to return the field to its own section.",
            )
        placement.anchor_field = None
        placement.anchor_position = None
        return

    if anchor == placement.api_name:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"{placement.api_name!r} cannot be anchored to itself.",
        )

    target = db.scalar(
        select(FieldPlacement).where(
            FieldPlacement.module_key == placement.module_key,
            FieldPlacement.scope_key == placement.scope_key,
            FieldPlacement.api_name == anchor,
            FieldPlacement.status == "active",
        )
    )
    if target is None:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"{placement.module_key} has no active field named {anchor!r}. A "
            f"field can only be anchored to one its own form draws — to put it "
            f"beside a field from another module, add a placement there.",
        )

    # Walk up from the proposed anchor towards ITS root. Arriving back at this
    # placement means the proposed anchor already draws inside it, so the chain
    # would close on itself and neither field would render.
    #
    # The order of the two guards matters and is the whole test: the loop check
    # comes FIRST. Reaching a name already visited is otherwise ambiguous — it
    # is a pre-existing loop somewhere further up that this edit is not part of,
    # and breaking on it before asking "is that name mine" would let exactly the
    # cycle being guarded against through.
    seen: set[str] = set()
    cursor: FieldPlacement | None = target
    for _ in range(64):
        if cursor is None:
            break
        if cursor.api_name == placement.api_name:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                f"Anchoring {placement.api_name!r} to {anchor!r} would make a "
                f"loop — {anchor!r} already draws inside {placement.api_name!r}, "
                f"directly or through another field.",
            )
        if cursor.api_name in seen:
            break
        seen.add(cursor.api_name)
        if cursor.anchor_field is None:
            break
        cursor = db.scalar(
            select(FieldPlacement).where(
                FieldPlacement.module_key == placement.module_key,
                FieldPlacement.scope_key == placement.scope_key,
                FieldPlacement.api_name == cursor.anchor_field,
                FieldPlacement.status == "active",
            )
        )

    position = data.get("anchor_position") or placement.anchor_position or "after"
    if position not in ANCHOR_POSITIONS:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"anchor_position must be one of: {', '.join(ANCHOR_POSITIONS)}",
        )

    placement.anchor_field = anchor
    placement.anchor_position = position


def _anchored_to(db: Session, placement: FieldPlacement) -> list[FieldPlacement]:
    """Active placements on this module that draw inside `placement`."""
    return list(
        db.scalars(
            select(FieldPlacement).where(
                FieldPlacement.module_key == placement.module_key,
                FieldPlacement.scope_key == placement.scope_key,
                FieldPlacement.anchor_field == placement.api_name,
                FieldPlacement.status == "active",
            )
        )
    )


def _apply_value_mode(
    db: Session, placement: FieldPlacement, definition: FieldDefinition, data: dict
) -> None:
    """
    Change how one module's copy of a field behaves, keeping the row coherent.

    The check constraints refuse an incoherent row, so this fills in what the
    mode implies rather than leaving the caller to get all four columns right:
    read_through stores nothing and is not editable; own and carry_forward
    store something; only carry_forward can be locked.
    """
    mode = data["value_mode"]
    if mode not in VALUE_MODES:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"value_mode must be one of: {', '.join(VALUE_MODES)}",
        )

    if mode in ("read_through", "carry_forward"):
        source = metadata_resolver.value_source(
            db, placement.module_key, placement.api_name
        )
        if source is None:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                f"{placement.module_key} has no ancestor holding "
                f"{placement.api_name!r}, so there is nothing to "
                f"{'read through' if mode == 'read_through' else 'carry forward'}.",
            )

    placement.value_mode = mode
    if mode == "read_through":
        # Its values stop being stored here. The business column and every
        # value already in it are LEFT ALONE — no DDL, no delete. They simply
        # stop being read, and switching back reads them again.
        placement.editable = False
        placement.storage = None
        placement.value_locked = False
    else:
        placement.editable = bool(data.get("editable", True))
        placement.storage = data.get("storage") or placement.storage or "custom_fields"
        placement.value_locked = (
            bool(data.get("value_locked", placement.value_locked))
            if mode == "carry_forward"
            else False
        )


@router.patch("/placements/{placement_id}/required", response_model=FieldOut)
def set_placement_required(
    placement_id: int, payload: RequiredUpdate, db: Session = Depends(get_db)
):
    """
    The Required toggle, on one module.

    Requirement is a placement property because it genuinely differs:
    incremental_value is Mandatory on one pipeline module and Conditional on
    another. Only moves between Mandatory and Optional — the other four
    requirements are set deliberately and a toggle must not silently discard
    one.
    """
    placement = _placement_or_404(db, placement_id)
    if placement.requirement not in ("Mandatory", "Optional"):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"{placement.api_name} is {placement.requirement!r}, which the "
            f"Required toggle does not move. Set the requirement explicitly.",
        )
    placement.requirement = "Mandatory" if payload.required else "Optional"
    db.commit()
    db.refresh(placement)
    return FieldOut(
        **_serialise_placement(
            db,
            placement,
            db.get(FieldDefinition, placement.definition_id),
            placement.section.label,
        )
    )


@router.delete("/placements/{placement_id}", response_model=FieldOut)
def delete_placement(
    placement_id: int,
    user_id: str | None = Query(default=None, alias="by"),
    db: Session = Depends(get_db),
):
    """
    Remove a field from ONE module. "Remove from Opportunities".

    The canonical definition and every other placement are untouched, and so is
    every byte of business data: no DROP COLUMN, no JSONB key removed. The
    field stops rendering on this module at the next publish and comes back
    exactly as it was on restore.

    deleted_by_cascade stays false, which is what makes restore correct later:
    a definition-level restore must not resurrect a placement somebody removed
    deliberately.

    ANYTHING ANCHORED TO IT IS RELEASED, not removed with it. A field whose
    anchor has gone returns to its own section's list, which is where it drew
    before anchors existed — a worse screen, never a missing field. It is done
    here rather than left to the resolver so that Administration SHOWS the
    consequence: the released fields' anchors read empty straight away instead
    of naming a field that is no longer on the module.
    """
    placement = _placement_or_404(db, placement_id)
    definition = db.get(FieldDefinition, placement.definition_id)
    if placement.status == "deleted":
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"{placement.api_name} is already removed from {placement.module_key}",
        )

    for dependent in _anchored_to(db, placement):
        dependent.anchor_field = None
        dependent.anchor_position = None

    placement.status = "deleted"
    placement.deleted_at = _now()
    placement.deleted_by = _check_user(db, user_id)
    placement.deleted_by_cascade = False
    db.commit()
    db.refresh(placement)
    return FieldOut(
        **_serialise_placement(db, placement, definition, placement.section.label)
    )


@router.post("/placements/{placement_id}/restore", response_model=FieldOut)
def restore_placement(placement_id: int, db: Session = Depends(get_db)):
    """Put a field back on one module, in the section and order it had."""
    placement = _placement_or_404(db, placement_id)
    definition = db.get(FieldDefinition, placement.definition_id)
    if placement.status != "deleted":
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"{placement.api_name} is not removed from {placement.module_key}",
        )
    if definition.status == "deleted":
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"{definition.api_name!r} is deleted everywhere. Restore the field "
            f"itself first (POST /fields/{definition.id}/restore).",
        )

    placement.status = "active"
    placement.deleted_at = None
    placement.deleted_by = None
    placement.deleted_by_cascade = False
    db.commit()
    db.refresh(placement)
    return FieldOut(
        **_serialise_placement(db, placement, definition, placement.section.label)
    )


@router.delete("/fields/{definition_id}", response_model=FieldDetailOut)
def delete_field(
    definition_id: int,
    user_id: str | None = Query(default=None, alias="by"),
    db: Session = Depends(get_db),
):
    """
    Delete a field EVERYWHERE. The definition and all of its placements.

    Logical, like every delete here: the rows stay, the typed columns stay,
    every value in them stays, and every custom_fields JSONB key stays. The
    field disappears from every screen at the next publish and comes back
    configured exactly as it was.

    Each placement is stamped deleted_by_cascade=true, so a later restore knows
    which ones this delete took down and which had already been removed from
    their module on purpose.
    """
    definition = _definition_or_404(db, definition_id)
    if definition.status == "deleted":
        raise HTTPException(
            status.HTTP_409_CONFLICT, f"{definition.api_name} is already deleted"
        )

    stamp, actor = _now(), _check_user(db, user_id)
    definition.status = "deleted"
    definition.deleted_at = stamp
    definition.deleted_by = actor

    for placement in definition.placements:
        if placement.status == "active":
            placement.status = "deleted"
            placement.deleted_at = stamp
            placement.deleted_by = actor
            placement.deleted_by_cascade = True

    db.commit()
    db.refresh(definition)
    return get_field(definition_id, db)


@router.post("/fields/{definition_id}/restore", response_model=FieldDetailOut)
def restore_field(definition_id: int, db: Session = Depends(get_db)):
    """
    Bring a deleted field back, on the modules it was on when it was deleted.

    ONLY the placements this deletion cascaded to. A placement an admin had
    removed from Deals a month earlier stays removed — that was a separate
    decision and restoring the field is not a reason to undo it. This is what
    deleted_by_cascade is for.

    Restore is not a rollback: one field comes back and nothing else moves.
    """
    definition = _definition_or_404(db, definition_id)
    if definition.status != "deleted":
        raise HTTPException(
            status.HTTP_409_CONFLICT, f"{definition.api_name} is not deleted"
        )

    definition.status = "active"
    definition.deleted_at = None
    definition.deleted_by = None

    for placement in definition.placements:
        if placement.status == "deleted" and placement.deleted_by_cascade:
            placement.status = "active"
            placement.deleted_at = None
            placement.deleted_by = None
            placement.deleted_by_cascade = False

    db.commit()
    db.refresh(definition)
    return get_field(definition_id, db)


@router.post("/placements/reorder", response_model=list[FieldOut])
def reorder_placements(payload: ReorderRequest, db: Session = Depends(get_db)):
    """
    Reorder fields within one module. Ids are PLACEMENT ids.

    One module at a time, for the same reason sections are: `sort_order` is
    scoped to a module, so a request mixing two would renumber both against one
    sequence and interleave their forms.
    """
    placements = {
        p.id: p
        for p in db.scalars(
            select(FieldPlacement).where(FieldPlacement.id.in_(payload.ids))
        )
    }
    missing = [i for i in payload.ids if i not in placements]
    if missing:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, f"No field placement(s) {missing}"
        )

    modules = {p.module_key for p in placements.values()}
    if len(modules) > 1:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"All fields must be on one module; got {sorted(modules)}",
        )

    for position, placement_id in enumerate(payload.ids, start=1):
        placements[placement_id].sort_order = position

    db.commit()
    labels = _section_labels(db)
    counts = _placement_counts(db)
    return [
        FieldOut(
            **_serialise_placement(
                db,
                placements[i],
                db.get(FieldDefinition, placements[i].definition_id),
                labels.get(placements[i].section_id, ""),
                counts,
            )
        )
        for i in payload.ids
    ]


# Kept at the old paths so nothing that already calls them breaks: a reorder of
# fields is a reorder of placements, and the Required toggle acts on one
# module's placement. Both take PLACEMENT ids, which is what /fields returns
# as `id`.
router.add_api_route(
    "/fields/reorder",
    reorder_placements,
    methods=["POST"],
    response_model=list[FieldOut],
    include_in_schema=False,
)
router.add_api_route(
    "/fields/{placement_id}/required",
    set_placement_required,
    methods=["PATCH"],
    response_model=FieldOut,
    include_in_schema=False,
)


# ---------------------------------------------------------------- picklists


@router.get("/picklists", response_model=list[PicklistOut])
def list_picklists(
    include_inactive: bool = Query(default=True),
    db: Session = Depends(get_db),
):
    # How many live FIELDS use each picklist. picklist_key is a definition
    # property — one dropdown behind one concept — so this counts definitions,
    # not placements: a field shown on three modules is one user of the
    # picklist, not three.
    usage = dict(
        db.execute(
            select(FieldDefinition.picklist_key, func.count())
            .where(
                FieldDefinition.status == "active",
                FieldDefinition.picklist_key.is_not(None),
            )
            .group_by(FieldDefinition.picklist_key)
        ).all()
    )

    query = select(Picklist).order_by(Picklist.sort_order, Picklist.picklist_key)
    if not include_inactive:
        query = query.where(Picklist.active.is_(True))

    return [
        PicklistOut(
            picklist_key=p.picklist_key,
            label=p.label,
            sort_order=p.sort_order,
            active=p.active,
            is_global=p.is_global,
            field_count=usage.get(p.picklist_key, 0),
            values=[PicklistValueOut.model_validate(v) for v in p.values],
        )
        for p in db.scalars(query)
    ]


@router.post("/picklists", response_model=PicklistOut, status_code=status.HTTP_201_CREATED)
def create_picklist(payload: PicklistCreate, db: Session = Depends(get_db)):
    if db.get(Picklist, payload.picklist_key) is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT, f"Picklist {payload.picklist_key} already exists"
        )
    picklist = Picklist(
        picklist_key=payload.picklist_key,
        label=payload.label,
        sort_order=payload.sort_order
        if payload.sort_order is not None
        else _next_sort_order(db, Picklist, []),
        active=payload.active,
    )
    db.add(picklist)
    db.commit()
    db.refresh(picklist)
    return PicklistOut(
        picklist_key=picklist.picklist_key,
        label=picklist.label,
        sort_order=picklist.sort_order,
        active=picklist.active,
        is_global=picklist.is_global,
        field_count=0,
        values=[],
    )


@router.patch("/picklists/{picklist_key}", response_model=PicklistOut)
def update_picklist(
    picklist_key: str, payload: PicklistUpdate, db: Session = Depends(get_db)
):
    """
    Label, order and active. The key is the identity every field points at.

    Deactivating a picklist that fields still use is allowed but not silent:
    publish reports it as an ERROR, because a picklist field with no options
    behind it renders as an empty dropdown nobody can answer. Deactivate the
    fields, or repoint them, first.
    """
    picklist = _picklist_or_404(db, picklist_key)
    changes = payload.model_dump(exclude_unset=True)
    if picklist.is_global and changes.get("is_global") is False:
        users = db.scalar(
            select(func.count())
            .select_from(FieldDefinition)
            .where(
                FieldDefinition.picklist_key == picklist_key,
                FieldDefinition.status == "active",
            )
        )
        if (users or 0) > 1:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                refusal(
                    "PICKLIST_SHARED",
                    f"{picklist.label or picklist_key} is used by {users} fields.",
                    ["A local list serves one field.", "Give the other fields their own lists first."],
                ),
            )
    for name, value in changes.items():
        setattr(picklist, name, value)
    db.commit()
    db.refresh(picklist)

    usage = db.scalar(
        select(func.count())
        .select_from(FieldDefinition)
        .where(
            FieldDefinition.picklist_key == picklist_key,
            FieldDefinition.status == "active",
        )
    )
    return PicklistOut(
        picklist_key=picklist.picklist_key,
        label=picklist.label,
        sort_order=picklist.sort_order,
        active=picklist.active,
        is_global=picklist.is_global,
        field_count=usage or 0,
        values=[PicklistValueOut.model_validate(v) for v in picklist.values],
    )


@router.post("/picklists/reorder", response_model=list[PicklistOut])
def reorder_picklists(payload: PicklistReorderRequest, db: Session = Depends(get_db)):
    picklists = {
        p.picklist_key: p
        for p in db.scalars(select(Picklist).where(Picklist.picklist_key.in_(payload.keys)))
    }
    missing = [k for k in payload.keys if k not in picklists]
    if missing:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, f"Unknown picklist(s): {missing}"
        )
    for position, key in enumerate(payload.keys, start=1):
        picklists[key].sort_order = position
    db.commit()
    return list_picklists(db=db)


@router.post(
    "/picklist-values", response_model=PicklistValueOut, status_code=status.HTTP_201_CREATED
)
def create_picklist_value(payload: PicklistValueCreate, db: Session = Depends(get_db)):
    _picklist_or_404(db, payload.picklist_key)
    clash = db.scalar(
        select(PicklistValue).where(
            PicklistValue.picklist_key == payload.picklist_key,
            PicklistValue.key == payload.key,
        )
    )
    if clash is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"{payload.picklist_key} already has a value {payload.key!r}",
        )

    value = PicklistValue(
        picklist_key=payload.picklist_key,
        key=payload.key,
        label=payload.label,
        sort_order=payload.sort_order
        if payload.sort_order is not None
        else _next_sort_order(
            db, PicklistValue, [PicklistValue.picklist_key == payload.picklist_key]
        ),
        active=payload.active,
    )
    db.add(value)
    db.commit()
    db.refresh(value)
    return PicklistValueOut.model_validate(value)


@router.patch("/picklist-values/{value_id}", response_model=PicklistValueOut)
def update_picklist_value(
    value_id: int, payload: PicklistValueUpdate, db: Session = Depends(get_db)
):
    """
    Label, order and active.

    `key` is not editable and PicklistValueUpdate does not carry it. The key is
    what every record already stores — INFRASTRUCTURE, not "Infrastructure" —
    and what the register's own conditions and lookup filters compare against.
    Renaming it would leave every stored value pointing at an option that no
    longer exists, and the dropdown would quietly render blank on records that
    were filled in correctly. Deactivate instead: existing records keep
    resolving, and nobody can choose it again.
    """
    value = _value_or_404(db, value_id)
    changes = payload.model_dump(exclude_unset=True)
    if value.is_system and changes.get("active") is False:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            refusal(
                "SYSTEM_VALUE",
                f"{value.label} can't be retired.",
                [
                    "The CRM's own rules read this choice, so it has to stay.",
                    "You can rename it.",
                ],
            ),
        )
    for name, attr in changes.items():
        setattr(value, name, attr)
    db.commit()
    db.refresh(value)
    return PicklistValueOut.model_validate(value)


@router.post("/picklist-values/reorder", response_model=list[PicklistValueOut])
def reorder_picklist_values(payload: ReorderRequest, db: Session = Depends(get_db)):
    values = {
        v.id: v
        for v in db.scalars(select(PicklistValue).where(PicklistValue.id.in_(payload.ids)))
    }
    missing = [i for i in payload.ids if i not in values]
    if missing:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, f"Unknown value id(s): {missing}"
        )
    picklists = {v.picklist_key for v in values.values()}
    if len(picklists) > 1:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "Values from more than one picklist cannot be reordered together",
        )

    for position, value_id in enumerate(payload.ids, start=1):
        values[value_id].sort_order = position
    db.commit()

    key = picklists.pop()
    return [
        PicklistValueOut.model_validate(v)
        for v in db.scalars(
            select(PicklistValue)
            .where(PicklistValue.picklist_key == key)
            .order_by(PicklistValue.sort_order)
        )
    ]


# ------------------------------------------------------------------- stages


@router.get("/conversion-mappings", response_model=list[ConversionMappingOut])
def list_conversion_mappings(db: Session = Depends(get_db)):
    """
    What each conversion copies — Zoho's Lead Conversion Mapping. Metadata v2.

    Read-only for now: the rows are written by metadata_v2.py from today's
    behaviour, and the screen that edits them arrives with the Setup rebuild.
    Labels are the module's own field labels, so the list reads the way the
    forms do.
    """
    labels = {
        (p.module_key, p.api_name): metadata_resolver.label_of(p, d)
        for p, d in db.execute(
            select(FieldPlacement, FieldDefinition).join(
                FieldDefinition, FieldDefinition.id == FieldPlacement.definition_id
            ).where(FieldPlacement.status == "active")
        ).all()
    }
    rows = db.scalars(
        select(ConversionMapping).order_by(ConversionMapping.sort_order, ConversionMapping.id)
    )
    return [
        ConversionMappingOut(
            id=r.id,
            path=r.path,
            kind=r.kind,
            source_module=r.source_module,
            source_api_name=r.source_api_name,
            source_label=labels.get((r.source_module, r.source_api_name)),
            target_module=r.target_module,
            target_api_name=r.target_api_name,
            target_label=labels.get((r.target_module, r.target_api_name)),
            transform=r.transform,
            locked=r.locked,
            note=r.note,
            sort_order=r.sort_order,
            active=r.active,
        )
        for r in rows
    ]


@router.get("/stages", response_model=list[StageOut])
def list_stages(
    include_inactive: bool = Query(default=True),
    db: Session = Depends(get_db),
):
    query = select(Stage).order_by(Stage.sort_order, Stage.stage)
    if not include_inactive:
        query = query.where(Stage.active.is_(True))
    return [StageOut.model_validate(s) for s in db.scalars(query)]


@router.post("/stages", response_model=StageOut, status_code=status.HTTP_201_CREATED)
def create_stage(payload: StageCreate, db: Session = Depends(get_db)):
    if db.get(Stage, payload.stage) is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT, f"Stage {payload.stage} already exists"
        )
    stage = Stage(
        stage=payload.stage,
        name=payload.name,
        progression_pct=payload.progression_pct,
        probability_pct=payload.probability_pct,
        owner_role=payload.owner_role,
        bid_phase=payload.bid_phase,
        applies_to=payload.applies_to,
        sort_order=payload.sort_order if payload.sort_order is not None else payload.stage,
        active=payload.active,
    )
    db.add(stage)
    db.commit()
    db.refresh(stage)
    return StageOut.model_validate(stage)


@router.patch("/stages/{stage}", response_model=StageOut)
def update_stage(stage: int, payload: StageUpdate, db: Session = Depends(get_db)):
    """
    Everything except the stage NUMBER, which is the identity records store.

    Renumbering a stage would repoint every record that sits on it, and every
    criterion code (E4.1, X3.2) and range in module_split.json built from it.
    Reordering for display is what sort_order is for.

    progression_pct / probability_pct are THE source of the two numbers every
    pipeline record takes on entering this stage (app/progression.py). A change
    reaches records as they next enter the stage; records already in it keep
    the value they were given.
    """
    row = _stage_or_404(db, stage)
    data = payload.model_dump(exclude_unset=True)

    for name, value in data.items():
        setattr(row, name, value)
    db.commit()
    db.refresh(row)
    return StageOut.model_validate(row)


@router.post("/stages/reorder", response_model=list[StageOut])
def reorder_stages(payload: ReorderRequest, db: Session = Depends(get_db)):
    """Reorders by stage NUMBER — the ids here are stage numbers."""
    stages = {s.stage: s for s in db.scalars(select(Stage).where(Stage.stage.in_(payload.ids)))}
    missing = [i for i in payload.ids if i not in stages]
    if missing:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, f"Unknown stage(s): {missing}"
        )
    for position, stage in enumerate(payload.ids, start=1):
        stages[stage].sort_order = position
    db.commit()
    return list_stages(db=db)


# ------------------------------------------------------- draft, publish, versions


@router.get("/validate", response_model=ValidationOut)
def validate_draft_endpoint(db: Session = Depends(get_db)):
    return _validation_out(build_snapshot(db))


@router.get("/draft", response_model=DraftStatus)
def draft_status(db: Session = Depends(get_db)):
    """
    What is waiting to be published, and whether it would publish cleanly.

    The review step. An admin reads this before publishing, which is what makes
    'draft -> review -> publish' a real gate rather than a label: the changes
    are listed in words, against the last published version.
    """
    snapshot = build_snapshot(db)
    latest = _latest_version(db)

    # Before the first publish everything is a change, and listing 566 field
    # additions helps nobody — the count says it better.
    changes = diff_snapshots(latest.snapshot, snapshot) if latest else []

    return DraftStatus(
        published_version=latest.version_no if latest else None,
        published_at=latest.published_at if latest else None,
        has_changes=bool(changes) if latest else True,
        changes=changes,
        validation=_validation_out(snapshot),
        counts={
            "modules": len(snapshot["modules"]),
            "sections": len(snapshot["sections"]),
            "fields": len(snapshot["fields"]),
            "picklists": len(snapshot["picklists"]),
            "stages": len(snapshot["stages"]),
            "deleted_fields": db.scalar(
                select(func.count())
                .select_from(FieldDefinition)
                .where(FieldPlacement.status == "deleted")
            )
            or 0,
        },
    )


def _version_out(version: MetadataVersion) -> MetadataVersionOut:
    snapshot = version.snapshot or {}
    return MetadataVersionOut(
        id=version.id,
        version_no=version.version_no,
        status=version.status,
        note=version.note,
        restored_from=version.restored_from,
        created_by=version.created_by,
        created_at=version.created_at,
        published_by=version.published_by,
        published_at=version.published_at,
        field_count=len(snapshot.get("fields", [])),
        picklist_count=len(snapshot.get("picklists", [])),
        stage_count=len(snapshot.get("stages", [])),
    )


@router.get("/versions", response_model=list[MetadataVersionOut])
def list_versions(db: Session = Depends(get_db)):
    return [
        _version_out(v)
        for v in db.scalars(
            select(MetadataVersion).order_by(MetadataVersion.version_no.desc())
        )
    ]


@router.get("/versions/{version_no}", response_model=MetadataVersionDetail)
def get_version(version_no: int, db: Session = Depends(get_db)):
    version = db.scalar(
        select(MetadataVersion).where(MetadataVersion.version_no == version_no)
    )
    if version is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"No version {version_no}")
    return MetadataVersionDetail(
        **_version_out(version).model_dump(), snapshot=version.snapshot
    )


def _publish(
    db: Session,
    snapshot: dict,
    note: str | None,
    acting_user_id: str | None,
    restored_from: int | None = None,
) -> PublishResult:
    """
    Validate, freeze, write. In that order, and it matters.

    A draft that does not validate NEVER becomes a published version and never
    reaches disk — that is the whole reason publish is a separate act from
    editing. The version row is written before the files so that a failed write
    rolls the version back with it, rather than leaving history claiming a
    publish that never landed.
    """
    validation = _validation_out(snapshot)
    if not validation.ok:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            {
                "message": (
                    f"{len(validation.errors)} error(s) — nothing was published "
                    f"and no file was written."
                ),
                "errors": validation.errors,
                "warnings": validation.warnings,
            },
        )

    user = _check_user(db, acting_user_id)
    highest = db.scalar(select(func.max(MetadataVersion.version_no))) or 0

    version = MetadataVersion(
        version_no=highest + 1,
        status="published",
        note=note,
        snapshot=snapshot,
        restored_from=restored_from,
        created_by=user,
        created_at=_now(),
        published_by=user,
        published_at=_now(),
    )
    db.add(version)
    db.flush()

    written = write_spec_documents(spec_documents(snapshot))
    db.commit()
    db.refresh(version)

    return PublishResult(
        version=_version_out(version),
        validation=validation,
        written=[str(p.relative_to(SPEC_DIR.parent.parent)) for p in written],
    )


@router.post("/publish", response_model=PublishResult)
def publish(payload: PublishRequest, db: Session = Depends(get_db)):
    """
    Freeze the draft as an immutable version and regenerate the spec files.

        draft -> validate -> snapshot -> spec/*.json -> the frontend reads it

    After this the new configuration exists in BOTH PostgreSQL and the
    regenerated JSON, and PostgreSQL remains the source of truth. A later
    hand-edit of a spec file changes nothing in the database and is overwritten
    by the next publish — see the module docstring in app/metadata_spec.py.

    The frontend imports those files at build time, so a running dev server
    picks the change up on its next reload; a built bundle needs rebuilding.
    That is the Phase-1 arrangement, and the reason Phase 2 may serve metadata
    from an API instead.
    """
    return _publish(db, build_snapshot(db), payload.note, payload.acting_user_id)


@router.post("/versions/{version_no}/rollback", response_model=PublishResult)
def rollback(version_no: int, payload: RollbackRequest, db: Session = Depends(get_db)):
    """
    Return the configuration to an earlier published version.

    History is EXTENDED, never rewound: republishing version 2 creates version
    4 whose snapshot is version 2's, with restored_from = 2. What was live and
    when stays true, and "we rolled back" is a visible fact rather than a gap
    in the numbering. Version 3 remains exactly as it was published.

    Nothing is destroyed on the way. A field the old snapshot does not carry is
    logically deleted, a picklist it does not carry is deactivated — so rolling
    forward again brings all of it back. See restore_snapshot().

    This is NOT the same operation as restoring one deleted field. Rollback
    moves the whole configuration; restore moves one field and leaves the rest
    where it is.
    """
    version = db.scalar(
        select(MetadataVersion).where(MetadataVersion.version_no == version_no)
    )
    if version is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"No version {version_no}")

    restore_snapshot(db, version.snapshot)
    db.flush()

    note = payload.note or f"Rolled back to version {version_no}"
    return _publish(
        db,
        build_snapshot(db),
        note,
        payload.acting_user_id,
        restored_from=version_no,
    )
