import type { ListRow } from '@/components/list/ListCell'
import { staleDaysOf } from '@/components/leads/leadListCell'
import { PipelineCard } from '@/components/pipeline/PipelineCard'
import type { FieldSpec } from '@/types/field'
import { PipelineKanbanBoard } from '@/components/pipeline/PipelineKanbanBoard'
import { RevenueAmount } from '@/components/pipeline/RevenueAmount'
import { date as fmtDate } from '@/lib/format'

function DealCard({ row }: { row: ListRow }) {
  return (
    <PipelineCard
      name={String(row.deal_name ?? row.id)}
      // End Client, then Partner: two partners on one project read as two cards.
      clients={[row.__labels?.end_client, row.__labels?.customer_partner_si]}
      // Actual Revenue — the contract value.
      value={<RevenueAmount row={row} />}
      // No probability on a Deal: Stage 7-9 are past forecasting odds. When it
      // goes live is what a delivery reader scans a Deal column for.
      aside={typeof row.go_live_date === 'string' && row.go_live_date ? fmtDate(row.go_live_date) : '—'}
      asideTitle="Go-Live Date"
      owner={row.__labels?.delivery_pm}
      // Deals stamp modified_by_date; daysSinceUpdate reads both spellings.
      staleDays={staleDaysOf(row)}
    />
  )
}

/**
 * Pipeline view for Deals (Stage 7-9), same shape as LeadKanbanBoard. Its one
 * terminal column is Closed Lost — see spec/extensions.json
 * kanban.terminal_statuses_by_module.
 */
export function DealKanbanBoard({
  filter,
  fields,
}: {
  filter?: Record<string, string | string[]>
  /** The page's filter fields — this person's board settings choose from them. */
  fields?: FieldSpec[]
}) {
  return (
    <PipelineKanbanBoard
      module="deals"
      collection="deals"
      basePath="/deals"
      stageValueOf={(row) => row.deal_stage}
      noun="deal"
      renderCard={(row) => <DealCard row={row} />}
      filter={filter}
      fields={fields}
      // What the card above shows, for Kanban View Settings to start from.
      defaultCardFields={['end_client', 'customer_partner_si', 'contract_value', 'go_live_date', 'delivery_pm']}
    />
  )
}
