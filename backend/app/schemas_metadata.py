"""
Wire shapes for the Round-6 metadata layer.

A second schemas module, rather than 300 more lines on the end of schemas.py:
everything here describes the field register, and nothing here describes a
business record. Keeping the two apart is the same separation models.py draws
with its ROUND 6 banner — a reader looking for what an Account looks like on
the wire should not have to scroll past what a picklist value looks like.

NAMING
------
The register calls two of its columns `type` and `order`. `type` shadows a
builtin and `order` is reserved in SQL, so the database stores them as
field_type and sort_order (see models.FieldMetadata). These schemas keep the
DATABASE names rather than the register's, because this is an Administration
API talking to an Administration screen — the register's own spelling appears
exactly once more, in the generated JSON, and app/metadata_spec.py owns that
translation. One rename in one place.
"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


# ----------------------------------------------------------------- acting user

class ActingUser(BaseModel):
    """
    Who is doing this.

    The prototype has no authentication and is not getting any (CLAUDE.md, out
    of scope), so the caller states who it is instead of the server knowing.
    Optional throughout: a null is honest about there being no identity, where
    a made-up USR-001 would be a lie recorded in an audit column.
    """

    acting_user_id: str | None = Field(default=None, max_length=20)


# ---------------------------------------------------------------------- modules

class ModuleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    module_key: str
    label: str
    sort_order: int
    active: bool
    # Counts, so the Administration list can say "58 fields, 3 deleted" without
    # fetching 566 rows to count them in the browser.
    field_count: int = 0
    deleted_field_count: int = 0
    section_count: int = 0


class ModuleCreate(BaseModel):
    module_key: str = Field(min_length=1, max_length=60, pattern=r"^[a-z][a-z0-9_]*$")
    label: str = Field(min_length=1, max_length=120)
    sort_order: int | None = None
    active: bool = True


class ModuleUpdate(BaseModel):
    """module_key is absent on purpose — see routers/metadata.py::update_module."""

    label: str | None = Field(default=None, min_length=1, max_length=120)
    sort_order: int | None = None
    active: bool | None = None


# --------------------------------------------------------------------- sections

class SectionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    module_key: str
    label: str
    sort_order: int
    active: bool
    field_count: int = 0
    deleted_field_count: int = 0


class SectionCreate(BaseModel):
    module_key: str = Field(min_length=1, max_length=60)
    label: str = Field(min_length=1, max_length=200)
    sort_order: int | None = None
    active: bool = True


class SectionUpdate(BaseModel):
    label: str | None = Field(default=None, min_length=1, max_length=200)
    sort_order: int | None = None
    active: bool | None = None


# ----------------------------------------------------------------------- fields

class FieldBase(BaseModel):
    """
    The register's own columns, all optional except the four that identify and
    render a field.

    Everything else is nullable in the register itself — 486 of 566 rows carry
    no max_length, 563 carry no condition — so demanding any of it here would
    make most of the register unrepresentable.
    """

    label: str = Field(min_length=1, max_length=200)
    field_type: str = Field(min_length=1, max_length=30)
    requirement: str = Field(default="Optional", max_length=20)

    sort_order: int | None = None
    max_length: int | None = None
    picklist_key: str | None = Field(default=None, max_length=120)
    lookup_target: str | None = Field(default=None, max_length=60)
    lookup_filter: str | None = None
    values_note: str | None = None
    capture_stage: int | None = None
    capture_any_stage: bool = False
    mandatory_from: int | None = None
    blocks_transition: str | None = Field(default=None, max_length=40)
    origin: str = Field(default="Administration", max_length=120)
    source_ref: str | None = Field(default=None, max_length=120)
    description: str = ""
    use_case: str = ""
    required_on_skip: bool | None = None
    visibility_condition: str | None = None
    condition: str | None = None
    computed_formula: str | None = None


class FieldCreate(FieldBase):
    module_key: str = Field(min_length=1, max_length=60)
    section_id: int
    # Lower case, digits and underscores: an api_name is an identifier in the
    # expression language (src/lib/spec/parser.ts) and a key on every stored
    # record. The register itself carries worse — leading digits, em dashes, a
    # trailing + — and those rows are preserved as they are; but nothing NEW
    # should be created that an expression has to be backtick-quoted to reach.
    api_name: str = Field(min_length=1, max_length=120, pattern=r"^[a-z][a-z0-9_]*$")


class FieldUpdate(BaseModel):
    """
    Every field optional — PATCH applies only what was sent.

    THIS EDITS THE CANONICAL DEFINITION, so every change here lands on every
    module the field appears on. That is the point: One-Time Revenue is one
    field, and renaming it renames it on Opportunities and Deals together. A
    module that needs a different word sets label_override on its own placement.

    api_name is absent. It is the key the value is stored under on every
    existing record, in every custom_fields JSONB entry, in every condition and
    every formula — renaming it would orphan all of that while looking like it
    worked. module_key is absent because a field does not live on a module any
    more: it has placements, and those are added and removed on their own
    endpoints.

    The placement-level keys below are accepted by the model and REFUSED by the
    endpoint, with a message naming the right route. Dropping them from the
    model instead would make them silently ignored, which is worse — an admin
    would move a field to another section and see nothing happen.
    """

    label: str | None = Field(default=None, min_length=1, max_length=200)
    field_type: str | None = Field(default=None, min_length=1, max_length=30)
    requirement: str | None = Field(default=None, max_length=20)
    section_id: int | None = None
    sort_order: int | None = None
    max_length: int | None = None
    picklist_key: str | None = Field(default=None, max_length=120)
    lookup_target: str | None = Field(default=None, max_length=60)
    lookup_filter: str | None = None
    values_note: str | None = None
    capture_stage: int | None = None
    capture_any_stage: bool | None = None
    mandatory_from: int | None = None
    blocks_transition: str | None = Field(default=None, max_length=40)
    origin: str | None = Field(default=None, max_length=120)
    source_ref: str | None = Field(default=None, max_length=120)
    description: str | None = None
    use_case: str | None = None
    required_on_skip: bool | None = None
    visibility_condition: str | None = None
    condition: str | None = None
    computed_formula: str | None = None


class RequiredUpdate(BaseModel):
    """
    The Required / Not Required toggle.

    True writes requirement 'Mandatory', false writes 'Optional'. This is an
    APPLICATION rule: it drives the red asterisk and layer 1 of the transition
    check. It does NOT touch the business table's nullability, and nothing
    here ever will — see models.FieldDefinition's docstring.

    A field on one of the other four requirements (Conditional, System,
    Computed, Advisory) is not moved by this toggle; the full requirement is
    editable through PATCH instead, so the toggle cannot silently flatten a
    Conditional field into a Mandatory one.
    """

    required: bool


class FieldOut(FieldBase):
    """
    One field as ONE MODULE shows it — a placement, with its definition inlined.

    The split is stated on the response rather than implied: an administrator
    has to be able to see, without opening anything, which properties are the
    field's and which are this module's.

        definition_* and the value-shape columns   change every module
        everything else                            change this module only

    `id` is the PLACEMENT id, because a list of fields on a module is a list of
    placements, and that is what gets reordered, removed and restored.
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    placement_id: int
    definition_id: int

    # ---- identity
    api_name: str
    module_key: str
    # The record shape this placement sits in. Almost always the module; a
    # child entity inside it for the ten api_names the register defines twice
    # in one module. See models.FieldDefinition.
    scope_key: str
    section_id: int
    section_label: str = ""

    # ---- naming. `label` is what THIS module calls it; definition_label is
    # the canonical name a rename would change everywhere.
    label_override: str | None = None
    definition_label: str = ""

    # ---- value behaviour on this module
    value_mode: str = "own"
    value_locked: bool = False
    editable: bool = True
    # Which module a read-through or carried value actually comes from — the
    # nearest ancestor that HOLDS it, past any that merely read it through.
    # Null for an owned field, which comes from nowhere.
    value_source_module: str | None = None
    # 'column' for a typed column, 'custom_fields' for the JSONB store, null
    # for read_through, which stores nothing at all.
    storage: str | None = None

    # ---- how many modules this field is live on. Drives "Used in 3 modules",
    # and the warning before an edit that changes all of them.
    module_count: int = 0
    origin_module: str | None = None

    # ---- state
    status: str
    definition_status: str = "active"
    deleted_at: datetime | None = None
    deleted_by: str | None = None
    # Was this placement removed by a delete-everywhere, or on its own? Restore
    # depends on the difference.
    deleted_by_cascade: bool = False
    # How the row was derived at migration. Audit only.
    provenance: str | None = None

    # ---- where it draws, as against what kind of field it is. See
    # models.FieldPlacement. Null anchor = "in my own section, in sort_order".
    anchor_field: str | None = None
    anchor_position: str | None = None
    layout_span: str | None = None

    created_at: datetime
    updated_at: datetime

    # True when spec/extensions.json binds a computed_expr, child_spec or
    # override to this field. The sidecar is hand-maintained and is NOT
    # regenerated, so deleting such a field leaves an orphaned key behind and
    # the screen should say so before, not after.
    has_extension: bool = False

    # Convenience mirror of requirement == 'Mandatory'. See RequiredUpdate.
    required: bool = False


