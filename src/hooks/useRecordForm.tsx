import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useReducer,
  useRef,
  type ReactNode,
} from 'react'

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
import { draftFor, useDraftStore } from '@/store/useDraftStore'
import type { FieldSpec } from '@/types/field'

export type FormMode = 'view' | 'edit'

/** Unsaved-record drafts key on this rather than a real id — see useDraftStore. */
export const NEW_RECORD_ID = 'new'

/** Stable empties, so a form with no parent chain never re-renders on identity. */
const EMPTY_VALUES: Values = {}
const EMPTY_NAMES: Set<string> = new Set()

const DRAFT_DEBOUNCE_MS = 300

interface State {
  values: Values
  children: Children
  touched: Record<string, true>
  dirty: boolean
  submitted: boolean
}

type Action =
  | { t: 'set'; api_name: string; value: unknown }
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

    // Keeps the values, drops the "unsaved" state. What a successful save or an
    // explicit cancel leaves behind: the values on screen are the record now,
    // so nothing here is a draft anymore. Without this the unmount flush below
    // rewrites the draft the save just cleared, and the ghost is replayed over
    // the record the next time the form opens.
    case 'clean':
      return { ...state, touched: {}, dirty: false }

    case 'submitted':
      return { ...state, submitted: true }
  }
}

/**
 * The subset of a form's state that is actually unsaved.
 *
 * A draft must hold ONLY what the user touched — never a snapshot of the whole
 * record. state.values starts life as a copy of the record, so persisting it
 * wholesale meant a draft carried every field the user never went near, and
 * hydrating it replayed those stale values over a record that had moved on
 * since. That is how editing Prescription fields could drag a lead back to
 * Connect: a draft captured while the lead sat at Stage 0 still held
 * project_stage = "0_CONNECT", and the next save wrote it back.
 *
 * Restricting the draft to touched keys makes the replay harmless by
 * construction: the only values that can override a fresher record are ones the
 * user really did type and really has not saved.
 */
function touchedOnly(state: State): { values: Values; children: Children } {
  const values: Values = {}
  const children: Children = {}

  for (const key of Object.keys(state.touched)) {
    if (key in state.children) children[key] = state.children[key]
    else if (key in state.values) values[key] = state.values[key]
  }

  return { values, children }
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
  /** module + this is the draft store's key. See useDraftStore. */
  recordId: string
  values: Values
  children: Children
  /** True from the moment a field is touched, OR from mount when a persisted
   * draft was found — either way, "there is something here that isn't saved". */
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
  /** Removes the persisted draft, leaving in-memory state untouched. Call this
   * once a save has succeeded — the values just written now match the record,
   * so nothing about them is unsaved anymore. */
  clearDraft: () => void
  /** Removes the persisted draft AND reverts in-memory state back to what this
   * form was opened with. Call this for an explicit Discard action. */
  discardDraft: () => void
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
  children: ReactNode
}

/**
 * Form state for exactly one record.
 *
 * Scoped rather than global because a lookup's "+ Create new" dialog renders a
 * second RecordForm over the first, and a child-list row is a third — a single
 * store keyed by api_name would have them overwriting each other.
 *
 * Drafts: an edit-mode form hydrates from useDraftStore on mount (merged over
 * initialValues, since the draft is the more recent thing) and writes back to
 * it, debounced, on every change — so navigating away, switching tabs or
 * refreshing the browser no longer loses what was typed. A view-mode form
 * never reads or writes a draft: it shows the saved record, not a draft of it.
 * Computed fields are never part of what gets persisted — only state.values,
 * the raw entered values — so a formula edited later still recomputes fresh
 * instead of replaying a stale snapshot.
 *
 * A draft holds ONLY the fields the user touched — see touchedOnly. The record
 * underneath a draft can change while the draft sits there (a stage advance is
 * a PUT of its own), and a draft that carried untouched fields would replay
 * them over the newer record on the next save. `touched` is therefore seeded
 * from a resumed draft's own keys, so a draft that survives a reload keeps
 * writing back exactly the fields it already holds.
 */
