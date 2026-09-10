import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useReducer,
  type ReactNode,
} from 'react'

import { homeSectionOf } from '@/lib/spec/anchors'
import {
  isStageScoped,
  stageScopedPatch,
  stageScopedValue,
} from '@/lib/stageScope'
import { isChildColumnOnly } from '@/lib/spec/childSpec'
import { isVisible, requirementOf, type Values } from '@/lib/spec/conditions'
import { computeAll, type Children } from '@/lib/spec/formula'
import { fieldsOf } from '@/lib/spec'
import type { InheritedSource, ResolvedRecord } from '@/lib/spec/resolveRecord'
import {
  missingRequired,
  validateChildrenForSave,
  validateForSave,
  type ChildErrors,
  type Errors,
} from '@/lib/spec/validation'
import type { FieldSpec } from '@/types/field'

export type FormMode = 'view' | 'edit'

/** A record that does not exist yet keys on this rather than a real id. */
export const NEW_RECORD_ID = 'new'

/** Stable empties, so a form with no parent chain never re-renders on identity. */
const EMPTY_VALUES: Values = {}
const EMPTY_NAMES: Set<string> = new Set()

interface State {
  values: Values
  children: Children
  touched: Record<string, true>
  dirty: boolean
  submitted: boolean
}

type Action =
  | { t: 'set'; api_name: string; value: unknown }
  // One edit that lands on MORE THAN ONE key. A per-stage field writes
  // `probability_pct__s3`, and — when the stage being edited is the one the
  // record is at — the plain `probability_pct` as well, so list columns and
  // the band check keep reading one number. `touch` is the field's plain
  // api_name, because that is what every error and required map is keyed on.
  | { t: 'patch'; touch: string; values: Values }
  | { t: 'setChild'; api_name: string; rows: Values[] }
  | { t: 'reset'; values: Values; children: Children }
  | { t: 'clean' }
  | { t: 'submitted' }

function reducer(state: State, action: Action): State {
  switch (action.t) {
    case 'set':
      if (state.values[action.api_name] === action.value) return state
      return {
        ...state,
        values: { ...state.values, [action.api_name]: action.value },
        touched: { ...state.touched, [action.api_name]: true },
        dirty: true,
      }

    case 'patch':
      return {
        ...state,
        values: { ...state.values, ...action.values },
        touched: { ...state.touched, [action.touch]: true },
        dirty: true,
      }

    case 'setChild':
      return {
        ...state,
        children: { ...state.children, [action.api_name]: action.rows },
        touched: { ...state.touched, [action.api_name]: true },
        dirty: true,
      }

    case 'reset':
      return {
        values: action.values,
        children: action.children,
        touched: {},
        dirty: false,
        submitted: false,
      }

    // Keeps the values, drops the "unsaved" state. What a successful save
    // leaves behind: the values on screen ARE the record now, so there is
    // nothing left for the leave-page guard to warn about.
    case 'clean':
      return { ...state, touched: {}, dirty: false }

    case 'submitted':
      return { ...state, submitted: true }
  }
}

/**
 * Pull childlist rows out of a flat record into `children`.
 *
 * A saved record carries its child rows under the childlist's own api_name —
 * toPayload writes them there and MSW stores them there — so a form opened on
 * an existing record receives them inside initialValues. Splitting them here is
 * what makes the round trip work: rows saved on Monday are editable rows on
 * Tuesday rather than an opaque array sitting in values.
 *
 * Which keys are childlists comes from the register, never from a guess about
 * the value being an array — multiselect fields are arrays too.
 */
function splitChildren(module: string, initial: Values | undefined): { values: Values; children: Children } {
  const values: Values = { ...(initial ?? {}) }
  const children: Children = {}

  for (const field of fieldsOf(module)) {
    if (field.type !== 'childlist') continue
    const v = values[field.api_name]
    if (Array.isArray(v)) children[field.api_name] = v as Values[]
    delete values[field.api_name]
  }

  return { values, children }
}

