import type { ListRow } from '@/components/list/ListCell'
import { staleDaysOf } from '@/components/leads/leadListCell'
import { PipelineCard } from '@/components/pipeline/PipelineCard'
import { PipelineKanbanBoard } from '@/components/pipeline/PipelineKanbanBoard'
import { RevenueAmount } from '@/components/pipeline/RevenueAmount'
import { percent } from '@/lib/format'

function LeadCard({ row }: { row: ListRow }) {
  return (
    <PipelineCard
      name={String(row.opportunity_name ?? row.id)}
      client={row.__labels?.end_client}
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
export function LeadKanbanBoard({ filter }: { filter?: Record<string, string | string[]> }) {
  return (
    <PipelineKanbanBoard
      module="leads"
      collection="leads"
      basePath="/leads"
      stageValueOf={(row) => row.project_stage}
      noun="lead"
      renderCard={(row) => <LeadCard row={row} />}
      filter={filter}
    />
  )
}
