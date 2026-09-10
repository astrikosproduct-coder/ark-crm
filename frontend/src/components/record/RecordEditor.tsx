import { useEffect, useMemo, useState, type ReactNode } from 'react'
import { useNavigate } from 'react-router-dom'
import { useMutation, useQueryClient, type QueryClient } from '@tanstack/react-query'

import { Button } from '@/components/ui/button'
import { CreateNewDialog } from '@/components/form/CreateNewDialog'
import { FormSection } from '@/components/form/RecordForm'
import {
  markFormSaved,
  requestDiscard,
  useUnsavedChangesStore,
} from '@/store/useUnsavedChangesStore'
import {
  RecordFormProvider,
  useRecordForm,
  visibleFieldsOf,
  type StageScope,
} from '@/hooks/useRecordForm'
import { api } from '@/lib/api'
import { fieldOf, fieldsOf, idOf, sectionsFor } from '@/lib/spec'
import type { Values } from '@/lib/spec/conditions'
import type { ResolvedRecord } from '@/lib/spec/resolveRecord'
import type { Errors } from '@/lib/spec/validation'
import type { FieldSpec } from '@/types/field'

export interface RecordEditorProps {
  module: string
  collection: string
  /** Present for an edit, absent for a create. */
  recordId?: string
  initialValues?: Values
  onSaved: (id: string, record: Record<string, unknown>) => void
  onCancel: () => void
  saveLabel?: string
  /** Render only these sections, in this order. Defaults to all of them. */
  sections?: string[]
  /**
   * api_names the SCREEN draws elsewhere and this editor must not draw twice —
   * a pipeline record's per-stage strip and sticky panel. See visibleFieldsOf.
   * They are excluded from the on-screen error scoping too, so this editor
   * never reports a field it is not showing.
   */
  hiddenFields?: ReadonlySet<string>
  /**
   * This editor is editing ONE STAGE of a pipeline record. Fields the spec
   * records per stage then read and write `<api_name>__s<stage>` instead of the
   * plain name, without any control on screen knowing — see useRecordForm.
   */
  stageScope?: StageScope
  /** With a single section, render only these api_names of it. Spec-declared. */
  only?: string[]
  /** Overrides the register's section name in the header of a single section. */
  sectionTitle?: string
  /** Merged into the payload on save — values ARK stamps rather than the user. */
  stamp?: Values
  /**
   * The parent chain, for a module whose identity is read through one. Its
   * fields render read-only with a link to the record that owns them, and are
   * stripped from the payload — see toPayload in useRecordForm.
   */
  resolved?: ResolvedRecord
  /**
   * Mounted inside the form context alongside the fields, purely for its
   * effects — see PipelineModuleSpec.sideEffectsForStage. Renders nothing of
   * its own; the fields above are still the only thing on screen.
   */
  sideEffects?: ReactNode
  /**
   * Fired once, after a save succeeds, with the saved record and the query
   * client — for a gap-fill onto a DIFFERENT record that a save should cause
   * but a keystroke should not. See PipelineModuleSpec.afterSaveForStage.
   */
  afterSave?: (record: Record<string, unknown>, queryClient: QueryClient) => void | Promise<void>
}

/** Field labels for a summary line, capped so it stays one readable sentence. */
function nameList(module: string, apiNames: string[], cap = 4): string {
  const labels = apiNames.map((n) => fieldOf(module, n)?.label ?? n)
  if (labels.length <= cap) return labels.join(', ')
  return `${labels.slice(0, cap).join(', ')} and ${labels.length - cap} more`
}

/**
 * Create or edit one record, rendered entirely by the form engine.
 *
 * A save enforces only the shape rules — validateForSave, not
 * validateForTransition. A half-filled record must be savable: mandatory fields
 * bite at a stage transition, which is what mandatory_from in the register
 * means. Accounts and Contacts have no stages, so nothing else ever bites.
 */
export function RecordEditor(props: RecordEditorProps) {
  return (
    <RecordFormProvider
      module={props.module}
      mode="edit"
      recordId={props.recordId}
      initialValues={props.initialValues}
      resolved={props.resolved}
      stageScope={props.stageScope}
    >
      <EditorBody {...props} />
    </RecordFormProvider>
  )
}

