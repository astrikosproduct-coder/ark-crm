import type { ReactNode } from 'react'
import { AlertTriangleIcon } from 'lucide-react'
import { format, isValid, parseISO } from 'date-fns'

import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import type { ListRow } from '@/components/list/ListCell'
import { StageChip } from '@/components/leads/StageChip'
import { RevenueAmount } from '@/components/pipeline/RevenueAmount'
import { date as fmtDate, percent } from '@/lib/format'
import type { Values } from '@/lib/spec/conditions'
import { resolverFor } from '@/lib/spec/resolvers'
import { cn } from '@/lib/utils'
import type { FieldSpec } from '@/types/field'

export const STALE_AFTER_DAYS = 30

/**
 * Days since a row last changed, and whether that crosses the CLAUDE.md
 * staleness line.
 *
 * Through the SAME resolver the Details tab's Days Since Last Update runs,
 * rather than reading modified_date a second way here. It read it directly
 * until 12 Sep 2026, because the register typed the field Computed and gave it
 * no formula — so the List tab showed "14d" while the Details tab showed "No
 * formula in the field register for this field.", two answers to one question
 * with nothing to say which was right. The field has a computed_by now; one
 * function answers both.
 *
 * A record neither date has ever been stamped on reads as unknown, not stale.
 */
export function daysSinceUpdate(row: ListRow): number | null {
  const days = resolverFor('days_since_update')?.('leads', row as Values)
  return typeof days === 'number' ? days : null
}

/** Days since the last update, but only once it is past the staleness line — for a card's warning. */
export function staleDaysOf(row: ListRow): number | null {
  const days = daysSinceUpdate(row)
  return days !== null && days > STALE_AFTER_DAYS ? days : null
}

/**
 * The Leads list columns that read as something other than their raw value —
 * same pattern as contactListCell and registrationListCell. Shared by the List
 * tab and the Kanban cards.
 */
export function MonthCell({ value }: { value: unknown }) {
  if (typeof value !== 'string' || !value) return <span className="text-muted-foreground">—</span>
  const parsed = parseISO(value)
  return <span className="whitespace-nowrap">{isValid(parsed) ? format(parsed, 'MMM yyyy') : value}</span>
}

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

  // The module's one revenue field, in the currency it was entered in — the
  // same amount the Kanban card reads. A bare number with no currency was
  // ambiguous.
  if (field.api_name === 'estimated_value') {
    return <RevenueAmount row={row} />
  }

  // A month, stored as its first day: "Oct 2026", not "01 Oct 2026".
  if (field.api_name === 'expected_close_month') {
    return <MonthCell value={row.expected_close_month} />
  }

  // progression_pct/probability_pct are fractions on the wire (0.70 is 70%)
  // — percent() is what turns either that
  // or an old whole-number value into "70%", never "0.7%". See lib/format.ts.
  if (field.api_name === 'probability_pct' || field.api_name === 'progression_pct') {
    const v = row[field.api_name]
    if (v === null || v === undefined || v === '') return <span className="text-muted-foreground">—</span>
    return <span className="tabular-nums">{percent(v)}</span>
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
