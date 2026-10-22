import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { ArrowRightIcon, CheckIcon } from 'lucide-react'

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
import { Bullets, ErrorNotice } from '@/components/ui/notice'
import { alreadyConvertedOf, stageKeyOf, stageOf, stagesFor, STAGE_PCT_FIELDS } from '@/lib/pipeline'
import { displayNameOf, fieldOf, fieldsOf, labelForValue } from '@/lib/spec'
import type { Values } from '@/lib/spec/conditions'

interface Props {
  open: boolean
  leadId: string
  values: Values
  /** The stage the Lead stands at — Stage 3, where Convert is offered. */
  currentStage: number
  onClose: () => void
}

/** Where a converted Lead lands: the first stage Opportunities own (4 — RFP / RFI). */
const OPENING_STAGE = stagesFor('opportunities')[0]?.stage ?? 4

interface ConversionResult {
  opportunityId: string
  copiedFieldCount: number
}

/**
 * Convert a Lead at Stage 3 to an Opportunity — the Leads twin of
 * ConvertToDealDialog (v1.2.1, 22 Oct 2026), so the two Convert buttons look
 * and behave the same: one question, one request, then where it went.
 *
 * The request is exactly the one Update Stage sends when a Lead crosses into
 * Opportunities (LeadAdvanceDialog): creating the Opportunity converts the Lead
 * and writes the conversion record in ONE server transaction, and a second
 * press is refused rather than making a second Opportunity (app/conversion.py).
 * The server checks the Lead is complete as it leaves; a missing field comes
 * back as the refusal, shown here, and nothing is converted.
 */
export function ConvertToOpportunityDialog({ open, leadId, values, currentStage, onClose }: Props) {
  const queryClient = useQueryClient()
  const navigate = useNavigate()
  const [result, setResult] = useState<ConversionResult | null>(null)

  const readThrough = new Set(
    fieldsOf('opportunities')
      .filter((field) => field.value_mode === 'read_through')
      .map((field) => field.api_name)
  )

  const convert = useMutation({
    mutationFn: async (): Promise<ConversionResult> => {
      const oppPayload: Values = {}
      for (const [key, value] of Object.entries(values)) {
        // As Update Stage does: read-through identity stays on the Lead, and
        // the Opportunity takes its own stage's Progression / Probability.
        if (key === 'id' || readThrough.has(key) || STAGE_PCT_FIELDS.has(key)) continue
        oppPayload[key] = value
      }
      oppPayload.parent_lead = leadId
      oppPayload.project_stage = stageKeyOf(OPENING_STAGE)
      oppPayload.lead_status = 'OPEN'
      oppPayload.conversion_note = `Moved to Opportunities from Stage ${currentStage}.`

      const created = await api.post<Record<string, unknown>>('/opportunities', oppPayload)
      const copied = Object.keys(oppPayload).filter(
        (key) => !['parent_lead', 'project_stage', 'lead_status', 'conversion_note'].includes(key)
      )
      return { opportunityId: String(created.data.id), copiedFieldCount: copied.length }
    },
    onSuccess: async (conversion) => {
      setResult(conversion)
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['record', 'leads', leadId] }),
        queryClient.invalidateQueries({ queryKey: ['list', 'leads'] }),
        queryClient.invalidateQueries({ queryKey: ['collection', 'leads'] }),
        queryClient.invalidateQueries({ queryKey: ['list', 'opportunities'] }),
        queryClient.invalidateQueries({ queryKey: ['collection', 'opportunities'] }),
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
  const opening = stageOf(OPENING_STAGE)

  return (
    <Dialog open={open} onOpenChange={(next) => !next && handleClose()}>
      <DialogContent className="max-w-lg max-h-[85vh] overflow-y-auto">
        {!result ? (
          <>
            <DialogHeader>
              <DialogTitle className="flex items-center gap-2">
                <ArrowRightIcon className="size-4" />
                Convert {displayNameOf(values)} to an Opportunity?
              </DialogTitle>
              <DialogDescription>When you convert:</DialogDescription>
            </DialogHeader>

            <Bullets
              className="text-sm"
              items={[
                `An Opportunity opens at Stage ${OPENING_STAGE}${opening?.name ? ` – ${opening.name}` : ''}.`,
                'Its details are carried into the Opportunity.',
                `This lead is locked and marked ${labelForValue(fieldOf('leads', 'lead_status')?.picklist, 'CONVERTED')}.`,
                `Fill in the Opportunity's Stage ${OPENING_STAGE} details there.`,
              ]}
            />

            {alreadyConverted ? (
              <p className="text-sm text-destructive">{alreadyConverted.message}</p>
            ) : (
              convert.isError && <ErrorNotice error={convert.error} suffix="Nothing was converted." />
            )}

            <DialogFooter>
              <Button type="button" variant="outline" onClick={handleClose} disabled={convert.isPending}>
                {alreadyConverted ? 'Close' : 'Cancel'}
              </Button>
              {alreadyConverted?.target_id ? (
                <Button
                  type="button"
                  onClick={() => {
                    const opportunityId = alreadyConverted.target_id
                    handleClose()
                    navigate(`/opportunities/${opportunityId}`)
                  }}
                >
                  Open the Opportunity
                </Button>
              ) : (
                !alreadyConverted && (
                  <Button type="button" onClick={() => convert.mutate()} disabled={convert.isPending}>
                    {convert.isPending ? 'Converting…' : 'Convert to Opportunity'}
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
                Opportunity created
              </DialogTitle>
              <DialogDescription className="sr-only">
                {displayNameOf(values)} was converted to an Opportunity.
              </DialogDescription>
            </DialogHeader>

            <Bullets
              className="text-sm"
              items={[
                `${result.copiedFieldCount} ${result.copiedFieldCount === 1 ? 'detail' : 'details'} carried over from ${displayNameOf(values)}.`,
                `${displayNameOf(values)} is now locked.`,
              ]}
            />

            <DialogFooter>
              <Button type="button" variant="outline" onClick={handleClose}>
                Close
              </Button>
              <Button
                type="button"
                onClick={() => {
                  const opportunityId = result.opportunityId
                  handleClose()
                  navigate(`/opportunities/${opportunityId}`)
                }}
              >
                Open the Opportunity
              </Button>
            </DialogFooter>
          </>
        )}
      </DialogContent>
    </Dialog>
  )
}