export interface RecordForm {
  module: string
  mode: FormMode
  /** The record being edited, NEW_RECORD_ID for one not saved yet. */
  recordId: string
  values: Values
  children: Children
  /** True from the moment a field is touched until the next successful save —
   * "there is something on screen that isn't saved". The leave-page guard
   * reads this. */
  dirty: boolean
  /** Errors for fields the user has touched, plus everything once submitted. */
  visibleErrors: Errors
  allErrors: Errors
  /** Required fields that are still empty, gated the same way visibleErrors is.
   * These do NOT block a save — they block the stage move. See missingRequired. */
  visibleRequired: Errors
  allRequired: Errors
  /** Per-cell child-row errors, keyed by childlist api_name. Always complete —
   * the table decides for itself which of them to show, since a row the user
   * just added has no per-row "touched" state to consult. */
  childErrors: ChildErrors
  setValue: (apiName: string, value: unknown) => void
  setChildRows: (apiName: string, rows: Values[]) => void
  reset: (values?: Values, children?: Children) => void
  markSubmitted: () => void
  /** Values as they should be persisted, computed fields snapshotted in. */
  toPayload: () => Values
  isVisible: (field: FieldSpec) => boolean
  isRequired: (field: FieldSpec) => boolean
  isUnruled: (field: FieldSpec) => boolean
  /** api_names whose value was read through a parent record, not stored here. */
  inherited: Set<string>
  /** Where an inherited value actually lives, for the affordance on the field. */
  sourceOf: (apiName: string) => InheritedSource | undefined
  /** read_through fields the chain could not resolve — see ResolvedRecord. */
  unresolvedInherited: Set<string>
  /** Drops the unsaved flag, keeping the values. Call this once a save has
   * succeeded — what was written now matches the record. */
  markSaved: () => void
}

const Ctx = createContext<RecordForm | null>(null)

export function useRecordForm(): RecordForm {
  const form = useContext(Ctx)
  if (!form) throw new Error('useRecordForm must be used inside a RecordFormProvider')
  return form
}

export interface RecordFormProviderProps {
  module: string
  mode: FormMode
  /** The record this form edits, "new" for one not yet saved. Defaults to
   * "new" — most callers rendering a fresh record never need to pass this. */
  recordId?: string
  initialValues?: Values
  initialChildren?: Children
  /**
   * The record's identity as read through its parent chain — see
   * useResolvedRecord. Merged over the stored values for everything the form
   * derives (formulas, validation, visibility) and stripped from the payload on
   * save, because a read_through field is displayed here and stored on the Lead.
   *
   * Absent for every module the split gives no parent, which is all of them
   * except Opportunities and Deals.
   */
  resolved?: ResolvedRecord
  /**
   * This form is editing ONE STAGE of a pipeline record.
   *
   * Without it, a stage-scoped field rendered in an ordinary form would read
   * and write the plain api_name and there would be one On Hold Reason per
   * record — the exact thing lib/stageScope.ts exists to prevent. With it, the
   * form reads `<api_name>__s<stage>` and writes it back, while every control,
   * condition, formula and error map above still sees the plain api_name.
   *
   * Absent for every non-pipeline form, and for the create page: a record that
   * does not exist yet is not at a stage.
   */
  stageScope?: StageScope
  children: ReactNode
}

/** Which stage a form is editing, and which one its record is actually at. */
export interface StageScope {
  /** The stage on screen. May be an earlier one the user selected on the rail. */
  stage: number
  /** The stage the record is at, which decides whether a carried value is
   * ALSO written to the plain api_name. Correcting history must not become
   * the record's current probability — see stageScopedPatch. */
  currentStage: number
}

