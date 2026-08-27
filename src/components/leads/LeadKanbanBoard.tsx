import { AlertTriangleIcon } from 'lucide-react'

import type { ListRow } from '@/components/list/ListCell'
import { daysSinceUpdate, STALE_AFTER_DAYS } from '@/components/leads/leadListCell'
import { PipelineKanbanBoard } from '@/components/pipeline/PipelineKanbanBoard'
import { money } from '@/lib/format'
import { cn } from '@/lib/utils'

function LeadCard({ row }: { row: ListRow }) {
  const days = daysSinceUpdate(row)
  const stale = days !== null && days > STALE_AFTER_DAYS
  const value = row.total_value_tcv ?? row.estimated_value

  return (
    <>
      <p className="truncate font-medium">{String(row.opportunity_name ?? row.id)}</p>
      <p className="truncate text-xs text-muted-foreground">{String(row.__labels?.end_client ?? '—')}</p>
      <div className="mt-1.5 flex items-center justify-between text-xs">
        <span className="tabular-nums">{typeof value === 'number' ? `$${money(value)}` : '—'}</span>
        <span className="tabular-nums text-muted-foreground">
          {typeof row.probability_pct === 'number' ? `${row.probability_pct}%` : '—'}
        </span>
      </div>
      <div className="mt-1 flex items-center justify-between text-xs text-muted-foreground">
        <span className="truncate">{String(row.__labels?.bd_owner ?? '—')}</span>
        {stale && (
          <span className={cn('flex items-center gap-1 text-amber-700 dark:text-amber-400')}>
            <AlertTriangleIcon className="size-3" />
            {days}d
          </span>
        )}
      </div>
    </>
  )
}

/**
 * Pipeline view: every open lead grouped by stage, each column headed by the
 * stage's probability band from spec/stages.json — CLAUDE.md's "Kanban /
 * Pipeline view by stage with Probability wrt stages".
 */
export function LeadKanbanBoard() {
  return (
    <PipelineKanbanBoard
      module="leads"
      collection="leads"
      basePath="/leads"
      stageValueOf={(row) => row.project_stage}
      noun="lead"
      renderCard={(row) => <LeadCard row={row} />}
    />
  )
}
