import { z } from 'zod'

import { childSpecFor, isChildColumnOnly, type ResolvedChildSpec } from './childSpec'
import { isVisible, requirementOf, type Values } from './conditions'
import { createRequiredFor, fieldOptions, fieldsOf, rangeOf, stageFieldOf } from './index'
import type { FieldSpec } from '@/types/field'

export interface FieldError {
  api_name: string
  label: string
  section: string
  message: string
}

export type Errors = Record<string, string>

/**
 * An empty array counts as blank.
 *
 * A childlist with no rows and a multiselect with nothing ticked are both
 * "nothing entered", and a Mandatory one has to say so at a transition. Without
 * this, `demo_attendees: []` satisfied "Required before 1 → 2".
 */
const BLANK = (v: unknown) =>
  v === null || v === undefined || v === '' || (Array.isArray(v) && v.length === 0)

/**
 * The register's Min value / Max value, both inclusive — '1 to 10' accepts 1 and 10.
 * The API refuses the same range on save (app/thresholds.py); this is the early,
 * on-screen half of it.
 */
function bounded(field: FieldSpec, schema: z.ZodNumber): z.ZodNumber {
  const low = field.min_value ?? undefined
  const high = field.max_value ?? undefined
  if (low === undefined && high === undefined) return schema
  const message =
    low !== undefined && high !== undefined
      ? `Must be between ${low} and ${high}`
      : low !== undefined
        ? `Must be at least ${low}`
        : `Must be at most ${high}`
  let s = schema
  if (low !== undefined) s = s.min(low, { message })
  if (high !== undefined) s = s.max(high, { message })
  return s
}

/**
 * The shape check for one field, ignoring whether it is required. Requirement
 * is layered on top because it depends on the record's values and, for
 * transitions, on the target stage.
 */
function shapeOf(field: FieldSpec): z.ZodTypeAny {
  const max = field.max_length ?? undefined

  switch (field.type) {
    case 'number':
      return bounded(field, z.number({ message: 'Must be a number' }))

    case 'currency':
      return bounded(
        field,
        z.number({ message: 'Must be an amount' }).min(0, { message: 'Cannot be negative' })
      )

    case 'percent':
      return z.number({ message: 'Must be a percentage' })

    case 'checkbox':
      return z.boolean()

    case 'date':
      return z
        .string()
        .regex(/^\d{4}-\d{2}-\d{2}$/, { message: 'Must be a date' })

    case 'datetime':
      return z
        .string()
        .regex(/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}/, { message: 'Must be a date and time' })

    case 'email':
      return z.email({ message: 'Must be an email address' })

    case 'phone': {
      // "+971 50 123 4567" — the dial code and the number in one string. Lenient
      // on shape, so a number typed before the dial code existed still saves.
      let s = z.string().regex(/^\+?[\d\s()./-]*$/, { message: 'Must be a phone number' })
      if (max) s = s.max(max, { message: `Longer than ${max} characters` })
      return s
    }

    case 'url':
      return z.url({ message: 'Must be a URL' })

    case 'picklist': {
      const keys = fieldOptions(field).map((o) => o.key)
      // A picklist with no set behind it (11 of them in the register) cannot
      // constrain anything, so it falls back to a free string rather than
      // rejecting everything the user types.
      if (!keys.length) return z.string()
      return z.enum(keys as [string, ...string[]], { message: 'Not one of the allowed values' })
    }

    case 'multiselect': {
      const keys = fieldOptions(field).map((o) => o.key)
      const item = keys.length
        ? z.enum(keys as [string, ...string[]], { message: 'Not one of the allowed values' })
        : z.string()
      return z.array(item)
    }

    case 'childlist':
      return z.array(z.record(z.string(), z.unknown()))

    case 'lookup':
      // The id of a record in the target collection. Existence is enforced by
      // the combobox, which only offers real records.
      return z.string()

    default: {
      let s = z.string()
      if (max) s = s.max(max, { message: `Longer than ${max} characters` })
      return s
    }
  }
}

