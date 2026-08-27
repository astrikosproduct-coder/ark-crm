import { useMemo, useState } from 'react'
import { useLocation, useParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { ArrowRightIcon, PencilIcon } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { RecordForm } from '@/components/form/RecordForm'
import { RecordEditor } from '@/components/record/RecordEditor'
import { UnsavedBadge } from '@/components/record/UnsavedBadge'
import { ReadinessPanel } from '@/components/leads/ReadinessPanel'
import { StageChip } from '@/components/leads/StageChip'
import { StageRail } from '@/components/leads/StageRail'
import { AdvanceStageDialog } from '@/components/pipeline/AdvanceStageDialog'
import { HEADER_STRIP_SECTION, HeaderStrip } from '@/components/pipeline/HeaderStrip'
import { StageHistoryTab } from '@/components/pipeline/StageHistoryTab'
import type {
  PipelineModuleSpec,
  PipelineRecordContext,
  PipelineTab,
} from '@/components/pipeline/types'
import { NEW_RECORD_ID } from '@/hooks/useRecordForm'
import { useResolvedRecord } from '@/hooks/useResolvedRecord'
import { api } from '@/lib/api'
import {
  sectionsForStage,
  skippedStagesOf,
  stageFieldOf,
  stageNumberOf,
  stageOf,
  type Transition,
} from '@/lib/pipeline'
import { displayNameOf, sectionsFor, withRecordId } from '@/lib/spec'
import type { Values } from '@/lib/spec/conditions'
import { useDiscardToken } from '@/store/useDraftStore'

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

  const firstStage = spec.stages.length ? spec.stages[0].stage : 0
  const lastStage = spec.stages.length ? spec.stages[spec.stages.length - 1].stage : firstStage

  const [activeTab, setActiveTab] = useState<PipelineTab>(spec.tabs[0] ?? 'current')
  // LeadCreatePage navigates here asking for the first stage section to open
  // ready to type in, rather than making the user find and press Edit.
  const [editingCurrent, setEditingCurrent] = useState(() =>
    Boolean((location.state as { editOnOpen?: boolean } | null)?.editOnOpen)
  )
  const [editingDetails, setEditingDetails] = useState(false)
  const [advanceOpen, setAdvanceOpen] = useState(false)
  const [selectedStage, setSelectedStage] = useState<number | null>(null)

  const draftId = id ?? NEW_RECORD_ID
  const currentDiscardToken = useDiscardToken(spec.module, draftId)

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

  const detailSections = useMemo(
    () =>
      sectionsFor(spec.module).filter(
        (s) => !s.startsWith('STAGE') && s !== HEADER_STRIP_SECTION
      ),
    [spec.module]
  )
  // Plural, deliberately: a stage can carry more than one section — Deals'
  // Stage 7 has both its own register-native ON CONVERSION and the
  // moved-in STAGE 7 — CLOSE. sectionForStage (singular) would silently drop
  // the second one; see its own comment in lib/pipeline.ts.
  const stageSections = sectionsForStage(spec.module, stageToShow)
  const stageSpec = stageOf(stageToShow)

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
    openAdvance: () => setAdvanceOpen(true),
    selectStage: (stage) => {
      setSelectedStage(stage)
      setActiveTab('current')
    },
    setActiveTab,
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

  const { Header, Actions, Banner, Related, Extras } = spec

  return (
    <div className="mx-auto max-w-7xl px-6 py-6">
      <div className="mb-4 flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0">
          <h1 className="flex flex-wrap items-center gap-2 text-xl font-semibold">
            {values ? displayNameOf(values) : (id ?? '')}
            <StageChip value={currentStage} />
            <UnsavedBadge module={spec.module} recordId={draftId} />
          </h1>
          <div className="text-muted-foreground mt-1 flex flex-wrap items-center gap-x-4 gap-y-1 text-sm">
            <span>{id}</span>
            {endClient && <span>Client: {displayNameOf(endClient)}</span>}
            {partner && <span>Partner: {displayNameOf(partner)}</span>}
            {Header && <Header ctx={ctx} />}
          </div>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          {Actions ? (
            <Actions ctx={ctx} />
          ) : (
            <Button onClick={ctx.openAdvance} disabled={isLoading || !values}>
              <ArrowRightIcon className="size-4" />
              {currentStage >= lastStage ? 'Change stage' : `Advance to Stage ${currentStage + 1}`}
            </Button>
          )}
        </div>
      </div>

      {Banner && <Banner ctx={ctx} />}

      {values && (
        <HeaderStrip
          module={spec.module}
          collection={spec.collection}
          recordId={id ?? ''}
          values={values}
          readOnly={readOnly}
        />
      )}

      {stageSpec && (
        <p className="text-muted-foreground mb-2 text-xs">
          {/* stageToShow, not currentStage: every other value on this line comes
              from the stage the rail has selected, so pairing them with the
              current stage's NUMBER read as "Stage 3 · Connect · 0–10%". */}
          Stage {stageToShow} · {stageSpec.name}
          {spec.showProbabilityBand &&
            ` · ${stageSpec.prob_min ?? '—'}–${stageSpec.prob_max ?? '—'}%`}{' '}
          · owner role {stageSpec.owner_role}
        </p>
      )}

      <div className="mb-6 rounded-lg border p-4">
        <StageRail
          stages={spec.stages}
          currentStage={currentStage}
          selectedStage={stageToShow}
          skipped={skipped}
          onSelectStage={ctx.selectStage}
        />
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-[1fr_360px]">
        <Tabs value={activeTab} onValueChange={(t) => setActiveTab(t as PipelineTab)}>
          <TabsList>
            {spec.tabs.map((tab) => (
              <TabsTrigger key={tab} value={tab}>
                {TAB_LABEL[tab]}
              </TabsTrigger>
            ))}
          </TabsList>

          <TabsContent value="current">
            {isLoading || !values ? (
              <p className="py-6 text-sm text-muted-foreground">Loading…</p>
            ) : (
              <div className="space-y-3">
                <div className="flex items-center justify-between">
                  <h2 className="text-sm font-semibold">
                    Stage {stageToShow}
                    {stageSpec ? ` — ${stageSpec.name}` : ''}
                  </h2>
                  {!editingCurrent && !readOnly && (
                    <Button variant="outline" size="sm" onClick={() => setEditingCurrent(true)}>
                      <PencilIcon className="size-4" />
                      Edit
                    </Button>
                  )}
                </div>

                {stageSections.length > 0 ? (
                  editingCurrent && !readOnly ? (
                    <RecordEditor
                      key={`edit:${id}:${stageToShow}:${dataUpdatedAt}:${currentDiscardToken}`}
                      module={spec.module}
                      collection={spec.collection}
                      recordId={id}
                      initialValues={values}
                      resolved={resolved}
                      sections={stageSections}
                      stamp={spec.stamp()}
                      sideEffects={spec.sideEffectsForStage?.(stageToShow)}
                      afterSave={spec.afterSaveForStage?.(stageToShow)}
                      onSaved={() => setEditingCurrent(false)}
                      onCancel={() => setEditingCurrent(false)}
                    />
                  ) : (
                    <RecordForm
                      key={`view:${id}:${stageToShow}:${dataUpdatedAt}`}
                      module={spec.module}
                      mode="view"
                      values={values}
                      resolved={resolved}
                      sections={stageSections}
                    />
                  )
                ) : (
                  <p className="text-sm text-muted-foreground">
                    No fields registered for this stage.
                  </p>
                )}
              </div>
            )}
          </TabsContent>

          <TabsContent value="details">
            {isLoading || !values ? (
              <p className="py-6 text-sm text-muted-foreground">Loading…</p>
            ) : (
              <div className="space-y-3">
                <div className="flex items-center justify-between">
                  <h2 className="text-sm font-semibold">{spec.detailsHeading}</h2>
                  {!editingDetails && !readOnly && (
                    <Button variant="outline" size="sm" onClick={() => setEditingDetails(true)}>
                      <PencilIcon className="size-4" />
                      Edit
                    </Button>
                  )}
                </div>

                {editingDetails && !readOnly ? (
                  <RecordEditor
                    key={`edit:${id}:details:${dataUpdatedAt}:${currentDiscardToken}`}
                    module={spec.module}
                    collection={spec.collection}
                    recordId={id}
                    initialValues={values}
                    resolved={resolved}
                    sections={detailSections}
                    stamp={spec.stamp()}
                    onSaved={() => setEditingDetails(false)}
                    onCancel={() => setEditingDetails(false)}
                  />
                ) : (
                  <RecordForm
                    key={`view:${id}:details:${dataUpdatedAt}`}
                    module={spec.module}
                    mode="view"
                    values={values}
                    resolved={resolved}
                    sections={detailSections}
                  />
                )}
              </div>
            )}
          </TabsContent>

          <TabsContent value="history">
            <StageHistoryTab
              transitions={transitions}
              emptyMessage={`No transitions recorded yet — this ${spec.noun} has never changed stage.`}
            />
          </TabsContent>

          <TabsContent value="related">{Related && <Related ctx={ctx} />}</TabsContent>
        </Tabs>

        <div className="lg:sticky lg:top-4 lg:self-start">
          {values && (
            <ReadinessPanel
              module={spec.module}
              values={values}
              from={currentStage}
              to={Math.min(currentStage + 1, lastStage)}
              onJumpToField={(field) => {
                if (field.capture_stage !== null) setSelectedStage(field.capture_stage)
                setActiveTab(field.capture_stage !== null ? 'current' : 'details')
              }}
            />
          )}
        </div>
      </div>

      {values && (
        <AdvanceStageDialog
          spec={spec}
          open={advanceOpen}
          recordId={id ?? ''}
          values={values}
          currentStage={currentStage}
          onClose={() => setAdvanceOpen(false)}
          onAdvanced={(toStage) => setSelectedStage(toStage)}
        />
      )}

      {Extras && <Extras ctx={ctx} />}
    </div>
  )
}
