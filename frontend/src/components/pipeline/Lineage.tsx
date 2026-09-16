import { Fragment } from 'react'
import { Link } from 'react-router-dom'

import { useLineage } from '@/components/pipeline/ParentRecordsPanel'
import type { PipelineRecordContext } from '@/components/pipeline/types'

/**
 * Where this pursuit came from, on the line under the record's name:
 *
 *     LEAD-00017 → OPP-00003 → DEAL-00002
 *
 * Every ancestor is a link; the record itself is not. A Deal made straight
 * from a Lead (a paid POC / pilot) shows LEAD → DEAL, because there is no
 * Opportunity. A Lead is the start of the chain and shows nothing — its own
 * "Go to" button already points forward once it has converted.
 *
 * Replaces the "From LEAD-00118" header link that was removed, which had left
 * an Opportunity with no route back to its Lead except a Stage 4 field.
 */
export function Lineage({ ctx }: { ctx: PipelineRecordContext }) {
  const { module, opportunityId, leadId } = useLineage(ctx)
  if (module === 'leads' || !ctx.id || (!leadId && !opportunityId)) return null

  const ancestors = [
    leadId && { id: leadId, path: `/leads/${leadId}` },
    opportunityId && { id: opportunityId, path: `/opportunities/${opportunityId}` },
  ].filter((step): step is { id: string; path: string } => Boolean(step))

  return (
    <span className="flex items-center gap-1" aria-label="Pursuit lineage">
      {ancestors.map((step) => (
        <Fragment key={step.id}>
          <Link className="hover:text-foreground underline underline-offset-2" to={step.path}>
            {step.id}
          </Link>
          <span aria-hidden>→</span>
        </Fragment>
      ))}
      <span className="text-foreground">{ctx.id}</span>
    </span>
  )
}