function EditorBody({
  module,
  collection,
  recordId,
  onSaved,
  onCancel,
  saveLabel,
  sections,
  hiddenFields,
  only,
  sectionTitle,
  stamp,
  sideEffects,
  afterSave,
}: RecordEditorProps) {
  const form = useRecordForm()
  const queryClient = useQueryClient()
  const navigate = useNavigate()
  const [creatingFor, setCreatingFor] = useState<FieldSpec | null>(null)
  /** True once Save has been pressed, so "nothing outstanding" is an answer to
   * a question the user asked rather than an unprompted reassurance. */
  const [attempted, setAttempted] = useState(false)

  /**
   * A Lead is not a quick-create. It opens at Stage 0 — Connect, with its own
   * eight-stage form and the End Client / Account mapping that lives there —
   * so "+ Create new lead" (Parent Lead, on a hand-created Opportunity) sends
   * the user to the real /leads/new page instead of the generic first-section-
   * only CreateNewDialog every other lookup uses. The in-progress form here is
   * not lost: RecordFormProvider's draft is in the persisted Zustand store, so
   * coming back to this record later finds it exactly as it was left.
   */
  const handleCreateNew = (field: FieldSpec) => {
    if (field.lookup_target === 'lead') {
      navigate('/leads/new')
      return
    }
    setCreatingFor(field)
  }

  /**
   * The api_names this editor actually puts on screen.
   *
   * An editor usually renders ONE section of a record — the Stage 1 fields of a
   * lead — while form.allErrors covers the whole module. Counting module-wide
   * made both messages lie: "54 required fields are still empty" when eight are
   * on screen, and worse, "1 field needs fixing before this can be saved" with
   * nothing marked below it, because the malformed value was Currency over in
   * Stage 0. That dead end is the reason this scoping exists.
   */
  const onScreen = useMemo(() => {
    const names = new Set<string>()
    const list = sections ?? sectionsFor(module)
    for (const section of list) {
      for (const field of visibleFieldsOf(form, module, section, hiddenFields)) {
        if (list.length === 1 && only && !only.includes(field.api_name)) continue
        names.add(field.api_name)
      }
    }
    return names
  }, [form, module, sections, only, hiddenFields])

  /**
   * Computed fields of the module that this editor does not show and that
   * evaluated to nothing.
   *
   * toPayload snapshots every computed field of the MODULE, which is right for
   * a record that is the module — a lead — and wrong where one register sheet
   * describes several record types. The Partners sheet holds DEAL REGISTRATION,
   * CONFLICT ADJUDICATION and QUARTERLY SCORECARD, so saving an adjudication
   * was writing acknowledgement_sla_met and exclusivity_expiry_date, both null,
   * onto a record that has no such thing.
   *
   * Only nulls are dropped, and only when off screen: a computed value that
   * actually computed is still snapshotted, because computed fields are always
   * re-derived at render anyway and the snapshot is a convenience, not a
   * source. The underlying problem is the register's, and it is on Spec Health.
   */
  const emptyOffScreenComputed = useMemo(() => {
    return new Set(
      fieldsOf(module)
        .filter((f) => f.type === 'computed' && !onScreen.has(f.api_name))
        .map((f) => f.api_name)
    )
  }, [module, onScreen])

  /**
   * Publish this form's unsaved state app-wide, so the shell's guard can hold a
   * navigation — or a tab switch — before it destroys the edits. The id names
   * the record AND this editor's sections, since a pipeline record can have the
   * stage editor and the details editor open at once.
   */
  const formId = `${module}:${recordId ?? 'new'}:${sections?.join(',') ?? 'all'}`
  const setFormDirty = useUnsavedChangesStore((s) => s.setFormDirty)

  useEffect(() => {
    setFormDirty(formId, form.dirty)
    return () => setFormDirty(formId, false)
  }, [formId, form.dirty, setFormDirty])

  const save = useMutation({
    mutationFn: async () => {
      const payload = { ...form.toPayload(), ...stamp }
      for (const key of emptyOffScreenComputed) {
        if (payload[key] === null || payload[key] === undefined) delete payload[key]
      }
      const res = recordId
        ? await api.put<Record<string, unknown>>(`/${collection}/${recordId}`, payload)
        : await api.post<Record<string, unknown>>(`/${collection}`, payload)
      return res.data
    },
    onSuccess: async (record) => {
      const id = idOf(record) || (recordId ?? '')
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['list', collection] }),
        queryClient.invalidateQueries({ queryKey: ['collection', collection] }),
        queryClient.invalidateQueries({ queryKey: ['record', collection] }),
      ])
      // What was just saved now IS the record. Both calls matter: markFormSaved
      // clears the app-wide flag synchronously, because onSaved navigates in
      // this same tick and would otherwise be held behind the "you have not
      // saved your changes" dialog; markSaved cleans the form itself, for the
      // case where it stays open afterwards.
      markFormSaved(formId)
      form.markSaved()
      // Fire-and-forget: a gap-fill onto a linked
      // record is a nice-to-have, not something a save should ever wait on or
      // fail over.
      void afterSave?.(record, queryClient)
      onSaved(id, record)
    },
  })

  const submit = () => {
    form.markSubmitted()
    setAttempted(true)
    // Only a malformed value the user can actually see and fix stops the save.
    // Empty required fields never do — a half-filled record has to be savable;
    // they stop the stage move instead. Nor do problems in other sections, for
    // the reason given on elsewhereErrors.
    const blocking = Object.keys(form.allErrors).filter((k) => onScreen.has(k))
    if (blocking.length > 0) return
    save.mutate()
  }

  // Closing the editor throws the edits away, so it asks first — the same
  // dialog a navigation gets. With nothing unsaved it just closes.
  const cancel = () => requestDiscard(onCancel)

  const split = (errors: Errors) => {
    const here: string[] = []
    const elsewhere: string[] = []
    for (const key of Object.keys(errors)) (onScreen.has(key) ? here : elsewhere).push(key)
    return { here, elsewhere }
  }

  // visibleErrors/visibleRequired, not the `all` maps: an untouched field is
  // not scolded before the first save attempt.
  const shape = split(form.visibleErrors)
  const missing = split(form.visibleRequired)

  // Malformed values in sections this editor cannot show. Reported, never
  // blocking — the user has no box here to fix them in, and the values are
  // already on the record either way, so refusing the save is a trap rather
  // than a safeguard.
  const elsewhereErrors = useMemo(() => {
    return Object.keys(form.allErrors)
      .filter((k) => !onScreen.has(k))
      .map((k) => fieldOf(module, k))
      .filter((f): f is FieldSpec => Boolean(f))
  }, [form.allErrors, onScreen, module])

  // Only leads and deals have stages, so only they have something to be "not
  // ready" for. Derived from the register — a module whose fields never carry
  // mandatory_from has no transition for an empty field to block.
  const hasStages = useMemo(() => fieldsOf(module).some((f) => f.mandatory_from !== null), [module])

  return (
    <div className="space-y-3 py-3">
      {sideEffects}
      {(sections ?? sectionsFor(module)).map((section) => (
        <FormSection
          key={section}
          module={module}
          section={section}
          hiddenFields={hiddenFields}
          onCreateNew={handleCreateNew}
          only={sections?.length === 1 ? only : undefined}
          title={sections?.length === 1 ? sectionTitle : undefined}
        />
      ))}

      <CreateNewDialog
        field={creatingFor}
        onClose={() => setCreatingFor(null)}
        onCreated={(id) => {
          if (creatingFor) form.setValue(creatingFor.api_name, id)
        }}
      />

      <div className="space-y-2 border-t pt-3">
        <div className="flex items-center gap-2">
          <Button type="button" onClick={submit} disabled={save.isPending}>
            {save.isPending ? 'Saving…' : (saveLabel ?? 'Save')}
          </Button>
          <Button type="button" variant="outline" onClick={cancel} disabled={save.isPending}>
            Cancel
          </Button>
          {save.isError && (
            <p className="text-sm text-destructive">The record could not be saved.</p>
          )}
        </div>

        {/* Two different things, said separately, because they have different
            consequences. A malformed value stops the save. An empty required
            field does not — a half-filled record has to be savable — but it
            does stop the record moving on. Each one is marked on the field
            itself as well; these lines only say how many and what they cost. */}
        {shape.here.length > 0 && (
          <p className="text-sm text-destructive">
            {shape.here.length} {shape.here.length === 1 ? 'field needs' : 'fields need'} fixing
            before this can be saved: {nameList(module, shape.here)}. Each is marked below.
          </p>
        )}

        {missing.here.length > 0 && (
          <p className="text-sm text-destructive">
            {missing.here.length} required{' '}
            {missing.here.length === 1 ? 'field is' : 'fields are'} still empty:{' '}
            {nameList(module, missing.here)}.{' '}
            <span className="text-muted-foreground">
              {hasStages
                ? 'You can still save; each is marked below and must be filled before this record can move to the next stage.'
                : 'You can still save; each is marked below.'}
            </span>
          </p>
        )}

        {/* Not blocking, and not silent either. Without this line a malformed
            Currency over in Stage 0 stopped a Stage 1 save with nothing on
            screen to explain it. */}
        {elsewhereErrors.length > 0 && (
          <p className="text-warning text-sm">
            {elsewhereErrors.length}{' '}
            {elsewhereErrors.length === 1 ? 'field has' : 'fields have'} an invalid value in another
            section and cannot be fixed here:{' '}
            {elsewhereErrors.map((f) => `${f.label} (${f.section})`).join(', ')}. This does not stop
            you saving.
          </p>
        )}

        {shape.here.length === 0 && missing.here.length === 0 && attempted && (
          <p className="text-success text-sm">
            Nothing outstanding on the fields shown
            {hasStages ? ' — ready to move to the next stage.' : '.'}
          </p>
        )}
      </div>
    </div>
  )
}
