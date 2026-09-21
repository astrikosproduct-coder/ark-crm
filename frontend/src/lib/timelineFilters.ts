import { useCallback, useMemo } from 'react'
import { useSearchParams } from 'react-router-dom'

import { companyDayKey } from '@/lib/time'
import type { TimelineEvent, TimelineKind } from '@/lib/timeline'

/**
 * The History tab's filter state, held in the URL.
 *
 * WHY THE URL AND NOT useState
 * ----------------------------
 * The question this tab answers is almost always asked by one person and
 * settled by another — "when did the close month move, and who moved it". A
 * filtered history that cannot be sent is a screenshot, and a screenshot is
 * where an audit trail stops being checkable. Same reasoning as the list
 * filters (lib/listFilters.ts), same place, same `replace: true` so Back
 * leaves the record rather than stepping through every dropdown.
 *
 * WHY THE FILTERING IS CLIENT-SIDE
 * --------------------------------
 * The timeline merges three sources — /audit-log, /transitions and
 * /conversions — and only the first takes query parameters. Pushing `when` to
 * the server would filter one source and not the other two, so "Last 7 days"
 * would mean something different for a field edit than for a stage move, and
 * the merge would quietly disagree with itself. Everything is filtered here, on
 * the merged list, where one rule applies to all three.
 *
 * That leaves one real limit, and it is NOT papered over: /audit-log caps a
 * record's rows (DEFAULT_LIMIT 500, MAX_LIMIT 2000 in
 * backend/app/routers/audit_log.py). The tab asks for the maximum and the
 * footer says so when the cap is actually hit, because a time filter over a
 * truncated set would otherwise answer confidently about a period it never
 * received.
 *
 * DAYS, NOT INSTANTS
 * ------------------
 * Every comparison is on `companyDayKey` — a 'yyyy-MM-dd' string on the company
 * calendar. "Today" therefore means today in IST for everyone looking, which is
 * the same thing the day headings below already group by. Comparing instants
 * against a browser-local midnight would give a manager in Bengaluru and a BD
 * in Dubai two different "Today"s over the same record.
 */

export type WhenKey = 'any' | 'today' | 'yesterday' | 'last7' | 'last30' | 'range' | 'on'

export const WHEN_OPTIONS: { key: WhenKey; label: string }[] = [
  { key: 'any', label: 'Any time' },
  { key: 'today', label: 'Today' },
  { key: 'yesterday', label: 'Yesterday' },
  { key: 'last7', label: 'Last 7 days' },
  { key: 'last30', label: 'Last 30 days' },
  { key: 'range', label: 'Custom range' },
  { key: 'on', label: 'Specific date' },
]

/** How many date boxes a choice needs: none, one, or a from/to pair. */
export function datesNeeded(when: WhenKey): 0 | 1 | 2 {
  if (when === 'range') return 2
  return when === 'on' ? 1 : 0
}

/** The `Show` choices. `all` is not a kind — it is the absence of a filter. */
export const SHOW_OPTIONS: { key: string; label: string; kinds?: TimelineKind[] }[] = [
  { key: 'all', label: 'All activity' },
  { key: 'fields', label: 'Field updates', kinds: ['updated'] },
  { key: 'stages', label: 'Stage changes', kinds: ['stage', 'conversion'] },
  { key: 'system', label: 'System', kinds: ['created', 'deleted', 'pct'] },
]

/** 'yyyy-MM-dd' shifted by whole days, on the calendar rather than the clock. */
function shiftDayKey(key: string, days: number): string {
  const at = Date.parse(`${key}T00:00:00Z`)
  return Number.isNaN(at) ? key : new Date(at + days * 86_400_000).toISOString().slice(0, 10)
}

/**
 * The inclusive day-key window a choice selects, or null for "no limit at that
 * end". `range` and `on` with their boxes still empty select nothing, so a
 * half-typed custom range shows everything rather than an empty screen.
 */
