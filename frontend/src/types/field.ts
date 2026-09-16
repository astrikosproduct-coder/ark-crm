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
  | 'phone'

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
  /**
   * api_names of columns that belong to the row but are NOT captured on this
   * module's screen — they are still columns of the row, and still consumed
   * from the register, they are simply asked for somewhere else.
   *
   * payment_milestones is the case this exists for: Milestone, % of Contract,
   * Trigger and Planned Date are commercial terms agreed on the Opportunity at
   * Stage 6, while Actual, Invoice, Payment Received and Status are facts of
   * delivery recorded on the Deal at Stage 8. Dropping the four from `columns`
   * instead would put them back on the form as loose fields — see
   * isChildColumnOnly — and one of them is Mandatory.
   */
  captured_elsewhere?: string[]
  /**
   * Columns summed under the table — % of Contract across the payment
   * milestones. Shown, never enforced: nothing in the register says a schedule
   * must total 100%, so the total is stated and a schedule that differs is
   * flagged rather than refused.
   */
  total_columns?: string[]
  /**
   * Values a new row takes when one column is chosen — the eight standard
   * payment milestones and their percentages and triggers.
   *
   * A DEFAULT, never a rule: every filled column stays editable, and a value
   * already typed is not overwritten. `by` is the column that selects the
   * default; `values` is keyed on that column's stored value.
   */
  row_defaults?: {
    by: string
    values: Record<string, Record<string, unknown>>
    /** Button that adds one row per entry above, in picklist order. */
    add_all_label?: string
  }
  /** Present when rows are records of another module rather than inline rows. */
  child_module?: string
  /** Linked-record lists are displayed, not edited. */
  readonly?: boolean
  /** Overrides "Add row" on the button — "Add attendee", "Add milestone". */
  add_label?: string
  /** Singular noun for the delete confirmation — "attendee", "milestone". */
  row_noun?: string
}

/**
 * The sidecar entry for one field. See spec/README.md.
 *
 * `computed_expr` was here until B2 and is now a register column on
 * RawFieldSpec above — an admin can write an expression, which is the whole
 * point, and a field cannot be marked `computed` with nothing to compute. It
 * must NOT be redeclared here: FieldSpec extends both interfaces, and two
 * declarations of one member is a type error rather than a merge.
 *
 * What is left is deliberately what an admin cannot author: names of frontend
 * functions (`child_spec`, `lookup_filter_expr`), and the prototype's recorded
 * departures from the register (`type_override`, `note`) — which are findings
 * for the reviewer, not corrections to apply.
 */
