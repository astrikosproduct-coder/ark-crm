export type FieldType =
  | 'autonumber'
  | 'text'
  | 'lookup'
  | 'picklist'
  | 'number'
  | 'date'
  | 'currency'
  | 'checkbox'
  | 'computed'
  | 'richtext'
  | 'childlist'
  | 'longtext'
  | 'multiselect'
  | 'file'
  | 'datetime'
  | 'percent'
  | 'url'
  | 'email'

export type Requirement =
  | 'System'
  | 'Mandatory'
  | 'Conditional'
  | 'Computed'
  | 'Advisory'
  | 'Optional'

/**
 * One column of a childlist row.
 *
 * Deliberately the same vocabulary a field in the register uses, so a column is
 * read and rendered by exactly the code that reads and renders a field — see
 * childColumnAsField in lib/spec/childSpec.ts.
 */
export interface ChildColumn {
  /** Key this column is stored under inside the row object. */
  api_name: string
  label: string
  type: FieldType
  /** Demanded on every row. See validateChildRows for when it bites. */
  required?: boolean
  /** Column width hint in px, applied as a minimum so the table still stretches. */
  width?: number
  /** picklist and multiselect columns name a key in spec/picklists.json. */
  picklist?: string
  /** lookup columns name the entity their target collection holds. */
  lookup_target?: string
  /** The register's prose filter, shown to the user when nothing matches. */
  lookup_filter?: string
  /** Executable form of the above. Same semantics as a field's. */
  lookup_filter_expr?: string
  /** Evaluated once per row. Identifiers resolve to a sibling column first,
   * then to a field of the parent record — see compileForChildRow. */
  computed_expr?: string
  /** The prose formula, for the column's tooltip. Never parsed. */
  computed_formula?: string
  max_length?: number
  /** Tooltip on the column header. */
  description?: string
}

/**
 * A column is either an inline definition or a `"<module>.<api_name>"` ref to a
 * field the register already carries. A ref means "this column IS that field",
 * and it inherits the field's type, picklist, lookup, formula and requirement —
 * which is how the milestone_—_* and guarantee_—_* fields become row columns
 * without being restated.
 */
export type ChildColumnRef = string | ChildColumn

/**
 * Fields mirrored between a childlist row and the record its trigger column
 * looks up — attendee -> contact, say. Declared in spec/extensions.json
 * alongside the childlist's own child_spec, read by ChildListTable and by
 * the module's afterSave wiring. See leads.demo_attendees for the shape this
 * exists for.
 */
export interface ChildFieldSync {
  /** The row column whose value, once picked, drives the fill — "attendee". */
  trigger_column: string
  /** Module the trigger column's lookup_target resolves to — "contacts". */
  target_module: string
  /** row column api_name -> target module's api_name. Same value both ways;
   * the two names differ where the row and the target module name the same
   * idea differently (organisation on the row, account on a contact). */
  mirror: Record<string, string>
}

/** A childlist row shape. Declared in spec/extensions.json, never in fields.json. */
export interface ChildSpec {
  /**
   * "stated" — the register actually defines this row shape.
   * "inferred" — it was derived, and `basis` says from what.
   *
   * Never upgrade an inference to stated because the table now renders. The
   * render is the prototype working; the gap is still in the register, and an
   * inferred spec stays on the Spec Health page until the register closes it.
   */
  origin: 'stated' | 'inferred'
  /** Required when origin is "inferred": what the shape was derived from. */
  basis?: string
  columns: ChildColumnRef[]
  /** Present when rows are records of another module rather than inline rows. */
  child_module?: string
  /** Linked-record lists are displayed, not edited. */
  readonly?: boolean
  /** Overrides "Add row" on the button — "Add attendee", "Add milestone". */
  add_label?: string
  /** Singular noun for the delete confirmation — "attendee", "milestone". */
  row_noun?: string
}

/** The sidecar entry for one field. See spec/README.md. */
export interface FieldExtension {
  computed_expr?: string
  lookup_filter_expr?: string
  child_spec?: ChildSpec
  child_field_sync?: ChildFieldSync
  /**
   * The field carries the record's pipeline stage, and a stage moves ONLY
   * through a recorded transition — never as a side effect of saving a form.
   *
   * A field marked this way renders read-only wherever the form engine shows
   * it, and is stripped from the payload when an EXISTING record is saved. On
   * a create it is still written, because that is the record establishing the
   * stage it opens at rather than a save quietly moving it.
   */
  transition_owned?: boolean
  /**
   * Ghost text inside an empty input. Prompts the user for the KIND of thing
   * the box wants, which a label cannot carry and a tooltip hides until hovered.
   * Never a value and never validated — an empty field is still empty.
   */
  placeholder?: string
  /**
   * A computed field whose value cannot be written in the expression language,
   * resolved by a named function instead — see resolvers.ts.
   *
   * progression_pct needs the ordered stage list, which is not a field of any
   * record, so no expression over api_names can produce it. The escape hatch is
   * ONE NAME looked up in a fixed table, never an eval: the same containment
   * transition_owned uses. A name with no resolver behind it reads blank and is
   * reported, exactly like a missing computed_expr.
   */
  computed_by?: string
  /**
   * Declared in extensions.json new_fields as plumbing rather than as a
   * business field — the parent_lead / parent_opportunity links that
   * carry-forward-by-reference needs. Counted separately on Spec Health so a
   * reviewer is not asked to approve a lookup as though it were a new
   * requirement.
   */
  structural?: boolean
  /** Why a field that should carry one of the above does not. */
  unexpressed?: string
  /** A judgement call made while translating prose, recorded for review. */
  note?: string
}

