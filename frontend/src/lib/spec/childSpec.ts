import { apiNamesOf, fieldByRef, fields as allFields, isAmbiguous, sectionsDefining } from './index'
import { FUNCTION_NAMES } from './evaluate'
import { identifiersOf, parse, SpecExprError, type Node } from './parser'
import type { ChildColumn, ChildFieldSync, ChildSpec, FieldSpec, Requirement } from '@/types/field'

/**
 * A childlist row shape, resolved against the register.
 *
 * Every column arrives here as a FieldSpec, whatever form it was declared in.
 * That is the whole point: a table cell then renders through FieldControl, the
 * same one control layer every other field on the screen goes through, instead
 * of a second set of table-only inputs that would drift away from it.
 */
export interface ResolvedChildColumn {
  /** Stable React key, unique within the table. */
  key: string
  /** What the cell renders as. Synthesised for an inline column. */
  field: FieldSpec
  required: boolean
  width?: number
}

export interface ResolvedChildSpec {
  origin: ChildSpec['origin']
  basis?: string
  readonly: boolean
  child_module?: string
  add_label: string
  row_noun: string
  columns: ResolvedChildColumn[]
  /**
   * Columns of the same row that are captured on another module's screen —
   * see ChildSpec.captured_elsewhere. Resolved exactly like `columns`, and
   * kept apart from them: this table does not draw them, and the screen that
   * does asks for them by name.
   */
  elsewhereColumns: ResolvedChildColumn[]
  row_defaults?: ChildSpec['row_defaults']
  total_columns: string[]
  /** Column refs that name a field the register no longer carries. Dropped. */
  orphanedColumns: string[]
}

const cache = new Map<string, ResolvedChildSpec | undefined>()

/**
 * The row shape of a childlist field, or undefined when the sidecar declares
 * none. Memoised on the field's qref — the spec is static after import.
 */
export function childSpecFor(field: FieldSpec): ResolvedChildSpec | undefined {
  if (field.type !== 'childlist') return undefined
  const hit = cache.get(field.qref)
  if (hit !== undefined || cache.has(field.qref)) return hit
  const resolved = resolve(field)
  cache.set(field.qref, resolved)
  return resolved
}

/**
 * The row <-> linked-record field mirror declared beside a childlist's own
 * child_spec, or undefined when the sidecar declares none. See
 * leads.demo_attendees for the shape this exists for.
 */
export function childFieldSyncFor(field: FieldSpec): ChildFieldSync | undefined {
  return field.child_field_sync
}

function resolve(field: FieldSpec): ResolvedChildSpec | undefined {
  const spec = field.child_spec
  if (!spec) return undefined

  const columns: ResolvedChildColumn[] = []
  const orphanedColumns: string[] = []
  // Nothing in a linked-record list is demanded of this form — the rows are
  // other people's records. A required marker there would ask the user for
  // something they cannot supply here.
  const readonly = spec.readonly === true

  for (const entry of spec.columns) {
    if (typeof entry === 'string') {
      const referenced = fieldByRef(entry)
      if (!referenced) {
        orphanedColumns.push(entry)
        continue
      }
      // A ref column IS the register's field, so it inherits the register's own
      // requirement — which is why Planned Date is demanded on a milestone row
      // and the other three milestone dates, Conditional in the register, are not.
      columns.push({
        key: referenced.qref,
        field: referenced,
        required: !readonly && referenced.requirement === 'Mandatory',
        width: undefined,
      })
      continue
    }

    columns.push({
      key: `${field.qref}::${entry.api_name}`,
      field: childColumnAsField(field, entry),
      required: !readonly && entry.required === true,
      width: entry.width,
    })
  }

  // Split AFTER resolution, so a column captured elsewhere is resolved by the
  // same rules and keeps its register requirement — it is the same column of
  // the same row, asked for on a different screen.
  const elsewhere = new Set(spec.captured_elsewhere ?? [])
  const here = columns.filter((c) => !elsewhere.has(c.field.api_name))
  const elsewhereColumns = columns.filter((c) => elsewhere.has(c.field.api_name))

  return {
    origin: spec.origin,
    basis: spec.basis,
    readonly,
    child_module: spec.child_module,
    add_label: spec.add_label ?? 'Add row',
    row_noun: spec.row_noun ?? 'row',
    columns: here,
    elsewhereColumns,
    row_defaults: spec.row_defaults,
    total_columns: spec.total_columns ?? [],
    orphanedColumns,
  }
}

/**
 * An inline column dressed as a FieldSpec.
 *
 * `module` is the PARENT's module, not child_module: a row-scoped expression
 * resolves a sibling column first and a field of the parent record second, so
 * the parent's namespace is the one it needs. `section` names the childlist it
 * belongs to, which is what a Spec Health row or an error message reads back.
 */
