import { useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { PlusIcon } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { PageLayout } from '@/components/layout/PageLayout'
import { ListFilterBar } from '@/components/list/ListFilterBar'
import { RecordListView } from '@/components/list/RecordListView'
import { useListFilters } from '@/lib/listFilters'
import { EDITIONS, EDITIONS_MODULE, PRICE_BOOKS, PRICE_BOOKS_MODULE } from '@/lib/priceBooks'
import { useCanEditCatalogue } from '@/lib/products'

/**
 * Price Books (Products phase 3, 13 Oct 2026) — Zoho's Price Books.
 *
 * Two lists. PRICE BOOKS: the Standard book and one per region, each with its
 * currency, its Region Pricing % and its FX rate; a book's prices are on its
 * own page. EDITIONS: the price list as it stood — the one in use, the drafts
 * being prepared, and the past ones.
 *
 * Both are the spec-driven list every module has (spec/extensions.json
 * list_views). An admin or a developer adds a book or starts an edition here;
 * everyone reads.
 */
export function PriceBooksPage() {
  const navigate = useNavigate()
  const canEdit = useCanEditCatalogue()
  const [tab, setTab] = useState('books')
  const filters = useListFilters({ view: PRICE_BOOKS_MODULE })
  const listFilter = useMemo(() => filters.params(), [filters])

  return (
    <PageLayout
      wide
      title="Price Books"
      activeTab={tab}
      onTabChange={setTab}
      actions={
        canEdit &&
        (tab === 'books' ? (
          <Button onClick={() => navigate('/price_books/new')}>
            <PlusIcon className="size-4" />
            New price book
          </Button>
        ) : (
          <Button onClick={() => navigate('/price_books/editions/new')}>
            <PlusIcon className="size-4" />
            New edition
          </Button>
        ))
      }
      tabs={[
        {
          key: 'books',
          label: 'Price books',
          content: (
            <>
              <ListFilterBar filters={filters} plural="Price books" searchPlaceholder="Search name or currency…" />
              <RecordListView
                module={PRICE_BOOKS_MODULE}
                collection={PRICE_BOOKS}
                basePath="/price_books"
                filter={listFilter}
                hideSearch
                pageSize={50}
                emptyMessage="No price books yet."
              />
            </>
          ),
        },
        {
          key: 'editions',
          label: 'Editions',
          content: (
            <div className="space-y-2 py-3">
              <p className="text-sm text-muted-foreground">
                The price list as it stood. To change prices, start a new edition, change them there, then make it current.
              </p>
              <RecordListView
                module={EDITIONS_MODULE}
                collection={EDITIONS}
                basePath="/price_books/editions"
                hideSearch
                pageSize={50}
                emptyMessage="No editions yet."
              />
            </div>
          ),
        },
      ]}
    />
  )
}
