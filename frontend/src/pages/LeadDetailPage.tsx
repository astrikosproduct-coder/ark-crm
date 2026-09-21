import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { ArrowRightIcon, LockIcon, Trash2Icon } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { DeleteLeadDialog } from '@/components/leads/DeleteLeadDialog'
import { backfillContactsFromDemoAttendees } from '@/components/leads/DemoAttendeeSync'
import { LeadAdvanceDialog } from '@/components/leads/LeadAdvanceDialog'
import { LeadAccountFieldSync, backfillAccountFieldsFromLead } from '@/components/leads/LeadAccountFieldSync'
import { PipelineRecordPage } from '@/components/pipeline/PipelineRecordPage'
import { PipelineRelated } from '@/components/pipeline/PipelineRelated'
import { PursuitBanner } from '@/components/pursuits/PursuitBanner'
import type { PipelineModuleSpec, PipelineRecordContext } from '@/components/pipeline/types'
import { api } from '@/lib/api'
import { date as fmtDate } from '@/lib/format'
import { stageKeyOf, stagesFor } from '@/lib/pipeline'
import { localAmount, revenueOf } from '@/lib/revenue'
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
 * reassigning a Stage 4-6 Lead to Opportunities when the seed data was
 * migrated, or — for data that predates the split
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
  // Estimated Value and nothing else — this read total_value_tcv first, a
  // field a Lead does not carry. One revenue source per module; see lib/revenue.ts.
  const revenue = ctx.values ? revenueOf(ctx.values) : null
  const closeMonth = ctx.values?.expected_close_month

  // Probability % is NOT shown here — it is a field in the record's header
  // section, set from the stage. See StageScopedFields.tsx.
  return (
    <>
      {revenue?.value != null && (
        <span>
          {revenue.label}: {localAmount(revenue)}
        </span>
      )}
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
  const [deleting, setDeleting] = useState(false)

  return (
    <>
      {/* Offered on every lead; the dialog says what, if anything, is in the
          way — a converted lead has its Opportunity or Deal. */}
      <Button variant="outline" onClick={() => setDeleting(true)} disabled={ctx.isLoading || !ctx.values}>
        <Trash2Icon className="size-4" />
        Delete
      </Button>
      <DeleteLeadDialog
        open={deleting}
        leadId={ctx.id}
        onClose={() => setDeleting(false)}
        onDeleted={() => navigate('/leads', { replace: true })}
      />
      {ctx.readOnly ? (
        dealId ? (
          <Button variant="outline" onClick={() => navigate(`/deals/${dealId}`)}>
            <ArrowRightIcon className="size-4" />
            Go to Deal
          </Button>
        ) : (
          oppId && (
            <Button variant="outline" onClick={() => navigate(`/opportunities/${oppId}`)}>
              <ArrowRightIcon className="size-4" />
              Go to Opportunity
            </Button>
          )
        )
      ) : (
        <Button onClick={() => setAdvanceOpen(true)} disabled={ctx.isLoading || !ctx.values}>
          Update Stage
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
          skipped={ctx.skipped}
          onClose={() => setAdvanceOpen(false)}
          onAdvancedWithinLeads={(stage) => ctx.selectStage(stage)}
          onJumpToField={ctx.jumpToField}
        />
      )}
    </>
  )
}

function LeadBanner({ ctx }: { ctx: PipelineRecordContext }) {
  return (
    <>
      <ConvertedBanner ctx={ctx} />
      <PursuitBanner ctx={ctx} />
    </>
  )
}

function ConvertedBanner({ ctx }: { ctx: PipelineRecordContext }) {
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
              View the {target.module}
            </button>
          </>
        )}
      </span>
    </div>
  )
}

// No module-specific children any more: Quotes has its own named section in
// PipelineRelated and the deal registration is built, so the catch-all
// "Quotes and the deal registration" placeholder the tab used to end with said
// less than the sections above it now do.
function LeadRelated({ ctx }: { ctx: PipelineRecordContext }) {
  return <PipelineRelated ctx={ctx} />
}

export const leadsPipeline: PipelineModuleSpec = {
  module: MODULE,
  collection: 'leads',
  basePath: '/leads',
  noun: 'lead',
  stages: LEADS_STAGES,
  stageKeyOf,
  skipReasonField: 'stage_skip_reason',
  reversalReasonField: 'stage_reversal_reason',
  recordHeading: 'Lead Information',
  detailsHeading: 'Aging and system fields',
  showProbabilityBand: true,
  tabs: ['current', 'details', 'related', 'history'],
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
