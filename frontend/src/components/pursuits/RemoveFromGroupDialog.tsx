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
import { Bullets, ErrorNotice } from '@/components/ui/notice'
import { Textarea } from '@/components/ui/textarea'
import { stageLabel } from '@/lib/pipeline'
import { MIN_REASON, type PursuitGroup, type PursuitMember, useRemoveFromGroup } from '@/lib/pursuitGroups'

interface Props {
  open: boolean
  group: PursuitGroup
  member: PursuitMember
  onClose: () => void
}

/**
 * Take one pursuit out of its group — "joined by mistake", or "a different
 * project after all". Its value goes straight back into the pipeline, which is
 * why a reason is required. Removing the primary while two or more pursuits
 * remain asks which becomes primary; a group left with one pursuit dissolves.
 */
export function RemoveFromGroupDialog({ open, group, member, onClose }: Props) {
  const remove = useRemoveFromGroup(group.group_id)
  const [reason, setReason] = useState('')
  const [newPrimary, setNewPrimary] = useState('')

  const remaining = group.members.filter((m) => m.pursuit !== member.pursuit)
  const needsNewPrimary = member.is_primary && remaining.length > 1
  const dissolves = remaining.length <= 1

  useEffect(() => {
    if (!open) return
    setReason('')
    setNewPrimary(remaining.find((m) => m.is_open)?.pursuit ?? '')
    remove.reset()
    // Re-seeded when the dialog opens for a pursuit, not on every render.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, member.pursuit])

  const chosen = remaining.find((m) => m.pursuit === newPrimary)
  const canSave = reason.trim().length >= MIN_REASON && (!needsNewPrimary || Boolean(chosen)) && !remove.isPending

  return (
    <Dialog open={open} onOpenChange={(next) => !next && !remove.isPending && onClose()}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>Remove {member.name ?? 'this pursuit'} from the group?</DialogTitle>
          <DialogDescription>{group.name ?? 'Pursuit group'}</DialogDescription>
        </DialogHeader>

        <div className="space-y-3 text-sm">
          <Bullets
            className="text-muted-foreground"
            items={[
              'It becomes a pursuit on its own.',
              'Its value is added back to the pipeline total.',
              dissolves && 'Only one pursuit would be left, so the group closes.',
            ]}
          />
          {needsNewPrimary && (
            <div className="space-y-1">
              <label className="text-muted-foreground">This pursuit counts now. Which one should count instead?</label>
              <Select value={newPrimary || undefined} onValueChange={setNewPrimary}>
                <SelectTrigger className="w-full">
                  <SelectValue placeholder="Choose a pursuit" />
                </SelectTrigger>
                <SelectContent>
                  {remaining.map((m) => (
                    <SelectItem key={m.pursuit} value={m.pursuit}>
                      {m.name ?? 'Untitled pursuit'} · {m.partner_name ?? '—'} · {stageLabel(m.stage_number) || '—'}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          )}
          <div className="space-y-1">
            <label className="text-muted-foreground">Reason (required)</label>
            <Textarea
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              placeholder="e.g. Joined by mistake — this SI is bidding a different package."
              rows={3}
            />
          </div>
          {remove.isError && <ErrorNotice error={remove.error} />}
        </div>

        <DialogFooter>
          <Button type="button" variant="outline" onClick={onClose} disabled={remove.isPending}>
            Cancel
          </Button>
          <Button
            type="button"
            variant="destructive"
            disabled={!canSave}
            onClick={() =>
              remove.mutate(
                {
                  recordId: member.record_id,
                  reason: reason.trim(),
                  newPrimary: needsNewPrimary ? chosen?.record_id : undefined,
                },
                { onSuccess: onClose }
              )
            }
          >
            {remove.isPending ? 'Removing…' : 'Remove from group'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
