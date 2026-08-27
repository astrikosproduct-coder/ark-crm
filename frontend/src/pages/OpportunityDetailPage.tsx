import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'

import { Button } from '@/components/ui/button'
import { ArrowRightIcon } from 'lucide-react'
import { ConvertToDealDialog } from '@/components/opportunities/ConvertToDealDialog'
import { PipelineRecordPage } from '@/components/pipeline/PipelineRecordPage'
import type { PipelineModuleSpec, PipelineRecordContext } from '@/components/pipeline/types'
import { CURRENT_USER_ID, stageKeyOf, stagesFor } from '@/lib/pipeline'
import { api } from '@/lib/api'
import { money } from '@/lib/format'
import type { Values } from '@/lib/spec/conditions'

const MODULE = 'opportunities'

/** Same rule as Leads: converted (here, into a Deal) and history from then on. */
function isConverted(values: Values): boolean {
  return values.lead_status === 'CONVERTED'
}

function OpportunityHeader({ ctx }: { ctx: PipelineRecordContext }) {
  const navigate = useNavigate()
  const tcv = ctx.values?.total_value_tcv
  const probability = ctx.values?.probability_pct
  const parentLead = ctx.values?.parent_lead

  return (
    <>
      {typeof tcv === 'number' && <span>TCV: ${money(tcv)}</span>}
      {typeof probability === 'number' && <span>Probability: {probability}%</span>}
      {typeof parentLead === 'string' && parentLead && (
        <button
          type="button"
          className="text-primary underline underline-offset-2"
          onClick={() => navigate(`/leads/${parentLead}`)}
        >
          From {parentLead}
        </button>
      )}
    </>
  )
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

  if (ctx.readOnly) {
    return dealIdText ? (
      <Button variant="outline" onClick={() => navigate(`/deals/${dealIdText}`)}>
        <ArrowRightIcon className="size-4" />
        Go to {dealIdText}
      </Button>
    ) : null
  }

  if (ctx.currentStage !== 6) {
    return (
      <Button onClick={ctx.openAdvance} disabled={ctx.isLoading || !ctx.values}>
        <ArrowRightIcon className="size-4" />
        Advance to Stage {ctx.currentStage + 1}
      </Button>
    )
  }

  return (
    <>
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

export const opportunitiesPipeline: PipelineModuleSpec = {
  module: MODULE,
  collection: 'opportunities',
  basePath: '/opportunities',
  noun: 'opportunity',
  stages: stagesFor(MODULE),
  stageKeyOf,
  writesProbability: true,
  skipReasonField: 'stage_skip_reason',
  reversalReasonField: 'stage_reversal_reason',
  stamp: () => ({ modified_date: new Date().toISOString(), modified_by: CURRENT_USER_ID }),
  detailsHeading: 'Cross-cutting, system and parent-linked fields',
  showProbabilityBand: true,
  tabs: ['current', 'details', 'history'],
  isReadOnly: isConverted,
  Header: OpportunityHeader,
  Actions: OpportunityActions,
}

export function OpportunityDetailPage() {
  return <PipelineRecordPage spec={opportunitiesPipeline} />
}
