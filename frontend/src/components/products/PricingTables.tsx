import { ListCell, NUMERIC_TYPES, type ListRow } from '@/components/list/ListCell'
import { pricingTable } from '@/lib/products'
import { fieldsOf } from '@/lib/spec'
import { cn } from '@/lib/utils'

const MODULE = 'cpq'
const SECTION = 'PRICING PARAMETERS'
const COLLECTION = 'pricingParams'

/**
 * The pricing parameters — the perpetual multiplier, the onsite premium and
 * their neighbours — as CPQ's Price Rules tab shows them until price rules are
 * built (phase 4): read-only, from the one pricing table still bundled
 * (lib/catalogue.ts).
 *
 * The rows ARE the register's fields for that section, in its order with its
 * labels and descriptions — a parameter the file has nothing for shows a dash,
 * which is the gap, stated.
 *
 * This file drew five tables until Products phase 3 (13 Oct 2026). Sizes are
 * the Sizing Guide now, regions are the price books, and the rate card and
 * support tiers are products with prices.
 */
export function PricingParameters() {
  const fields = fieldsOf(MODULE).filter((f) => f.section === SECTION)
  const row = (pricingTable(COLLECTION)[0] ?? {}) as ListRow
  if (fields.length === 0) return null

  return (
    <div className="overflow-x-auto rounded-md border">
      <table className="w-full text-sm">
        <tbody className="divide-y">
          {fields.map((f) => (
            <tr key={f.api_name}>
              <td className="px-3 py-2 font-medium">{f.label}</td>
              <td className={cn('px-3 py-2', NUMERIC_TYPES.has(f.type) && 'text-right')}>
                <ListCell field={f} row={row} />
              </td>
              <td className="text-muted-foreground px-3 py-2">{f.description}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
