import { useEffect, useState } from 'react'

import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Bullets } from '@/components/ui/notice'
import { Textarea } from '@/components/ui/textarea'
import { stageLabel } from '@/lib/pipeline'
import { MIN_REASON, pathOfRecord, type PursuitMatch } from '@/lib/pursuitGroups'

interface Props {
  open: boolean
  matches: PursuitMatch[]
  /**
   * The reason Partners recorded when this lead's registration was declared a
   * different project. Pre-fills the answer; the pursuits listed were NOT part
   * of that decision, which is why the question is still asked.
   */
  suggestedReason?: string
  pending: boolean
  onJoin: (recordId: string) => void
  onDecline: (reason: string) => void
  onClose: () => void
}

/**
 * "This End Client already has an open pursuit." Asked by the server when a
 * lead is saved beside one (backend/app/pursuits.py::guard_possible_duplicate).
 *
 * Two honest answers and no third: it is the same project — join that
 * pursuit's group, and only the primary counts — or it is a different project,
 * and the reason is kept on the lead. Closing the dialog saves nothing.
 */
export function DuplicatePursuitDialog({
  open,
  matches,
  suggestedReason,
  pending,
  onJoin,
  onDecline,
  onClose,
}: Props) {
  const [declining, setDeclining] = useState(false)
  const [reason, setReason] = useState('')

  useEffect(() => {
    if (open) {
      setDeclining(false)
      setReason(suggestedReason ?? '')
    }
  }, [open, suggestedReason])

  return (
    <Dialog open={open} onOpenChange={(next) => !next && !pending && onClose()}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>Is this the same project?</DialogTitle>
          <DialogDescription>This End Client already has an open pursuit.</DialogDescription>
        </DialogHeader>

        <Bullets
          className="text-muted-foreground text-sm"
          items={[
            'Same project: join its group. Only one pursuit counts in the pipeline total.',
            "Different project: tell us why, and it's saved on its own.",
          ]}
        />

        {suggestedReason && (
          <p className="rounded-md border px-3 py-1.5 text-sm text-muted-foreground">
            Partners already marked this registration as a different project. That decision didn't cover the
            pursuits below, so please confirm.
          </p>
        )}

        {!declining ? (
          <ul className="divide-y rounded-md border text-sm">
            {matches.map((m) => (
              <li key={m.pursuit} className="flex items-center justify-between gap-3 px-3 py-2">
                <span className="min-w-0">
                  <a
                    className="font-medium underline underline-offset-2"
                    href={pathOfRecord(m.record_id)}
                    target="_blank"
                    rel="noreferrer"
                  >
                    {m.name ?? 'Untitled pursuit'}
                  </a>
                  <span className="text-muted-foreground">
                    {m.partner_name ? ` · ${m.partner_name}` : ''}
                    {stageLabel(m.stage_number) ? ` · ${stageLabel(m.stage_number)}` : ''}
                    {m.group_id
                      ? ` · in ${m.group_name ?? 'a pursuit group'}${m.is_primary ? ' (primary)' : ''}`
                      : ' · not in a group yet'}
                  </span>
                </span>
                <Button type="button" size="sm" disabled={pending} onClick={() => onJoin(m.record_id)}>
                  Join this group
                </Button>
              </li>
            ))}
          </ul>
        ) : (
          <div className="space-y-1 text-sm">
            <label className="text-muted-foreground">Why is this a different project? (required)</label>
            <Textarea
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              placeholder="e.g. Separate datacentre tender, not the smart city programme."
              rows={3}
            />
            {suggestedReason && (
              <p className="text-xs text-muted-foreground">
                Pre-filled with the reason given in Partners — edit it if it does not also apply to the pursuits
                above.
              </p>
            )}
          </div>
        )}

        <DialogFooter>
          <Button type="button" variant="outline" onClick={onClose} disabled={pending}>
            Cancel
          </Button>
          {!declining ? (
            <Button type="button" variant="outline" onClick={() => setDeclining(true)} disabled={pending}>
              It's a different project…
            </Button>
          ) : (
            <Button
              type="button"
              disabled={pending || reason.trim().length < MIN_REASON}
              onClick={() => onDecline(reason.trim())}
            >
              {pending ? 'Saving…' : 'Save as a different project'}
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
