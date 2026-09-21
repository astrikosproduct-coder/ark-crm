import type { ListRow } from '@/components/list/ListCell'
import { money } from '@/lib/format'

/**
 * What a pipeline row contributes to its stage's total — decided by the server,
 * never here. See backend/app/revenue.py for the rule, frozen 13 Sep 2026:
 *
 *   Leads          Estimated Value      estimated_value
 *   Opportunities  Opportunity Revenue  total_value_tcv
 *   Deals          Actual Revenue       contract_value
 *
 * One field per module, no fallbacks. Only Open / On Hold primary pursuits
 * count, in USD at the pursuit's own FX rate (local units per 1 USD).
 *
 * This file only reads the answer every list row already carries as
 * `row.revenue` and adds it up, so the card, the column header and the API
 * cannot disagree about what counts.
 */
export interface Revenue {
  field: string
  label: string
  value: number | null
  currency: string | null
  fx_rate: number | null
  usd: number | null
  counted: boolean
  excluded: 'closed_lost' | 'converted' | 'secondary' | 'no_primary' | null
  flag: 'no_value' | 'no_currency' | 'no_fx_rate' | null
}

export function revenueOf(row: ListRow): Revenue | null {
  const r = row.revenue
  return r && typeof r === 'object' ? (r as Revenue) : null
}

/** "AED 367,250" — a record's value in the currency it was entered in. */
export function localAmount(revenue: Revenue | null): string {
  if (!revenue || revenue.value === null) return '—'
  return `${revenue.currency ?? ''} ${money(revenue.value)}`.trim()
}

export function usd(value: number): string {
  return `$${money(value)}`
}

export interface StageTotal {
  /** Sum of counted rows' USD. */
  usd: number
  label: string | null
  counted: number
  secondary: { count: number; usd: number }
  /** Counted, but adding nothing until someone fixes the record. */
  noValue: number
  noCurrency: number
  noFxRate: number
}

export function stageTotal(rows: ListRow[]): StageTotal {
  const total: StageTotal = {
    usd: 0,
    label: null,
    counted: 0,
    secondary: { count: 0, usd: 0 },
    noValue: 0,
    noCurrency: 0,
    noFxRate: 0,
  }
  for (const row of rows) {
    const r = revenueOf(row)
    if (!r) continue
    total.label ??= r.label
    if (r.excluded === 'secondary' || r.excluded === 'no_primary') {
      total.secondary.count += 1
      total.secondary.usd += r.usd ?? 0
      continue
    }
    if (!r.counted) continue
    total.counted += 1
    if (r.flag === 'no_value') total.noValue += 1
    else if (r.flag === 'no_currency') total.noCurrency += 1
    else if (r.flag === 'no_fx_rate') total.noFxRate += 1
    total.usd += r.usd ?? 0
  }
  return total
}

/**
 * The hover text under a column total: what it covers, in the reader's terms.
 *
 * Reworded 18 Sep 2026. It used to tally our own bookkeeping — "3 without a
 * value — counted as $0", "2 without an FX rate — not converted" — which is a
 * data-quality report, and a hover on a sales board is not where one belongs.
 * The rules it describes are unchanged; a record still needs a value, a
 * currency and a rate to add anything. What went is the running count of how
 * many did not.
 */
export function stageTotalExplained(total: StageTotal): string {
  const lines = [`Sum of ${total.label ?? 'revenue'} in USD, across open and on-hold work.`]
  if (total.secondary.count) {
    lines.push('Where partners share a project, it is counted once, on the lead pursuit.')
  }
  if (total.noValue || total.noCurrency || total.noFxRate) {
    lines.push('A record still missing its value, currency or exchange rate adds nothing yet.')
  }
  return lines.join('\n')
}
