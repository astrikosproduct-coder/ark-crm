import type { ReactNode } from 'react'
import { AlertTriangleIcon } from 'lucide-react'

import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import type { ListRow } from '@/components/list/ListCell'
import { StageChip } from '@/components/leads/StageChip'
import { date as fmtDate, daysSince } from '@/lib/format'
import { cn } from '@/lib/utils'
import type { FieldSpec } from '@/types/field'

export const STALE_AFTER_DAYS = 30

/**
 * Days since a row last changed, and whether that crosses the CLAUDE.md
 * staleness line. leads.days_since_last_update is Computed with no
 * computed_expr anywhere in the register — nothing to run through the formula
 * engine — so this reads created_date/modified_date directly instead. A
 * record neither field has ever been stamped on reads as unknown, not stale.
 */
export function daysSinceUpdate(row: ListRow): number | null {
  return daysSince(row.modified_date ?? row.created_date)
}

/**
 * The Leads list columns that read as something other than their raw value —
 * same pattern as contactListCell and registrationListCell. Shared by the List
 * tab and the Kanban cards.
 */
export function leadListCell(field: FieldSpec, row: ListRow): ReactNode | undefined {
  if (field.api_name === 'lead_id') {
    // autonumber field the store never actually stores under this key — see
    // withRecordId — a raw list row carries the record id as `id` instead.
    return <span className="font-medium">{String(row.id ?? '—')}</span>
  }

  if (field.api_name === 'opportunity_name') {
    return <span className="font-medium">{String(row.opportunity_name ?? '—')}</span>
  }

  if (field.api_name === 'project_stage') {
    return <StageChip value={row.project_stage} />
  }

  if (field.api_name === 'probability_pct') {
    const v = row.probability_pct
    if (v === null || v === undefined || v === '') return <span className="text-muted-foreground">—</span>
    return <span className="tabular-nums">{String(v)}%</span>
  }

  if (field.api_name === 'days_since_last_update') {
    const days = daysSinceUpdate(row)
    if (days === null) return <span className="text-muted-foreground">—</span>
    const stale = days > STALE_AFTER_DAYS
    const cell = (
      <span className={cn('tabular-nums flex items-center justify-end gap-1', stale && 'text-amber-700 dark:text-amber-400')}>
        {stale && <AlertTriangleIcon className="size-3.5" />}
        {days}d
      </span>
    )
    if (!stale) return cell
    return (
      <Tooltip>
        <TooltipTrigger asChild>{cell}</TooltipTrigger>
        <TooltipContent>
          No update since {fmtDate((row.modified_date ?? row.created_date) as string)} — over{' '}
          {STALE_AFTER_DAYS} days.
        </TooltipContent>
      </Tooltip>
    )
  }

  return undefined
}
