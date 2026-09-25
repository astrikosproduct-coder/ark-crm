import { useEffect, useState } from 'react'
import { UploadIcon } from 'lucide-react'

import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { ErrorNotice, Notice } from '@/components/ui/notice'
import { Textarea } from '@/components/ui/textarea'
import { useDraftStatus, usePublishMetadata, type DraftStatus } from '@/lib/metadata'

/** "3 unpublished changes" — or, before the first publish, when the draft is all change. */
function pendingLabel(draft: DraftStatus): string {
  const n = draft.changes.length
  if (n === 0) return 'Unpublished changes'
  return `${n} unpublished change${n === 1 ? '' : 's'}`
}

/**
 * The line across the top of Setup: "3 unpublished changes · Publish".
 *
 * D1 of the Setup rebuild (25 Sep 2026): ARK keeps draft → publish, with
 * versions and rollback — its own feature; Zoho has none. It replaces the
 * draft notice every register tab used to carry, and it is on every Setup page
 * because an edit made under Global Sets is still waiting when you are reading
 * Users. Absent when there is nothing to publish.
 */
export function PublishBanner() {
  const { data: draft } = useDraftStatus()
  const [open, setOpen] = useState(false)

  return (
    <>
      {draft?.has_changes && (
        <div className="bg-muted/40 mb-4 flex items-center gap-2 rounded-md border px-3 py-1.5 text-sm">
          <UploadIcon className="text-muted-foreground size-3.5 shrink-0" />
          <span className="font-medium">{pendingLabel(draft)}</span>
          <span className="text-muted-foreground">· Nobody sees them until you publish.</span>
          <Button size="sm" className="ml-auto" onClick={() => setOpen(true)}>
            Publish
          </Button>
        </div>
      )}
      {/* Mounted outside the banner: a successful publish empties the draft
          and takes the banner away, and the dialog must stay to say so. */}
      <PublishDialog open={open} onOpenChange={setOpen} />
    </>
  )
}

/**
 * Review and publish, from the banner. The Versions page keeps its own fuller
 * review — validation warnings, counts and the history — this is the short one.
 */
function PublishDialog({
  open,
  onOpenChange,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
}) {
  const { data: draft } = useDraftStatus()
  const publish = usePublishMetadata()
  const [note, setNote] = useState('')
  const [published, setPublished] = useState(false)

  useEffect(() => {
    if (!open) return
    setNote('')
    setPublished(false)
    publish.reset()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open])

  const doPublish = async () => {
    try {
      await publish.mutateAsync(note)
      setPublished(true)
    } catch {
      // Shown below from publish.error.
    }
  }

  if (published) {
    return (
      <Dialog open={open} onOpenChange={onOpenChange}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Published — it's live now</DialogTitle>
            <DialogDescription>
              Everyone gets it the next time they open or reload a page.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="ghost" onClick={() => onOpenChange(false)}>
              Keep working
            </Button>
            {/* This page still runs on the register it loaded with. */}
            <Button onClick={() => window.location.reload()}>Reload now</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    )
  }

  const count = draft?.changes.length ?? 0
  const errors = draft?.validation.errors ?? []
  const blocked = !draft?.validation.ok

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-xl">
        <DialogHeader>
          <DialogTitle>
            {count > 0 ? `Publish ${count} change${count === 1 ? '' : 's'}?` : 'Publish the draft?'}
          </DialogTitle>
          <DialogDescription>
            Everyone gets them the next time they open or reload a page.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-3 text-sm">
          {blocked && (
            <Notice
              boxed
              tone="error"
              lead="The draft can't be published yet."
              bullets={[
                ...errors.slice(0, 8),
                errors.length > 8 ? `…and ${errors.length - 8} more, listed under Versions.` : null,
                'Fix these, then publish.',
              ]}
            />
          )}

          {count > 0 && (
            <ul className="text-muted-foreground max-h-60 list-disc space-y-0.5 overflow-y-auto pl-5 text-xs">
              {draft?.changes.map((line) => (
                <li key={line}>{line}</li>
              ))}
            </ul>
          )}

          <Textarea
            rows={2}
            placeholder="What changed, and why. This becomes the version note."
            value={note}
            onChange={(e) => setNote(e.target.value)}
          />

          <ErrorNotice error={publish.error} suffix="Nothing was published." />
        </div>

        <DialogFooter>
          <Button variant="ghost" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button disabled={blocked || publish.isPending} onClick={doPublish}>
            <UploadIcon className="size-4" />
            {publish.isPending
              ? 'Publishing…'
              : count > 0
                ? `Publish ${count} change${count === 1 ? '' : 's'}`
                : 'Publish'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
