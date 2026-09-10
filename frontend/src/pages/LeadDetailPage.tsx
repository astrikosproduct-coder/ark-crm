import { currentUserId } from '@/lib/currentUser'
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { ArrowRightIcon, LockIcon, PlusIcon } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { RecordListView } from '@/components/list/RecordListView'
import { contactListCell } from '@/components/contacts/contactListCell'
import { backfillContactsFromDemoAttendees } from '@/components/leads/DemoAttendeeSync'
import { LeadAdvanceDialog } from '@/components/leads/LeadAdvanceDialog'
import { LeadAccountFieldSync, backfillAccountFieldsFromLead } from '@/components/leads/LeadAccountFieldSync'
import { PipelineRecordPage } from '@/components/pipeline/PipelineRecordPage'
import type { PipelineModuleSpec, PipelineRecordContext } from '@/components/pipeline/types'
import { ComingSoon } from '@/pages/ComingSoon'
import { api } from '@/lib/api'
import { date as fmtDate, money } from '@/lib/format'
import { stageKeyOf, stagesFor } from '@/lib/pipeline'
import { displayNameOf } from '@/lib/spec'
import type { Values } from '@/lib/spec/conditions'

const MODULE = 'leads'
/** Leads' own range under the 14-stage-review split — spec/module_split.json
 * ranges.leads. See PipelineModuleSpec.stages: this is the one place that
 * range reaches the Lead screens. */
const LEADS_STAGES = stagesFor(MODULE)

/**
 * A converted Lead is history: it stays visible and stops being editable, so
 * the record that carried the pursuit through Stages 0-3 is still readable
 * after the Opportunity (or, for a Lead converted under the old flow before
 * the split, the Deal) takes over.
 */
function isConverted(values: Values): boolean {
  return values.lead_status === 'CONVERTED'
}

/**
 * The Deal this Lead became.
 *
 * The Lead register carries no field pointing forward to it — see
 * spec/extensions.json. Found by asking deals for the one with this parent_lead,
 * exactly the way deals.parent_lead is populated. Called from two slots; React
 * Query dedupes them on the key, so it is one request.
 */
function useConvertedDeal(ctx: PipelineRecordContext): string | undefined {
  const { data } = useQuery({
    queryKey: ['list', 'deals', 'parent_lead', ctx.id],
    queryFn: async () =>
      (await api.get<Values[]>('/deals', { params: { parent_lead: ctx.id } })).data,
    enabled: Boolean(ctx.id) && ctx.readOnly,
  })
  return data?.[0] ? String(data[0].id) : undefined
}

/**
 * The Opportunity this Lead became, exactly the same shape as useConvertedDeal.
 *
 * A read-only Lead can now be read-only for THREE reasons: LeadAdvanceDialog's
 * Move to picker landing on an Opportunity stage, the 14-stage-review split
 * reassigning a Stage 4-6 Lead to Opportunities at seed time or via the returning-browser
 * migration (lib/spec/pipelineSeed.ts), or — for data that predates the split
 * entirely — the old Stage-7 → Deal conversion. All three flip lead_status to
 * CONVERTED the same way, so the slots below still need to ask which target
 * actually exists: the wrong noun in a read-only banner is a small lie, but
 * it is still a lie.
 */
function useConvertedOpportunity(ctx: PipelineRecordContext): string | undefined {
  const { data } = useQuery({
    queryKey: ['list', 'opportunities', 'parent_lead', ctx.id],
    queryFn: async () =>
      (await api.get<Values[]>('/opportunities', { params: { parent_lead: ctx.id } })).data,
    enabled: Boolean(ctx.id) && ctx.readOnly,
  })
  return data?.[0] ? String(data[0].id) : undefined
}

function LeadHeader({ ctx }: { ctx: PipelineRecordContext }) {
  const tcv = ctx.values?.total_value_tcv ?? ctx.values?.estimated_value
  const probability = ctx.values?.probability_pct
  const closeMonth = ctx.values?.expected_close_month

  return (
    <>
      {typeof tcv === 'number' && (
        <span>
          {ctx.values?.total_value_tcv ? 'TCV' : 'Est. value'}: ${money(tcv)}
        </span>
      )}
      {typeof probability === 'number' && <span>Probability: {probability}%</span>}
      {typeof closeMonth === 'string' && closeMonth && <span>Close: {fmtDate(closeMonth)}</span>}
    </>
  )
}

/**
 * The advance dialog lives here rather than in a slot of its own, because the
 * button that opens it is the only thing that knows it exists. Radix portals the
 * dialog to the body, so rendering it beside the button costs nothing in
 * layout and keeps the state where it belongs.
 *
 * One button at every stage — not "Advance to Stage N" plus a separate
 * "Move to Opportunity's Module" at Stage 3 — because LeadAdvanceDialog's own
 * Move to picker already offers every reachable stage, Leads' own and
 * Opportunities', from wherever the lead currently sits.
 */
