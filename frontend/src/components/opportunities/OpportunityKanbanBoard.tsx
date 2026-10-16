import type { ListRow } from '@/components/list/ListCell'
import { staleDaysOf } from '@/components/leads/leadListCell'
import { PriorityFlagMark } from '@/components/opportunities/PriorityFlagMark'
import { PipelineCard } from '@/components/pipeline/PipelineCard'
import type { FieldSpec } from '@/types/field'
import { PipelineKanbanBoard } from '@/components/pipeline/PipelineKanbanBoard'
import { RevenueAmount } from '@/components/pipeline/RevenueAmount'
import { percent } from '@/lib/format'

function OpportunityCard({ row }: { row: ListRow }) {
  return (
    <PipelineCard
      // Read-through identity, resolved onto the list row by the server —
      // backend/app/read_through_rows.py.
      name={String(row.opportunity_name ?? row.id)}
      // End Client, then Partner: two partners on one project read as two cards.
      clients={[row.__labels?.end_client, row.__labels?.customer_partner_si]}
      mark={<PriorityFlagMark row={row} variant="compact" />}
      // Opportunity Revenue (TCV), served on the list row.
      value={<RevenueAmount row={row} />}
      aside={typeof row.probability_pct === 'number' ? percent(row.probability_pct) : '—'}
      asideTitle="Probability"
      owner={row.__labels?.sales_owner}
      staleDays={staleDaysOf(row)}
    />
  )
}

/** Pipeline view for Opportunities (Stage 4-6), same shape as LeadKanbanBoard. */
export function OpportunityKanbanBoard({
  filter,
  fields,
}: {
  filter?: Record<string, string | string[]>
  /** The page's filter fields — this person's board settings choose from them. */
  fields?: FieldSpec[]
}) {
  return (
    <PipelineKanbanBoard
      module="opportunities"
      collection="opportunities"
      basePath="/opportunities"
      stageValueOf={(row) => row.project_stage}
      noun="opportunity"
      nounPlural="opportunities"
      renderCard={(row) => <OpportunityCard row={row} />}
      filter={filter}
      fields={fields}
      // What the card above shows, for Kanban View Settings to start from.
      defaultCardFields={['end_client', 'customer_partner_si', 'total_value_tcv', 'probability_pct', 'sales_owner']}
    />
  )
}