/** Fields the user can be held to. Computed and System values are not typed in. */
export function isUserEditable(field: FieldSpec): boolean {
  return (
    field.type !== 'computed' &&
    field.type !== 'autonumber' &&
    field.requirement !== 'System' &&
    field.requirement !== 'Computed' &&
    // A read-through field's value lives on the parent record and is rendered
    // read-only here. Holding this record to it would demand something the user
    // cannot enter on this screen — and the parent already demanded it at the
    // stage that captures it. See field_placements.value_mode.
    field.value_mode !== 'read_through' &&
    // A field that only exists to define a child-list column is entered per
    // ROW, never on the record, so the record cannot be held to it. Its
    // requirement is enforced by validateChildRows instead.
    !isChildColumnOnly(field) &&
    // A locked Round-5 lookup is disabled — nobody can type a value into it —
    // so holding a record to it would make its blocks_transition stage
    // permanently unreachable. See LockedField in FieldControl.tsx.
    !field.phase1_locked &&
    // A value frozen on this record — a carried value locked against change, or
    // one the register marks not editable (a Deal's Contract Value). It renders
    // read-only and the server refuses a change, so a blank one cannot be
    // demanded: a paid-pilot Deal has no Opportunity and no ARR to carry.
    !field.value_locked &&
    field.editable !== false
  )
}

function checkShape(field: FieldSpec, value: unknown): string | null {
  if (BLANK(value)) return null
  const result = shapeOf(field).safeParse(value)
  if (result.success) return null
  return result.error.issues[0]?.message ?? 'Invalid value'
}

// ------------------------------------------------------------- child rows

/** One problem in one cell of one child row. */
export interface ChildRowError {
  /** 0-based index of the row in the childlist. */
  row: number
  /** api_name of the column, which is the key inside the row object. */
  api_name: string
  label: string
  message: string
}

export type ChildErrors = Record<string, ChildRowError[]>

function rowIsEmpty(spec: ResolvedChildSpec, row: Values): boolean {
  return spec.columns.every((c) => BLANK(row[c.field.api_name]))
}

/**
 * Validate the rows of one childlist against its declared row shape.
 *
 * `demandRequired` separates the two callers, and follows the rule the rest of
 * this module already applies to fields:
 *
 *   save       — shape everywhere, and required columns only on a row that has
 *                something in it. A half-filled record must stay savable, and a
 *                row the user has added but not typed into yet is not an error.
 *   transition — required columns on every row, empty ones included. A blank
 *                row is exactly what mandatory_from is meant to catch.
 *
 * A read-only childlist (a linked-record list) is never validated: its rows are
 * other people's records, not this form's input.
 */
export function validateChildRows(
  field: FieldSpec,
  rows: Values[],
  demandRequired: 'non_empty_rows' | 'all_rows'
): ChildRowError[] {
  const spec = childSpecFor(field)
  if (!spec || spec.readonly) return []

  const out: ChildRowError[] = []

  rows.forEach((row, index) => {
    const skipRequired = demandRequired === 'non_empty_rows' && rowIsEmpty(spec, row)

    for (const column of spec.columns) {
      if (!isUserEditable(column.field)) continue
      const value = row[column.field.api_name]

      const shape = checkShape(column.field, value)
      if (shape) {
        out.push({ row: index, api_name: column.field.api_name, label: column.field.label, message: shape })
        continue
      }

      if (column.required && !skipRequired && BLANK(value)) {
        out.push({ row: index, api_name: column.field.api_name, label: column.field.label, message: 'Required' })
      }
    }
  })

  return out
}

/** "Row 2 · Attendee — Required" and so on, capped so an error line stays readable. */
function summariseChildErrors(errors: ChildRowError[]): string {
  const first = errors
    .slice(0, 2)
    .map((e) => `Row ${e.row + 1} · ${e.label} — ${e.message}`)
    .join('; ')
  return errors.length > 2 ? `${first}; and ${errors.length - 2} more` : first
}

/**
 * Child rows of a module, read out of the record's own values.
 *
 * The form provider merges its child rows into `values` under the childlist's
 * api_name, and toPayload persists them the same way, so a childlist's rows are
 * reachable from a plain record with no second argument threaded through every
 * caller of this module.
 */
function rowsOf(values: Values, field: FieldSpec): Values[] {
  const v = values[field.api_name]
  return Array.isArray(v) ? (v as Values[]) : []
}

/**
 * What a save demands: formats and lengths only.
 *
 * A half-filled Stage 0 lead has to be savable — a BD user types a client name
 * and comes back tomorrow. Mandatory fields bite at the stage transition, not
 * here, which is what mandatory_from in the register actually means.
 */
