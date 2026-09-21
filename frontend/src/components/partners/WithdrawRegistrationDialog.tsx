import { useEffect, useState } from 'react'
import { AlertTriangleIcon, InfoIcon } from 'lucide-react'

import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Textarea } from '@/components/ui/textarea'
import { Bullets, ErrorNotice } from '@/components/ui/notice'
import { stageLabel } from '@/lib/pipeline'
import { MIN_REASON } from '@/lib/pursuitGroups'
import { type PursuitAction, useWithdrawalPreview, useWithdrawRegistration } from '@/lib/registrations'
import { fieldOf, labelForValue } from '@/lib/spec'
import { cn } from '@/lib/utils'

interface Props {
  open: boolean
  registrationId: string
  /** "Gulfstar Systems Integration LLC · Al Waha …" */
  registrationName: string
  onClose: () => void
}

/**
 * Withdraw a deal registration — and say, in the same breath, what happens to
 * the pursuit it protected. The server does all of it in one transaction
 * (backend/app/registration_withdrawal.py); this dialog only asks the question
 * the server's preview says is needed.
 *
 * THE KNOCK-ON. Closing the primary pursuit of a pursuit group while another
 * pursuit is open would be refused, so the dialog asks which pursuit becomes
 * primary before the button unlocks. When no other pursuit is open, it says
 * which registration takes over as primary — so its lead counts once created.
 */