function childColumnAsField(parent: FieldSpec, column: ChildColumn): FieldSpec {
  const requirement: Requirement = column.required ? 'Mandatory' : 'Optional'
  const section = `${parent.section} · ${parent.label}`

  return {
    module: parent.module,
    section,
    order: 0,
    // A child column is not a placement — it is a column of a row inside one
    // field. It stores its value on the child row, is editable, and inherits
    // nothing, so the resolved keys take the values that say exactly that.
    value_mode: 'own',
    value_locked: false,
    editable: true,
    read_through_from: null,
    read_through_via: null,
    register_module: parent.register_module ?? parent.module,
    register_order: null,
    // A column draws where its table draws. There is no cell of the section
    // grid for it to be anchored into, so anchoring is not a thing a column
    // can carry — see lib/spec/anchors.ts.
    anchor_field: null,
    anchor_position: null,
    layout_span: null,
    // A child row is not on a stage — the TABLE is the field, and the field is
    // what carries a stage. Per-stage values key on the record's stage, and a
    // milestone row has none of its own to key on.
    stage_scoped: 'none',
    api_name: column.api_name,
    label: column.label,
    type: column.type,
    max_length: column.max_length ?? null,
    picklist: column.picklist ?? null,
    lookup_target: column.lookup_target ?? null,
    lookup_filter: column.lookup_filter ?? null,
    values_note: null,
    capture_stage: parent.capture_stage,
    capture_any_stage: parent.capture_any_stage,
    mandatory_from: column.required ? parent.mandatory_from : null,
    blocks_transition: column.required ? parent.blocks_transition : null,
    requirement,
    origin: 'Sidecar',
    source_ref: parent.qref,
    description: column.description ?? '',
    use_case: '',
    required_on_skip: parent.required_on_skip,
    visibility_condition: null,
    condition: null,
    computed_formula: column.computed_formula ?? null,
    computed_expr: column.computed_expr ?? null,
    lookup_filter_expr: column.lookup_filter_expr,
    ref: `${parent.module}.${column.api_name}`,
    qref: `${parent.module}.${section}.${column.api_name}`,
  }
}

// --------------------------------------------- fields consumed as columns

let consumed: Set<string> | null = null

/**
 * qrefs of every field some child_spec names as a ref column.
 *
 * Derived rather than declared: a field is "consumed" precisely because a row
 * shape points at it, so there is nothing extra to keep in step. Computed on
 * first use, not at import, because this module is imported from index's own
 * dependents and must not read `fields` before index has finished evaluating.
 */
function consumedAsColumn(): Set<string> {
  if (consumed) return consumed
  const set = new Set<string>()

  for (const field of allFields) {
    if (field.type !== 'childlist' || !field.child_spec) continue

    // A LINKED-RECORD list points at another module's records —
    // deals.linked_expansion_leads lists Lead records. Its columns are real
    // fields of that other module and must go on rendering there; only an
    // INLINE child list consumes fields of its own module as a row shape.
    if (field.child_spec.child_module) continue

    for (const entry of field.child_spec.columns) {
      if (typeof entry !== 'string') continue
      const referenced = fieldByRef(entry)
      // Belt and braces on the same rule: never consume a field belonging to a
      // module other than the one the child list lives on.
      if (referenced && referenced.module === field.module) set.add(referenced.qref)
    }
  }

  consumed = set
  return set
}

/**
 * True when a field exists ONLY to define a column of a child list.
 *
 * The register writes these flat — the four milestone_—_* dates sit loose in
 * STAGE 7 — CLOSE, the seven guarantee_—_* fields loose in ON CONVERSION — but
 * they describe one ROW of a table, not one value on the record. Rendering them
 * both ways gave two places to type the same thing, only one of which is kept,
 * and left record-level validation demanding a value with nowhere to enter it:
 * milestone_—_planned_date is Mandatory from Stage 7, so once the flat field is
 * hidden it would block 7 → Deal forever.
 *
 * So a consumed field is not a record-level field at all. It is dropped from
 * the form (visibleFieldsOf) and from everything isUserEditable gates —
 * validateForSave, validateForTransition and the readiness panel — while the
 * child table goes on rendering it as a column with its register requirement
 * intact. Nothing is deleted from the register.
 */
export function isChildColumnOnly(field: FieldSpec): boolean {
  return consumedAsColumn().has(field.qref)
}

// ------------------------------------------------- row-scoped expressions

const rowCache = new Map<string, Node>()

/**
 * Compile an expression that will be evaluated against ONE CHILD ROW.
 *
 * compileFor checks identifiers against the module's api_names alone, which is
 * right for a record-level formula and wrong here: a row column
 * (`pct_of_contract`) is not a field of the module, and a record-level field
 * (`contract_value`) is not a column of the row. Both are legal in a row
 * expression, so both namespaces are accepted — and a name in neither still
 * throws, rather than evaluating to null and showing a plausible wrong number.
 *
 * A name defined in both resolves to the ROW, which is stated in spec/README.md
 * and is the only order that lets a column shadow the flat field it was derived
 * from — guarantee_—_value exists as both.
 */
export function compileForChildRow(
  module: string,
  columns: ResolvedChildColumn[],
  expr: string
): Node {
  const key = `${module}::${columns.map((c) => c.field.api_name).join(',')}::${expr}`
  const hit = rowCache.get(key)
  if (hit) return hit

  const ast = parse(expr)
  const rowNames = new Set(columns.map((c) => c.field.api_name))
  const moduleNames = apiNamesOf(module)

  for (const name of identifiersOf(ast)) {
    if (FUNCTION_NAMES.includes(name)) continue
    if (rowNames.has(name)) continue

    if (!moduleNames.has(name)) {
      throw new SpecExprError(
        `Unknown identifier ${JSON.stringify(name)} — it is neither a column of this ` +
          `child row nor a field of module ${JSON.stringify(module)}`,
        expr,
        name
      )
    }

    if (isAmbiguous(module, name)) {
      throw new SpecExprError(
        `Ambiguous identifier ${JSON.stringify(name)} for module ${JSON.stringify(module)}: ` +
          `defined in ${sectionsDefining(module, name).map((s) => JSON.stringify(s)).join(' and ')}.`,
        expr,
        name
      )
    }
  }

  rowCache.set(key, ast)
  return ast
}