export function validateForSave(module: string, values: Values): Errors {
  const errors: Errors = {}

  for (const field of fieldsOf(module)) {
    if (!isUserEditable(field)) continue
    // A hidden field keeps its value but is never validated — see the note on
    // retention in useRecordForm.
    if (!isVisible(field, values)) continue

    const message = checkShape(field, values[field.api_name])
    if (message) {
      errors[field.api_name] = message
      continue
    }

    if (field.type === 'childlist') {
      const rowErrors = validateChildRows(field, rowsOf(values, field), 'non_empty_rows')
      if (rowErrors.length) errors[field.api_name] = summariseChildErrors(rowErrors)
    }
  }

  return errors
}

/**
 * Child-row problems for a whole module, keyed by childlist api_name.
 *
 * The table needs the individual cells, not the one-line summary validateForSave
 * folds them into, so it reads this instead.
 */
export function validateChildrenForSave(module: string, values: Values): ChildErrors {
  const out: ChildErrors = {}

  for (const field of fieldsOf(module)) {
    if (field.type !== 'childlist' || !isVisible(field, values)) continue
    const rowErrors = validateChildRows(field, rowsOf(values, field), 'non_empty_rows')
    if (rowErrors.length) out[field.api_name] = rowErrors
  }

  return out
}

/** What an empty required field says about itself, wherever it is rendered. */
export const REQUIRED_MESSAGE = 'This is a required field.'

/**
 * Required fields that are still empty, keyed by api_name.
 *
 * Separate from validateForSave on purpose, and NOT merged into it: a save
 * enforces shape only, because a half-filled Stage 0 lead has to be savable —
 * a BD user types a client name and comes back tomorrow. What these block is
 * the stage move, which is layer 1 of the four-layer check.
 *
 * The rule is deliberately the same one the red asterisk uses — requirementOf,
 * so Mandatory always and Conditional when its condition holds. A field marked
 * required on screen and a field that says it is required have to be the same
 * set, or the form is arguing with itself.
 */
export function missingRequired(module: string, values: Values): Errors {
  const out: Errors = {}

  for (const field of fieldsOf(module)) {
    if (!isUserEditable(field)) continue
    if (!isVisible(field, values)) continue
    if (!requirementOf(field, values).required) continue
    if (!BLANK(values[field.api_name])) continue
    out[field.api_name] = REQUIRED_MESSAGE
  }

  return out
}

// ------------------------------------------------------------ due fields

/**
 * The stage a field's answer belongs to: mandatory_from, else the first number
 * of blocks_transition ("3 → 4"), else capture_stage. Null for a field of no
 * stage — an Account's or a Contact's, due always.
 */
export function dueStageOf(field: FieldSpec): number | null {
  if (field.mandatory_from !== null && field.mandatory_from !== undefined) return field.mandatory_from
  const blocks = /^(\d+)/.exec(field.blocks_transition ?? '')
  if (blocks) return Number(blocks[1])
  return field.capture_stage ?? null
}

export interface DueOptions {
  /** Stages the record jumped over and never stood at. Their fields are not
   *  demanded (decided 21 Sep 2026). */
  skipped?: readonly number[]
  /** Read the record as if it stood here — the stage being LEFT on a move. */
  atStage?: number | null
}

const STATUS_ONLY = new Set(['CLOSED_LOST', 'ON_HOLD'])

/** Mandatory in the register, never typed by a person: the stage moves by the
 *  Update Stage dialog, the status defaults to Open, and the percentages follow
 *  the stage. The server skips the same four (app/requirements.py). */
const SYSTEM_SET = new Set(['lead_status', 'progression_pct', 'probability_pct'])

/**
 * Required fields that are empty AND due now, keyed by api_name — the fields
 * that stop a save, and on a move, the fields that stop leaving the stage.
 *
 * THE SAME RULE THE SERVER APPLIES (backend/app/requirements.py). This copy
 * exists so the form can say what is missing and mark it before a request is
 * made; the server's refusal is the one that counts.
 *
 *   at stage S          fields due at S or earlier, minus skipped stages and
 *                       stages below the module's own range (the parent's)
 *   On Hold, Closed Lost  only the reason the status asks for
 *   Converted           nothing
 *   POC/Pilot Deal      nothing due at Stage 7 or before (decided 21 Sep 2026)
 *
 * Built on missingRequired, so "required" means what the red asterisk means.
 */
