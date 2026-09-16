import { currentUserId } from '@/lib/currentUser'
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { ArrowRightIcon, CheckIcon } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { SecondaryCannotWin } from '@/components/pursuits/SecondaryCannotWin'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { api } from '@/lib/api'
import { errorMessage } from '@/lib/admin'
import { pursuitErrorOf } from '@/lib/pursuitGroups'
import { alreadyConvertedOf, dealStageKeyOf, stageOf, STAGE_PCT_FIELDS } from '@/lib/pipeline'
import { displayNameOf, fieldOf, fieldsOf, labelForValue } from '@/lib/spec'
import type { Values } from '@/lib/spec/conditions'

interface Props {
  open: boolean
  opportunityId: string
  values: Values
  onClose: () => void
}

/**
 * Where a converted Opportunity lands: Stage 7 — Close, the first stage Deals
 * own (spec/module_split.json ranges), and the stage whose two sections —
 * STAGE 7 — COMMERCIAL TERMS (AS WON), carried in and locked, and STAGE 7 —
 * CLOSE, the closing work — exist precisely to be filled at this moment.
 *
 * It used to be 8, which was wrong in four ways at once: G3 Commercial is
 * anchored to ENTERING Stage 7 so that no skip can bypass it, and it never
 * fired; Stage 7's entry criteria never ran; Stage 7's own fields (PO number,
 * contract signed date, payment schedule confirmed, ERP reference, PSP,
 * handover pack, kickoff) were never demanded while the rail drew that stage
 * as completed; and a Deal booked this morning opened at Stage 8's 100/100,
 * reporting delivery complete before a single milestone. 7 → 8 is now an
 * ordinary Update Stage move with its own checks.
 *
 * A paid-pilot Deal has always opened here (app/progression.py PILOT_DEAL_STAGE).
 */
const OPENING_STAGE = 7

interface ConversionResult {
  dealId: string
  copiedFieldCount: number
}