export function RecordFormProvider({
  module,
  mode,
  recordId = NEW_RECORD_ID,
  initialValues,
  initialChildren,
  resolved,
  children,
}: RecordFormProviderProps) {
  const [state, dispatch] = useReducer(
    reducer,
    undefined,
    (): State => {
      const draft = mode === 'edit' ? draftFor(module, recordId) : undefined
      const initial = splitChildren(module, initialValues)
      return {
        values: { ...initial.values, ...(draft?.values ?? {}) },
        children: { ...initial.children, ...(initialChildren ?? {}), ...(draft?.children ?? {}) },
        // Seeded from the draft, not left empty: these ARE the unsaved fields,
        // and without this the first flush would persist an empty draft over
        // the real one and lose everything the user typed before the reload.
        touched: Object.fromEntries(
          [...Object.keys(draft?.values ?? {}), ...Object.keys(draft?.children ?? {})].map((k) => [
            k,
            true as const,
          ])
        ),
        // A resumed draft reads as unsaved from the moment it appears, before
        // the user has touched anything this session.
        dirty: Boolean(draft),
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
    () => ({ ...state.values, ...inheritedValues, ...state.children, ...computed }),
    [state.values, inheritedValues, state.children, computed]
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

  const setValue = useCallback((apiName: string, value: unknown) => {
    dispatch({ t: 'set', api_name: apiName, value })
  }, [])

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
      if (field.carry === 'read_through') delete payload[field.api_name]
    }

    return payload
  }, [module, recordId, state.values, state.children, computed])

  /**
   * Set the moment a save or a cancel succeeds, and never unset.
   *
   * A ref rather than reducer state because the caller closes the editor in the
   * same commit — the provider unmounts, so a dispatched 'clean' is thrown away
   * before the unmount flush below ever reads it, and the flush would rewrite
   * the draft the save just deleted. A ref is written synchronously and
   * survives into the cleanup function.
   */
  const settled = useRef(false)

  const clearDraft = useCallback(() => {
    settled.current = true
    useDraftStore.getState().clearDraft(module, recordId)
    // Also clean the reducer, for the case where the form STAYS mounted after
    // saving — the badge and the dirty flag have to stop showing there too.
    dispatch({ t: 'clean' })
  }, [module, recordId])

  const discardDraft = useCallback(() => {
    useDraftStore.getState().discardDraft(module, recordId)
    dispatch({ t: 'reset', values: initialValues ?? {}, children: initialChildren ?? {} })
  }, [module, recordId, initialValues, initialChildren])

  // Debounced draft persistence. Only ever the TOUCHED raw values/children —
  // never `values`, which has computed fields merged in, and never the
  // untouched rest of the record. See touchedOnly.
  const latest = useRef(state)
  latest.current = state

  useEffect(() => {
    if (mode !== 'edit' || !state.dirty || settled.current) return
    const timer = setTimeout(() => {
      const draft = touchedOnly(state)
      useDraftStore.getState().setDraft(module, recordId, draft.values, draft.children)
    }, DRAFT_DEBOUNCE_MS)
    return () => clearTimeout(timer)
  }, [module, recordId, mode, state])

  // Flush immediately on unmount, so a route change or tab switch inside the
  // debounce window doesn't lose the last edit to it. Runs after the effect
  // above on every render, so this only ever fires the redundant "same value
  // again" write unless the form is actually being torn down mid-debounce.
  useEffect(() => {
    return () => {
      if (mode === 'edit' && latest.current.dirty && !settled.current) {
        const draft = touchedOnly(latest.current)
        useDraftStore.getState().setDraft(module, recordId, draft.values, draft.children)
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [module, recordId, mode])

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
      clearDraft,
      discardDraft,
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
      clearDraft,
      discardDraft,
    ]
  )

  return <Ctx.Provider value={api}>{children}</Ctx.Provider>
}

/** Fields of a section that should be rendered, given mode and visibility. */
export function visibleFieldsOf(form: RecordForm, module: string, section: string): FieldSpec[] {
  return fieldsOf(module)
    .filter((f) => f.section === section)
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
