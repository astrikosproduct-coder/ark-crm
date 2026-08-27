/**
 * The record-id convention every collection follows — PREFIX-00001, per
 * CLAUDE.md's Conventions list.
 *
 * Pulled out of useDataStore so a seed-time transform (deriveOpportunitiesFromLeads,
 * which runs before any store exists) and the store's own create() can share one
 * counting rule instead of drifting into two.
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

/** The next id in `scheme`, one past the highest number already present. */
export function nextId(scheme: IdScheme, existing: unknown[]): string {
  let max = 0
  for (const item of existing) {
    const id = identify(item)
    if (id?.startsWith(`${scheme.prefix}-`)) {
      const num = Number.parseInt(id.slice(scheme.prefix.length + 1), 10)
      if (!Number.isNaN(num) && num > max) max = num
    }
  }
  return `${scheme.prefix}-${String(max + 1).padStart(scheme.pad, '0')}`
}
