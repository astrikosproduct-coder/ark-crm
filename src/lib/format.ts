import { differenceInCalendarDays, format, isValid, parseISO } from 'date-fns'

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

export function number(value: unknown): string {
  const n = typeof value === 'number' ? value : Number(value)
  if (!Number.isFinite(n)) return ''
  return n.toLocaleString('en-US', { maximumFractionDigits: 2 })
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
  const d = parseISO(raw)
  if (!isValid(d)) return null
  return Math.max(0, differenceInCalendarDays(new Date(), d))
}

/** dd MMM yyyy — CLAUDE.md Conventions. */
export function date(value: unknown): string {
  if (typeof value !== 'string' || !value) return ''
  const d = parseISO(value)
  return isValid(d) ? format(d, 'dd MMM yyyy') : value
}

export function dateTime(value: unknown): string {
  if (typeof value !== 'string' || !value) return ''
  const d = parseISO(value)
  return isValid(d) ? format(d, 'dd MMM yyyy HH:mm') : value
}
