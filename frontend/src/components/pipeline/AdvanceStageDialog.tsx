import { useMemo, useState } from 'react'
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
import type { PipelineModuleSpec } from '@/components/pipeline/types'
import { api } from '@/lib/api'
import { logAutomation } from '@/lib/automation'
import { CURRENT_USER_ID, probabilityMidpoint, stageFieldOf, type Transition } from '@/lib/pipeline'
import type { Values } from '@/lib/spec/conditions'

interface Props {
  spec: PipelineModuleSpec
  open: boolean
  recordId: string
  values: Values
  currentStage: number
  onClose: () => void
  onAdvanced?: (toStage: number) => void
}

/**
 * The one place a pipeline record's stage ever changes, for every module.
 *
 * Stages are states, not steps (CLAUDE.md) — a skip forward and a move backward
 * are both legal, and each carries a mandatory recorded reason. An ordinary
 * one-stage move does not.
 *
 * What differs per module is described in the descriptor, not branched on here:
 * which field holds the stage, which picklist keys it, whether the transition
 * writes a probability midpoint, and whether the record has its own reason
 * fields to write alongside the Transition. A module with only two stages can
 * never produce a skip, so nothing special is needed to suppress one.
 *
 * POC-1: the readiness panel shown here is advisory only. Confirm always
 * succeeds, whatever it shows — see CLAUDE.md prompt 5.
 */
export function AdvanceStageDialog({
  spec,
  open,
  recordId,
  values,
  currentStage,
  onClose,
  onAdvanced,
}: Props) {
  const queryClient = useQueryClient()
  const stages = spec.stages
  const maxStage = stages.length ? stages[stages.length - 1].stage : currentStage
  const [target, setTarget] = useState(Math.min(currentStage + 1, maxStage))
  const [reason, setReason] = useState('')

  const isSkip = target > currentStage + 1
  const isReversal = target < currentStage
  const reasonRequired = isSkip || isReversal
  const canConfirm = target !== currentStage && (!reasonRequired || reason.trim().length > 0)

  const stageOptions = useMemo(
    () => stages.filter((s) => s.stage !== currentStage),
    [stages, currentStage]
  )

  const advance = useMutation({
    mutationFn: async () => {
      const stageField = stageFieldOf(spec.module)
      const patch: Values = { ...spec.stamp() }
      if (stageField) patch[stageField] = spec.stageKeyOf(target) ?? target
      if (spec.writesProbability) {
        patch.probability_pct = probabilityMidpoint(target) ?? values.probability_pct ?? null
      }
      if (isSkip && spec.skipReasonField) patch[spec.skipReasonField] = reason.trim()
      if (isReversal && spec.reversalReasonField) patch[spec.reversalReasonField] = reason.trim()

      await api.put<Values>(`/${spec.collection}/${recordId}`, patch)

      const transition: Transition = {
        module: spec.module as Transition['module'],
        record_id: recordId,
        from: currentStage,
        to: target,
        reason: reasonRequired ? reason.trim() : null,
        is_skip: isSkip,
        is_reversal: isReversal,
        actor: CURRENT_USER_ID,
        timestamp: new Date().toISOString(),
      }
      await api.post('/transitions', transition)
    },
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['record', spec.collection, recordId] }),
        queryClient.invalidateQueries({ queryKey: ['list', spec.collection] }),
        queryClient.invalidateQueries({ queryKey: ['collection', spec.collection] }),
        queryClient.invalidateQueries({ queryKey: ['list', 'transitions'] }),
      ])
      void logAutomation({
        type: 'record_update',
        target: recordId,
        module: spec.module,
        detail: `${recordId} advanced Stage ${currentStage} → Stage ${target}${
          reason.trim() ? ` — ${reason.trim()}` : ''
        }`,
      })
      onAdvanced?.(target)
      setReason('')
      onClose()
    },
  })

  // A module whose rail is two stages long cannot skip, so the sentence about
  // skipping would be describing something the dialog cannot do.
  const canSkip = maxStage - stages[0].stage > 1

  return (
    <Dialog open={open} onOpenChange={(next) => !next && onClose()}>
      <DialogContent className="max-w-lg max-h-[85vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <ArrowRightIcon className="size-4" />
            Advance {recordId}
          </DialogTitle>
          <DialogDescription>
            {canSkip
              ? "Stages are states, not steps — moving forward more than one, or moving back, is legal here as long as it's explained."
              : "Stages are states, not steps — moving back is legal here too, as long as it's explained."}
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-3 text-sm">
          <div className="flex items-center gap-3">
            <span className="text-muted-foreground">Move to</span>
            <Select value={String(target)} onValueChange={(v) => setTarget(Number(v))}>
              <SelectTrigger className="w-64">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {stageOptions.map((s) => (
                  <SelectItem key={s.stage} value={String(s.stage)}>
                    Stage {s.stage} · {s.name}
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

          <ReadinessPanel module={spec.module} values={values} from={currentStage} to={target} />
        </div>

        {advance.isError && (
          <p className="text-sm text-destructive">The stage could not be advanced.</p>
        )}

        <DialogFooter>
          <Button type="button" variant="outline" onClick={onClose}>
            Cancel
          </Button>
          <Button
            type="button"
            onClick={() => advance.mutate()}
            disabled={!canConfirm || advance.isPending}
          >
            {advance.isPending ? 'Advancing…' : `Advance to Stage ${target}`}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