class FieldDetailOut(BaseModel):
    """
    One canonical field and EVERY module it appears on.

    What the edit dialog loads. The placement list is what lets the screen say
    "this changes Opportunities and Deals" by naming them, instead of expecting
    the administrator to already know.
    """

    model_config = ConfigDict(from_attributes=True)

    definition_id: int
    scope_key: str
    api_name: str
    definition_label: str
    field_type: str
    max_length: int | None = None
    picklist_key: str | None = None
    lookup_target: str | None = None
    lookup_filter: str | None = None
    computed_formula: str | None = None
    values_note: str | None = None
    description: str = ""
    use_case: str = ""
    origin: str = ""
    source_ref: str | None = None
    origin_module: str | None = None
    definition_status: str = "active"
    has_extension: bool = False

    placements: list[FieldOut] = []


class PlacementCreate(BaseModel):
    """
    Show an existing field on another module. "Also show on…".

    Carries no label, type or picklist: those belong to the definition and are
    already decided. What a placement needs is where it goes on this module and
    how its value behaves here.
    """

    module_key: str = Field(min_length=1, max_length=60)
    section_id: int
    sort_order: int | None = None
    label_override: str | None = Field(default=None, max_length=200)
    capture_stage: int | None = None
    requirement: str | None = Field(default=None, max_length=20)
    # 'own' unless stated. read_through and carry_forward are refused when the
    # module has no ancestor holding the value — there would be nothing to read
    # or to copy.
    value_mode: str | None = None
    value_locked: bool | None = None
    storage: str | None = Field(default=None, max_length=20)


