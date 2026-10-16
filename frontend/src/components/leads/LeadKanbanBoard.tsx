import type { ListRow } from '@/components/list/ListCell'
import { staleDaysOf } from '@/components/leads/leadListCell'
import { PipelineCard } from '@/components/pipeline/PipelineCard'
import type { FieldSpec } from '@/types/field'
import { PipelineKanbanBoard } from '@/components/pipeline/PipelineKanbanBoard'
import { RevenueAmount } from '@/components/pipeline/RevenueAmount'
import { percent } from '@/lib/format'

function LeadCard({ row }: { row: ListRow }) {
  return (
    <PipelineCard
      name={String(row.opportunity_name ?? row.id)}
      // End Client, then Partner: two partners on one project read as two cards.
      clients={[row.__labels?.end_client, row.__labels?.customer_partner_si]}
      // Estimated Value, and only Estimated Value — a Lead's one revenue field.
      value={<RevenueAmount row={row} />}
      // A fraction (0.70 is 70%); percent() turns it into "70%", never "0.7%".
      aside={typeof row.probability_pct === 'number' ? percent(row.probability_pct) : '—'}
      asideTitle="Probability"
      owner={row.__labels?.bd_owner}
      staleDays={staleDaysOf(row)}
    />
  )
}

/**
 * Pipeline view: every lead grouped by stage, each column headed by the
 * stage's Probability % from spec/stages.json. Filtered by the same bar as the
 * List tab — see ListFilterBar.
 */
export function LeadKanbanBoard({
  filter,
  fields,
}: {
  filter?: Record<string, string | string[]>
  /** The page's filter fields — this person's board settings choose from them. */
  fields?: FieldSpec[]
}) {
  return (
    <PipelineKanbanBoard
      module="leads"
      collection="leads"
      basePath="/leads"
      stageValueOf={(row) => row.project_stage}
      noun="lead"
      renderCard={(row) => <LeadCard row={row} />}
      filter={filter}
      fields={fields}
      // What the card above shows, for Kanban View Settings to start from.
      defaultCardFields={['end_client', 'customer_partner_si', 'estimated_value', 'probability_pct', 'bd_owner']}
    />
  )
}