function LeadActions({ ctx }: { ctx: PipelineRecordContext }) {
  const navigate = useNavigate()
  const dealId = useConvertedDeal(ctx)
  const oppId = useConvertedOpportunity(ctx)
  const [advanceOpen, setAdvanceOpen] = useState(false)

  return (
    <>
      {ctx.readOnly ? (
        dealId ? (
          <Button variant="outline" onClick={() => navigate(`/deals/${dealId}`)}>
            <ArrowRightIcon className="size-4" />
            Go to {dealId}
          </Button>
        ) : (
          oppId && (
            <Button variant="outline" onClick={() => navigate(`/opportunities/${oppId}`)}>
              <ArrowRightIcon className="size-4" />
              Go to {oppId}
            </Button>
          )
        )
      ) : (
        <Button onClick={() => setAdvanceOpen(true)} disabled={ctx.isLoading || !ctx.values}>
          <ArrowRightIcon className="size-4" />
          Advance
        </Button>
      )}

      {/* OUTSIDE the readOnly branch, deliberately. A move into Opportunities
          sets lead_status to CONVERTED, which flips ctx.readOnly in the same
          invalidation — a dialog rendered inside the branch above would
          unmount itself mid-mutation. */}
      {ctx.values && (
        <LeadAdvanceDialog
          open={advanceOpen}
          leadId={ctx.id}
          values={ctx.values}
          currentStage={ctx.currentStage}
          onClose={() => setAdvanceOpen(false)}
          onAdvancedWithinLeads={(stage) => ctx.selectStage(stage)}
        />
      )}
    </>
  )
}

function LeadBanner({ ctx }: { ctx: PipelineRecordContext }) {
  const navigate = useNavigate()
  const dealId = useConvertedDeal(ctx)
  const oppId = useConvertedOpportunity(ctx)
  if (!ctx.readOnly) return null

  // dealId wins when both somehow resolve — it cannot in practice, since a
  // Lead converts to exactly one thing, but preferring the Deal keeps this
  // consistent with LeadActions' own precedence above.
  const target = dealId
    ? { article: 'a', module: 'Deal', id: dealId, path: 'deals' }
    : oppId
      ? { article: 'an', module: 'Opportunity', id: oppId, path: 'opportunities' }
      : undefined

  return (
    <div className="mb-4 flex items-center gap-2 rounded-lg border border-amber-500/40 bg-amber-500/10 px-4 py-2 text-sm text-amber-700 dark:text-amber-400">
      <LockIcon className="size-4 shrink-0" />
      <span>
        {target
          ? `This lead was converted to ${target.article} ${target.module} and is read-only.`
          : 'This lead is read-only.'}
        {target && (
          <>
            {' '}
            <button
              type="button"
              className="underline underline-offset-2"
              onClick={() => navigate(`/${target.path}/${target.id}`)}
            >
              View {target.id}
            </button>
          </>
        )}
      </span>
    </div>
  )
}

function LeadRelated({ ctx }: { ctx: PipelineRecordContext }) {
  const navigate = useNavigate()
  if (!ctx.values) return null

  const endClientId = typeof ctx.values.end_client === 'string' ? ctx.values.end_client : undefined

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between gap-3">
        <p className="text-sm text-muted-foreground">
          {ctx.endClient ? `Contacts at ${displayNameOf(ctx.endClient)}.` : 'No End Client set yet.'}
        </p>
        {endClientId && (
          <Button
            variant="outline"
            size="sm"
            onClick={() => navigate(`/contacts/new?account=${endClientId}`)}
          >
            <PlusIcon className="size-4" />
            Add contact
          </Button>
        )}
      </div>
      {endClientId ? (
        <RecordListView
          module="contacts"
          collection="contacts"
          basePath="/contacts"
          filter={{ account: endClientId }}
          hiddenColumns={['account']}
          renderCell={contactListCell}
          pageSize={10}
          emptyMessage="No contacts at this account yet."
        />
      ) : (
        <p className="text-sm text-muted-foreground">No End Client set yet.</p>
      )}
      <ComingSoon label="Quotes and the deal registration" />
    </div>
  )
}

export const leadsPipeline: PipelineModuleSpec = {
  module: MODULE,
  collection: 'leads',
  basePath: '/leads',
  noun: 'lead',
  stages: LEADS_STAGES,
  stageKeyOf,
  writesProbability: true,
  skipReasonField: 'stage_skip_reason',
  reversalReasonField: 'stage_reversal_reason',
  stamp: () => ({ modified_date: new Date().toISOString(), modified_by: currentUserId() }),
  detailsHeading: 'Cross-cutting and system fields',
  showProbabilityBand: true,
  tabs: ['current', 'details', 'history', 'related'],
  isReadOnly: isConverted,
  Header: LeadHeader,
  Actions: LeadActions,
  Banner: LeadBanner,
  Related: LeadRelated,
  // Segment <-> End Client account mapping lives only on Stage 0 — Connect,
  // where end_client is captured. See LeadAccountFieldSync.
  sideEffectsForStage: (stage) => (stage === 0 ? <LeadAccountFieldSync /> : undefined),
  // The Contact-record half of demo_attendees' field_sync only needs to run
  // once a Stage 1 save has actually happened — the live row <-> Contact
  // direction runs inside ChildListTable itself, on every stage that renders
  // the table, and needs no afterSave wiring at all.
  afterSaveForStage: (stage) => {
    if (stage === 0) return backfillAccountFieldsFromLead
    if (stage === 1) return backfillContactsFromDemoAttendees
    return undefined
  },
}

export function LeadDetailPage() {
  return <PipelineRecordPage spec={leadsPipeline} />
}