class PlacementUpdate(BaseModel):
    """
    Edit one module's copy of a field. Nothing on any other module moves.

    Every property here is one that measurement showed genuinely differs
    between modules: one_time_revenue sits in `STAGE 4 — RFP / RFI` at stage 4
    on Opportunities and in `ON CONVERSION` at stage 7 on Deals.

    api_name, type, picklist and lookup target are absent — they are the shape
    of the value and are the same everywhere by definition. Use
    PATCH /fields/{definition_id} for those.
    """

    section_id: int | None = None
    sort_order: int | None = None
    label_override: str | None = Field(default=None, max_length=200)
    capture_stage: int | None = None
    capture_any_stage: bool | None = None
    mandatory_from: int | None = None
    blocks_transition: str | None = Field(default=None, max_length=40)
    requirement: str | None = Field(default=None, max_length=20)
    required_on_skip: bool | None = None
    visibility_condition: str | None = None
    condition: str | None = None
    value_mode: str | None = Field(default=None, max_length=20)
    value_locked: bool | None = None
    editable: bool | None = None
    storage: str | None = Field(default=None, max_length=20)

    # ---- position, which is data rather than a consequence of the section.
    #
    # Sending anchor_field: null clears the anchor and returns the field to its
    # own section's list. anchor_position defaults to 'after' when an anchor is
    # set without one, because that is the placement almost every conditional
    # field wants: the box appears directly beneath the question that revealed
    # it. A bare anchor_position moves a field that is ALREADY anchored, and is
    # refused only when there is no anchor for it to be a position against.
    anchor_field: str | None = Field(default=None, max_length=120)
    anchor_position: str | None = Field(default=None, max_length=10)
    layout_span: str | None = Field(default=None, max_length=10)


# -------------------------------------------------------------------- picklists

class PicklistValueOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    picklist_key: str
    key: str
    label: str
    sort_order: int
    active: bool


class PicklistValueCreate(BaseModel):
    picklist_key: str = Field(min_length=1, max_length=120)
    key: str = Field(min_length=1, max_length=120, pattern=r"^[A-Za-z0-9_$.\-/+ ]+$")
    label: str = Field(min_length=1, max_length=200)
    sort_order: int | None = None
    active: bool = True