export interface FieldExtension {
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
   * days_in_current_stage needs a derived date and the clock, neither a field of
   * the record, so no expression over api_names can produce it. The escape hatch is
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
  /**
   * Overrides the register's own `type` for this field — a deliberate BUILD
   * decision layered on top of the workbook, not a register correction (those
   * go in module_split.json's register_corrections instead). fields.json is
   * never hand-edited, so this is the only legitimate way to change how a
   * register field renders: every upload-style field became a link (url)
   * field prototype-wide, since there is nowhere for an uploaded file to go.
   *
   * Named `type_override`, not `type` — FieldSpec already inherits a
   * mandatory `type` from RawFieldSpec, and TypeScript refuses to extend two
   * interfaces that declare the same member differently. Applied explicitly
   * in lib/spec/index.ts's merge, not by the generic ext spread.
   */
  type_override?: FieldType
  /** Overrides the register's own label, same reasoning and same explicit
   * application as `type_override` above (RawFieldSpec.label is mandatory
   * too) — e.g. "RFP Document" becoming "RFP Document Link" alongside
   * file -> url. */
  label_override?: string
  /**
   * PHASE-1 FREEZE: the field's lookup_target is a Round-5 table (products,
   * quotes, poc, bid, gates) with no records to resolve against yet. Renders
   * disabled with a "coming soon" tooltip instead of a combobox with nothing
   * in it — see LockedField in FieldControl.tsx. The register's own type is
   * untouched; this only changes how it renders, same as type_override.
   * Drop the flag once the target table ships and the lookup works for real.
   */
  phase1_locked?: boolean
  /**
   * This percent field STORES A FRACTION: 0.70 on the wire and in the column,
   * 70 in the box. progression_pct and probability_pct are the only fields like
   * this — Numeric(5,4) columns. See app/models.py and
   * app/progression.py::serialise_pct, which states the convention.
   *
   * Declared rather than guessed. lib/format.ts's percent() infers it from the
   * value being <= 1, which is fine for DISPLAY but cannot be used while
   * someone is typing: "1" would mean 100% on one keystroke and 1% on the
   * next. FieldControl scales the edit box by this flag alone.
   */
  stored_as?: 'fraction'
  /**
   * Picklist keys this PLACEMENT must not offer. For a value that belongs to one
   * module of a picklist several modules share — POC_PILOT_DEAL is a Deal status
   * on the status list Leads and Opportunities also use. Hiding is not the
   * boundary; the server refuses the value too (app/progression.py).
   */
  exclude_options?: string[]
  /**
   * This list is not closed: the control offers the register's options plus
   * "+ Other", and choosing it swaps the dropdown for a text box.
   *
   * What gets stored is WHAT THE USER TYPED, not a picklist key. Three
   * consequences, and a field only earns this flag when all three are
   * acceptable: the value is invisible to anything comparing against a key (a
   * condition, a criterion, a formula); it is a value on one record rather
   * than an option anyone else will see, because Administration owns the
   * picklist and this does not touch it; and the column must accept free text
   * at its own length.
   *
   * Declared per PLACEMENT, so a shared picklist can be open on the module
   * that needs it and closed on the one that must not.
   *
   * State the column's own length in the SAME sidecar entry, as `max_length`.
   * It is deliberately not declared on this interface — RawFieldSpec already
   * requires that key, and declaring it here too makes the two parents of
   * FieldSpec disagree — but the merge spreads the sidecar over the register
   * row, so the value lands on field.max_length and caps the text box. Without
   * it someone types past what the column holds and the save fails at the
   * database.
   */
  allow_custom_value?: boolean
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
  /** Inclusive bounds on a number field. Absent or null: unbounded on that side. */
  min_value?: number | null
  max_value?: number | null
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

  // ---------------------------------------------------------------
  // RESOLVED FROM field_placements. Present on every row since Round 7.
  //
  // These used to be computed in the browser by src/lib/spec/moduleSplit.ts,
  // which re-homed fields by capture stage and added the shared, own-instance
  // and read-through copies. They are columns now, so the projection is gone
  // and there is one authority for where a field appears: the database.
  // ---------------------------------------------------------------

  /** How this module's copy of the value behaves. See ValueMode. */
  value_mode: ValueMode
  /** May a carried value diverge from its source afterwards? */
  value_locked: boolean
  /** False for read_through, which renders read-only. */
  editable: boolean
  /**
   * The module a read-through value is resolved from — the nearest ancestor
   * that actually HOLDS it, past any that merely read it through. Null unless
   * the value comes from somewhere else.
   */
  read_through_from: string | null
  /** The lookup field on THIS record holding that ancestor's id. */
  read_through_via: string | null
  /**
   * The module the field's canonical definition originated on. `leads` for
   * every Stage 4-7 pipeline field, which is what keeps a sidecar key written
   * as `leads.rfp_received_date` resolving after the field's placement moved
   * to Opportunities.
   */
  register_module: string | null
  /** This placement's own order. Kept for Spec Health's duplicate report. */
  register_order: number | null

