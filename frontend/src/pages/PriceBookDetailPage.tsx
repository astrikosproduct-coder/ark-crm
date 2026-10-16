import { useParams } from 'react-router-dom'

import { Bullets } from '@/components/ui/notice'
import { PriceGrid } from '@/components/priceBooks/PriceGrid'
import { SimpleRecordPage } from '@/components/record/SimpleRecordPage'
import { PRICE_BOOKS, PRICE_BOOKS_MODULE } from '@/lib/priceBooks'
import { useCanEditCatalogue } from '@/lib/products'
import { fieldOf, labelForValue } from '@/lib/spec'

/**
 * One price book: what it is (Overview — its currency, Region Pricing % and FX
 * rate, from the register) and what everything costs in it (Prices).
 *
 * PRICES ARE READ-ONLY HERE, for everyone (decided 13 Oct 2026). A price is
 * changed in one place — Price Books -> Editions -> the edition -> Prices —
 * and this tab points an admin or a developer there. What IS edited on this
 * page is the book itself: its name, currency, Region Pricing % and FX rate.
 *
 * The Standard book is never deleted or deactivated — every other book is
 * worked out from it — so it is offered neither; the server refuses both
 * whatever this page draws.
 */
export function PriceBookDetailPage() {
  const { id } = useParams<{ id: string }>()
  const canEdit = useCanEditCatalogue()
  const standardLabel = fieldOf(PRICE_BOOKS_MODULE, 'is_standard')?.label ?? 'Standard Price Book'

  return (
    <SimpleRecordPage
      module={PRICE_BOOKS_MODULE}
      collection={PRICE_BOOKS}
      listPath="/price_books"
      noun="price book"
      canEdit={canEdit}
      badge={(values) =>
        values.is_standard === true && <span className="text-muted-foreground text-sm font-normal">{standardLabel}</span>
      }
      subtitle={(values) => labelForValue(fieldOf(PRICE_BOOKS_MODULE, 'currency')?.picklist, values.currency) || undefined}
      deletable={(values) => values.is_standard !== true}
      deleteDescription="Deleting a price book removes the prices of its own."
      deleteGuidance={
        <Bullets
          className="text-muted-foreground"
          items={[
            'Its worked-out prices were never stored, so nothing else goes.',
            'Deactivate keeps the book and stops it being quoted from.',
          ]}
        />
      }
      tabs={() => [{ key: 'prices', label: 'Prices', content: <PriceGrid bookId={id ?? ''} canEdit={false} editHint={canEdit} /> }]}
    />
  )
}
