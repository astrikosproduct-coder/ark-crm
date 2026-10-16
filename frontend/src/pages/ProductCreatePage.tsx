import { useMemo } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'

import { PageLayout } from '@/components/layout/PageLayout'
import { RecordEditor } from '@/components/record/RecordEditor'
import { PRODUCTS_MODULE, productSections, useProduct, withBoxesAnswered } from '@/lib/products'
import { displayNameOf, fieldsOf } from '@/lib/spec'
import type { Values } from '@/lib/spec/conditions'

const COLLECTION = 'products'

/**
 * A new product — blank, or a copy of another (`/products/new?clone=PRD-0001`,
 * the record page's Clone button).
 *
 * The form is a PRODUCT's own section of the register and nothing else
 * (lib/products.ts). A clone opens with everything the source holds except
 * what makes it that product: its number, and its SKU Code, which is one
 * product's and has to be typed. List prices are not copied — they are the
 * price book's, and a new product has none until it is priced there.
 */
export function ProductCreatePage() {
  const navigate = useNavigate()
  const [search] = useSearchParams()
  const cloneId = search.get('clone') ?? undefined
  const source = useProduct(cloneId)
  const sections = useMemo(() => productSections(), [])

  const initialValues = useMemo(() => {
    if (!cloneId) return withBoxesAnswered({}, true)
    if (!source.data) return undefined
    const copied: Values = {}
    for (const f of fieldsOf(PRODUCTS_MODULE)) {
      // The product's own typed-in fields: not its number, not a formula.
      if (!sections.includes(f.section) || f.type === 'autonumber' || f.type === 'computed') continue
      if (f.api_name in source.data) copied[f.api_name] = source.data[f.api_name]
    }
    delete copied.sku_code
    // A copy starts on sale, whatever the product it was made from is.
    return withBoxesAnswered({ ...copied, active: true }, true)
  }, [cloneId, source.data, sections])

  const title = cloneId ? 'Clone product' : 'New product'
  const subtitle = cloneId && source.data ? `A copy of ${displayNameOf(source.data)}. Give it a SKU Code of its own.` : undefined

  return (
    <PageLayout
      title={title}
      subtitle={subtitle}
      tabs={[
        {
          key: 'new',
          label: 'Details',
          content:
            cloneId && source.isError ? (
              <p className="py-6 text-sm text-destructive">The product to copy no longer exists. It may have been deleted.</p>
            ) : !initialValues ? (
              <p className="py-6 text-sm text-muted-foreground">Loading…</p>
            ) : (
              <RecordEditor
                // Keyed on the source, so the form seeds once the copy has loaded.
                key={cloneId ?? 'new'}
                module={PRODUCTS_MODULE}
                collection={COLLECTION}
                initialValues={initialValues}
                sections={sections}
                saveLabel="Create product"
                onSaved={(id) => navigate(`/products/${id}`, { replace: true })}
                onCancel={() => navigate(cloneId ? `/products/${cloneId}` : '/products')}
              />
            ),
        },
      ]}
    />
  )
}
