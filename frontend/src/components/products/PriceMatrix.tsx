import { currencySign, money } from '@/lib/format'
import { EDITIONS_MODULE, PRICES_MODULE } from '@/lib/priceBooks'
import type { ProductPrice } from '@/lib/products'
import { fieldOf } from '@/lib/spec'

/**
 * A product's list price on its own page: the Standard price book, the edition
 * in use — sizes across, one row, as the price book lays it out. Read-only
 * here; prices are set in Price Books.
 *
 * Every word on it is the register's: the row is named by the List Price
 * field, the columns by the sizes of the Sizing Guide, in its order (the
 * server sends them so), each with the currency's sign — "XS ($)". A product
 * with one price whatever the size shows that one figure; a Support product
 * shows its percentage; one with none says so.
 */
export function PriceMatrix({ prices }: { prices: ProductPrice[] }) {
  const priceLabel = fieldOf(PRICES_MODULE, 'list_price_usa_usd')?.label ?? 'List Price'
  const pctLabel = fieldOf(PRICES_MODULE, 'pct_of_annual_licence')?.label ?? '% of Annual Licence'
  const sizeLabel = fieldOf(PRICES_MODULE, 'size')?.label ?? 'Size'
  const editionLabel = fieldOf(EDITIONS_MODULE, 'price_book_version')?.label ?? 'Price Book Version'

  if (prices.length === 0) {
    return (
      <p className="text-sm text-muted-foreground">
        No list price yet. This item can be picked on a Lead, but it can't be quoted until it has a price in the Standard
        price book.
      </p>
    )
  }

  const editions = [...new Set(prices.map((p) => p.price_book_version).filter(Boolean))]
  const sign = currencySign(prices[0]?.currency)
  const edition = editions.length > 0 && (
    <p className="text-xs text-muted-foreground">
      {editionLabel}: {editions.join(', ')}.
    </p>
  )
  const flat = prices.find((p) => p.size === null)

  if (flat) {
    const share = flat.pct_of_annual_licence
    return (
      <div className="space-y-1.5">
        <p className="text-sm">
          <span className="text-muted-foreground">{share !== null ? pctLabel : `${priceLabel}, at every size`}: </span>
          <span className="font-medium tabular-nums">
            {share !== null ? `${Math.round(share * 1_000_000) / 10_000}%` : money(flat.list_price_usa_usd)}
          </span>
        </p>
        {edition}
      </div>
    )
  }

  return (
    <div className="space-y-1.5">
      <div className="overflow-x-auto rounded-md border">
        <table className="w-full text-sm">
          <thead className="bg-muted/50 text-muted-foreground">
            <tr>
              <th className="px-3 py-2 text-left font-medium">{sizeLabel}</th>
              {prices.map((p) => (
                <th key={p.size} className="px-3 py-2 text-right font-medium whitespace-nowrap">
                  {p.size}
                  {sign && ` (${sign})`}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            <tr>
              <td className="px-3 py-2 text-muted-foreground">{priceLabel}</td>
              {prices.map((p) => (
                <td key={p.size} className="px-3 py-2 text-right tabular-nums">
                  {money(p.list_price_usa_usd)}
                </td>
              ))}
            </tr>
          </tbody>
        </table>
      </div>
      {edition}
    </div>
  )
}