/**
 * Form state for exactly one record.
 *
 * Scoped rather than global because a lookup's "+ Create new" dialog renders a
 * second RecordForm over the first, and a child-list row is a third — a single
 * store keyed by api_name would have them overwriting each other.
 *
 * Nothing here is persisted. A form holds what the user has typed for as long
 * as it is on screen, and `dirty` says whether any of it is unsaved — which is
 * what the leave-page guard reads before letting a navigation through. Closing
 * the form without saving discards the edits, deliberately: an edit that was
 * never saved is not a record, and a half-typed value quietly resurrected days
 * later over a record that has moved on is worse than losing it.
 */
export function RecordFormProvider({
  module,
  mode,
  recordId = NEW_RECORD_ID,
  initialValues,
  initialChildren,
  resolved,
  stageScope,
  children,
}: RecordFormProviderProps) {
  const [state, dispatch] = useReducer(
    reducer,
    undefined,
    (): State => {
      const initial = splitChildren(module, initialValues)
      return {
        values: initial.values,
        children: { ...initial.children, ...(initialChildren ?? {}) },
        touched: {},
        dirty: false,
        submitted: false,
      }
    }
  )

  /**
   * Identity read through the parent, merged OVER the stored values.
   *
   * The parent wins on purpose. A Deal converted before the split holds its own
   * copy of end_client; preferring the stored one would be preferring the drift
   * this whole mechanism exists to prevent. toPayload strips these, so the next
   * save clears the stale copy rather than writing it back.
   */
  const inheritedValues = useMemo(() => {
    if (!resolved?.inherited.size) return EMPTY_VALUES
    const out: Values = {}
    for (const name of resolved.inherited) out[name] = resolved.values[name]
    return out
  }, [resolved])

  /**
   * read_through fields the parent chain could not supply.
   *
   * Kept apart from `inherited` so the control can tell "the Lead has no End
   * Client" from "this record is not linked to a Lead at all". Rendering both as
   * an em dash would hide a broken link behind an empty field.
   */
  const unresolvedInherited = useMemo(
    () => (resolved?.unresolved.length ? new Set(resolved.unresolved) : EMPTY_NAMES),
    [resolved]
  )

  /**
   * Fields of this module that are recorded PER STAGE — see lib/stageScope.ts.
   *
   * Empty unless the form was given a stage, which is what keeps every other
   * form in the app (accounts, contacts, the create pages, the quick-create
   * dialogs) on exactly the code path it was on before.
   */
  const scopedFields = useMemo(
    () => (stageScope ? fieldsOf(module).filter((f) => isStageScoped(module, f)) : []),
    [module, stageScope]
  )

  /**
   * THE PROJECTION. `on_hold_reason__s3` read back out under `on_hold_reason`.
   *
   * This is the whole trick, and it is deliberately one map rather than a
   * change to every reader. FieldRow, FieldControl, every condition, every
   * formula, validateForSave and missingRequired all go on asking for the
   * plain api_name and know nothing about stages; only this layer and
   * setValue below have to. A sticky field projects THIS stage's answer and
   * nothing else, so a reason given at Stage 1 never pre-fills the Stage 3
   * box — which is what makes the second hold get its own reason.
   */
  const stageProjection = useMemo(() => {
    if (!stageScope || scopedFields.length === 0) return EMPTY_VALUES
    const out: Values = {}
    for (const field of scopedFields) {
      out[field.api_name] = stageScopedValue(module, field, state.values, stageScope.stage)
    }
    return out
  }, [module, stageScope, scopedFields, state.values])

  // Computed fields are derived here, never stored in state, so editing a
  // formula in the sidecar changes existing records on the next render instead
  // of leaving a stale snapshot behind. Inherited values are part of the input:
  // a formula on an Opportunity may read a field that lives on its Lead.
  const computed = useMemo(
    () => computeAll(module, { ...state.values, ...inheritedValues }, state.children),
    [module, state.values, inheritedValues, state.children]
  )

  /**
   * Child rows are merged in under the childlist's own api_name, so a childlist
   * is just another value to everything downstream — validation, the readiness
   * panel, view mode's "hide what is empty" rule and any expression that reads
   * one. state.children stays the editable copy, and is what sum() is handed.
   */
  const values = useMemo(
    () => ({
      ...state.values,
      ...inheritedValues,
      ...state.children,
      ...computed,
      // Last, so a per-stage answer wins over a legacy record-level one left
      // behind by a save from before this mechanism existed.
      ...stageProjection,
    }),
    [state.values, inheritedValues, state.children, computed, stageProjection]
  )

  const allErrors = useMemo(() => validateForSave(module, values), [module, values])

  const childErrors = useMemo(() => validateChildrenForSave(module, values), [module, values])

  const allRequired = useMemo(() => missingRequired(module, values), [module, values])

  // One gate, applied to both maps: an untouched field is not scolded before
  // the first save attempt, and everything speaks up after one.
  const gate = useCallback(
    (errors: Errors): Errors => {
      if (state.submitted) return errors
      const out: Errors = {}
      for (const key of Object.keys(errors)) {
        if (state.touched[key]) out[key] = errors[key]
      }
      return out
    },
    [state.touched, state.submitted]
  )

  const visibleErrors = useMemo(() => gate(allErrors), [gate, allErrors])

  /**
   * Empty required fields are shown straight away when EDITING AN EXISTING
   * record, without waiting for a save attempt.
   *
   * The point of opening a stage section on a lead is to find out what is still
   * missing before it can move on, so making the user press Save to be told
   * hides the answer behind a guess — and once the save succeeds the editor
   * closes and the answer disappears with it.
   *
   * A NEW record keeps the touched/submitted gate: a blank create form that
   * greets the user with a screen of red before they have typed anything is
   * scolding them for not having started.
   */
  const showAllRequired = mode === 'edit' && recordId !== NEW_RECORD_ID
  const visibleRequired = useMemo(
    () => (showAllRequired ? allRequired : gate(allRequired)),
    [showAllRequired, gate, allRequired]
  )

  const setValue = useCallback(
    (apiName: string, value: unknown) => {
      // A per-stage field is stored under the stage's own key. The control that
      // called this passed the plain api_name and is none the wiser, which is
      // the point: one input, one place, whatever the storage underneath.
      const scoped = stageScope
        ? scopedFields.find((f) => f.api_name === apiName)
        : undefined
      if (scoped && stageScope) {
        dispatch({
          t: 'patch',
          touch: apiName,
          values: stageScopedPatch(scoped, stageScope.stage, stageScope.currentStage, value),
        })
        return
      }
      dispatch({ t: 'set', api_name: apiName, value })
    },
    [scopedFields, stageScope]
  )

  const setChildRows = useCallback((apiName: string, rows: Values[]) => {
    dispatch({ t: 'setChild', api_name: apiName, rows })
  }, [])

  const reset = useCallback((next?: Values, nextChildren?: Children) => {
    dispatch({ t: 'reset', values: next ?? {}, children: nextChildren ?? {} })
  }, [])

  const markSubmitted = useCallback(() => dispatch({ t: 'submitted' }), [])

  const toPayload = useCallback(() => {
    // Hidden fields keep their values. A lead switched from Perpetual to
    // Subscription and back must not have lost its licence fee in between —
    // the register says hide it, not delete it.
    const payload: Values = { ...state.values, ...computed, ...state.children }

    // A save must not be able to move the record's stage. Every form holds a
    // snapshot of the record taken when it opened, and a save sends the whole
    // thing back — so a form opened against an older stage would write that
    // older stage. Stripping the field means only Advance / Change stage can
    // move a lead, which is what AdvanceStageDialog always claimed.
    //
    // A create is exempt: there the value is the record establishing the stage
    // it opens at (LeadCreatePage seeds Stage 0), not a save undoing one.
    if (recordId !== NEW_RECORD_ID) {
      for (const field of fieldsOf(module)) {
        if (field.transition_owned) delete payload[field.api_name]
      }
    }

    // A read_through field is DISPLAYED here and STORED on the parent. Writing
    // it would put a second copy of the End Client on the Opportunity, which is
    // the drift spec/module_split.json exists to prevent — so it is stripped
    // whatever the mode, unlike transition_owned, which a create is exempt from.
    // Spec-driven rather than driven by what actually resolved: a chain that
    // failed to load must not become a licence to start storing identity.
    for (const field of fieldsOf(module)) {
      if (field.value_mode === 'read_through') delete payload[field.api_name]
    }

    return payload
  }, [module, recordId, state.values, state.children, computed])

  /**
   * What was just saved IS the record now, so the form stops reading as
   * unsaved. Called by the editor on a successful save — including the case
   * where the form stays open afterwards, which is why it is a dispatch rather
   * than something the caller could get away with skipping.
   */
  const markSaved = useCallback(() => {
    dispatch({ t: 'clean' })
  }, [])

  const api = useMemo<RecordForm>(
    () => ({
      module,
      mode,
      recordId,
      values,
      children: state.children,
      dirty: state.dirty,
      visibleErrors,
      allErrors,
      visibleRequired,
      allRequired,
      childErrors,
      setValue,
      setChildRows,
      reset,
      markSubmitted,
      toPayload,
      isVisible: (field) => isVisible(field, values),
      isRequired: (field) => requirementOf(field, values).required,
      isUnruled: (field) => requirementOf(field, values).unruled === true,
      inherited: resolved?.inherited ?? EMPTY_NAMES,
      sourceOf: (apiName: string) => resolved?.sources[apiName],
      unresolvedInherited: unresolvedInherited,
      markSaved,
    }),
    [
      module,
      mode,
      recordId,
      values,
      resolved,
      unresolvedInherited,
      state.children,
      state.dirty,
      visibleErrors,
      allErrors,
      visibleRequired,
      allRequired,
      childErrors,
      setValue,
      setChildRows,
      reset,
      markSubmitted,
      toPayload,
      markSaved,
    ]
  )

  return <Ctx.Provider value={api}>{children}</Ctx.Provider>
}

