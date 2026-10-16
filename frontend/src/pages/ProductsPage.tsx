import { useMemo } from 'react'
import { useNavigate } from 'react-router-dom'

import { PageLayout } from '@/components/layout/PageLayout'
import { ListFilterBar } from '@/components/list/ListFilterBar'
import { ModuleActions } from '@/components/list/ModuleActions'
import { RecordListView } from '@/components/list/RecordListView'
import { useListFilters } from '@/lib/listFilters'
import { productSections, useCanEditCatalogue } from '@/lib/products'

/**
 * Products — the catalogue.
 *
 * The list is the same spec-driven list every module has — its columns, search
 * and filters are spec/extensions.json list_views.products. Since phase 2
 * (13 Oct 2026) an admin or a developer adds a product here, by hand or from
 * a sheet; everyone can export what the list shows.
 *
 * Prices are not here: they are set in Price Books, and the sizes they are
 * set at in CPQ's Sizing Guide (Products phase 3). The "Price book" tab this
 * page had, with its five read-only tables, went with them.
 */
export function ProductsPage() {
  const navigate = useNavigate()
  const canEdit = useCanEditCatalogue()
  const sections = useMemo(() => productSections(), [])
  const filters = useListFilters({ view: 'products', sections })
  const listFilter = useMemo(() => filters.params(), [filters])

  return (
    <PageLayout
      wide
      title="Products"
      actions={
        <ModuleActions
          module="products"
          plural="Products"
          noun="product"
          createLabel={canEdit ? 'New product' : undefined}
          onCreate={canEdit ? () => navigate('/products/new') : undefined}
          exportFilter={() => listFilter}
          allowImport={canEdit}
          importNamesRecords={false}
          importNote="A new product has no list price yet. Prices are set in Price Books."
        />
      }
      tabs={[
        {
          key: 'list',
          label: 'List',
          content: (
            <>
              <ListFilterBar filters={filters} plural="Products" searchPlaceholder="Search name, SKU or description…" />
              <RecordListView module="products" collection="products" basePath="/products" filter={listFilter} hideSearch pageSize={50} />
            </>
          ),
        },
      ]}
    />
  )
}
