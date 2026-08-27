import { useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { ArrowRightIcon } from 'lucide-react'

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
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { ReadinessPanel } from '@/components/leads/ReadinessPanel'
import { api } from '@/lib/api'
import { logAutomation } from '@/lib/automation'
import { CURRENT_USER_ID, probabilityMidpoint, stageKeyOf, stagesFor, type Transition } from '@/lib/pipeline'
import { fieldsOf } from '@/lib/spec'
import type { Values } from '@/lib/spec/conditions'

interface Props {
  open: boolean
  leadId: string
  values: Values
  currentStage: number
  onClose: () => void
  /** Fired after a same-module move — selects the new stage on this same page. */
  onAdvancedWithinLeads: (toStage: number) => void
}

const LEADS_STAGES = stagesFor('leads')
const OPPORTUNITY_STAGES = stagesFor('opportunities')
const LAST_LEAD_STAGE = LEADS_STAGES[LEADS_STAGES.length - 1]?.stage ?? 3

/**
 * The one place a Lead's stage — or its whole pipeline module — changes.
 *
 * Replaces AdvanceStageDialog for Leads specifically (Opportunities and
 * Deals still use it unmodified) and folds in what ConvertToOpportunityDialog
 * used to do on its own, because the two are the same decision from the
 * user's side: "move to stage N" and "move to Opportunities" are one Move to
 * dropdown, not two buttons — a Lead at Stage 0 can jump straight to
 * Opportunities' RFP / RFI without ever visiting Stages 1-3 first.
 *
 * Deal stages (7-9) are deliberately NOT offered here. A Deal reads its own
 * identity through parent_opportunity, not through a Lead directly — jumping
 * a Lead straight to a Deal stage would mean synthesising an Opportunity it
 * never really had, which is a different, larger feature than "let this
 * pursuit skip ahead" and isn't built. See spec/extensions.json open_questions.
 */
export function LeadAdvanceDialog({
  open,
  leadId,
  values,
  currentStage,
  onClose,
  onAdvancedWithinLeads,
}: Props) {
  const queryClient = useQueryClient()
  const navigate = useNavigate()
  const [reason, setReason] = useState('')

  const options = useMemo(
    () => [
      ...LEADS_STAGES.filter((s) => s.stage !== currentStage).map((s) => ({ ...s, module: 'leads' as const })),
      ...OPPORTUNITY_STAGES.map((s) => ({ ...s, module: 'opportunities' as const })),
    ],
    [currentStage]
  )

  const [target, setTarget] = useState(() => Math.min(currentStage + 1, OPPORTUNITY_STAGES[OPPORTUNITY_STAGES.length - 1]?.stage ?? currentStage))

  const targetOption = options.find((o) => o.stage === target)
  const crossesToOpportunities = target > LAST_LEAD_STAGE

  const isSkip = target > currentStage + 1
  const isReversal = target < currentStage
  const reasonRequired = isSkip || isReversal
  const canConfirm = target !== currentStage && (!reasonRequired || reason.trim().length > 0)

  const readThrough = useMemo(
    () => new Set(fieldsOf('opportunities').filter((f) => f.carry === 'read_through').map((f) => f.api_name)),
    []
  )

  const advanceWithinLeads = useMutation({
    mutationFn: async () => {
      const now = new Date().toISOString()
      const patch: Values = { modified_date: now, modified_by: CURRENT_USER_ID }
      patch.project_stage = stageKeyOf(target) ?? target
      patch.probability_pct = probabilityMidpoint(target) ?? values.probability_pct ?? null
      if (isSkip) patch.stage_skip_reason = reason.trim()
      if (isReversal) patch.stage_reversal_reason = reason.trim()

      await api.put(`/leads/${leadId}`, patch)

      const transition: Transition = {
        module: 'leads',
        record_id: leadId,
        from: currentStage,
        to: target,
        reason: reasonRequired ? reason.trim() : null,
        is_skip: isSkip,
        is_reversal: isReversal,
        actor: CURRENT_USER_ID,
        timestamp: now,
      }
      await api.post('/transitions', transition)
    },
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['record', 'leads', leadId] }),
        queryClient.invalidateQueries({ queryKey: ['list', 'leads'] }),
        queryClient.invalidateQueries({ queryKey: ['collection', 'leads'] }),
        queryClient.invalidateQueries({ queryKey: ['list', 'transitions'] }),
      ])
      void logAutomation({
        type: 'record_update',
        target: leadId,
        module: 'leads',
        detail: `${leadId} advanced Stage ${currentStage} → Stage ${target}${
          reason.trim() ? ` — ${reason.trim()}` : ''
        }`,
      })
      onAdvancedWithinLeads(target)
      handleClose()
    },
  })

  const moveToOpportunity = useMutation({
    mutationFn: async () => {
      const now = new Date().toISOString()

      const oppPayload: Values = {}
      for (const [key, val] of Object.entries(values)) {
        if (key === 'id' || readThrough.has(key)) continue
        oppPayload[key] = val
      }
      oppPayload.parent_lead = leadId
      oppPayload.project_stage = stageKeyOf(target)
      oppPayload.probability_pct = probabilityMidpoint(target)
      oppPayload.lead_status = 'OPEN'
      oppPayload.created_date = now
      oppPayload.created_by = CURRENT_USER_ID
      oppPayload.modified_date = now
      oppPayload.modified_by = CURRENT_USER_ID

      const createdOpp = await api.post<Record<string, unknown>>('/opportunities', oppPayload)
      const opportunityId = String(createdOpp.data.id)

      await api.put(`/leads/${leadId}`, {
        lead_status: 'CONVERTED',
        modified_date: now,
        modified_by: CURRENT_USER_ID,
      })

      const copiedFields = Object.keys(oppPayload).filter(
        (k) => !['parent_lead', 'lead_status', 'project_stage', 'probability_pct'].includes(k)
      )

      await api.post('/conversions', {
        source_module: 'leads',
        source_id: leadId,
        target_module: 'opportunities',
        target_id: opportunityId,
        actor: CURRENT_USER_ID,
        timestamp: now,
        copied_fields: copiedFields,
        note: isSkip
          ? `${leadId} moved directly from Stage ${currentStage} to Opportunity Stage ${target}, skipping its own remaining stages — ${reason.trim()}`
          : `${leadId} moved to Opportunities from Stage ${currentStage}.`,
      })

      void logAutomation({
        type: 'record_update',
        target: opportunityId,
        module: 'opportunities',
        detail: `${opportunityId} created at Stage ${target} by moving ${leadId} to the Opportunities module`,
      })
      void logAutomation({
        type: 'record_update',
        target: leadId,
        module: 'leads',
        detail: `${leadId} moved to ${opportunityId} — now read-only`,
      })

      return opportunityId
    },
    onSuccess: async (opportunityId) => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['record', 'leads', leadId] }),
        queryClient.invalidateQueries({ queryKey: ['list', 'leads'] }),
        queryClient.invalidateQueries({ queryKey: ['collection', 'leads'] }),
        queryClient.invalidateQueries({ queryKey: ['list', 'opportunities'] }),
        queryClient.invalidateQueries({ queryKey: ['collection', 'opportunities'] }),
      ])
      handleClose()
      // Straight to the new record — no intermediate "here's what happened"
      // screen. The effects list below the Move to picker already said what
      // would happen, before the click that just fired it.
      navigate(`/opportunities/${opportunityId}`)
    },
  })

  const pending = advanceWithinLeads.isPending || moveToOpportunity.isPending
  const isError = advanceWithinLeads.isError || moveToOpportunity.isError

  const handleClose = () => {
    if (pending) return
    setReason('')
    advanceWithinLeads.reset()
    moveToOpportunity.reset()
    onClose()
  }

  const confirm = () => {
    if (crossesToOpportunities) moveToOpportunity.mutate()
    else advanceWithinLeads.mutate()
  }

  return (
    <Dialog open={open} onOpenChange={(next) => !next && handleClose()}>
      <DialogContent className="max-w-lg max-h-[85vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <ArrowRightIcon className="size-4" />
            Advance {leadId}
          </DialogTitle>
          <DialogDescription>
            Stages are states, not steps — move to any stage below, in Leads or straight into
            Opportunities, as long as it's explained.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-3 text-sm">
          <div className="flex items-center gap-3">
            <span className="text-muted-foreground">Move to</span>
            <Select value={String(target)} onValueChange={(v) => setTarget(Number(v))}>
              <SelectTrigger className="w-72">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {options.map((o) => (
                  <SelectItem key={`${o.module}:${o.stage}`} value={String(o.stage)}>
                    {o.stage} · {o.name} ({o.module === 'leads' ? 'Leads' : 'Opportunities'})
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {isSkip && (
            <p className="text-xs text-amber-700 dark:text-amber-400">
              Skips Stage{currentStage + 1 === target - 1 ? '' : 's'}{' '}
              {Array.from({ length: target - currentStage - 1 }, (_, i) => currentStage + 1 + i).join(', ')}.
              Recorded as a skip — a reason is required.
            </p>
          )}
          {isReversal && (
            <p className="text-xs text-amber-700 dark:text-amber-400">
              Moves backward from Stage {currentStage}. Recorded as a reversal — a reason is
              required.
            </p>
          )}

          {reasonRequired && (
            <Textarea
              placeholder={isReversal ? 'Why is this moving back?' : 'Why skip ahead?'}
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              rows={3}
            />
          )}

          {crossesToOpportunities ? (
            <ul className="space-y-2 rounded-md border p-3">
              <Effect>
                An Opportunity is created (OPP-00001 format), opening at Stage {target} —{' '}
                {targetOption?.name}.
              </Effect>
              <Effect>
                End Client, Segment, Opportunity Name and the rest of this lead&apos;s identity are
                not copied — the Opportunity reads them from {leadId} from now on.
              </Effect>
              <Effect>{leadId} becomes read-only and its status becomes Converted.</Effect>
              <Effect>A conversion record is written for the audit trail.</Effect>
            </ul>
          ) : (
            <ReadinessPanel module="leads" values={values} from={currentStage} to={target} />
          )}
        </div>

        {isError && (
          <p className="text-sm text-destructive">The move failed — nothing was changed.</p>
        )}

        <DialogFooter>
          <Button type="button" variant="outline" onClick={handleClose} disabled={pending}>
            Cancel
          </Button>
          <Button type="button" onClick={confirm} disabled={!canConfirm || pending}>
            {pending
              ? crossesToOpportunities
                ? 'Moving…'
                : 'Advancing…'
              : crossesToOpportunities
                ? 'Yes, move to Opportunities'
                : `Yes, advance to Stage ${target}`}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function Effect({ children }: { children: React.ReactNode }) {
  return (
    <li className="flex items-start gap-2 text-sm">
      <span className="mt-1.5 size-1.5 shrink-0 rounded-full bg-muted-foreground" />
      <span>{children}</span>
    </li>
  )
}
