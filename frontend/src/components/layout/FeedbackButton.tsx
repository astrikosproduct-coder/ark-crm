import { useEffect, useState } from 'react'
import { useLocation } from 'react-router-dom'
import { CheckIcon, MessageSquarePlusIcon } from 'lucide-react'

import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { ErrorNotice } from '@/components/ui/notice'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Textarea } from '@/components/ui/textarea'
import { recordRefOf, useSendFeedback } from '@/lib/feedback'
import { optionsFor } from '@/lib/spec'

const CATEGORY_PICKLIST = 'feedback__category'
const MAX_LENGTH = 5000

/**
 * The top bar's Feedback button and the dialog it opens (UX roadmap item 2).
 *
 * HAND-BUILT, like UserDialog — a documented exception to CLAUDE.md hard rule 3.
 * Feedback is not a module in the field register and is not meant to become
 * one: it is two inputs about the product, not a business record. The category
 * dropdown still comes from a picklist (hard rule 4), `feedback__category`.
 *
 * The page the person is on is attached automatically, so nobody has to explain
 * where they were. Only the ARK developers can read what is sent.
 */
export function FeedbackButton() {
  const { pathname } = useLocation()
  const [open, setOpen] = useState(false)
  const [category, setCategory] = useState('')
  const [message, setMessage] = useState('')
  const send = useSendFeedback()
  const categories = optionsFor(CATEGORY_PICKLIST)

  useEffect(() => {
    if (!open) return
    setCategory('')
    setMessage('')
    send.reset()
    // Reset when the dialog opens, not on every render.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open])

  const canSend = Boolean(category) && message.trim().length > 0 && !send.isPending

  return (
    <>
      <button
        type="button"
        aria-label="Send feedback"
        title="Send feedback"
        onClick={() => setOpen(true)}
        className="text-muted-foreground hover:bg-accent hover:text-accent-foreground flex size-9 items-center justify-center rounded-md transition-colors"
      >
        <MessageSquarePlusIcon className="size-4.5" />
      </button>

      <Dialog open={open} onOpenChange={(next) => !send.isPending && setOpen(next)}>
        <DialogContent className="max-w-md">
          {send.isSuccess ? (
            <>
              <DialogHeader>
                <DialogTitle className="flex items-center gap-2">
                  <CheckIcon className="size-4 text-emerald-600 dark:text-emerald-400" />
                  Thanks — feedback sent
                </DialogTitle>
                <DialogDescription>The developers will read it.</DialogDescription>
              </DialogHeader>
              <DialogFooter>
                <Button type="button" onClick={() => setOpen(false)}>
                  Close
                </Button>
              </DialogFooter>
            </>
          ) : (
            <form
              className="grid gap-3"
              onSubmit={(e) => {
                e.preventDefault()
                if (!canSend) return
                send.mutate({ category, message: message.trim(), page_path: pathname, record_ref: recordRefOf(pathname) })
              }}
            >
              <DialogHeader>
                <DialogTitle>Send feedback</DialogTitle>
                <DialogDescription>Only the ARK developers read this.</DialogDescription>
              </DialogHeader>

              <div className="grid gap-1 text-sm">
                <label htmlFor="feedback-category" className="text-muted-foreground">
                  What is it about?
                </label>
                <Select value={category || undefined} onValueChange={setCategory}>
                  <SelectTrigger id="feedback-category" className="w-full">
                    <SelectValue placeholder="Choose one" />
                  </SelectTrigger>
                  <SelectContent>
                    {categories.map((option) => (
                      <SelectItem key={option.key} value={option.key}>
                        {option.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              <div className="grid gap-1 text-sm">
                <label htmlFor="feedback-message" className="text-muted-foreground">
                  Your feedback
                </label>
                <Textarea
                  id="feedback-message"
                  rows={5}
                  maxLength={MAX_LENGTH}
                  value={message}
                  onChange={(e) => setMessage(e.target.value)}
                  placeholder="What happened, or what would help?"
                />
                <p className="text-muted-foreground text-xs">Sent with the page you are on.</p>
              </div>

              {send.isError && <ErrorNotice error={send.error} />}

              <DialogFooter>
                <Button type="button" variant="outline" onClick={() => setOpen(false)} disabled={send.isPending}>
                  Cancel
                </Button>
                <Button type="submit" disabled={!canSend}>
                  {send.isPending ? 'Sending…' : 'Send feedback'}
                </Button>
              </DialogFooter>
            </form>
          )}
        </DialogContent>
      </Dialog>
    </>
  )
}