export function WithdrawRegistrationDialog({ open, registrationId, registrationName, onClose }: Props) {
  const { data: preview, isLoading } = useWithdrawalPreview(registrationId, open)
  const withdraw = useWithdrawRegistration(registrationId)
  const [reason, setReason] = useState('')
  const [action, setAction] = useState<PursuitAction | null>(null)
  const [newPrimary, setNewPrimary] = useState<string | null>(null)

  useEffect(() => {
    if (!open) return
    setReason('')
    setAction(null)
    setNewPrimary(null)
    withdraw.reset()
    // Re-seeded when the dialog opens, not on every render.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open])

  const pursuit = preview?.pursuit ?? null
  const openPursuit = pursuit?.is_open ? pursuit : null
  const needsNewPrimary = action === 'close' && Boolean(openPursuit?.is_primary) && (openPursuit?.other_open.length ?? 0) > 0
  const showsHandover =
    Boolean(preview?.primary_handover) && (!openPursuit || (action === 'close' && !needsNewPrimary))

  const canConfirm =
    Boolean(preview?.can_withdraw) &&
    reason.trim().length >= MIN_REASON &&
    (!openPursuit || action !== null) &&
    (!needsNewPrimary || Boolean(newPrimary)) &&
    !withdraw.isPending

  // Every status, reason and field named below is read from the register, and
  // the stage from the stages table — renamed in Administration, renamed here.
  const statusPicklist = fieldOf('leads', 'lead_status')?.picklist
  const onHold = labelForValue(statusPicklist, 'ON_HOLD')
  const closedLost = labelForValue(statusPicklist, 'CLOSED_LOST')
  const partnerWithdrew = labelForValue(fieldOf('leads', 'closed_lost_reason_code')?.picklist, 'PARTNER_WITHDRAWN')
  const partnerField = fieldOf('leads', 'customer_partner_si')?.label ?? 'partner'
  const stageName = stageLabel(openPursuit?.stage_number)
  const stageText = stageName ? ` at ${stageName}` : ''

  const options: { key: PursuitAction; title: string; body: string }[] = openPursuit
    ? [
        {
          key: 'keep',
          title: 'Keep pursuing — direct or with another partner',
          body: `${openPursuit.name ?? 'The pursuit'} stays open${stageText}. The partner is removed from ${partnerField}; set a new one if someone takes over.`,
        },
        {
          key: 'hold',
          title: 'Put on hold',
          body: `Status becomes ${onHold}${stageText}. It still counts in the pipeline total.`,
        },
        {
          key: 'close',
          title: 'Close as lost',
          body: `Status becomes ${closedLost} (${partnerWithdrew}). It leaves the pipeline total.`,
        },
      ]
    : []

  return (
    <Dialog open={open} onOpenChange={(next) => !next && !withdraw.isPending && onClose()}>
      <DialogContent className="max-h-[90vh] max-w-lg overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Withdraw {registrationName}?</DialogTitle>
          <DialogDescription asChild>
            <div>
              <Bullets
                items={["The partner's exclusivity ends.", 'The registration is locked.', "This can't be undone."]}
              />
            </div>
          </DialogDescription>
        </DialogHeader>

        {isLoading || !preview ? (
          <p className="text-muted-foreground text-sm">Loading…</p>
        ) : !preview.can_withdraw ? (
          <p className="flex gap-2 rounded-md border border-amber-500/40 bg-amber-500/10 px-3 py-2 text-sm">
            <AlertTriangleIcon className="mt-0.5 size-4 shrink-0" />
            {preview.blocked_reason}
          </p>
        ) : (
          <div className="space-y-4 text-sm">
            <div className="space-y-1">
              <label className="text-muted-foreground" htmlFor="withdrawal-reason">
                Why did the partner withdraw? (required)
              </label>
              <Textarea
                id="withdrawal-reason"
                value={reason}
                onChange={(e) => setReason(e.target.value)}
                placeholder="e.g. Partner lost its local licence and cannot bid."
                rows={3}
              />
            </div>

            {openPursuit ? (
              <fieldset className="space-y-2">
                <legend className="mb-1 font-medium">
                  What happens to the pursuit {openPursuit.name ? `"${openPursuit.name}"` : ''}?
                </legend>
                {options.map((option) => (
                  <label
                    key={option.key}
                    className={cn(
                      'flex cursor-pointer gap-3 rounded-md border px-3 py-2',
                      action === option.key && 'border-primary bg-primary/5'
                    )}
                  >
                    <input
                      type="radio"
                      name="pursuit-action"
                      className="mt-1"
                      checked={action === option.key}
                      onChange={() => setAction(option.key)}
                    />
                    <span className="min-w-0">
                      <span className="block font-medium">{option.title}</span>
                      <span className="text-muted-foreground block">{option.body}</span>
                    </span>
                  </label>
                ))}
              </fieldset>
            ) : pursuit ? (
              <p className="text-muted-foreground">
                Its pursuit{pursuit.name ? ` "${pursuit.name}"` : ''} is already closed, so nothing changes on it.
              </p>
            ) : (
              <p className="text-muted-foreground">No lead has been created from this registration.</p>
            )}

            {needsNewPrimary && openPursuit && (
              <fieldset className="space-y-2 rounded-md border border-amber-500/40 bg-amber-500/10 p-3">
                <legend className="px-1 font-medium">Choose the new primary</legend>
                <p className="text-muted-foreground">
                  This is the primary pursuit of {openPursuit.group_name ?? 'its pursuit group'}, and another pursuit of
                  the same project is still open. Only the primary counts toward pipeline, so choose which one takes
                  over.
                </p>
                {openPursuit.other_open.map((m) => (
                  <label key={m.record_id} className="flex cursor-pointer items-start gap-3">
                    <input
                      type="radio"
                      name="new-primary"
                      className="mt-1"
                      checked={newPrimary === m.record_id}
                      onChange={() => setNewPrimary(m.record_id)}
                    />
                    <span>
                      <span className="font-medium">{m.name ?? 'Untitled pursuit'}</span>
                      <span className="text-muted-foreground">
                        {m.partner_name ? ` · ${m.partner_name}` : ''}
                        {stageLabel(m.stage_number) ? ` · ${stageLabel(m.stage_number)}` : ''}
                      </span>
                    </span>
                  </label>
                ))}
              </fieldset>
            )}

            {showsHandover && preview.primary_handover && (
              <p className="flex gap-2 rounded-md border border-sky-500/40 bg-sky-500/10 px-3 py-2">
                <InfoIcon className="mt-0.5 size-4 shrink-0" />
                <span>
                  {preview.primary_handover.name} becomes the primary registration of the conflict. Its lead counts
                  toward pipeline — as soon as it is created, if it has not been yet.
                </span>
              </p>
            )}

            {withdraw.isError && <ErrorNotice error={withdraw.error} />}
          </div>
        )}

        <DialogFooter>
          <Button type="button" variant="outline" onClick={onClose} disabled={withdraw.isPending}>
            {preview && !preview.can_withdraw ? 'Close' : 'Cancel'}
          </Button>
          {preview?.can_withdraw && (
            <Button
              type="button"
              variant="destructive"
              disabled={!canConfirm}
              onClick={() =>
                withdraw.mutate(
                  {
                    reason: reason.trim(),
                    pursuit_action: openPursuit ? action : null,
                    new_primary: needsNewPrimary ? newPrimary : null,
                  },
                  { onSuccess: onClose }
                )
              }
            >
              {withdraw.isPending ? 'Withdrawing…' : 'Withdraw registration'}
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