/** Exactly the columns build_spec.py emits. Do not add to this interface. */
export interface RawFieldSpec {
  module: string
  section: string
  order: number
  api_name: string
  label: string
  type: FieldType
  max_length: number | null
  picklist: string | null
  lookup_target: string | null
  lookup_filter: string | null
  values_note: string | null
  capture_stage: number | null
  capture_any_stage: boolean
  mandatory_from: number | null
  blocks_transition: string | null
  requirement: Requirement
  origin: string
  source_ref: string
  description: string
  use_case: string
  required_on_skip: boolean | null
  visibility_condition: string | null
  condition: string | null
  computed_formula: string | null
}

/**
 * How a field came to be on the module it is on, after spec/module_split.json
 * has been applied.
 *
 *   own            the register writes it on this module and it stayed
 *   moved          reassigned by capture stage — a Stage 5 field is an
 *                  Opportunity field wherever the register happened to file it
 *   shared         a CROSS-CUTTING or SYSTEM field placed on all three modules
 *   own_instance   per-record state each module keeps its own copy of
 *   read_through   resolved from the parent record and never stored here
 *   new            declared in extensions.json new_fields
 */
export type FieldCarry = 'own' | 'moved' | 'shared' | 'own_instance' | 'read_through' | 'new'

/** A raw field with its sidecar entry merged on top. What components consume. */
export interface FieldSpec extends RawFieldSpec, FieldExtension {
  /**
   * "<module>.<api_name>" — the short sidecar key. NOT unique: nine api_names
   * are defined in two sections of one module. Use it to look a field up only
   * through fieldByRef, which refuses to resolve an ambiguous one.
   */
  ref: string
  /**
   * "<module>.<section>.<api_name>" — always unique, so this is the identity of
   * a field and the right React key. A sidecar entry may key on it to reach one
   * definition of a duplicated name.
   */
  qref: string
  /** How this field arrived on this module. See FieldCarry. */
  carry?: FieldCarry
  /**
   * The module the register itself writes this field on, when the split moved
   * or copied it somewhere else. `leads` for every Stage 4-7 field.
   */
  register_module?: string
  /** The register's own `order`, before the split renumbered the module. */
  register_order?: number
  /**
   * The module this field's value is resolved from, for a read_through field.
   * The value is NEVER stored on this record — carrying it by reference is what
   * stops the same End Client existing in three places and drifting.
   */
  read_through_from?: string
  /** The lookup field on THIS record holding the parent's id. */
  read_through_via?: string
}

/** A module's list-screen column set. Declared in spec/extensions.json. */
export interface ListViewSpec {
  /** Field references of the form "<module>.<api_name>", in column order. */
  columns: string[]
  /** api_name the list sorts by until the user clicks a header. */
  default_sort: string
  /** api_names the free-text filter searches. */
  search: string[]
}

/** A named subset of one section's fields. Declared in spec/extensions.json. */
export interface FieldSetSpec {
  module: string
  section: string
  /** Bare api_names, in the order they should render. */
  fields: string[]
}

/** Partner Playbook §6.2 numbers the register does not carry as data. */
export interface PartnerRegistrationSpec {
  /** 89, not 90: the window includes the start day. */
  exclusivity_days: number
  /**
   * The 48-hour SLA expressed in whole days, which is all `date` can carry.
   * Nothing in the app displays or computes hours — see `precision_limits`.
   */
  acknowledgement_sla_days: number
  /** Days remaining below which a live registration reads as Expiring. */
  expiring_within_days: number
  capture_fields: FieldSetSpec
  /** The three criteria a conflict is weighed against. */
  adjudication_criteria: FieldSetSpec
  /** What the adjudicator decides once the criteria are assessed. */
  adjudication_outcome: FieldSetSpec
}

/**
 * A note recorded by hand in the sidecar against a field or a whole module.
 *
 * Used for two different things, kept in separate blocks: `open_questions` are
 * gaps somebody must answer, `precision_limits` are things the register's types
 * cannot express and which are not going to change.
 */
export interface SpecNote {
  /** "module.api_name", or a bare module when it is about the sheet. */
  ref: string
  detail: string
}

/** How one seed collection is reconciled with the register. See spec/README.md. */
export interface SeedNormalisationSpec {
  /** The module in fields.json whose api_names the collection should use. */
  module: string
  /** Seed key → register api_name. */
  rename?: Record<string, string>
}

export interface PicklistOption {
  key: string
  label: string
  sort: number
  active: boolean
}

export type PicklistMap = Record<string, PicklistOption[]>
