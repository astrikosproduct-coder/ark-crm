import { format, isValid, parseISO } from 'date-fns'

/**
 * The company clock.
 *
 * TWO KINDS OF TIME, AND THEY ARE NOT THE SAME
 * --------------------------------------------
 * An INSTANT is a moment that happened — a save, a stage move, a sign-in. It
 * arrives as a UTC timestamp and is the same instant for everyone; Dubai,
 * Houston and Bengaluru merely print it differently.
 *
 * A CALENDAR FACT is a day — a contract signed date, an expected close month.
 * It arrives as 'YYYY-MM-DD', carries no zone, and must NEVER be converted: a
 * contract signed on 30 Sep was signed on 30 Sep in every country on earth.
 * Running one through a timezone conversion is how it becomes 29 Sep for half
 * the company, and it is the single most common date bug there is.
 *
 * `dateOnly` below handles the second kind and deliberately does no conversion
 * at all. Everything else here handles the first.
 *
 * WHY ONE FIXED ZONE RATHER THAN THE VIEWER'S OWN
 * -----------------------------------------------
 * ARK CRM is an in-house CRM for a company with one HQ, not a multi-tenant
 * product — there is no tenant to personalise for. A manager in Bengaluru and
 * the BD in Dubai reading the same record must see the same string, or the
 * audit trail they are discussing is two different documents. A list of forty
 * rows should read as one sequence, not forty translations. And aging —
 * "12 days in stage" — must not depend on who is looking, which it did before
 * this existed: the server counted in UTC and the browser counted in local
 * time, so the same record could read 11 on one screen and 12 on another.
 *
 * Nothing is stored in company time. Storage stays UTC, so moving to per-user
 * zones later is a change to this file and nothing else.
 *
 * WHAT THIS DOES NOT CHANGE: ELAPSED TIME
 * ---------------------------------------
 * A 48-hour SLA is a duration between two stored instants, and a duration is
 * timezone-independent by construction — rendering it in IST cannot make it
 * longer or shorter for a BD in Houston. A deal registered at 16:00 in Houston
 * is due 48 hours later, which that BD reads as 16:00 two days on and a manager
 * here reads as 02:30 the morning after that; same instant, same 48 hours.
 * Only CALENDAR-worded rules ("by end of day", "within 2 business days") depend
 * on the zone, and those are a policy decision rather than a formatting one.
 *
 * Never derive an SLA from a formatted date. Subtract the instants.
 *
 * Mirrored by app/clock.py on the server — change both together.
 */
export const COMPANY_TZ = 'Asia/Kolkata'

export const COMPANY_TZ_LABEL = 'IST'

function parsed(value: unknown): Date | null {
  if (value instanceof Date) return isValid(value) ? value : null
  if (typeof value !== 'string' || !value) return null
  const d = parseISO(value)
  return isValid(d) ? d : null
}

/**
 * Intl rather than a date-fns timezone add-on: `timeZone` is built into every
 * browser, knows the IANA database including DST, and costs no dependency.
 * Formatters are expensive to construct and are reused.
 */
/**
 * en-US, NOT en-GB, purely for the month abbreviation: en-GB renders September
 * as "Sept", four letters, where CLAUDE.md's convention is `dd MMM yyyy` and
 * every other date in the app (date-fns 'MMM') says "Sep". The parts are
 * recomposed below into day-month-year order, so the US locale never reaches
 * the screen — only its three-letter month does.
 */
const DAY = new Intl.DateTimeFormat('en-US', {
  timeZone: COMPANY_TZ,
  day: '2-digit',
  month: 'short',
  year: 'numeric',
})

/**
 * 12-hour with AM/PM — "08:42 PM", not "20:42".
 *
 * `hour: '2-digit'` with hour12 keeps the leading zero, so a column of times
 * stays aligned down the History rail instead of stepping in and out by a
 * character between 9 AM and 10 AM.
 */
const TIME = new Intl.DateTimeFormat('en-US', {
  timeZone: COMPANY_TZ,
  hour: '2-digit',
  minute: '2-digit',
  hour12: true,
})

/** 'en-CA' is ISO-shaped — 2026-09-12 — which is what makes it a sortable key. */
const DAY_KEY = new Intl.DateTimeFormat('en-CA', {
  timeZone: COMPANY_TZ,
  year: 'numeric',
  month: '2-digit',
  day: '2-digit',
})

/** dd MMM yyyy on the company calendar — CLAUDE.md Conventions. */
export function companyDate(value: unknown): string {
  const d = parsed(value)
  if (!d) return ''
  // Recomposed from parts rather than string-patched: en-US formats as
  // "Sep 12, 2026" and the convention is "12 Sep 2026".
  const parts = Object.fromEntries(DAY.formatToParts(d).map((p) => [p.type, p.value]))
  return `${parts.day} ${parts.month} ${parts.year}`
}

/** dd MMM yyyy HH:mm, company clock. The zone is NOT appended — see COMPANY_TZ_LABEL. */
export function companyDateTime(value: unknown): string {
  const d = parsed(value)
  return d ? `${companyDate(d)} ${TIME.format(d)}` : ''
}

/** HH:mm alone, for a timeline already grouped under a date heading. */
export function companyTime(value: unknown): string {
  const d = parsed(value)
  return d ? TIME.format(d) : ''
}

/**
 * The company-calendar day an instant fell on, as 'yyyy-MM-dd'.
 *
 * A grouping KEY, not a display string: the History timeline groups its events
 * into day headings with it, and two events an hour apart either side of
 * midnight IST belong under different headings for everyone, not just for
 * viewers who happen to be in IST.
 */
export function companyDayKey(value: unknown): string {
  const d = parsed(value)
  return d ? DAY_KEY.format(d) : ''
}

/**
 * A date-only value, printed exactly as stored.
 *
 * NO TIMEZONE CONVERSION HAPPENS HERE, deliberately. 'YYYY-MM-DD' from a `Date`
 * column is a calendar fact; parseISO reads it as local midnight and formatting
 * it locally returns the same day everywhere, which is the correct answer.
 * Routing it through formatInTimeZone would shift it a day for anyone far
 * enough west, which is the bug this function exists to not have.
 */
export function dateOnly(value: unknown): string {
  const d = parsed(value)
  return d ? format(d, 'dd MMM yyyy') : typeof value === 'string' ? value : ''
}

/**
 * Whole company-calendar days between an instant and now, floored at 0.
 *
 * Counted on the company calendar so it agrees with the server's own
 * days_in_current_stage / days_since_last_update, which count the same way.
 */
export function daysSinceCompany(value: unknown): number | null {
  const d = parsed(value)
  if (!d) return null
  // Both reduced to a company-calendar day first, then subtracted as plain
  // dates. Counting elapsed hours and dividing would answer a different
  // question — "12 days in stage" counts date boundaries crossed, not 288
  // hours — and would disagree with the server, which counts boundaries too.
  const a = Date.parse(`${companyDayKey(new Date())}T00:00:00Z`)
  const b = Date.parse(`${companyDayKey(d)}T00:00:00Z`)
  return Math.max(0, Math.round((a - b) / 86_400_000))
}