export function missingDue(module: string, values: Values, options: DueOptions = {}): Errors {
  const stageField = stageFieldOf(module)
  const status = typeof values.lead_status === 'string' ? values.lead_status : null
  if (stageField && status === 'CONVERTED') return {}

  const stage = options.atStage ?? (stageField ? stageOf(values[stageField]) : null)
  const range = rangeOf(module)
  const skipped = new Set(options.skipped ?? [])
  const statusOnly = Boolean(stageField && status && STATUS_ONLY.has(status))
  const pilotThrough = module === 'deals' && status === 'POC_PILOT_DEAL' ? 7 : null

  const out: Errors = {}
  for (const name of Object.keys(missingRequired(module, values))) {
    const field = fieldsOf(module).find((f) => f.api_name === name)
    if (!field) continue
    if (SYSTEM_SET.has(name) || name === stageField) continue
    if (statusOnly && !(field.condition ?? '').includes('lead_status')) continue
    const due = dueStageOf(field)
    if (stageField && due !== null && stage !== null) {
      if (due > stage) continue
      if (range && due < range[0]) continue
      if (due !== stage && skipped.has(due)) continue
      if (pilotThrough !== null && due <= pilotThrough) continue
    }
    out[name] = REQUIRED_MESSAGE
  }
  return out
}

export interface SaveOptions {
  /** The record is being created — nothing saved yet. */
  creating: boolean
  /** The values as last saved, to tell a field EMPTIED by this edit from one
   *  that was never filled. */
  saved: Values
  skipped?: readonly number[]
}

/**
 * Required fields that stop a SAVE — revised 21 Sep 2026: a stage move is the
 * gate, a save is not. The server applies the same rule (app/requirements.py).
 *
 *   new record            only createRequiredFor(module) — Leads: name, End
 *                         Client, BD Owner, Currency
 *   ordinary save         a field of a stage already LEFT may not be emptied;
 *                         the current stage may be saved half-filled
 *   pilot marked Paid     a move (the Lead becomes its Deal): the stage must
 *                         be complete, which asks for Pilot PO Received Date
 *   any save              the reason a status asks for (On Hold, Closed Lost)
 *   Accounts, Contacts    every required field, as before
 */
export function missingOnSave(module: string, values: Values, options: SaveOptions): Errors {
  const stageField = stageFieldOf(module)
  if (!stageField) return missingDue(module, values)
  if (values.lead_status === 'CONVERTED') return {}

  const stage = stageOf(values[stageField])
  if (module === 'leads' && String(values.pilot_commercial_model ?? '').toUpperCase() === 'PAID') {
    return missingDue(module, values, { skipped: options.skipped })
  }

  const due = missingDue(module, values, { skipped: options.skipped })
  const create = createRequiredFor(module)
  const out: Errors = {}
  for (const name of Object.keys(due)) {
    const field = fieldsOf(module).find((f) => f.api_name === name)
    if (!field) continue
    const statusReason = (field.condition ?? '').includes('lead_status')
    if (statusReason) {
      out[name] = due[name]
      continue
    }
    if (options.creating) {
      if (create.has(name)) out[name] = due[name]
      continue
    }
    const at = dueStageOf(field)
    const left = at !== null && stage !== null && at < stage
    if (left && !BLANK(options.saved[name])) out[name] = due[name]
  }
  return out
}

/**
 * What a field's requirement means RIGHT NOW, for the mark beside its label —
 * the Zoho split (decided 21 Sep 2026):
 *
 *   'save'   red asterisk and "This is a required field." — the save is
 *            refused without it (the same list missingOnSave checks)
 *   'move'   grey asterisk and a quiet note — needed before the record leaves
 *            this stage, asked for again in the Update Stage dialog
 *   null     not asked for now (a later stage, a skipped one, hidden, optional)
 *
 * Marking every field the register calls required, whatever the stage, told a
 * person creating a lead that twelve fields were missing while the save needed
 * two — the form and its own message disagreed.
 */
export type RequirementKind = 'save' | 'move' | null

