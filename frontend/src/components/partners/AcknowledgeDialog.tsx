import { useMutation, useQueryClient } from '@tanstack/react-query'
import { ShieldCheckIcon } from 'lucide-react'

import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { api } from '@/lib/api'
import { ErrorNotice } from '@/components/ui/notice'
import { date as fmtDate } from '@/lib/format'
import {
  ACK_SLA_DAYS,
  EXCLUSIVITY_DAYS,
  ackSlaText,
  acknowledgementPatch,
  proposedWindow,
  registrationState,
} from '@/lib/partners'
import type { Values } from '@/lib/spec/conditions'

interface Props {
  open: boolean
  registration: Values
  /** Display name of the partner, for the sentence about who is protected. */
  partnerName: string
  clientName: string
  onClose: () => void
}

/**
 * Acknowledgement is the moment Astrikos takes on an obligation, so the click
 * is never silent.
 *
 * The modal says in words what confirming commits Astrikos to and what window
 * it opens, because everything it then stamps — acknowledged date, SLA met,
 * both exclusivity dates and the status — is written without further input.
 * Nothing is emailed to the partner; an entry goes to the automation log
 * instead (CLAUDE.md rule 6).
 */
export function AcknowledgeDialog({ open, registration, partnerName, clientName, onClose }: Props) {
  const queryClient = useQueryClient()
  const id = String(registration.id ?? '')
  const state = registrationState(registration)
  const window = proposedWindow()

  const acknowledge = useMutation({
    mutationFn: async () => {
      const patch = acknowledgementPatch(registration)
      return (await api.put<Values>(`/registrations/${id}`, patch)).data
    },
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['record', 'registrations'] }),
        queryClient.invalidateQueries({ queryKey: ['list', 'registrations'] }),
        queryClient.invalidateQueries({ queryKey: ['collection', 'registrations'] }),
      ])
      onClose()
    },
  })

  return (
    <Dialog open={open} onOpenChange={(next) => !next && onClose()}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <ShieldCheckIcon className="size-4" />
            Acknowledge registration
          </DialogTitle>
          <DialogDescription>
            This is a promise to the partner, not just a status change.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-3 text-sm">
          <p>Confirming commits Astrikos to:</p>
          <ul className="list-disc space-y-1 pl-5 text-muted-foreground">
            <li>
              treating <span className="text-foreground font-medium">{partnerName}</span> as the
              exclusive route to{' '}
              <span className="text-foreground font-medium">{clientName}</span> for{' '}
              <span className="text-foreground font-medium">
                {String(registration.project_name ?? 'this project')}
              </span>
              , and this project only — not the whole account;
            </li>
            <li>
              declining to support a competing partner on the same project while the window is
              open, unless a conflict adjudication says otherwise;
            </li>
            <li>
              recording the acknowledgement against the {ACK_SLA_DAYS}-day SLA, whether or not it
              was met.
            </li>
          </ul>

          <div className="rounded-lg border p-3">
            <p className="font-medium">The window this opens</p>
            <dl className="mt-1.5 grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-muted-foreground">
              <dt>Exclusivity start</dt>
              <dd className="text-foreground">{fmtDate(window.start)}</dd>
              <dt>Exclusivity expiry</dt>
              <dd className="text-foreground">
                {fmtDate(window.expiry)}{' '}
                <span className="text-muted-foreground">
                  ({EXCLUSIVITY_DAYS} days)
                </span>
              </dd>
              <dt>Acknowledgement SLA</dt>
              <dd className={state.ackOverdue ? 'text-destructive' : 'text-foreground'}>
                {ackSlaText(state)}
              </dd>
            </dl>
          </div>
        </div>

        {acknowledge.isError && (
          <ErrorNotice error={acknowledge.error} fallback="The registration wasn't acknowledged. Try again." />
        )}

        <DialogFooter>
          <Button type="button" variant="outline" onClick={onClose}>
            Cancel
          </Button>
          <Button
            type="button"
            onClick={() => acknowledge.mutate()}
            disabled={acknowledge.isPending}
          >
            {acknowledge.isPending ? 'Acknowledging…' : 'Confirm acknowledgement'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
