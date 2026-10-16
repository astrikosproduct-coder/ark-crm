import { Link } from 'react-router-dom'

import { Bullets } from '@/components/ui/notice'
import { money } from '@/lib/format'
import { moduleFor } from '@/lib/modules'
import { stageLabel, stageNumberOf } from '@/lib/pipeline'
import { useProductPursuits, type ProductPursuit } from '@/lib/products'
import { pursuitStatusLabel } from '@/lib/pursuitGroups'
import { fieldOf } from '@/lib/spec'

/** "Lead", "Opportunity", "Deal" — the module's own name, in the singular. */
function nounOf(module: string): string {
  const label = moduleFor(module)?.label ?? module
  return label.endsWith('ies') ? `${label.slice(0, -3)}y` : label.replace(/s$/, '')
}

/** The fields that name the product on this pursuit, as the form labels them. */
function namedIn(row: ProductPursuit): string {
  return row.fields.map((f) => fieldOf(f.module, f.api_name)?.label ?? f.api_name).join(', ')
}

/**
 * Every pursuit naming one product — the product page's Pursuits tab.
 *
 * The rows and both totals are backend/app/products.py's: a pursuit is listed
 * once, as the record it is today, and counted once however many of its fields
 * name the product. The figures follow the dashboard's rule (app/revenue.py),
 * so they reconcile with the boards.
 */
export function ProductPursuits({ productId }: { productId: string }) {
  const { data, isLoading } = useProductPursuits(productId)

  if (isLoading) return <p className="py-6 text-sm text-muted-foreground">Loading…</p>

  const rows = data?.records ?? []
  if (rows.length === 0) {
    return <p className="py-3 text-sm text-muted-foreground">No Lead, Opportunity or Deal names this product yet.</p>
  }
  const total = data!.total

  return (
    <div className="space-y-3 py-3">
      <div className="overflow-x-auto rounded-md border">
        <table className="w-full text-sm">
          <thead className="bg-muted/50 text-muted-foreground text-left">
            <tr>
              <th className="px-3 py-2 font-medium">Pursuit</th>
              <th className="px-3 py-2 font-medium">Module</th>
              <th className="px-3 py-2 font-medium">Stage</th>
              <th className="px-3 py-2 font-medium">Status</th>
              <th className="px-3 py-2 font-medium">Named in</th>
              <th className="px-3 py-2 text-right font-medium">Value (USD)</th>
            </tr>
          </thead>
          <tbody className="divide-y">
            {rows.map((r) => (
              <tr key={`${r.module}:${r.id}`}>
                <td className="px-3 py-2">
                  <Link className="font-medium underline-offset-2 hover:underline" to={`/${r.module}/${r.id}`}>
                    {r.name}
                  </Link>
                </td>
                <td className="px-3 py-2">{nounOf(r.module)}</td>
                <td className="px-3 py-2 whitespace-nowrap">{stageLabel(stageNumberOf(r.stage))}</td>
                <td className="px-3 py-2 whitespace-nowrap">{pursuitStatusLabel(r.module, r.status)}</td>
                <td className="px-3 py-2">{namedIn(r)}</td>
                <td className="px-3 py-2 text-right tabular-nums">
                  {r.revenue.usd === null ? <span className="text-muted-foreground">—</span> : money(r.revenue.usd)}
                </td>
              </tr>
            ))}
          </tbody>
          <tfoot className="border-t font-medium">
            <tr>
              <td className="px-3 py-2" colSpan={5}>
                Open pipeline · {total.pipeline_count} {total.pipeline_count === 1 ? 'pursuit' : 'pursuits'}
              </td>
              <td className="px-3 py-2 text-right tabular-nums">{money(total.pipeline_usd)}</td>
            </tr>
            <tr>
              <td className="px-3 py-2" colSpan={5}>
                Won · {total.won_count} {total.won_count === 1 ? 'deal' : 'deals'}
              </td>
              <td className="px-3 py-2 text-right tabular-nums">{money(total.won_usd)}</td>
            </tr>
          </tfoot>
        </table>
      </div>
      <Bullets
        className="text-muted-foreground text-xs"
        items={[
          'Each pursuit is listed once, as the record it is today.',
          'Open pipeline: open and on-hold Leads and Opportunities.',
          'Won: Deals whose PO has been received.',
          'A value is the whole pursuit, not this product’s share of it.',
        ]}
      />
    </div>
  )
}