export function requirementKindOf(
  module: string,
  field: FieldSpec,
  values: Values,
  options: { creating: boolean; skipped?: readonly number[] }
): RequirementKind {
  if (!isUserEditable(field) || !isVisible(field, values)) return null
  if (!requirementOf(field, values).required) return null
  const stageField = stageFieldOf(module)
  if (!stageField) return 'save'
  if (SYSTEM_SET.has(field.api_name) || field.api_name === stageField) return null
  const status = typeof values.lead_status === 'string' ? values.lead_status : null
  if (status === 'CONVERTED') return null
  if ((field.condition ?? '').includes('lead_status')) return 'save'

  const stage = stageOf(values[stageField])
  const due = dueStageOf(field)
  if (due === null || stage === null) return 'save'
  const range = rangeOf(module)
  if (due > stage || (range && due < range[0])) return null
  if (due !== stage && (options.skipped ?? []).includes(due)) return null
  if (module === 'deals' && status === 'POC_PILOT_DEAL' && due <= 7) return null
  if (STATUS_ONLY.has(status ?? '')) return null

  const paidPilot = module === 'leads' && String(values.pilot_commercial_model ?? '').toUpperCase() === 'PAID'
  if (paidPilot) return 'save'
  if (options.creating) return createRequiredFor(module).has(field.api_name) ? 'save' : 'move'
  return due < stage ? 'save' : 'move'
}

function stageOf(value: unknown): number | null {
  if (typeof value === 'number') return Number.isFinite(value) ? value : null
  const m = typeof value === 'string' ? /^(\d+)/.exec(value) : null
  return m ? Number(m[1]) : null
}

export interface TransitionOptions {
  /** Stage being left. */
  from: number
  /** Stage being entered. */
  to: number
}

/**
 * Layer 1 of the four-layer transition check: mandatory fields.
 *
 * Three register columns decide this together:
 *   mandatory_from     the stage at which the field starts being required
 *   blocks_transition  the hop the register says it blocks, e.g. "4 → 5"
 *   required_on_skip   whether it still applies when its stage is skipped past
 *
 * Exit criteria, entry criteria and gate status are layers 2 to 4 and are not
 * this module's business.
 */
export function validateForTransition(
  module: string,
  values: Values,
  { from, to }: TransitionOptions
): FieldError[] {
  const out: FieldError[] = []
  const isSkip = to - from > 1

  for (const field of fieldsOf(module)) {
    if (!isUserEditable(field)) continue
    if (!isVisible(field, values)) continue

    const shape = checkShape(field, values[field.api_name])
    if (shape) {
      out.push({ api_name: field.api_name, label: field.label, section: field.section, message: shape })
      continue
    }

    // A childlist that HAS rows is checked row by row. One with none falls
    // through to the blank test below, where mandatory_from decides whether an
    // empty table blocks the hop.
    if (field.type === 'childlist') {
      const rowErrors = validateChildRows(field, rowsOf(values, field), 'all_rows')
      if (rowErrors.length) {
        out.push({
          api_name: field.api_name,
          label: field.label,
          section: field.section,
          message: summariseChildErrors(rowErrors),
        })
        continue
      }
    }

    if (!BLANK(values[field.api_name])) continue

    // A Mandatory field is governed by its stage, not by the record's values.
    // mandatory_from is populated on every Mandatory field in leads and deals —
    // the only two modules that have stages — so a null there means the field
    // belongs to a module a stage transition does not apply to.
    //
    // Conditional fields are governed by their condition instead, which is why
    // they go through requirementOf rather than the stage comparison.
    const demanded =
      field.requirement === 'Mandatory'
        ? field.mandatory_from !== null && field.mandatory_from <= to
        : requirementOf(field, values).required

    if (!demanded) continue

    // A field the register explicitly exempts when its stage is jumped over.
    if (isSkip && field.required_on_skip === false) continue

    out.push({
      api_name: field.api_name,
      label: field.label,
      section: field.section,
      message: field.blocks_transition
        ? `Required before ${field.blocks_transition}`
        : 'Required',
    })
  }

  return out
}

/**
 * Fields that would block a transition, grouped for display. Used by the
 * transition dialog in a later prompt; exposed here so the rule lives in one
 * place.
 */
export function blockersBySection(errors: FieldError[]): Map<string, FieldError[]> {
  const grouped = new Map<string, FieldError[]>()
  for (const e of errors) {
    grouped.set(e.section, [...(grouped.get(e.section) ?? []), e])
  }
  return grouped
}

/** The Zod object for a module, if a caller wants the whole schema at once. */
export function schemaFor(module: string): z.ZodObject<Record<string, z.ZodTypeAny>> {
  const shape: Record<string, z.ZodTypeAny> = {}
  for (const field of fieldsOf(module)) {
    if (!isUserEditable(field)) continue
    shape[field.api_name] = shapeOf(field).optional()
  }
  return z.object(shape)
}
