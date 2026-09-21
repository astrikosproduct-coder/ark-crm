/**
 * The record-id convention every collection follows — PREFIX-00001, per
 * CLAUDE.md's Conventions list.
 *
 * Pulled out of useDataStore so a seed-time transform (deriveOpportunitiesFromLeads,
 * which runs before any store exists) and the store's own create() can share one
 * counting rule instead of drifting into two.
 *
 * A NUMBER IS NEVER HANDED OUT TWICE. This used to be "one past the highest
 * number present", which reuses ids: delete QT-00087, the newest quote, and the
 * next quote was QT-00087 again — and anything still naming the old one (a
 * comment pin, an approval, an email somebody sent) silently pointed at a
 * different quote. The PostgreSQL modules already count this way
 * (backend/app/ids.py); `floor` is the browser store's stored high-water mark,
 * so the browser-only modules now do too.
 */
export interface IdScheme {
  prefix: string
  pad: number
}

/**
 * Not every collection keys its rows on `id` — products key on sku, sizes on
 * code, rate_card on level. Resolve whichever identifying field a record
 * actually has rather than forcing every collection to conform.
 */
function identify(item: unknown): string | undefined {
  if (!item || typeof item !== 'object') return undefined
  const rec = item as Record<string, unknown>
  const key = rec.id ?? rec.sku ?? rec.code ?? rec.level ?? rec.tier
  return typeof key === 'string' ? key : undefined
}

/** The highest number in `scheme` among the rows present. 0 when none. */
export function highestIdNumber(scheme: IdScheme, existing: unknown[]): number {
  let max = 0
  for (const item of existing) {
    const id = identify(item)
    if (id?.startsWith(`${scheme.prefix}-`)) {
      const num = Number.parseInt(id.slice(scheme.prefix.length + 1), 10)
      if (!Number.isNaN(num) && num > max) max = num
    }
  }
  return max
}

export function formatId(scheme: IdScheme, number: number): string {
  return `${scheme.prefix}-${String(number).padStart(scheme.pad, '0')}`
}

/**
 * The next id in `scheme`: one past the higher of the rows present and
 * `floor`, the highest number ever issued for the collection.
 */
export function nextId(scheme: IdScheme, existing: unknown[], floor = 0): string {
  return formatId(scheme, Math.max(highestIdNumber(scheme, existing), floor) + 1)
}
