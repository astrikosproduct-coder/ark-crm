import { useCallback, useLayoutEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { useLocation, useNavigate, useParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { formatDistanceToNow } from 'date-fns'
import { ArrowLeftIcon, ClockIcon, PencilIcon } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { RecordForm } from '@/components/form/RecordForm'
import { RecordEditor } from '@/components/record/RecordEditor'
import { StageRail } from '@/components/leads/StageRail'
import { AdvanceStageDialog } from '@/components/pipeline/AdvanceStageDialog'
import { HEADER_STRIP_SECTION, HeaderStrip } from '@/components/pipeline/HeaderStrip'
import { PriorityFlagMark } from '@/components/opportunities/PriorityFlagMark'
import { RecordTimelineTab } from '@/components/pipeline/RecordTimelineTab'
import { Lineage } from '@/components/pipeline/Lineage'
import { ReasonsPanel } from '@/components/pipeline/StageScopedFields'
import type {
  PipelineModuleSpec,
  PipelineRecordContext,
  PipelineTab,
} from '@/components/pipeline/types'
import { useResolvedRecord } from '@/hooks/useResolvedRecord'
import { api } from '@/lib/api'
import {
  STAGES,
  sectionsForStage,
  skippedStagesOf,
  stageFieldOf,
  stageNumberOf,
  type Transition,
} from '@/lib/pipeline'
import { displayNameOf, fieldOf, fieldsOf, sectionsFor, withRecordId } from '@/lib/spec'
import { requestDiscard } from '@/store/useUnsavedChangesStore'
import { revealField } from '@/lib/revealField'
import { restoreScroll } from '@/lib/preserveScroll'
import { ragAccent } from '@/lib/rag'
import { cn } from '@/lib/utils'
import { type Values } from '@/lib/spec/conditions'
import { hiddenFromFormNamesOf, isStageScopedModule } from '@/lib/stageScope'
import type { FieldSpec } from '@/types/field'

/**
 * The register section holding the record's key facts — Overall RAG, Next
 * Milestone (+ date), Expected Close Month, and Progression % / Probability %.
 * Drawn first on the stage tab and excluded from Details, so there is only ever
 * one place to edit them.
 *
 * FOUND BY A FIELD IT CONTAINS, NEVER BY ITS NAME. This was `'HEADER'`, a
 * literal section label, and renaming that section in Administration to
 * "Health & Forecast" — which is exactly what Administration is for — broke
 * this screen in two ways at once: the stage tab rendered an empty box for a
 * section that no longer existed, and the six real fields fell through to the
 * Details tab, because the filter below was excluding the old name too.
 *
 * A section's LABEL is display text a user may rewrite at any time. An
 * api_name is its key. So the section is resolved through one, per module,
 * since a rename now moves the answer rather than deleting it.
 */
const KEY_FACTS_ANCHOR = 'overall_rag'

function keyFactsSectionOf(module: string): string | null {
  return fieldOf(module, KEY_FACTS_ANCHOR)?.section ?? null
}

/**
 * A tab's own header, pinned under the top bar: what you are looking at on the
 * left, what you can do to it on the right.
 *
 * One line, one set of controls, swapped for each other rather than stacked:
 * Edit while reading, Cancel and Save while editing. Before this, Edit scrolled
 * away with the heading and the editor opened a SECOND sticky bar below the top
 * bar to hold Save — two bars for one row of buttons, and the one you wanted
 * was whichever was not on screen. `top-14` is the top bar's own h-14.
 */
function SectionBar({ title, children }: { title: ReactNode; children?: ReactNode }) {
  return (
    <div className="bg-background sticky top-14 z-20 -mx-1 flex items-center justify-between gap-3 border-b px-1 py-2">
      <h2 className="truncate text-sm font-semibold">{title}</h2>
      <div className="flex shrink-0 items-center gap-2">{children}</div>
    </div>
  )
}

const TAB_LABEL: Record<PipelineTab, string> = {
  current: 'Current stage',
  details: 'Details',
  history: 'History',
  related: 'Related',
}

/**
 * One record of one pipeline module.
 *
 * Leads and Deals were separate 430-line files that had drifted apart in small
 * ways nobody intended — a date formatted two ways, a heading worded twice, a
 * stage line reading a different variable. Adding Opportunities as a third copy
 * would have made every future change a three-way edit with two chances to
 * forget one.
 *
 * So the shell lives here once: fetch the record, resolve it through its parent
 * chain, draw the rail, render the selected stage's section, the non-stage
 * sections, the readiness panel and the history. Everything genuinely specific
 * to a module — its buttons, its banner, its Related tab, its dialogs — arrives
 * as a slot component from the module's own page, where it stays readable.
 */
export function PipelineRecordPage({ spec }: { spec: PipelineModuleSpec }) {
  const { id } = useParams<{ id: string }>()
  const location = useLocation()
  const navigate = useNavigate()

  /**
   * A stage number as a person reads it. The timeline renders a move as
   * "Stage 1 - Demo Presentation", and a transition row carries only the
   * numbers — ALL ten stages are looked up here rather than spec.stages,
   * which is this module's own range: a Lead that moved to an Opportunity
   * stage has a transition naming a stage its own rail never draws.
   */
  const stageNameOf = useCallback(
    (stage: number) => STAGES.find((s) => s.stage === stage)?.name ?? `Stage ${stage}`,
    []
  )

  const firstStage = spec.stages.length ? spec.stages[0].stage : 0

  const [activeTab, setActiveTab] = useState<PipelineTab>(spec.tabs[0] ?? 'current')
  // LeadCreatePage navigates here asking for the first stage section to open
  // ready to type in, rather than making the user find and press Edit.
  const [editingCurrent, setEditingCurrent] = useState(() =>
    Boolean((location.state as { editOnOpen?: boolean } | null)?.editOnOpen)
  )
  const [editingDetails, setEditingDetails] = useState(false)
  /**
   * Where each tab's editor paints its Save and Cancel.
   *
   * State rather than a ref, because a ref would not re-render the editor when
   * the node arrives and the portal would never open. Rendered unconditionally
   * — not only while editing — so the element already exists on the render
   * that mounts the editor, and the buttons appear on the same frame the form
   * does. See RecordEditor.actionsSlot.
   */
  const [currentActionsEl, setCurrentActionsEl] = useState<HTMLDivElement | null>(null)
  const [detailsActionsEl, setDetailsActionsEl] = useState<HTMLDivElement | null>(null)

  /**
   * Where the page was when Edit (or Cancel, or a save) was pressed.
   *
   * Set by the click, consumed by the layout effect below, which runs after
   * React has swapped the form for the editor but before the browser paints —
   * so the reader stays exactly where they were and never sees the jump. See
   * lib/preserveScroll.ts for what the browser does without this.
   */
  const scrollBack = useRef<number | null>(null)

  const switchMode = (change: () => void) => {
    scrollBack.current = window.scrollY
    change()
  }

  useLayoutEffect(() => {
    const y = scrollBack.current
    if (y === null) return
    scrollBack.current = null
    restoreScroll(y)
  }, [editingCurrent, editingDetails])
  const [advanceOpen, setAdvanceOpen] = useState(false)
  const [selectedStage, setSelectedStage] = useState<number | null>(null)

  const { data, isLoading, isError, dataUpdatedAt } = useQuery({
    queryKey: ['record', spec.collection, id],
    queryFn: async () => (await api.get<Record<string, unknown>>(`/${spec.collection}/${id}`)).data,
    enabled: Boolean(id),
  })

  const stored = useMemo(() => (data ? withRecordId(spec.module, data) : undefined), [spec.module, data])

  /**
   * The EFFECTIVE record: what this record's values ARE, not what it stores.
   *
   * Identity is read through the parent chain rather than copied — see
   * read_through in spec/module_split.json. Everything below is handed `values`,
   * so the form, the formulas and the readiness panel all see the same merged
   * record and none of them needs to know a parent exists. A module with no
   * parent resolves to itself and fires no queries.
   */
  const resolved = useResolvedRecord(spec.module, stored)
  const values = stored ? resolved.values : undefined

  const stageField = stageFieldOf(spec.module)
  const currentStage =
    (values && stageField ? stageNumberOf(values[stageField]) : null) ?? firstStage
  const stageToShow = selectedStage ?? currentStage
  const readOnly = Boolean(values && spec.isReadOnly?.(values))

  /**
   * Drill down from a readiness criterion to the field that proves it.
   *
   * Three things have to happen in order and none of them is optional: the
   * field's own stage has to be selected (a Stage 1 field is not on screen
   * while the rail shows Stage 3), the tab that holds it has to be active, and
   * the section has to be in EDIT mode — landing a user on a read-only line of
   * text when they came to fill it in is a dead end. revealField then waits for
   * React to commit all of that before it scrolls and pulses.
   *
   * requestDiscard wraps the lot, so an editor with unsaved changes gets the
   * same question here as it would for any other navigation.
   */
  const jumpToField = (field: FieldSpec) => {
    requestDiscard(() => {
      const onStage = field.capture_stage !== null
      if (onStage) setSelectedStage(field.capture_stage)
      setActiveTab(onStage ? 'current' : 'details')
      if (!readOnly) {
        if (onStage) setEditingCurrent(true)
        else setEditingDetails(true)
      }
      revealField(field.api_name)
    })
  }

  const { data: endClient } = useQuery({
    queryKey: ['record', 'accounts', values?.end_client],
    queryFn: async () => (await api.get<Values>(`/accounts/${values?.end_client}`)).data,
    enabled: Boolean(values?.end_client),
  })
  const { data: partner } = useQuery({
    queryKey: ['record', 'accounts', values?.customer_partner_si],
    queryFn: async () => (await api.get<Values>(`/accounts/${values?.customer_partner_si}`)).data,
    enabled: Boolean(values?.customer_partner_si),
  })

  const { data: transitions } = useQuery({
    queryKey: ['list', 'transitions', id],
    queryFn: async () =>
      (await api.get<Transition[]>('/transitions', { params: { record_id: id } })).data,
    enabled: Boolean(id),
  })

  const skipped = useMemo(() => skippedStagesOf(transitions ?? []), [transitions])

  // The record's own modified_date, not when this browser last fetched it.
  // Absent on a module that does not register one, in which case the line is
  // not drawn at all rather than guessed at.
  const lastUpdate = useMemo(() => {
    const raw = values?.modified_date
    if (typeof raw !== 'string' || !raw) return null
    const at = new Date(raw)
    return Number.isNaN(at.getTime()) ? null : formatDistanceToNow(at, { addSuffix: true })
  }, [values])

  const keyFacts = useMemo(() => keyFactsSectionOf(spec.module), [spec.module])

  const detailSections = useMemo(
    () =>
      sectionsFor(spec.module).filter(
        (s) =>
          !s.startsWith('STAGE') &&
          s !== HEADER_STRIP_SECTION &&
          s !== keyFacts &&
          // Identity read through the parent is shown on the Related tab only,
          // under the parent record that owns it (decided 16 Sep 2026) — see
          // ParentRecordsPanel. Decided by the fields, not by the section's
          // name: a section every one of whose fields is read-through.
          !fieldsOf(spec.module)
            .filter((f) => f.section === s)
            .every((f) => f.value_mode === 'read_through')
      ),
    [spec.module, keyFacts]
  )
  // Plural, deliberately: a stage can carry more than one section — Deals'
  // Stage 7 has STAGE 7 — COMMERCIAL TERMS and STAGE 7 — CLOSE, and
  // Opportunities' Stage 4 has three. sectionForStage (singular) would
  // silently drop all but the first; see its own comment in lib/pipeline.ts.
  //
  // HEADER leads, on every stage. It holds the record's key facts — Overall
  // RAG, Next Milestone, Progression % / Probability %, Expected Close Month —
  // which used to be three hand-built strips above the tabs that each saved on
  // a 300ms debounce as the user typed. They are ordinary fields of this form
  // now: one Save, one request, and the per-stage ones still read and write
  // their own stage through the projection in useRecordForm.
  // A module whose register has no such section simply renders the stage's own
  // sections — never an empty box for a name nothing answers to.
  const stageSections = useMemo(
    () => [...(keyFacts ? [keyFacts] : []), ...sectionsForStage(spec.module, stageToShow)],
    [spec.module, stageToShow, keyFacts]
  )

  /**
   * api_names the FORM must not draw, because another surface on this screen
   * draws them — see lib/stageScope.ts.
   *
   * This used to be every stage-scoped name. Two of them come back off the list
   * in Phase A2: On Hold Reason and Closed Lost Reason Code are anchored to the
   * status field and rendered by the ordinary RecordForm now, in the same form
   * as the picklist that reveals them, which is the only way a condition can
   * fire before a save. What stays hidden is what genuinely has its own
   * surface: the two reasons the Advance dialog writes, which no form should
   * offer a second box for.
   */
  const hiddenFields = useMemo(
    () => (isStageScopedModule(spec.module) ? hiddenFromFormNamesOf(spec.module) : undefined),
    [spec.module]
  )

  /**
   * Which stage a form's per-stage fields read and write.
   *
   * The stage tab edits the stage on the rail. The Details tab edits the stage
   * the record is AT: a reason typed there is being given now, so it belongs to
   * now. Without this the inline reason box would read and write the plain
   * api_name and there would be one On Hold Reason per record — the thing
   * lib/stageScope.ts exists to prevent.
   */
  // Memoised, and not for tidiness: a new object each render would make the
  // form's scoped-field list, its per-stage projection and therefore its whole
  // `values` map recompute on every keystroke, dragging validation and every
  // formula along with them.
  const stageScope = useMemo(
    () =>
      isStageScopedModule(spec.module) ? { stage: stageToShow, currentStage } : undefined,
    [spec.module, stageToShow, currentStage]
  )
  const detailsStageScope = useMemo(
    () =>
      isStageScopedModule(spec.module)
        ? { stage: currentStage, currentStage }
        : undefined,
    [spec.module, currentStage]
  )

  const ctx: PipelineRecordContext = {
    spec,
    id: id ?? '',
    values,
    resolved,
    currentStage,
    stageToShow,
    isLoading,
    readOnly,
    endClient,
    partner,
    transitions,
    // Each of these unmounts or re-keys an open editor, so each asks first
    // when something is unsaved — see useUnsavedChangesStore.
    openAdvance: () => requestDiscard(() => setAdvanceOpen(true)),
    selectStage: (stage) =>
      requestDiscard(() => {
        setSelectedStage(stage)
        setActiveTab('current')
      }),
    setActiveTab: (tab) => requestDiscard(() => setActiveTab(tab)),
    jumpToField,
  }

  if (isError) {
    return (
      <div className="mx-auto max-w-5xl px-6 py-6">
        <p className="text-sm text-destructive">
          No {spec.noun} with id {id}.
        </p>
      </div>
    )
  }

  const { Header, Actions, Banner, Related, Extras, StagePanel } = spec

  return (
    <div className="mx-auto max-w-7xl px-6 py-6">
      {/* The RAG stripe, third of the three places it appears — the Kanban card
          and the list row are the other two, drawn by the same helper so a Red
          pursuit is the same mark wherever it is met. pl-3 keeps the back
          button off the stripe. */}
      <div
        className={cn(
          'mb-4 flex flex-wrap items-start justify-between gap-4',
          values && ragAccent(values) && `${ragAccent(values)} rounded-l-sm pl-3`
        )}
      >
        <div className="flex min-w-0 items-start gap-2">
          {/* Back before the title, as the reference has it — §3.3. */}
          <button
            type="button"
            aria-label="Back"
            title="Back"
            onClick={() => requestDiscard(() => navigate(-1))}
            className="text-muted-foreground hover:bg-accent hover:text-foreground mt-0.5 flex size-8 shrink-0 items-center justify-center rounded-md transition-colors"
          >
            <ArrowLeftIcon className="size-5" />
          </button>
          <div className="min-w-0">
          <h1 className="text-record-title flex flex-wrap items-center gap-2 font-bold">
            {values ? displayNameOf(values) : (id ?? '')}
            {/* Low Hanging / Top 10. Nothing on Leads and Deals, which do
                not carry the flags. See PriorityFlagMark. */}
            <PriorityFlagMark row={values} variant="full" className="text-sm" />
          </h1>
          <div className="text-muted-foreground text-meta mt-1 flex flex-wrap items-center gap-x-4 gap-y-1">
            {/* No record id. It is in the address bar, and the Update Stage
                dialog puts it in its own title where it is actually needed —
                on the line under the record's NAME it was the least useful
                thing there. */}
            {endClient && <span>End client: {displayNameOf(endClient)}</span>}
            {partner && <span>Partner: {displayNameOf(partner)}</span>}
            <Lineage ctx={ctx} />
            {Header && <Header ctx={ctx} />}
          </div>
          </div>
        </div>
        {/* ml-auto keeps the actions in the right corner of the title line
            even when the title wraps. Readiness is not here: the Update Stage
            dialog shows the same checks for the move actually being made. */}
        <div className="ml-auto flex shrink-0 items-center gap-2">
          {Actions ? (
            <Actions ctx={ctx} />
          ) : (
            <Button onClick={ctx.openAdvance} disabled={isLoading || !values}>
              Update Stage
            </Button>
          )}
        </div>
      </div>

      {Banner && <Banner ctx={ctx} />}

      <Tabs
        value={activeTab}
        onValueChange={(t) => requestDiscard(() => setActiveTab(t as PipelineTab))}
      >
        {/* Where the record IS, above how you look at it. The rail states the
            record's state and the pill below chooses a view of it — the order
            they were in read as though the rail were a fifth tab. */}
        <div className="bg-card mb-4 rounded-lg p-4 shadow-sm">
          {/* Nothing under the rail. The line that used to sit here — "Stage 1 ·
              Demo Presentation · 10–20% · owner role BD_OWNER" — restated the
              node the rail had just drawn and highlighted, then added a
              probability band and an owner ROLE CODE that no reader of this
              screen acts on. The section header below already names the stage
              whose fields are on screen. */}
          <StageRail stages={spec.stages} currentStage={currentStage} skipped={skipped} />
        </div>

        {/* The reference's sub-header: the view switcher as a segmented pill on
            the left, when the record was last touched on the right — §3.3. */}
        <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
          <TabsList variant="pill">
            {spec.tabs.map((tab) => (
              <TabsTrigger key={tab} value={tab} variant="pill">
                {TAB_LABEL[tab]}
              </TabsTrigger>
            ))}
          </TabsList>
          {lastUpdate && (
            <span className="text-muted-foreground flex items-center gap-1.5 text-xs">
              <ClockIcon className="size-3.5" />
              Last update: {lastUpdate}
            </span>
          )}
        </div>

        {values && (
          <HeaderStrip
            module={spec.module}
            collection={spec.collection}
            recordId={id ?? ''}
            values={values}
            readOnly={readOnly}
          />
        )}

        <TabsContent value="current">
          {isLoading || !values ? (
            <p className="py-6 text-sm text-muted-foreground">Loading…</p>
          ) : (
            <div className="space-y-3">
              <SectionBar title={spec.recordHeading}>
                {!editingCurrent && !readOnly && (
                  <Button variant="outline" size="sm" onClick={() => switchMode(() => setEditingCurrent(true))}>
                    <PencilIcon className="size-4" />
                    Edit
                  </Button>
                )}
                <div ref={setCurrentActionsEl} className="contents" />
              </SectionBar>

              {stageSections.length > 0 ? (
                editingCurrent && !readOnly ? (
                  <RecordEditor
                    key={`edit:${id}:${stageToShow}:${dataUpdatedAt}`}
                    module={spec.module}
                    collection={spec.collection}
                    recordId={id}
                    initialValues={values}
                    resolved={resolved}
                    sections={stageSections}
                    hiddenFields={hiddenFields}
                    stageScope={stageScope}
                    sideEffects={spec.sideEffectsForStage?.(stageToShow)}
                    afterSave={spec.afterSaveForStage?.(stageToShow)}
                    actionsSlot={currentActionsEl}
                    onSaved={() => switchMode(() => setEditingCurrent(false))}
                    onCancel={() => switchMode(() => setEditingCurrent(false))}
                  />
                ) : (
                  <RecordForm
                    key={`view:${id}:${stageToShow}:${dataUpdatedAt}`}
                    module={spec.module}
                    mode="view"
                    values={values}
                    resolved={resolved}
                    sections={stageSections}
                    hiddenFields={hiddenFields}
                    stageScope={stageScope}
                  />
                )
              ) : (
                <p className="text-sm text-muted-foreground">
                  No fields registered for this stage.
                </p>
              )}

              {/* A table that belongs to this stage but not to this record's
                  own fields — Deals' Stage 8 payment milestones, whose rows
                  are the parent Opportunity's. The slot decides which stages
                  it draws on; it is mounted on every one. */}
              {StagePanel && <StagePanel ctx={ctx} />}

              {/* The reasons this stage calls for are IN the form above now,
                  beside the field that asks for them — see
                  lib/spec/anchors.ts. What every stage answered is on the
                  Details tab, read-only, in ReasonsPanel. */}
            </div>
          )}
        </TabsContent>

        <TabsContent value="details">
          {isLoading || !values ? (
            <p className="py-6 text-sm text-muted-foreground">Loading…</p>
          ) : (
            <div className="space-y-3">
              <SectionBar title={spec.detailsHeading}>
                {!editingDetails && !readOnly && (
                  <Button variant="outline" size="sm" onClick={() => switchMode(() => setEditingDetails(true))}>
                    <PencilIcon className="size-4" />
                    Edit
                  </Button>
                )}
                <div ref={setDetailsActionsEl} className="contents" />
              </SectionBar>

              {editingDetails && !readOnly ? (
                <RecordEditor
                  key={`edit:${id}:details:${dataUpdatedAt}`}
                  module={spec.module}
                  collection={spec.collection}
                  recordId={id}
                  initialValues={values}
                  resolved={resolved}
                  sections={detailSections}
                  hiddenFields={hiddenFields}
                  stageScope={detailsStageScope}
                  actionsSlot={detailsActionsEl}
                  onSaved={() => switchMode(() => setEditingDetails(false))}
                  onCancel={() => switchMode(() => setEditingDetails(false))}
                />
              ) : (
                <RecordForm
                  key={`view:${id}:details:${dataUpdatedAt}`}
                  module={spec.module}
                  mode="view"
                  values={values}
                  resolved={resolved}
                  sections={detailSections}
                  hiddenFields={hiddenFields}
                  stageScope={detailsStageScope}
                />
              )}

              {/* Every reason the record has given, at every stage it gave
                  one. Read-only on purpose: the boxes are inline, this is
                  the record of what went into them. */}
              {isStageScopedModule(spec.module) && (
                <ReasonsPanel
                  module={spec.module}
                  values={values}
                  onOpenStage={ctx.selectStage}
                  onOpenHistory={() => ctx.setActiveTab('history')}
                />
              )}
            </div>
          )}
        </TabsContent>

        <TabsContent value="history">
          {id && (
            <RecordTimelineTab
              module={spec.module}
              recordId={id}
              noun={spec.noun}
              transitions={transitions}
              stageName={stageNameOf}
            />
          )}
        </TabsContent>

        <TabsContent value="related">{Related && <Related ctx={ctx} />}</TabsContent>
      </Tabs>

      {values && (
        <AdvanceStageDialog
          spec={spec}
          open={advanceOpen}
          recordId={id ?? ''}
          values={values}
          currentStage={currentStage}
          onJumpToField={jumpToField}
          onClose={() => setAdvanceOpen(false)}
          onAdvanced={(toStage) => setSelectedStage(toStage)}
        />
      )}

      {Extras && <Extras ctx={ctx} />}
    </div>
  )
}
