import { isValid, parseISO } from 'date-fns'

import { companyDate, companyDateTime, dateOnly, daysSinceCompany } from './time'

/**
 * A value that is a calendar DAY, not an instant — 'YYYY-MM-DD' with no time
 * and no zone, which is what every `Date` column in the backend produces
 * (expected_close_month, contract_signed_date, demo_date and 70 others).
 *
 * These must never be timezone-converted: a contract signed on 30 Sep was
 * signed on 30 Sep everywhere, and shifting it would show 29 Sep to anyone far
 * enough west of the company clock. See lib/time.ts.
 */
const DATE_ONLY = /^\d{4}-\d{2}-\d{2}$/

export function humanize(key: string): string {
  return key
    .split(/[_-]/)
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(' ')
}

/** Thousands separators, no decimals — CLAUDE.md Conventions. */
export function money(value: unknown): string {
  const n = typeof value === 'number' ? value : Number(value)
  if (!Number.isFinite(n)) return ''
  return n.toLocaleString('en-US', { maximumFractionDigits: 0 })
}

/**
 * The sign a currency is written with — "$" for USD, "₹" for INR — or its code
 * where it has no sign of its own ("AED"). Asked of the browser, which knows
 * every currency; none is listed here. Empty when there is no currency.
 */
export function currencySign(code: unknown): string {
  if (typeof code !== 'string' || !code) return ''
  try {
    const parts = new Intl.NumberFormat('en-US', { style: 'currency', currency: code, currencyDisplay: 'narrowSymbol' }).formatToParts(0)
    return parts.find((p) => p.type === 'currency')?.value ?? code
  } catch {
    // Not a currency the browser knows (a code typed into Setup): show it as it is.
    return code
  }
}

/**
 * A plain number, as it is held. Up to six decimals, because that is what an
 * FX rate carries (3.6725): two would show a different rate from the one the
 * prices were worked out with.
 */
export function number(value: unknown): string {
  const n = typeof value === 'number' ? value : Number(value)
  if (!Number.isFinite(n)) return ''
  return n.toLocaleString('en-US', { maximumFractionDigits: 6 })
}

/**
 * The register never states whether a percent is 0-1 or 0-100 — see
 * spec/extensions.json conventions.percent_unit. Values at or below 1 are
 * shown as fractions because that is what seed/regions.json stores; anything
 * larger is shown as typed.
 */
export function percent(value: unknown): string {
  const n = typeof value === 'number' ? value : Number(value)
  if (!Number.isFinite(n)) return ''
  const shown = Math.abs(n) <= 1 ? n * 100 : n
  return `${shown.toLocaleString('en-US', { maximumFractionDigits: 1 })}%`
}

/**
 * Days between `raw` and now, floored at 0. Shared by every module's
 * staleness badge — each module stamps its own SYSTEM section under a
 * different pair of api_names (leads: modified_date/created_date, deals:
 * modified_by_date/created_by_date), so callers pass whichever raw string
 * their own record actually carries rather than this guessing a name.
 */
export function daysSince(raw: unknown): number | null {
  if (typeof raw !== 'string' || !raw) return null
  return daysSinceCompany(raw)
}

/**
 * dd MMM yyyy — CLAUDE.md Conventions.
 *
 * An instant is rendered on the company clock; a date-only value is rendered
 * exactly as stored. Both arrive here as strings and only their SHAPE tells
 * them apart, which is why DATE_ONLY exists: converting a calendar fact would
 * move a close date a day for anyone west of IST.
 */
export function date(value: unknown): string {
  if (typeof value !== 'string' || !value) return ''
  if (!isValid(parseISO(value))) return value
  return DATE_ONLY.test(value) ? dateOnly(value) : companyDate(value)
}

/** dd MMM yyyy HH:mm on the company clock. Only ever used on instants. */
export function dateTime(value: unknown): string {
  if (typeof value !== 'string' || !value) return ''
  return isValid(parseISO(value)) ? companyDateTime(value) : value
}
