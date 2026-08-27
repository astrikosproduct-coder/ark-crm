import { AlertTriangleIcon } from 'lucide-react'

import type { ListRow } from '@/components/list/ListCell'
import { PipelineKanbanBoard } from '@/components/pipeline/PipelineKanbanBoard'
import { STALE_AFTER_DAYS } from '@/components/leads/leadListCell'
import { daysSince, money } from '@/lib/format'
import { cn } from '@/lib/utils'

function DealCard({ row }: { row: ListRow }) {
  // Deals stamp created_by_date/modified_by_date, not created_date/modified_date
  // — see the SYSTEM section split in fields.json — so this cannot reuse
  // leadListCell's daysSinceUpdate, only the shared daysSince(raw) it wraps.
  const days = daysSince(row.modified_by_date ?? row.created_by_date)
  const stale = days !== null && days > STALE_AFTER_DAYS
  const value = row.contract_value

  return (
    <>
      <p className="truncate font-medium">{String(row.deal_name ?? row.id)}</p>
      <p className="truncate text-xs text-muted-foreground">{String(row.__labels?.end_client ?? '—')}</p>
      <div className="mt-1.5 flex items-center justify-between text-xs">
        <span className="tabular-nums">{typeof value === 'number' ? `$${money(value)}` : '—'}</span>
        <span className="truncate text-muted-foreground">{String(row.__labels?.delivery_pm ?? '—')}</span>
      </div>
      {stale && (
        <div className="mt-1 flex items-center justify-end text-xs text-muted-foreground">
          <span className={cn('flex items-center gap-1 text-amber-700 dark:text-amber-400')}>
            <AlertTriangleIcon className="size-3" />
            {days}d
          </span>
        </div>
      )}
    </>
  )
}

/**
 * Pipeline view for Deals (Stage 7-9), same shape as LeadKanbanBoard. No
 * probability_pct on a Deal — Stage 7-9 are past the point of forecasting
 * odds, per CLAUDE.md's probability table (90-100%, 100%, and Expansion has
 * none at all) — so the card shows the delivery PM in its place.
 */
export function DealKanbanBoard() {
  return (
    <PipelineKanbanBoard
      module="deals"
      collection="deals"
      basePath="/deals"
      stageValueOf={(row) => row.deal_stage}
      noun="deal"
      renderCard={(row) => <DealCard row={row} />}
    />
  )
}
