import { useEffect, useState } from 'react'
import { ExternalLinkIcon } from 'lucide-react'

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
import { date as fmtDate } from '@/lib/format'
import { MIN_REASON } from '@/lib/pursuitGroups'
import type { ConflictAnswer, PossibleConflictMatch } from '@/lib/registrations'
import { labelForValue } from '@/lib/spec'
import { cn } from '@/lib/utils'

interface Props {
  open: boolean
  matches: PossibleConflictMatch[]
  pending: boolean
  onResolve: (answer: ConflictAnswer) => void
  onClose: () => void
}

type Choice = 'same' | 'different'

/**
 * "A similar project is already registered at this End Client." Asked by the
 * server when a registration is saved beside one
 * (backend/app/registration_matching.py) — the same shape as the Leads
 * duplicate check, so there is one pattern to learn.
 *
 * Two honest answers per match: the same project, which saves the registration
 * AND raises a conflict for the BD Director to adjudicate — the claim is never
 * refused, because its Submitted Date is evidence — or a different project,
 * with the reason kept on both registrations. Closing saves nothing.
 *
 * Same partner twice is not a conflict: that card offers the existing
 * registration instead.
 */
export function PossibleConflictDialog({ open, matches, pending, onResolve, onClose }: Props) {
  const [choices, setChoices] = useState<Record<string, Choice>>({})
  const [step, setStep] = useState<'choose' | 'reason'>('choose')
  const [reason, setReason] = useState('')

  useEffect(() => {
    if (open) {
      setChoices({})
      setStep('choose')
      setReason('')
    }
  }, [open, matches])

  const single = matches.length === 1
  const onlySamePartner = matches.every((m) => m.same_partner)
  const raising = matches.filter((m) => choices[m.registration_id] === 'same').map((m) => m.registration_id)
  const declining = matches.filter((m) => choices[m.registration_id] === 'different').map((m) => m.registration_id)
  const allDecided = matches.every((m) => choices[m.registration_id])

  const choose = (match: PossibleConflictMatch, choice: Choice) => {
    if (single) {
      if (choice === 'same') {
        onResolve({ raise_conflict_with: [match.registration_id] })
      } else {
        setChoices({ [match.registration_id]: 'different' })
        setStep('reason')
      }
      return
    }
    setChoices((prev) => ({ ...prev, [match.registration_id]: choice }))
  }

  const proceed = () => {
    if (declining.length > 0) setStep('reason')
    else onResolve({ raise_conflict_with: raising, not_conflict_with: [] })
  }

  const save = () =>
    onResolve({
      raise_conflict_with: raising,
      not_conflict_with: declining,
      not_conflict_reason: reason.trim(),
    })

  return (
    <Dialog open={open} onOpenChange={(next) => !next && !pending && onClose()}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>
            {onlySamePartner
              ? 'This partner already registered a similar project'
              : 'Is this the same project?'}
          </DialogTitle>
          <DialogDescription>
            {onlySamePartner
              ? 'Same claim: open the existing registration instead. Separate project: tell us why.'
              : "A similar project is already registered at this End Client. Same project: it's saved and a conflict is raised for review. Different project: tell us why."}
          </DialogDescription>
        </DialogHeader>

        {step === 'choose' ? (
          <ul className="divide-y rounded-md border text-sm">
            {matches.map((m) => {
              const choice = choices[m.registration_id]
              return (
                <li
                  key={m.registration_id}
                  className={cn(
                    'space-y-2 px-3 py-3',
                    choice === 'same' && 'bg-amber-500/10',
                    choice === 'different' && 'bg-muted/50'
                  )}
                >
                  <div className="min-w-0">
                    <p className="font-medium">{m.partner_name ?? 'No partner'}</p>
                    <p>{m.project_name}</p>
                    {m.end_client_name && <p className="text-muted-foreground">{m.end_client_name}</p>}
                    <p className="text-muted-foreground text-xs">
                      Submitted {m.submitted_date ? fmtDate(m.submitted_date) : 'date not recorded'} ·{' '}
                      {statusText(m)}
                    </p>
                  </div>

                  {m.same_partner ? (
                    <div className="flex flex-wrap items-center justify-end gap-2">
                      <a
                        className="text-link inline-flex items-center gap-1 underline underline-offset-2"
                        href={`/partners/registrations/${m.registration_id}`}
                        target="_blank"
                        rel="noreferrer"
                      >
                        Open existing registration
                        <ExternalLinkIcon className="size-3.5" />
                      </a>
                      {!single && (
                        <Button
                          type="button"
                          size="sm"
                          variant={choice === 'different' ? 'default' : 'outline'}
                          onClick={() => choose(m, 'different')}
                        >
                          Separate project
                        </Button>
                      )}
                    </div>
                  ) : (
                    <div className="flex flex-wrap justify-end gap-2">
                      {!single && (
                        <Button
                          type="button"
                          size="sm"
                          variant={choice === 'different' ? 'default' : 'outline'}
                          onClick={() => choose(m, 'different')}
                        >
                          Different project
                        </Button>
                      )}
                      <Button
                        type="button"
                        size="sm"
                        variant={choice === 'same' ? 'default' : single ? 'default' : 'outline'}
                        disabled={pending}
                        onClick={() => choose(m, 'same')}
                      >
                        Same project, raise conflict
                      </Button>
                    </div>
                  )}
                </li>
              )
            })}
          </ul>
        ) : (
          <div className="space-y-1 text-sm">
            <label className="text-muted-foreground" htmlFor="not-conflict-reason">
              Why is this a different project? (required)
            </label>
            <Textarea
              id="not-conflict-reason"
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              placeholder="e.g. Phase 2 data-centre tender, separate from the command & control centre."
              rows={3}
            />
          </div>
        )}

        <DialogFooter>
          {step === 'choose' ? (
            <>
              <Button type="button" variant="outline" onClick={onClose} disabled={pending}>
                Cancel
              </Button>
              {single ? (
                <Button
                  type="button"
                  variant="outline"
                  disabled={pending}
                  onClick={() => choose(matches[0], 'different')}
                >
                  {onlySamePartner ? 'Separate project…' : 'Different project…'}
                </Button>
              ) : (
                <Button type="button" disabled={pending || !allDecided} onClick={proceed}>
                  {pending ? 'Saving…' : 'Continue'}
                </Button>
              )}
            </>
          ) : (
            <>
              <Button type="button" variant="outline" onClick={() => setStep('choose')} disabled={pending}>
                Back
              </Button>
              <Button type="button" disabled={pending || reason.trim().length < MIN_REASON} onClick={save}>
                {pending ? 'Saving…' : single ? 'Save as a different project' : 'Save registration'}
              </Button>
            </>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function statusText(match: PossibleConflictMatch): string {
  const label = match.registration_status
    ? labelForValue('partners__registration_status', match.registration_status)
    : 'Submitted'
  return match.exclusivity_expiry_date
    ? `${label}, exclusive until ${fmtDate(match.exclusivity_expiry_date)}`
    : label
}
