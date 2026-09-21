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
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Bullets, ErrorNotice, Notice } from '@/components/ui/notice'
import { Textarea } from '@/components/ui/textarea'
import { stageLabel } from '@/lib/pipeline'
import { localAmount } from '@/lib/revenue'
import { MIN_REASON, useChangePrimary, usePursuitGroup } from '@/lib/pursuitGroups'

interface Props {
  open: boolean
  groupId: string
  /** Pre-selected pursuit — any record id of its chain. */
  initialRecordId?: string
  /** Why the dialog was opened, when a refused save or conversion opened it. */
  context?: { lead: string; bullets?: string[] }
  onClose: () => void
  /** After the primary has actually moved. */
  onChanged?: () => void
}

/**
 * Change which pursuit of a group counts toward pipeline.
 *
 * Only the group row changes — never a converted, read-only record — so this
 * works whatever stage or module either pursuit has reached. The reason is
 * required and lands on every affected record's History.
 *
 * Open to any signed-in user today (decided 13 Sep 2026); Admin-only once
 * role-based permissions are built.
 */
export function ChangePrimaryDialog({ open, groupId, initialRecordId, context, onClose, onChanged }: Props) {
  const { data: group } = usePursuitGroup(open ? groupId : null)
  const change = useChangePrimary(groupId)
  const [target, setTarget] = useState<string>('')
  const [reason, setReason] = useState('')

  const candidates = (group?.members ?? []).filter((m) => !m.is_primary)
  const current = group?.members.find((m) => m.is_primary)

  useEffect(() => {
    if (!open) return
    setReason('')
    change.reset()
    const preset = candidates.find((m) => m.is_open && m.chain.some((c) => c.record_id === initialRecordId))
    setTarget(preset?.pursuit ?? candidates.find((m) => m.is_open)?.pursuit ?? '')
    // Re-seeded when the dialog OPENS and when the group first arrives — never
    // on a later refetch. It used to depend on group.modified_date, and the
    // save's own invalidate changes exactly that: the reset below tore down the
    // in-flight mutation before its onSuccess ran, so the dialog sat open after
    // a successful save and, worse, the retry that PursuitSaveResolver and
    // SecondaryCannotWin hang on onChanged never fired at all.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, group?.group_id, initialRecordId])

  const chosen = candidates.find((m) => m.pursuit === target)
  const canSave = Boolean(chosen) && reason.trim().length >= MIN_REASON && !change.isPending

  return (
    <Dialog open={open} onOpenChange={(next) => !next && !change.isPending && onClose()}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>Which pursuit should count?</DialogTitle>
          <DialogDescription>{group?.name ?? 'Pursuit group'}</DialogDescription>
        </DialogHeader>

        <div className="space-y-3 text-sm">
          {context && <Notice tone="warning" boxed lead={context.lead} bullets={context.bullets} />}
          <Bullets
            className="text-muted-foreground"
            items={[
              'Only the primary pursuit counts in the pipeline total.',
              'The others stay visible.',
              'Their partners keep their credit.',
            ]}
          />
          <p className="text-muted-foreground">
            Counting now:{' '}
            <span className="text-foreground font-medium">
              {current
                ? `${current.name ?? 'Untitled pursuit'} · ${current.partner_name ?? '—'} · ${localAmount(current.revenue)}`
                : 'none yet'}
            </span>
          </p>

          <div className="space-y-1">
            <label className="text-muted-foreground">Make this one primary</label>
            {/* The popup is capped at the width of the box that opens it, and
                each option reads over two lines. One line of name · partner ·
                stage · value ran past the right edge of the dialog and off the
                panel entirely. */}
            <Select value={target || undefined} onValueChange={setTarget}>
              <SelectTrigger className="w-full">
                <SelectValue placeholder="Choose a pursuit">
                  {chosen ? (chosen.name ?? 'Untitled pursuit') : undefined}
                </SelectValue>
              </SelectTrigger>
              <SelectContent className="max-w-(--radix-select-trigger-width)">
                {candidates.map((m) => (
                  <SelectItem key={m.pursuit} value={m.pursuit} disabled={!m.is_open}>
                    <span className="flex min-w-0 flex-col">
                      <span className="truncate">{m.name ?? 'Untitled pursuit'}</span>
                      <span className="text-muted-foreground truncate text-xs">
                        {m.partner_name ?? '—'} · {stageLabel(m.stage_number) || '—'} · {localAmount(m.revenue)}
                        {m.is_open ? '' : ' (closed)'}
                      </span>
                    </span>
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-1">
            <label className="text-muted-foreground">Reason (required)</label>
            <Textarea
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              placeholder="e.g. The other partner's pursuit is further ahead with the client."
              rows={3}
            />
          </div>

          {change.isError && <ErrorNotice error={change.error} />}
        </div>

        <DialogFooter>
          <Button type="button" variant="outline" onClick={onClose} disabled={change.isPending}>
            Cancel
          </Button>
          <Button
            type="button"
            disabled={!canSave}
            // Awaited rather than given an onSuccess callback: the callback
            // belongs to the mutation observer and is dropped if anything
            // resets it first, which is how a saved change left the dialog
            // open. This closure cannot be taken away — the server confirmed,
            // so the dialog closes and the caller's retry runs.
            onClick={async () => {
              if (!chosen) return
              try {
                await change.mutateAsync({ recordId: chosen.record_id, reason: reason.trim() })
              } catch {
                return // change.isError renders the message above.
              }
              onChanged?.()
              onClose()
            }}
          >
            {change.isPending ? 'Saving…' : 'Make primary'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
