import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'

interface Props {
  open: boolean
  /** Stay on the page and keep the edits. Also what a dismiss (Esc, backdrop) does. */
  onStay: () => void
  /** Leave, discarding whatever is unsaved. */
  onLeave: () => void
}

/**
 * The one confirmation shown whenever an action would throw away unsaved edits
 * — navigating away, closing the editor, or opening another record.
 *
 * Deliberately not a "save my work for later" prompt: nothing is persisted
 * behind the user's back any more, so the choice offered is the honest one —
 * stay and save, or leave and lose it.
 */
export function UnsavedChangesDialog({ open, onStay, onLeave }: Props) {
  return (
    <Dialog open={open} onOpenChange={(next) => !next && onStay()}>
      <DialogContent className="max-w-lg gap-6 p-7">
        <DialogHeader className="gap-2">
          <DialogTitle className="text-page-title leading-snug">
            Leave without saving?
          </DialogTitle>
          <DialogDescription className="text-foreground/80 text-sm">
            Your changes on this page will be lost.
          </DialogDescription>
        </DialogHeader>
        <DialogFooter>
          <Button type="button" variant="outline" onClick={onStay}>
            Stay Here
          </Button>
          <Button type="button" variant="destructive" onClick={onLeave}>
            Leave without saving
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