class PicklistValueUpdate(BaseModel):
    """
    `key` is absent. It is the value already written into business rows, into
    every lookup filter and into the register's own conditions, so renaming it
    would silently orphan stored data — the label is what a reader sees, and
    that is editable. A value that should no longer be offered is deactivated.
    """

    label: str | None = Field(default=None, min_length=1, max_length=200)
    sort_order: int | None = None
    active: bool | None = None


class PicklistOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    picklist_key: str
    label: str | None = None
    sort_order: int
    active: bool
    values: list[PicklistValueOut] = []
    # How many register fields name this picklist. Deactivating one that 40
    # fields use should look different from deactivating an unused one.
    field_count: int = 0


class PicklistCreate(BaseModel):
    picklist_key: str = Field(min_length=1, max_length=120, pattern=r"^[a-z][a-z0-9_]*$")
    label: str | None = Field(default=None, max_length=200)
    sort_order: int | None = None
    active: bool = True


class PicklistUpdate(BaseModel):
    label: str | None = Field(default=None, max_length=200)
    sort_order: int | None = None
    active: bool | None = None


# ----------------------------------------------------------------------- stages

class StageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    stage: int
    name: str
    prob_min: int | None = None
    prob_max: int | None = None
    owner_role: str | None = None
    bid_phase: str | None = None
    applies_to: str | None = None
    sort_order: int
    active: bool


class StageCreate(BaseModel):
    stage: int = Field(ge=0)
    name: str = Field(min_length=1, max_length=120)
    prob_min: int | None = Field(default=None, ge=0, le=100)
    prob_max: int | None = Field(default=None, ge=0, le=100)
    owner_role: str | None = Field(default=None, max_length=30)
    bid_phase: str | None = Field(default=None, max_length=60)
    applies_to: str | None = Field(default=None, max_length=20)
    sort_order: int | None = None
    active: bool = True


class StageUpdate(BaseModel):
    """`stage` is absent: the number is the identity every record stores."""

    name: str | None = Field(default=None, min_length=1, max_length=120)
    prob_min: int | None = Field(default=None, ge=0, le=100)
    prob_max: int | None = Field(default=None, ge=0, le=100)
    owner_role: str | None = Field(default=None, max_length=30)
    bid_phase: str | None = Field(default=None, max_length=60)
    applies_to: str | None = Field(default=None, max_length=20)
    sort_order: int | None = None
    active: bool | None = None


# ---------------------------------------------------------------------- reorder

class ReorderRequest(BaseModel):
    """
    The ids of the things being ordered, in the order they should now be in.

    A whole-list replacement rather than a move-this-one-here instruction: the
    screen already knows the full order it wants, and sending it entire means a
    reorder cannot half-apply and leave two rows claiming position 3.
    """

    ids: list[int] = Field(min_length=1)


class PicklistReorderRequest(BaseModel):
    """Picklists are keyed by string, so their reorder cannot reuse ReorderRequest."""

    keys: list[str] = Field(min_length=1)


# ------------------------------------------------------------------- validation

class ValidationOut(BaseModel):
    ok: bool
    errors: list[str]
    warnings: list[str]
    # extensions.json keys naming a field the draft no longer carries.
    orphaned_sidecar_refs: list[str] = []


# --------------------------------------------------------------------- versions

class MetadataVersionOut(BaseModel):
    """A published version WITHOUT its snapshot — the list shape."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    version_no: int
    status: str
    note: str | None = None
    restored_from: int | None = None
    created_by: str | None = None
    created_at: datetime
    published_by: str | None = None
    published_at: datetime | None = None
    # Sizes, so the version list can show what a version contained without
    # shipping a 2MB snapshot per row.
    field_count: int = 0
    picklist_count: int = 0
    stage_count: int = 0


class MetadataVersionDetail(MetadataVersionOut):
    snapshot: dict[str, Any]


class PublishRequest(ActingUser):
    note: str | None = Field(default=None, max_length=2000)


class RollbackRequest(ActingUser):
    note: str | None = Field(default=None, max_length=2000)


class PublishResult(BaseModel):
    version: MetadataVersionOut
    validation: ValidationOut
    # Repo-relative paths of the regenerated spec files.
    written: list[str]


class DraftStatus(BaseModel):
    """
    What is waiting to be published.

    `changes` compares the live draft against the last published version's
    snapshot — the review step between editing and publishing, so nobody
    publishes without seeing what they are publishing.
    """

    published_version: int | None = None
    published_at: datetime | None = None
    has_changes: bool = False
    changes: list[str] = []
    validation: ValidationOut
    counts: dict[str, int] = {}
