import { Bullets } from '@/components/ui/notice'
import { SimpleRecordPage } from '@/components/record/SimpleRecordPage'
import { SIZES, SIZES_MODULE } from '@/lib/priceBooks'
import { useCanEditCatalogue } from '@/lib/products'

/**
 * One deployment size — a row of CPQ's Sizing Guide. The register's form and
 * nothing else. A size that prices are set at can't be deleted (the server
 * says so, with how many); it is deactivated instead.
 */
export function SizeDetailPage() {
  const canEdit = useCanEditCatalogue()
  return (
    <SimpleRecordPage
      module={SIZES_MODULE}
      collection={SIZES}
      listPath="/cpq"
      noun="size"
      canEdit={canEdit}
      deleteDescription="A size can be deleted only while no price is set at it."
      deleteGuidance={
        <Bullets
          className="text-muted-foreground"
          items={['Deactivate keeps the size and the prices already set at it.', 'It stops being a column for new prices.']}
        />
      }
    />
  )
}
