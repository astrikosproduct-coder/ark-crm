import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'

import { Button } from '@/components/ui/button'
import { ArrowRightIcon } from 'lucide-react'
import { ConvertToDealDialog } from '@/components/opportunities/ConvertToDealDialog'
import { PipelineRecordPage } from '@/components/pipeline/PipelineRecordPage'
import { PipelineRelated } from '@/components/pipeline/PipelineRelated'
import { PursuitBanner } from '@/components/pursuits/PursuitBanner'
import { ErasePursuitButton } from '@/components/pursuits/ErasePursuit'
import type { PipelineModuleSpec, PipelineRecordContext } from '@/components/pipeline/types'
import { stageKeyOf, stagesFor } from '@/lib/pipeline'
import { api } from '@/lib/api'
import { localAmount, revenueOf } from '@/lib/revenue'
import type { Values } from '@/lib/spec/conditions'

const MODULE = 'opportunities'
const OPPORTUNITY_STAGES = stagesFor(MODULE)
/** Where Convert to Deal is offered — the end of this module's own range. */
const LAST_STAGE = OPPORTUNITY_STAGES[OPPORTUNITY_STAGES.length - 1]?.stage ?? 6

/** Same rule as Leads: converted (here, into a Deal) and history from then on. */
function isConverted(values: Values): boolean {
  return values.lead_status === 'CONVERTED'
}

function OpportunityHeader({ ctx }: { ctx: PipelineRecordContext }) {
  const revenue = ctx.values ? revenueOf(ctx.values) : null

  // Probability % is NOT shown here any more — see LeadHeader's own note.
  // Neither is any route back to the Lead ("From LEAD-00118", then the
  // lineage breadcrumb): both removed on instruction. The Lead is on the
  // Related tab, by name — see ParentRecordsPanel.
  return <>{revenue?.value != null && <span>{revenue.label}: {localAmount(revenue)}</span>}</>
}

function OpportunityActions({ ctx }: { ctx: PipelineRecordContext }) {
  const [convertOpen, setConvertOpen] = useState(false)
  const navigate = useNavigate()
  const { data: deals } = useQuery({
    queryKey: ['list', 'deals', 'parent_opportunity', ctx.id],
    queryFn: async () =>
      (await api.get<Values[]>('/deals', { params: { parent_opportunity: ctx.id } })).data,
    enabled: Boolean(ctx.id) && ctx.readOnly,
  })
  const dealId = deals?.[0]?.id
  const dealIdText = typeof dealId === 'string' ? dealId : undefined

  const eraseButton = (
    <ErasePursuitButton
      recordId={ctx.id}
      noun="opportunity"
      disabled={ctx.isLoading || !ctx.values}
      onErased={() => navigate('/opportunities', { replace: true })}
    />
  )

  if (ctx.readOnly) {
    return (
      <>
        {eraseButton}
        {dealIdText && (
          <Button variant="outline" onClick={() => navigate(`/deals/${dealIdText}`)}>
            <ArrowRightIcon className="size-4" />
            Go to Deal
          </Button>
        )}
      </>
    )
  }

  const updateStage = (
    <Button
      variant={ctx.currentStage === LAST_STAGE ? 'outline' : 'default'}
      onClick={ctx.openAdvance}
      disabled={ctx.isLoading || !ctx.values}
    >
      Update Stage
    </Button>
  )

  if (ctx.currentStage !== LAST_STAGE) {
    return (
      <>
        {eraseButton}
        {updateStage}
      </>
    )
  }

  // Convert does NOT replace Update Stage at the last stage. It did, and an
  // Opportunity at Commercial Evaluation then had no way back to an earlier
  // stage — stages are states, not steps, and a reversal is always legal.
  return (
    <>
      {eraseButton}
      {updateStage}
      <Button
        onClick={() => setConvertOpen(true)}
        disabled={ctx.isLoading || !ctx.values}
      >
        <ArrowRightIcon className="size-4" />
        Convert
      </Button>
      {ctx.values && (
        <ConvertToDealDialog
          open={convertOpen}
          opportunityId={ctx.id}
          values={ctx.values}
          onClose={() => setConvertOpen(false)}
        />
      )}
    </>
  )
}

/**
 * Opportunities had NO Related tab at all until now — its `tabs` listed only
 * current, details and history. It carries Stages 4 to 7, the RFP-to-Close
 * stretch where who-is-who at the client and at the partner matters most, so
 * being the one pipeline module with nowhere to see them was an omission
 * rather than a decision.
 */
function OpportunityRelated({ ctx }: { ctx: PipelineRecordContext }) {
  return <PipelineRelated ctx={ctx} />
}

export const opportunitiesPipeline: PipelineModuleSpec = {
  module: MODULE,
  collection: 'opportunities',
  basePath: '/opportunities',
  noun: 'opportunity',
  stages: stagesFor(MODULE),
  stageKeyOf,
  skipReasonField: 'stage_skip_reason',
  reversalReasonField: 'stage_reversal_reason',
  recordHeading: 'Opportunity Information',
  detailsHeading: 'Record state, reasons and system fields',
  showProbabilityBand: true,
  tabs: ['current', 'details', 'related', 'history'],
  isReadOnly: isConverted,
  Header: OpportunityHeader,
  Actions: OpportunityActions,
  Related: OpportunityRelated,
  Banner: PursuitBanner,
}

export function OpportunityDetailPage() {
  return <PipelineRecordPage spec={opportunitiesPipeline} />
}
