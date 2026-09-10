import { currentUserId } from '@/lib/currentUser'
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
import { probabilityMidpoint, stageKeyOf } from '@/lib/pipeline'
import { displayNameOf, fieldsOf } from '@/lib/spec'
import type { Values } from '@/lib/spec/conditions'

interface Props {
  open: boolean
  leadId: string
  values: Values
  onClose: () => void
}

/** The Opportunity a converted Lead opens at — the stage right after the last
 * one Leads still owns. See spec/module_split.json ranges. */
const OPENING_STAGE = 4

interface ConversionResult {
  opportunityId: string
  copiedFieldCount: number
}

/**
 * Closes the loop the 14-stage-review split opened but left unbuilt (see the
 * comments on OpportunitiesPage and PipelineModuleSpec.stages): a Lead at
 * Stage 3 becomes an Opportunity at Stage 4. Nothing happens until Confirm —
 * same rule as ConvertToDealDialog and AdvanceStageDialog.
 *
 * Identity is never copied. End Client, Segment, Opportunity Name and the
 * rest of spec/module_split.json's read_through fields are resolved from the
 * frozen Lead by useResolvedRecord from here on — carrying them onto the new
 * record would be exactly the two-places-to-drift bug carry-forward-by-
 * reference exists to prevent. Everything else the Lead was holding becomes
 * the Opportunity's starting point, the same rule lib/spec/pipelineSeed.ts
 * uses to migrate a Lead seeded on the far side of the split.
 */
export function ConvertToOpportunityDialog({ open, leadId, values, onClose }: Props) {
  const queryClient = useQueryClient()
  const navigate = useNavigate()
  const [result, setResult] = useState<ConversionResult | null>(null)

  const readThrough = new Set(
    fieldsOf('opportunities')
      .filter((f) => f.value_mode === 'read_through')
      .map((f) => f.api_name)
  )

  const convert = useMutation({
    mutationFn: async (): Promise<ConversionResult> => {
      const now = new Date().toISOString()

      const oppPayload: Values = {}
      for (const [key, val] of Object.entries(values)) {
        if (key === 'id' || readThrough.has(key)) continue
        oppPayload[key] = val
      }
      oppPayload.parent_lead = leadId
      oppPayload.project_stage = stageKeyOf(OPENING_STAGE)
      oppPayload.probability_pct = probabilityMidpoint(OPENING_STAGE)
      oppPayload.lead_status = 'OPEN'
      oppPayload.created_date = now
      oppPayload.created_by = currentUserId()
      oppPayload.modified_date = now
      oppPayload.modified_by = currentUserId()

      const createdOpp = await api.post<Record<string, unknown>>('/opportunities', oppPayload)
      const opportunityId = String(createdOpp.data.id)

      await api.put(`/leads/${leadId}`, {
        lead_status: 'CONVERTED',
        modified_date: now,
        modified_by: currentUserId(),
      })

      const copiedFields = Object.keys(oppPayload).filter(
        (k) => !['parent_lead', 'lead_status', 'project_stage', 'probability_pct'].includes(k)
      )

      await api.post('/conversions', {
        source_module: 'leads',
        source_id: leadId,
        target_module: 'opportunities',
        target_id: opportunityId,
        actor: currentUserId(),
        timestamp: now,
        copied_fields: copiedFields,
        note: `${leadId} moved to Opportunities from its Stage 3 detail page.`,
      })


      return { opportunityId, copiedFieldCount: copiedFields.length }
    },
    onSuccess: async (r) => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['record', 'leads', leadId] }),
        queryClient.invalidateQueries({ queryKey: ['list', 'leads'] }),
        queryClient.invalidateQueries({ queryKey: ['collection', 'leads'] }),
        queryClient.invalidateQueries({ queryKey: ['list', 'opportunities'] }),
        queryClient.invalidateQueries({ queryKey: ['collection', 'opportunities'] }),
      ])
      setResult(r)
    },
  })

  const handleClose = () => {
    if (convert.isPending) return
    setResult(null)
    convert.reset()
    onClose()
  }

  return (
    <Dialog open={open} onOpenChange={(next) => !next && handleClose()}>
      <DialogContent className="max-w-lg max-h-[85vh] overflow-y-auto">
        {!result ? (
          <>
            <DialogHeader>
              <DialogTitle className="flex items-center gap-2">
                <ArrowRightIcon className="size-4" />
                Move {leadId} to Opportunities
              </DialogTitle>
              <DialogDescription>
                Nothing happens until you confirm. This is what will happen:
              </DialogDescription>
            </DialogHeader>

            <ul className="space-y-2 text-sm">
              <Effect>An Opportunity is created (OPP-00001 format), opening at Stage {OPENING_STAGE}.</Effect>
              <Effect>
                End Client, Segment, Opportunity Name and the rest of this lead&apos;s identity are not
                copied — the Opportunity reads them from {leadId} from now on.
              </Effect>
              <Effect>{leadId} becomes read-only and its status becomes Converted.</Effect>
              <Effect>A conversion record is written for the audit trail.</Effect>
            </ul>

            {convert.isError && (
              <p className="text-sm text-destructive">The move failed — nothing was changed.</p>
            )}

            <DialogFooter>
              <Button type="button" variant="outline" onClick={handleClose} disabled={convert.isPending}>
                Cancel
              </Button>
              <Button type="button" onClick={() => convert.mutate()} disabled={convert.isPending}>
                {convert.isPending ? 'Moving…' : 'Confirm move'}
              </Button>
            </DialogFooter>
          </>
        ) : (
          <>
            <DialogHeader>
              <DialogTitle className="flex items-center gap-2">
                <CheckIcon className="size-4 text-emerald-600 dark:text-emerald-400" />
                {leadId} moved to {result.opportunityId}
              </DialogTitle>
              <DialogDescription>Here is exactly what happened.</DialogDescription>
            </DialogHeader>

            <ul className="space-y-2 text-sm">
              <li className="flex items-start gap-2">
                <CheckIcon className="mt-0.5 size-4 shrink-0 text-emerald-600 dark:text-emerald-400" />
                <span>
                  Opportunity {result.opportunityId} created at Stage {OPENING_STAGE} —{' '}
                  {displayNameOf(values)}, {result.copiedFieldCount} field
                  {result.copiedFieldCount === 1 ? '' : 's'} carried over.
                </span>
              </li>
              <li className="flex items-start gap-2">
                <CheckIcon className="mt-0.5 size-4 shrink-0 text-emerald-600 dark:text-emerald-400" />
                <span>{leadId} is now read-only, status Converted.</span>
              </li>
            </ul>

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
                Go to Opportunity
              </Button>
            </DialogFooter>
          </>
        )}
      </DialogContent>
    </Dialog>
  )
}

function Effect({ children }: { children: React.ReactNode }) {
  return (
    <li className="flex items-start gap-2">
      <span className="mt-1.5 size-1.5 shrink-0 rounded-full bg-muted-foreground" />
      <span>{children}</span>
    </li>
  )
}
