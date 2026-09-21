import { useEffect, useMemo, useState, type ReactNode } from 'react'
import { createPortal } from 'react-dom'
import { useNavigate } from 'react-router-dom'
import { useMutation, useQueryClient, type QueryClient } from '@tanstack/react-query'

import { Button } from '@/components/ui/button'
import { CreateNewDialog } from '@/components/form/CreateNewDialog'
import { PursuitSaveResolver } from '@/components/pursuits/PursuitSaveResolver'
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
import { ErrorNotice } from '@/components/ui/notice'
import { answerableRefusalOf } from '@/lib/pursuitGroups'
import { refusalOf } from '@/lib/errors'
import { requestRegisterCheck } from '@/lib/spec/source'
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
  /**
   * Merged into the payload on save — values this form does not collect but
   * the record needs, like a registration's opening status or the two records
   * a conflict links.
   *
   * NEVER a system field. created_by/date and modified_by/date are stamped by
   * the server from the Entra session and its own clock, and a value sent for
   * one of them is discarded (app/routers/leads.py, SYSTEM_STAMPED). The
   * pipeline specs used to stamp them here; see PipelineModuleSpec in
   * components/pipeline/types.ts for why they no longer do.
   */
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
  /**
   * Where to render Save and Cancel, when the SCREEN already owns a bar they
   * belong in.
   *
   * A pipeline record has a sticky section header — "Stage 1 — Demo
   * Presentation" with its Edit button — and the edit controls belong on that
   * same line, replacing Edit, rather than opening a second sticky bar
   * underneath the first. The editor still owns the buttons and everything
   * they do; only where they are painted moves. Left undefined — every create
   * page, the registration form, CreateNewDialog — the editor renders its own
   * sticky bar exactly as before.
   */
  actionsSlot?: HTMLElement | null
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
 * A save is stopped by a malformed value, and by a required field it may not
 * leave empty (missingOnSave; the server applies the same rule,
 * app/requirements.py): a new record's few, a status's reason, or a field of a
 * stage the record has already left being emptied. The current stage may be
 * saved half-filled — the stage move is what asks for all of it.
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
  actionsSlot,
}: RecordEditorProps) {
  const form = useRecordForm()
  const queryClient = useQueryClient()
  const navigate = useNavigate()
  const [creatingFor, setCreatingFor] = useState<FieldSpec | null>(null)

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
    // `extra` is the answer to a question the server asked on a refused save —
    // "join this pursuit's group", "here is why it is a different project" —
    // merged into the SAME payload. See PursuitSaveResolver.
    mutationFn: async (extra?: Values) => {
      const payload = { ...form.toPayload(), ...stamp, ...extra }
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

  // Required fields this save may not leave empty, on this screen: they stop
  // the save. One that is due but in another section is left to the server, whose
  // refusal names it — this editor has no box to fill it in.
  const dueHere = Object.keys(form.dueRequired).filter((k) => onScreen.has(k))

  const submit = () => {
    form.markSubmitted()
    // A malformed value the user can see and fix stops the save, and so does
    // a required field it may not leave empty (see missingOnSave). Problems in
    // other sections do not, for the reason given on elsewhereErrors.
    const blocking = Object.keys(form.allErrors).filter((k) => onScreen.has(k))
    if (blocking.length > 0 || dueHere.length > 0) return
    save.mutate(undefined)
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

  // visibleErrors, not allErrors: an untouched field is not scolded before the
  // first save attempt.
  const shape = split(form.visibleErrors)

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

  // A required field the SERVER demanded and this screen didn't mark: someone
  // published a change in Administration since the page opened. Named here —
  // the one case where names help, since nothing below is marked — and the
  // update banner is asked to check (RegisterUpdateBanner).
  const unmarked = useMemo(() => {
    if (!save.isError) return []
    const refusal = refusalOf(save.error)
    if (refusal.code !== 'REQUIRED_FIELDS_MISSING') return []
    const fields = ((refusal.raw as { fields?: { api_name: string; label: string }[] } | null)?.fields ?? [])
    return fields.filter((f) => !(f.api_name in form.dueRequired))
  }, [save.isError, save.error, form.dueRequired])

  useEffect(() => {
    if (unmarked.length > 0) requestRegisterCheck()
  }, [unmarked.length])

  // The server's own reason, never a bare "could not be saved": a refused
  // Submitted Date in the future said nothing about what was wrong.
  const saveError =
    save.isError && !answerableRefusalOf(save.error) ? (
      <ErrorNotice
        error={save.error}
        suffix={
          unmarked.length > 0
            ? `Changed since this page opened: ${unmarked.map((f) => f.label).join(', ')}.`
            : undefined
        }
        fieldLabel={(name) => fieldOf(module, name.replace(/__s\d+$/, ''))?.label}
        fallback="The record wasn't saved. Try again."
      />
    ) : null

  /* Cancel before Save, reading order matching the destructive-then-primary
     pair every dialog in the app already uses. */
  const actions = (
    <>
      <Button
        type="button"
        variant="outline"
        size="sm"
        onClick={cancel}
        disabled={save.isPending}
      >
        Cancel
      </Button>
      <Button type="button" size="sm" onClick={submit} disabled={save.isPending}>
        {save.isPending ? 'Saving…' : (saveLabel ?? 'Save')}
      </Button>
    </>
  )

  return (
    <div className="space-y-3 py-3">
      {/* Two homes for one pair of buttons. Given a slot, they go and sit on
          the screen's own sticky header, on the line that a moment ago held
          Edit. Given none, the editor pins its own bar — which is what every
          create page still does. Either way Save is reachable without
          scrolling to the end of a form the register can make very long. */}
      {actionsSlot === undefined ? (
        <div className="bg-background sticky top-14 z-20 -mx-1 flex items-center justify-end gap-2 border-b px-1 py-2">
          {saveError && <div className="mr-auto">{saveError}</div>}
          {actions}
        </div>
      ) : actionsSlot ? (
        // `undefined` means no slot was asked for; `null` means one was asked
        // for and its element has not mounted yet. Told apart on purpose —
        // treating both as "render my own bar" flashed a second sticky bar for
        // one frame every time a tab remounted the editor.
        createPortal(actions, actionsSlot)
      ) : null}

      {/* With the buttons up in the screen's header there is no room for this
          beside them, and it is not a line to lose: it is the only thing that
          says a save FAILED rather than quietly did nothing. */}
      {actionsSlot !== undefined && saveError}
      {save.isError && (
        <PursuitSaveResolver error={save.error} pending={save.isPending} retry={(extra) => save.mutate(extra)} />
      )}

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

      <div className="space-y-2 border-t pt-3 empty:hidden">
        {/* A malformed value stops the save, so it is said here as well as on
            the field. So does an empty required field that is due — said
            once the user has tried to save, not before. */}
        {form.submitted && dueHere.length > 0 && (
          <p className="text-sm text-destructive">
            Fill in {dueHere.length === 1 ? 'this required field' : `these ${dueHere.length} required fields`}{' '}
            before saving.
          </p>
        )}
        {shape.here.length > 0 && (
          <p className="text-sm text-destructive">
            {shape.here.length} {shape.here.length === 1 ? 'field needs' : 'fields need'} fixing
            before this can be saved: {nameList(module, shape.here)}. Each is marked below.
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
            {elsewhereErrors.map((f) => `${f.label} (${f.section})`).join(', ')}. This
            does not stop you saving.
          </p>
        )}
      </div>
    </div>
  )
}
