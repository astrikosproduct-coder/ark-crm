import type { ListRow } from '@/components/list/ListCell'
import { localAmount, revenueOf } from '@/lib/revenue'

/**
 * A record's value: the module's ONE revenue field, in the currency it was
 * entered in — never another field standing in for a blank one, and never a
 * "$" on an AED amount. See lib/revenue.ts.
 *
 * NO STRIKETHROUGH, EVER (18 Sep 2026)
 * ------------------------------------
 * This used to draw a line through the amount whenever the server said the
 * record did not roll up — a secondary pursuit, a Closed Lost, a Converted.
 * Struck-out text reads as deleted, wrong or cancelled, and a real contract
 * value is none of those: it is a true figure that a particular total happens
 * not to sum. The rule has not changed and the totals are unaffected; only the
 * presentation is, because a number the business believes should look like a
 * number the business believes.
 */
export function RevenueAmount({ row }: { row: ListRow }) {
  const revenue = revenueOf(row)
  return (
    <span className="tabular-nums" title={revenue?.label}>
      {localAmount(revenue)}
    </span>
  )
}
