import { useMemo, useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'

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
import { RequiredBeforeMove, requiredBeforeMove } from '@/components/pipeline/RequiredBeforeMove'
import { useAttestations } from '@/components/leads/useAttestations'
import type { PipelineModuleSpec } from '@/components/pipeline/types'
import { api } from '@/lib/api'
import { Bullets, ErrorNotice } from '@/components/ui/notice'
import { stageFieldOf, stageList, type NewTransition } from '@/lib/pipeline'
import { displayNameOf } from '@/lib/spec'
import type { Values } from '@/lib/spec/conditions'
import type { FieldSpec } from '@/types/field'

interface Props {
  spec: PipelineModuleSpec
  open: boolean
  recordId: string
  values: Values
  currentStage: number
  /** Stages the record jumped over — their required fields are not demanded. */
  skipped?: readonly number[]
  onClose: () => void
  onAdvanced?: (toStage: number) => void
  /**
   * Drill down from a criterion to the field that proves it. The dialog closes
   * on the way — the field is on the record behind it, and a user who has just
   * asked to go and fill something in does not want to answer a modal first.
   */
  onJumpToField?: (field: FieldSpec) => void
}

/**
 * The one place a pipeline record's stage ever changes, for every module.
 *
 * Stages are states, not steps (CLAUDE.md) — a skip forward and a move backward
 * are both legal, and each carries a mandatory recorded reason. An ordinary
 * one-stage move does not.
 *
 * What differs per module is described in the descriptor, not branched on here:
 * which field holds the stage, which picklist keys it, and whether the record
 * has its own reason fields to write alongside the Transition. A module with
 * only two stages can never produce a skip, so nothing special is needed to
 * suppress one.
 *
 * Progression % / Probability % are NOT written by this dialog. The server
 * gives the record the target stage's pair on this same PUT — see
 * app/progression.py.
 *
 * The readiness panel is advisory for everything the record can answer itself
 * — a field filled, a formula passing. The checks nothing can evaluate are
 * different: a forward move waits until a person ticks each one, and the ticks
 * are recorded on the transition with who and when. See useAttestations.
 */
export function AdvanceStageDialog({
  spec,
  open,
  recordId,
  values,
  currentStage,
  skipped,
  onClose,
  onAdvanced,
  onJumpToField,
}: Props) {
  const queryClient = useQueryClient()
  const stages = spec.stages
  const maxStage = stages.length ? stages[stages.length - 1].stage : currentStage
  const [target, setTarget] = useState(Math.min(currentStage + 1, maxStage))
  const [reason, setReason] = useState('')

  const isSkip = target > currentStage + 1
  const isReversal = target < currentStage
  const reasonRequired = isSkip || isReversal
  const attestations = useAttestations(spec.module, values, currentStage, target)
  // Layer 1, enforced (21 Sep 2026): the stage being left must be complete.
  const required = requiredBeforeMove(spec.module, values, currentStage, target, skipped)
  const canConfirm =
    target !== currentStage &&
    (!reasonRequired || reason.trim().length > 0) &&
    attestations.outstanding.length === 0 &&
    required.length === 0

  const stageOptions = useMemo(
    () => stages.filter((s) => s.stage !== currentStage),
    [stages, currentStage]
  )

  const advance = useMutation({
    mutationFn: async () => {
      const stageField = stageFieldOf(spec.module)
      // No system-field stamp: the server owns modified_by/modified_date and
      // discards whatever the body claims. See PipelineModuleSpec in types.ts.
      const patch: Values = {}
      if (stageField) patch[stageField] = spec.stageKeyOf(target) ?? target
      // Progression %/Probability % are NOT written here: the server sets the
      // target stage's pair on this PUT (app/progression.py).
      if (isSkip && spec.skipReasonField) patch[spec.skipReasonField] = reason.trim()
      if (isReversal && spec.reversalReasonField) patch[spec.reversalReasonField] = reason.trim()

      await api.put<Values>(`/${spec.collection}/${recordId}`, patch)

      const transition: NewTransition = {
        module: spec.module as NewTransition['module'],
        record_id: recordId,
        from: currentStage,
        to: target,
        reason: reasonRequired ? reason.trim() : null,
        is_skip: isSkip,
        is_reversal: isReversal,
        attested: attestations.codes,
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
          <DialogTitle>Move {displayNameOf(values)} to another stage</DialogTitle>
          <DialogDescription className="sr-only">Choose the stage this record moves to.</DialogDescription>
        </DialogHeader>

        <div className="space-y-3 text-sm">
          <Bullets
            className="text-muted-foreground"
            items={
              canSkip
                ? ['You can move forward, skip ahead or go back.', 'Skipping or going back needs a short reason.']
                : ['You can move forward one stage, or go back.', 'Going back needs a short reason.']
            }
          />
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
              Skipping {stageList(Array.from({ length: target - currentStage - 1 }, (_, i) => currentStage + 1 + i))}.
              Add a reason below.
            </p>
          )}
          {isReversal && (
            <p className="text-xs text-amber-700 dark:text-amber-400">
              Moving back from Stage {currentStage}. Add a reason below.
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

          <RequiredBeforeMove
            fields={required}
            from={currentStage}
            onJumpToField={
              onJumpToField &&
              ((field) => {
                onClose()
                onJumpToField(field)
              })
            }
          />

          <ReadinessPanel
            module={spec.module}
            values={values}
            from={currentStage}
            to={target}
            attested={attestations.attested}
            onToggleAttested={attestations.toggle}
            onJumpToField={
              onJumpToField &&
              ((field) => {
                onClose()
                onJumpToField(field)
              })
            }
          />
          {attestations.outstanding.length > 0 && (
            <p className="text-xs text-amber-700 dark:text-amber-400">
              Tick the {attestations.outstanding.length} remaining check
              {attestations.outstanding.length === 1 ? '' : 's'} above to continue.
            </p>
          )}
        </div>

        {advance.isError && (
          <ErrorNotice error={advance.error} suffix="The stage wasn't changed." />
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
            {advance.isPending ? 'Moving…' : `Move to Stage ${target}`}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
