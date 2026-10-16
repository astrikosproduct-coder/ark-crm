import { useMemo, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { CopyIcon, PencilIcon, RotateCcwIcon, Trash2Icon } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Bullets } from '@/components/ui/notice'
import { PageLayout } from '@/components/layout/PageLayout'
import { RecordForm } from '@/components/form/RecordForm'
import { PriceMatrix } from '@/components/products/PriceMatrix'
import { ProductPursuits } from '@/components/products/ProductPursuits'
import { DeleteRecordDialog } from '@/components/record/DeleteRecordDialog'
import { RecordEditor } from '@/components/record/RecordEditor'
import { PRODUCTS_MODULE, productSections, useCanEditCatalogue, useProduct, withBoxesAnswered } from '@/lib/products'
import { useSetRecordActive } from '@/lib/recordLifecycle'
import { PRODUCT_REFERRERS } from '@/lib/referrers'
import { displayNameOf, fieldsOf, labelForValue, fieldOf, withRecordId } from '@/lib/spec'
import { cn } from '@/lib/utils'

const MODULE = PRODUCTS_MODULE
const COLLECTION = 'products'

/**
 * One catalogue item.
 *
 * Overview is the product's own section of the register, drawn by the form
 * engine like any record, with the item's list price at each size under it.
 * Pursuits lists every Lead, Opportunity and Deal naming it.
 *
 * Since phase 2 (13 Oct 2026) an admin or a developer can Edit it, Clone it,
 * deactivate or reactivate it, and Delete it — the last only while nothing
 * names it. Everyone else reads it; the server holds that line, the buttons
 * are just not drawn (lib/products.ts). Prices are still the price book's.
 */
export function ProductDetailPage() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const canEdit = useCanEditCatalogue()
  const [editing, setEditing] = useState(false)
  const [deleting, setDeleting] = useState(false)
  const { data, isLoading, isError, dataUpdatedAt } = useProduct(id)

  const sections = useMemo(() => productSections(), [])
  const values = useMemo(() => (data ? withRecordId(MODULE, data) : undefined), [data])

  // A product loaded from the price book has no answer for Supports Perpetual
  // or Quantity Allowed — the file stated none. An unticked box would read as
  // "No", so on the page they are left off until someone has answered. The
  // edit form shows them unticked; saving it is the answer.
  const unanswered = useMemo(() => {
    const out = new Set<string>()
    for (const f of fieldsOf(MODULE)) {
      if (sections.includes(f.section) && f.type === 'checkbox' && (values?.[f.api_name] ?? null) === null) out.add(f.api_name)
    }
    return out
  }, [values, sections])

  const setActive = useSetRecordActive(COLLECTION, id ?? '', {
    noun: 'product',
    recordName: values ? displayNameOf(values) : (id ?? ''),
  })

  if (isError) {
    return (
      <PageLayout
        back
        title="Product"
        tabs={[
          {
            key: 'missing',
            label: 'Overview',
            content: <p className="py-6 text-sm text-destructive">This product no longer exists. It may have been deleted.</p>,
          },
        ]}
      />
    )
  }

  const inactive = values?.active === false
  const category = labelForValue(fieldOf(MODULE, 'catalogue_category')?.picklist, values?.catalogue_category)

  return (
    <>
      <PageLayout
        back
        title={
          <>
            <span className={cn(inactive && 'text-muted-foreground')}>{values ? displayNameOf(values) : ''}</span>
            {inactive && <span className="text-muted-foreground text-sm font-normal">Inactive</span>}
          </>
        }
        subtitle={category || undefined}
        actions={
          canEdit &&
          !editing && (
            <>
              <Button variant="outline" onClick={() => setEditing(true)} disabled={isLoading || !values}>
                <PencilIcon className="size-4" />
                Edit
              </Button>
              <Button variant="outline" onClick={() => navigate(`/products/new?clone=${id}`)} disabled={isLoading || !values}>
                <CopyIcon className="size-4" />
                Clone
              </Button>
              {/* Reactivating is the safe, reversible action, so it sits in
                  plain sight next to Edit rather than inside a Delete dialog. */}
              {inactive && (
                <Button variant="outline" onClick={() => setActive.mutate(true)} disabled={setActive.isPending}>
                  <RotateCcwIcon className="size-4" />
                  {setActive.isPending ? 'Reactivating…' : 'Reactivate'}
                </Button>
              )}
              <Button
                variant="outline"
                onClick={() => setDeleting(true)}
                disabled={isLoading || !values}
                className="text-destructive hover:text-destructive"
              >
                <Trash2Icon className="size-4" />
                Delete
              </Button>
            </>
          )
        }
        tabs={[
          {
            key: 'overview',
            label: 'Overview',
            content: isLoading ? (
              <p className="py-6 text-sm text-muted-foreground">Loading…</p>
            ) : editing ? (
              // A RecordForm seeds its state once, so both of these are keyed
              // on the fetch that produced their values.
              <RecordEditor
                key={`edit:${id}:${dataUpdatedAt}`}
                module={MODULE}
                collection={COLLECTION}
                recordId={id}
                initialValues={values ? withBoxesAnswered(values) : undefined}
                sections={sections}
                onSaved={() => setEditing(false)}
                onCancel={() => setEditing(false)}
              />
            ) : (
              <div className="space-y-3 py-3">
                <RecordForm
                  key={`view:${id}:${dataUpdatedAt}`}
                  module={MODULE}
                  mode="view"
                  values={values}
                  sections={sections}
                  hiddenFields={unanswered}
                />
                <PriceMatrix prices={data?.prices ?? []} />
              </div>
            ),
          },
          { key: 'pursuits', label: 'Pursuits', content: <ProductPursuits productId={id ?? ''} /> },
        ]}
      />

      {values && canEdit && (
        <DeleteRecordDialog
          open={deleting}
          onOpenChange={setDeleting}
          collection={COLLECTION}
          recordId={id ?? ''}
          recordName={displayNameOf(values)}
          noun="product"
          active={!inactive}
          lookupTarget="product"
          referrers={PRODUCT_REFERRERS}
          onDeleted={() => navigate('/products')}
          guidance={
            <Bullets
              className="text-muted-foreground"
              items={[
                'Delete removes the product and its list prices for good.',
                'Deactivate keeps it and stops it being picked.',
              ]}
            />
          }
        />
      )}
    </>
  )
}
