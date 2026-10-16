import { useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { CheckIcon, Trash2Icon } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Bullets, ErrorNotice } from '@/components/ui/notice'
import { PriceGrid } from '@/components/priceBooks/PriceGrid'
import { SimpleRecordPage } from '@/components/record/SimpleRecordPage'
import { EDITIONS, EDITIONS_MODULE, useDeleteEdition, useMakeEditionCurrent } from '@/lib/priceBooks'
import { useCanEditCatalogue } from '@/lib/products'
import { displayNameOf, fieldOf, labelForValue } from '@/lib/spec'

/**
 * One edition of the price list: what it is (Overview), and its prices
 * (Prices) — THE place a price is changed (decided 13 Oct 2026). The tab opens
 * on the Standard book; the Price book box above the grid turns it to a
 * regional book, to give that book a price of its own. A price book's own
 * page shows the same prices, read-only.
 *
 * A DRAFT is made current here, or deleted. Neither is offered for an edition
 * that has been in use: it is kept as it was, which is what lets a quote keep
 * the price it was issued at. The server holds both lines.
 */
export function EditionDetailPage() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const canEdit = useCanEditCatalogue()
  const [asking, setAsking] = useState<'current' | 'delete' | null>(null)
  const makeCurrent = useMakeEditionCurrent(id ?? '')
  const remove = useDeleteEdition(id ?? '')
  const status = fieldOf(EDITIONS_MODULE, 'status')
  const busy = makeCurrent.isPending || remove.isPending

  const close = () => {
    makeCurrent.reset()
    remove.reset()
    setAsking(null)
  }

  return (
    <SimpleRecordPage
      module={EDITIONS_MODULE}
      collection={EDITIONS}
      listPath="/price_books"
      noun="edition"
      canEdit={canEdit}
      deletable={() => false}
      badge={(values) => (
        <span className="text-muted-foreground text-sm font-normal">{labelForValue(status?.picklist, values.status)}</span>
      )}
      actions={(values) =>
        values.status === 'DRAFT' && (
          <>
            <Button onClick={() => setAsking('current')}>
              <CheckIcon className="size-4" />
              Make current
            </Button>
            <Button variant="outline" onClick={() => setAsking('delete')} className="text-destructive hover:text-destructive">
              <Trash2Icon className="size-4" />
              Delete
            </Button>

            <Dialog open={asking === 'current'} onOpenChange={(open) => !open && close()}>
              <DialogContent className="sm:max-w-lg">
                <DialogHeader>
                  <DialogTitle>Sell from {displayNameOf(values)} from now on?</DialogTitle>
                  <DialogDescription>It becomes the edition in use, for every price book.</DialogDescription>
                </DialogHeader>
                <Bullets
                  className="text-muted-foreground text-sm"
                  items={[
                    'The edition in use today is retired, as of today.',
                    'After this, its prices can’t be changed. A new price needs a new edition.',
                  ]}
                />
                {makeCurrent.isError && <ErrorNotice error={makeCurrent.error} fallback="It wasn't made current. Try again." />}
                <DialogFooter>
                  <Button variant="outline" onClick={close} disabled={busy}>
                    Cancel
                  </Button>
                  <Button onClick={() => makeCurrent.mutate(undefined, { onSuccess: close })} disabled={busy}>
                    {makeCurrent.isPending ? 'Saving…' : 'Make current'}
                  </Button>
                </DialogFooter>
              </DialogContent>
            </Dialog>

            <Dialog open={asking === 'delete'} onOpenChange={(open) => !open && close()}>
              <DialogContent className="sm:max-w-lg">
                <DialogHeader>
                  <DialogTitle>Delete {displayNameOf(values)}?</DialogTitle>
                  <DialogDescription>This draft and every price in it are removed for good.</DialogDescription>
                </DialogHeader>
                <Bullets className="text-muted-foreground text-sm" items={['The edition in use is not touched.']} />
                {remove.isError && <ErrorNotice error={remove.error} fallback="It wasn't deleted. Try again." />}
                <DialogFooter>
                  <Button variant="outline" onClick={close} disabled={busy}>
                    Cancel
                  </Button>
                  <Button
                    variant="destructive"
                    onClick={() =>
                      remove.mutate(undefined, {
                        onSuccess: () => {
                          setAsking(null)
                          navigate('/price_books')
                        },
                      })
                    }
                    disabled={busy}
                  >
                    {remove.isPending ? 'Deleting…' : 'Delete draft'}
                  </Button>
                </DialogFooter>
              </DialogContent>
            </Dialog>
          </>
        )
      }
      tabs={() => [{ key: 'prices', label: 'Prices', content: <PriceGrid editionId={id} canEdit={canEdit} /> }]}
    />
  )
}
