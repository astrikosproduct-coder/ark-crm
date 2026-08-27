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
import { logAutomation } from '@/lib/automation'
import { CURRENT_USER_ID, dealStageKeyOf } from '@/lib/pipeline'
import { displayNameOf, fieldsOf } from '@/lib/spec'
import type { Values } from '@/lib/spec/conditions'

interface Props {
  open: boolean
  opportunityId: string
  values: Values
  onClose: () => void
}

const OPENING_STAGE = 8

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
      .filter((field) => field.carry === 'read_through')
      .map((field) => field.api_name)
  )

  const convert = useMutation({
    mutationFn: async (): Promise<ConversionResult> => {
      const now = new Date().toISOString()
      const tcv = typeof values.total_value_tcv === 'number' ? values.total_value_tcv : 0
      const dealPayload: Values = {}

      for (const [key, value] of Object.entries(values)) {
        if (key === 'id' || readThrough.has(key)) continue
        dealPayload[key] = value
      }

      dealPayload.deal_name = values.opportunity_name ?? opportunityId
      dealPayload.parent_opportunity = opportunityId
      dealPayload.deal_stage = dealStageKeyOf(OPENING_STAGE)
      dealPayload.contract_value = tcv
      dealPayload.delivery_pm = CURRENT_USER_ID
      dealPayload.order_booked = true
      dealPayload.booking_date = now.slice(0, 10)
      dealPayload.created_by_date = now
      dealPayload.modified_by_date = now

      const createdDeal = await api.post<Record<string, unknown>>('/deals', dealPayload)
      const dealId = String(createdDeal.data.id)

      await api.put(`/opportunities/${opportunityId}`, {
        lead_status: 'CONVERTED',
        modified_date: now,
        modified_by: CURRENT_USER_ID,
      })

      const copiedFields = Object.keys(dealPayload).filter(
        (key) => !['parent_opportunity', 'deal_stage'].includes(key)
      )
      await api.post('/conversions', {
        source_module: 'opportunities',
        source_id: opportunityId,
        target_module: 'deals',
        target_id: dealId,
        actor: CURRENT_USER_ID,
        timestamp: now,
        copied_fields: copiedFields,
        note: `${opportunityId} moved to Deals from its Stage 6 detail page.`,
      })

      void logAutomation({
        type: 'record_update',
        target: dealId,
        module: 'deals',
        detail: `${dealId} created by moving ${opportunityId} to the Deals module`,
      })
      void logAutomation({
        type: 'record_update',
        target: opportunityId,
        module: 'opportunities',
        detail: `${opportunityId} moved to ${dealId} — now read-only`,
      })

      return { dealId, copiedFieldCount: copiedFields.length }
    },
    onSuccess: async (conversion) => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['record', 'opportunities', opportunityId] }),
        queryClient.invalidateQueries({ queryKey: ['list', 'opportunities'] }),
        queryClient.invalidateQueries({ queryKey: ['collection', 'opportunities'] }),
        queryClient.invalidateQueries({ queryKey: ['list', 'deals'] }),
        queryClient.invalidateQueries({ queryKey: ['collection', 'deals'] }),
      ])
      setResult(conversion)
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
                Convert {opportunityId} to a Deal
              </DialogTitle>
              <DialogDescription>
                Nothing happens until you confirm. This is what will happen:
              </DialogDescription>
            </DialogHeader>

            <ul className="space-y-2 text-sm">
              <li>A Deal is created at Stage {OPENING_STAGE}.</li>
              <li>{opportunityId} becomes read-only and its status becomes Converted.</li>
              <li>The Opportunity fields are carried into the Deal and the conversion is audited.</li>
            </ul>

            {convert.isError && (
              <p className="text-sm text-destructive">The conversion failed — nothing was changed.</p>
            )}

            <DialogFooter>
              <Button type="button" variant="outline" onClick={handleClose} disabled={convert.isPending}>
                Cancel
              </Button>
              <Button type="button" onClick={() => convert.mutate()} disabled={convert.isPending}>
                {convert.isPending ? 'Converting…' : 'Confirm conversion'}
              </Button>
            </DialogFooter>
          </>
        ) : (
          <>
            <DialogHeader>
              <DialogTitle className="flex items-center gap-2">
                <CheckIcon className="size-4 text-emerald-600 dark:text-emerald-400" />
                {opportunityId} converted to {result.dealId}
              </DialogTitle>
              <DialogDescription>Here is exactly what happened.</DialogDescription>
            </DialogHeader>

            <p className="flex items-start gap-2 text-sm">
              <CheckIcon className="mt-0.5 size-4 shrink-0 text-emerald-600 dark:text-emerald-400" />
              <span>
                Deal {result.dealId} created from {displayNameOf(values)} with {result.copiedFieldCount}{' '}
                carried field{result.copiedFieldCount === 1 ? '' : 's'}.
              </span>
            </p>
            <p className="flex items-start gap-2 text-sm">
              <CheckIcon className="mt-0.5 size-4 shrink-0 text-emerald-600 dark:text-emerald-400" />
              <span>{opportunityId} is now read-only, status Converted.</span>
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