export function ConvertToDealDialog({ open, opportunityId, values, onClose }: Props) {
  const queryClient = useQueryClient()
  const navigate = useNavigate()
  const [result, setResult] = useState<ConversionResult | null>(null)

  const readThrough = new Set(
    fieldsOf('deals')
      .filter((field) => field.value_mode === 'read_through')
      .map((field) => field.api_name)
  )

  const convert = useMutation({
    mutationFn: async (): Promise<ConversionResult> => {
      const now = new Date().toISOString()
      const tcv = typeof values.total_value_tcv === 'number' ? values.total_value_tcv : 0
      const dealPayload: Values = {}

      for (const [key, value] of Object.entries(values)) {
        // STAGE_PCT_FIELDS, like readThrough, is excluded: the Deal takes its
        // OWN stage's Progression %/Probability % on create. Sending Stage 6's
        // 85/70 to a Deal opening at Stage 8 reads as an override of Stage 8's
        // 100/100, and the server refuses the whole conversion for want of an
        // Override Justification nobody meant to give (app/progression.py).
        if (key === 'id' || readThrough.has(key) || STAGE_PCT_FIELDS.has(key)) continue
        dealPayload[key] = value
      }

      dealPayload.deal_name = values.opportunity_name ?? opportunityId
      dealPayload.parent_opportunity = opportunityId
      dealPayload.deal_stage = dealStageKeyOf(OPENING_STAGE)
      dealPayload.contract_value = tcv
      dealPayload.delivery_pm = currentUserId()
      dealPayload.order_booked = true
      dealPayload.booking_date = now.slice(0, 10)
      dealPayload.conversion_note = `${opportunityId} moved to Deals from its Stage 6 detail page.`

      // ONE request. Creating the Deal converts the Opportunity and writes the
      // conversion record in the same server transaction, and a second press
      // is refused rather than booking a second Deal — see
      // backend/app/conversion.py.
      const createdDeal = await api.post<Record<string, unknown>>('/deals', dealPayload)

      const copiedFields = Object.keys(dealPayload).filter(
        (key) => !['parent_opportunity', 'deal_stage', 'conversion_note'].includes(key)
      )
      return { dealId: String(createdDeal.data.id), copiedFieldCount: copiedFields.length }
    },
    onSuccess: async (conversion) => {
      setResult(conversion)
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['record', 'opportunities', opportunityId] }),
        queryClient.invalidateQueries({ queryKey: ['list', 'opportunities'] }),
        queryClient.invalidateQueries({ queryKey: ['collection', 'opportunities'] }),
        queryClient.invalidateQueries({ queryKey: ['list', 'deals'] }),
        queryClient.invalidateQueries({ queryKey: ['collection', 'deals'] }),
      ])
    },
  })

  const handleClose = () => {
    if (convert.isPending) return
    setResult(null)
    convert.reset()
    onClose()
  }

  const alreadyConverted = alreadyConvertedOf(convert.error)

  return (
    <Dialog open={open} onOpenChange={(next) => !next && handleClose()}>
      <DialogContent className="max-w-lg max-h-[85vh] overflow-y-auto">
        {!result ? (
          <>
            <DialogHeader>
              <DialogTitle className="flex items-center gap-2">
                <ArrowRightIcon className="size-4" />
                Convert {displayNameOf(values)} to a Deal
              </DialogTitle>
              <DialogDescription>
                Nothing happens until you confirm. This is what will happen:
              </DialogDescription>
            </DialogHeader>

            <ul className="space-y-2 text-sm">
              <li>
                A Deal is created at Stage {OPENING_STAGE}
                {stageOf(OPENING_STAGE)?.name ? ` — ${stageOf(OPENING_STAGE)?.name}` : ''}, taking that
                stage&apos;s Progression % and Probability %. Stage 8 is a move you make once delivery has
                actually started.
              </li>
              <li>This opportunity becomes read-only and its status becomes {labelForValue(fieldOf('leads', 'lead_status')?.picklist, 'CONVERTED')}.</li>
              <li>The Opportunity fields are carried into the Deal and the conversion is audited.</li>
            </ul>

            {alreadyConverted ? (
              <p className="text-sm text-destructive">{alreadyConverted.message}</p>
            ) : (
              convert.isError &&
              !pursuitErrorOf(convert.error) && (
                <p className="text-sm text-destructive">
                  {errorMessage(convert.error, { fallback: 'The conversion failed.' })} Nothing was changed.
                </p>
              )
            )}
            {convert.isError && (
              <SecondaryCannotWin error={convert.error} recordId={opportunityId} retry={() => convert.mutate()} />
            )}

            <DialogFooter>
              <Button type="button" variant="outline" onClick={handleClose} disabled={convert.isPending}>
                {alreadyConverted ? 'Close' : 'Cancel'}
              </Button>
              {alreadyConverted?.target_id ? (
                <Button
                  type="button"
                  onClick={() => {
                    const dealId = alreadyConverted.target_id
                    handleClose()
                    navigate(`/deals/${dealId}`)
                  }}
                >
                  Go to {alreadyConverted.target_id}
                </Button>
              ) : (
                !alreadyConverted && (
                  <Button type="button" onClick={() => convert.mutate()} disabled={convert.isPending}>
                    {convert.isPending ? 'Converting…' : 'Confirm conversion'}
                  </Button>
                )
              )}
            </DialogFooter>
          </>
        ) : (
          <>
            <DialogHeader>
              <DialogTitle className="flex items-center gap-2">
                <CheckIcon className="size-4 text-emerald-600 dark:text-emerald-400" />
                {displayNameOf(values)} converted to a Deal
              </DialogTitle>
              <DialogDescription>Here is exactly what happened.</DialogDescription>
            </DialogHeader>

            <p className="flex items-start gap-2 text-sm">
              <CheckIcon className="mt-0.5 size-4 shrink-0 text-emerald-600 dark:text-emerald-400" />
              <span>
                A Deal was created from {displayNameOf(values)} with {result.copiedFieldCount}{' '}
                carried field{result.copiedFieldCount === 1 ? '' : 's'}.
              </span>
            </p>
            <p className="flex items-start gap-2 text-sm">
              <CheckIcon className="mt-0.5 size-4 shrink-0 text-emerald-600 dark:text-emerald-400" />
              <span>{displayNameOf(values)} is now read-only, status {labelForValue(fieldOf('leads', 'lead_status')?.picklist, 'CONVERTED')}.</span>
            </p>

            <DialogFooter>
              <Button type="button" variant="outline" onClick={handleClose}>
                Close
              </Button>
              <Button
                type="button"
                onClick={() => {
                  const dealId = result.dealId
                  handleClose()
                  navigate(`/deals/${dealId}`)
                }}
              >
                Go to {result.dealId}
              </Button>
            </DialogFooter>
          </>
        )}
      </DialogContent>
    </Dialog>
  )
}
