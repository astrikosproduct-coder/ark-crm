import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { PlusIcon } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { PageLayout } from '@/components/layout/PageLayout'
import { RecordListView } from '@/components/list/RecordListView'
import { PricingParameters } from '@/components/products/PricingTables'
import { SIZES, SIZES_MODULE } from '@/lib/priceBooks'
import { useCanEditCatalogue } from '@/lib/products'
import { ComingSoon } from '@/pages/ComingSoon'

/**
 * CPQ — configure, price, quote. A module of its own in ARK (decided 13 Oct
 * 2026); in Zoho it sits under Setup.
 *
 *   Sizing Guide          the deployment sizes a price is set at, as records
 *                         — built, Products phase 3
 *   Product Configurator  what goes with what            — phase 4
 *   Price Rules           the multipliers and discounts  — phase 4. Until
 *                         then the numbers those rules will hold are shown
 *                         here, read-only.
 */
export function CpqPage() {
  const navigate = useNavigate()
  const canEdit = useCanEditCatalogue()
  const [tab, setTab] = useState('sizes')

  return (
    <PageLayout
      wide
      title="CPQ"
      activeTab={tab}
      onTabChange={setTab}
      actions={
        canEdit &&
        tab === 'sizes' && (
          <Button onClick={() => navigate('/cpq/sizes/new')}>
            <PlusIcon className="size-4" />
            New size
          </Button>
        )
      }
      tabs={[
        {
          key: 'sizes',
          label: 'Sizing Guide',
          content: (
            <div className="space-y-2 py-3">
              <p className="text-sm text-muted-foreground">
                The deployment sizes a price is set at. A new size becomes a column of every price book.
              </p>
              <RecordListView
                module={SIZES_MODULE}
                collection={SIZES}
                basePath="/cpq/sizes"
                hideSearch
                pageSize={50}
                emptyMessage="No sizes yet."
              />
            </div>
          ),
        },
        { key: 'configurator', label: 'Product Configurator', content: <ComingSoon label="The product configurator" /> },
        {
          key: 'rules',
          label: 'Price Rules',
          content: (
            <div className="space-y-3 py-3">
              <p className="text-sm text-muted-foreground">
                The numbers the price rules will use. They can’t be changed here yet.
              </p>
              <PricingParameters />
              <ComingSoon label="Price rules" />
            </div>
          ),
        },
      ]}
    />
  )
}