  /**
   * WHERE THIS FIELD DRAWS, as against what kind of field it is.
   *
   * `section` says what kind of field this is — CROSS-CUTTING, SYSTEM, RECORD
   * STATE. `anchor_field` says where it goes: the api_name on this module
   * beside which it renders, wherever that field happens to be, including in a
   * section this field does not belong to. Null is the ordinary case and means
   * "in my own section's list, in `order`" — the behaviour every field had
   * before anchors existed.
   *
   * This is what lets a conditional field work at all. Its visibility_condition
   * is evaluated against LIVE form state, so it has to be inside the same
   * RecordForm as the field that triggers it; otherwise the reveal cannot
   * happen until after a save, and the user pays two saves for one answer.
   */
  anchor_field: string | null
  /**
   * 'after'  — a new row directly beneath the anchor, sharing its grid cell.
   * 'beside' — the adjacent grid cell: spliced into the section's flat field
   *            list immediately after the anchor.
   * Null exactly when anchor_field is.
   */
  anchor_position: 'after' | 'beside' | null
  /**
   * How much of the two-column form grid this field takes. Null means
   * "whatever this field type takes on its own" — see FULL_WIDTH in
   * FieldRow.tsx — which is what every field carried before anchors existed.
   */
  layout_span: 'full' | 'half' | null

  /**
   * One value per RECORD, or one per STAGE. See StageScoped.
   *
   * A column since 0015; it was a rule in spec/extensions.json before that,
   * which is why nobody could make a field sticky without editing a file. The
   * rule caught fields by section and condition; this holds the answer, so an
   * admin can change one field without silently changing four others.
   */
  stage_scoped: StageScoped

  /**
   * The expression the engine evaluates — `one_time_cost + annual_recurring`.
   *
   * NOT `computed_formula`, which is the register's own English sentence about
   * the same rule and is rendered as help text beside it. Both are shown on
   * purpose: where they disagree, the disagreement is a finding for the
   * reviewer, not a bug to tidy away. See FieldRow.tsx.
   */
  computed_expr: string | null
}

/**
 * How many values a field keeps, and what a new stage inherits.
 *
 * Values live under `<api_name>__s<stage>` — see lib/stageScope.ts.
 *
 *   none            one value per record. Almost every field.
 *   carry_forward   a stage with no answer of its own shows the nearest
 *                   earlier stage that has one. The base api_name also holds
 *                   the current answer, so list columns and the readiness
 *                   engine keep reading one number and know nothing about it.
 *   sticky          answered at the stage its condition became true, and never
 *                   carried. Two holds get two reasons. The base api_name is
 *                   never written — there is no single "the" on-hold reason.
 *
 * Orthogonal to ValueMode: that says where an OPENING value comes from, this
 * says how many values there are. expected_close_month is both.
 */
export type StageScoped = 'none' | 'carry_forward' | 'sticky'

/**
 * How a field's VALUE behaves on the module it is on.
 *
 * Read straight off field_placements.value_mode — this is data now, not
 * something the loader works out. Three modes, and the two a field is not are
 * what define the one it is:
 *
 *   own            this module stores the value in its own table. Absorbs the
 *                  old `own`, `moved`, `shared` and `own_instance`, which all
 *                  meant exactly this and differed only in how the old loader
 *                  picked the field and which section the copy landed in.
 *   read_through   never stored here; resolved from the parent every time it
 *                  is read, so the same End Client cannot exist in three
 *                  places and drift. Rendered read-only.
 *   carry_forward  copied from the parent ONCE when the record is created,
 *                  and owned from then on. A Deal opens at the Opportunity's
 *                  figure and may renegotiate it.
 */
export type ValueMode = 'own' | 'read_through' | 'carry_forward'

/**
 * A raw field with its sidecar entry merged on top. What components consume.
 *
 * Since Round 7 the module, section and order in RawFieldSpec are already the
 * ones the field renders under — spec/fields.json is generated from
 * field_placements, one row per module a field appears on. Nothing is
 * re-homed at load time any more.
 */
export interface FieldSpec extends RawFieldSpec, FieldExtension {
  /**
   * "<module>.<api_name>" — the short sidecar key. NOT unique: ten api_names
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