export function windowOf(when: WhenKey, from: string, to: string): { since: string | null; until: string | null } {
  const today = companyDayKey(new Date())
  switch (when) {
    case 'today':
      return { since: today, until: today }
    case 'yesterday': {
      const day = shiftDayKey(today, -1)
      return { since: day, until: day }
    }
    // Inclusive of today, so "Last 7 days" is a week ending now, not a week
    // ending yesterday plus today.
    case 'last7':
      return { since: shiftDayKey(today, -6), until: today }
    case 'last30':
      return { since: shiftDayKey(today, -29), until: today }
    case 'range':
      return { since: from || null, until: to || null }
    case 'on':
      return from ? { since: from, until: from } : { since: null, until: null }
    default:
      return { since: null, until: null }
  }
}

export interface TimelineFilters {
  show: string
  setShow: (key: string) => void
  who: string
  setWho: (actorId: string) => void
  when: WhenKey
  setWhen: (key: WhenKey) => void
  /** Custom range start, or the single day for `on`. 'yyyy-MM-dd'. */
  from: string
  setFrom: (day: string) => void
  to: string
  setTo: (day: string) => void
  /** api_name of a single field to follow through the record's whole history. */
  field: string
  setField: (apiName: string) => void
  /** How many of the four are doing something — the count on the Filter button. */
  activeCount: number
  clearAll: () => void
  /** True when this event survives every filter that is on. */
  matches: (event: TimelineEvent) => boolean
}

export function useTimelineFilters(prefix = 'h'): TimelineFilters {
  const [searchParams, setSearchParams] = useSearchParams()

  const read = useCallback(
    (key: string) => searchParams.get(prefix + key) ?? '',
    [searchParams, prefix]
  )

  const write = useCallback(
    (entries: Record<string, string>) => {
      setSearchParams(
        (current) => {
          const next = new URLSearchParams(current)
          for (const [key, value] of Object.entries(entries)) {
            if (value) next.set(prefix + key, value)
            else next.delete(prefix + key)
          }
          return next
        },
        { replace: true }
      )
    },
    [setSearchParams, prefix]
  )

  const show = read('show') || 'all'
  const who = read('who') || 'all'
  const when = (read('when') || 'any') as WhenKey
  const from = read('from')
  const to = read('to')
  const field = read('field')

  // Changing the choice drops the date boxes with it. Leaving 'from' behind
  // would make a later switch back to Custom range silently inherit a date
  // nobody typed this time.
  const setWhen = useCallback((key: WhenKey) => write({ when: key === 'any' ? '' : key, from: '', to: '' }), [write])

  const { since, until } = useMemo(() => windowOf(when, from, to), [when, from, to])

  const kinds = useMemo(() => SHOW_OPTIONS.find((o) => o.key === show)?.kinds, [show])

  const matches = useCallback(
    (event: TimelineEvent) => {
      if (kinds && !kinds.includes(event.kind)) return false
      if (who !== 'all' && event.actor !== who) return false
      if (field && !event.changes.some((change) => change.field === field)) return false
      if (since || until) {
        const day = companyDayKey(event.timestamp)
        if (!day) return false
        if (since && day < since) return false
        if (until && day > until) return false
      }
      return true
    },
    [kinds, who, field, since, until]
  )

  const activeCount =
    (show === 'all' ? 0 : 1) + (who === 'all' ? 0 : 1) + (when === 'any' ? 0 : 1) + (field ? 1 : 0)

  const clearAll = useCallback(
    () => write({ show: '', who: '', when: '', from: '', to: '', field: '' }),
    [write]
  )

  return {
    show,
    setShow: (key: string) => write({ show: key === 'all' ? '' : key }),
    who,
    setWho: (actorId: string) => write({ who: actorId === 'all' ? '' : actorId }),
    when,
    setWhen,
    from,
    setFrom: (day: string) => write({ from: day }),
    to,
    setTo: (day: string) => write({ to: day }),
    field,
    setField: (apiName: string) => write({ field: apiName === 'all' ? '' : apiName }),
    activeCount,
    clearAll,
    matches,
  }
}