/**
 * Fields of a section that should be rendered, given mode and visibility.
 *
 * `hidden` names api_names this SCREEN renders somewhere else — the per-stage
 * strip and the sticky panel on a pipeline record take Probability, Progression
 * and the CROSS-CUTTING reasons out of the ordinary sections and draw them
 * themselves. It is a rendering decision of one screen, never a property of the
 * field, which is why it arrives as an argument and not as a spec flag: the same
 * field still renders normally on the create page, where there is no stage strip
 * to put it in.
 */
export function visibleFieldsOf(
  form: RecordForm,
  module: string,
  section: string,
  hidden?: ReadonlySet<string>
): FieldSpec[] {
  return fieldsOf(module)
    // homeSectionOf, not f.section: an anchored field draws in the section its
    // ANCHOR is in, which is the whole point — On Hold Reason is filed under
    // CROSS-CUTTING and rendered inside STAGE 0 — CONNECT, beside the Lead
    // Status that reveals it. Every filter below then applies to it unchanged.
    .filter((f) => homeSectionOf(module, f) === section)
    .filter((f) => !hidden?.has(f.api_name))
    // The register writes some child-row columns as loose fields in the same
    // section as their table — the milestone_—_* dates beside Payment
    // Milestones. They belong to the row, so they render only as columns.
    .filter((f) => !isChildColumnOnly(f))
    .filter((f) => form.isVisible(f))
    .filter((f) => {
      if (form.mode === 'edit') return true
      // View mode hides empties, so a record reads as what it is rather than
      // as a wall of dashes.
      const v = form.values[f.api_name]
      if (Array.isArray(v)) return v.length > 0
      return v !== null && v !== undefined && v !== ''
    })
}
