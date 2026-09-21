import { useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
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
import { useAttestations } from '@/components/leads/useAttestations'
import { api } from '@/lib/api'
import { Bullets, ErrorNotice } from '@/components/ui/notice'
import { STAGE_PCT_FIELDS, alreadyConvertedOf, stageKeyOf, stageList, stagesFor, type NewTransition } from '@/lib/pipeline'
import { displayNameOf, fieldOf, fieldsOf, labelForValue } from '@/lib/spec'
import type { Values } from '@/lib/spec/conditions'
import type { FieldSpec } from '@/types/field'

interface Props {
  open: boolean
  leadId: string
  values: Values
  currentStage: number
  onClose: () => void
  /** Fired after a same-module move — selects the new stage on this same page. */
  onAdvancedWithinLeads: (toStage: number) => void
  /**
   * Drill down from a readiness criterion to the field that proves it. Only
   * offered for a same-module move — crossing to Opportunities shows the
   * effects list instead of the readiness panel, so there is nothing to jump
   * to on that branch.
   */
  onJumpToField?: (field: FieldSpec) => void
}

const LEADS_STAGES = stagesFor('leads')
const LAST_LEAD_STAGE = LEADS_STAGES[LEADS_STAGES.length - 1]?.stage ?? 3
/**
 * The ONE Opportunity stage a Lead may cross into: the first stage that module
 * owns. See "A CROSSING LANDS ON THE FIRST STAGE" below.
 */
const OPPORTUNITY_ENTRY = stagesFor('opportunities')[0]

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
 * A CROSSING LANDS ON THE FIRST STAGE OF THE TARGET MODULE — ONLY
 * ---------------------------------------------------------------
 * Skips are legal WITHIN a module. They are not legal ACROSS one. This picker
 * used to offer all three Opportunity stages, so a Lead at Connect could land
 * directly in Technical Evaluation. Three things broke, and the same three had
 * already broken once on the other crossing — see the note in
 * opportunities/ConvertToDealDialog.tsx, which fixed them there the same way:
 *
 *   1. G2 Commit to Bid is anchored to ENTERING Stage 4, precisely so that no
 *      skip can bypass it. A record entering Opportunities at Stage 5 never
 *      produces the entry event the gate fires on, so the gate never runs.
 *   2. Stage 4 captures the commercial set. Landing at 5 leaves a Technical
 *      Evaluation with no RFP behind it and no screen that will ever ask.
 *   3. The readiness checks below read the LEAD's fields (useAttestations
 *      'leads'). Against a Stage 5 or 6 target those are an Opportunity's
 *      criteria judged on a Lead's values, which cannot be a correct answer.
 *
 * Nothing is lost: 4 -> 5 -> 6 skips stay legal inside Opportunities, with the
 * recorded reason, judged against Opportunity fields by Opportunity screens.
 *
 * Deal stages (7-9) are deliberately NOT offered here either. A Deal reads its
 * own identity through parent_opportunity, not through a Lead directly —
 * jumping a Lead straight to a Deal stage would mean synthesising an
 * Opportunity it never really had, which is a different, larger feature than
 * "let this pursuit skip ahead" and isn't built. See spec/extensions.json
 * open_questions.
 */
export function LeadAdvanceDialog({
  open,
  leadId,
  values,
  currentStage,
  onClose,
  onAdvancedWithinLeads,
  onJumpToField,
}: Props) {
  const queryClient = useQueryClient()
  const navigate = useNavigate()
  const [reason, setReason] = useState('')

  const options = useMemo(
    () => [
      ...LEADS_STAGES.filter((s) => s.stage !== currentStage).map((s) => ({ ...s, module: 'leads' as const })),
      ...(OPPORTUNITY_ENTRY ? [{ ...OPPORTUNITY_ENTRY, module: 'opportunities' as const }] : []),
    ],
    [currentStage]
  )

  const [target, setTarget] = useState(() =>
    Math.min(currentStage + 1, OPPORTUNITY_ENTRY?.stage ?? LAST_LEAD_STAGE)
  )

  const targetOption = options.find((o) => o.stage === target)
  const crossesToOpportunities = target > LAST_LEAD_STAGE

  const isSkip = target > currentStage + 1
  const isReversal = target < currentStage
  const reasonRequired = isSkip || isReversal
  // Read against the Lead's own register fields in both directions: these are
  // the Lead's values, and an Opportunity field name would not resolve as proof.
  const attestations = useAttestations('leads', values, currentStage, target)
  const canConfirm =
    target !== currentStage &&
    (!reasonRequired || reason.trim().length > 0) &&
    attestations.outstanding.length === 0

  const readThrough = useMemo(
    () => new Set(fieldsOf('opportunities').filter((f) => f.value_mode === 'read_through').map((f) => f.api_name)),
    []
  )

  const advanceWithinLeads = useMutation({
    mutationFn: async () => {
      // No modified_date/modified_by here any more: the server stamps both
      // from the Entra session and its own clock, and ignores whatever the
      // body claims. See app/routers/leads.py, SYSTEM_STAMPED.
      const patch: Values = { project_stage: stageKeyOf(target) ?? target }
      // Progression %/Probability % are NOT written here. The server gives the
      // record the target stage's pair on this same PUT (app/progression.py).
      if (isSkip) patch.stage_skip_reason = reason.trim()
      if (isReversal) patch.stage_reversal_reason = reason.trim()

      await api.put(`/leads/${leadId}`, patch)

      const transition: NewTransition = {
        module: 'leads',
        record_id: leadId,
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
        queryClient.invalidateQueries({ queryKey: ['record', 'leads', leadId] }),
        queryClient.invalidateQueries({ queryKey: ['list', 'leads'] }),
        queryClient.invalidateQueries({ queryKey: ['collection', 'leads'] }),
        queryClient.invalidateQueries({ queryKey: ['list', 'transitions'] }),
      ])
      onAdvancedWithinLeads(target)
      reset()
    },
  })

  const moveToOpportunity = useMutation({
    mutationFn: async () => {

      const oppPayload: Values = {}
      for (const [key, val] of Object.entries(values)) {
        // STAGE_PCT_FIELDS, like readThrough, is excluded from the blind copy:
        // the new Opportunity takes its own stage's pair on create.
        if (key === 'id' || readThrough.has(key) || STAGE_PCT_FIELDS.has(key)) continue
        oppPayload[key] = val
      }
      oppPayload.parent_lead = leadId
      oppPayload.project_stage = stageKeyOf(target)
      oppPayload.lead_status = 'OPEN'

      // ONE request. Creating the Opportunity converts the Lead and writes the
      // conversion record in the same server transaction, and a second press
      // is refused rather than making a second Opportunity — see
      // backend/app/conversion.py. This used to be three requests, and the
      // last one failing left a converted Lead behind a dialog that said
      // "Nothing was changed".
      //
      // A move into Opportunities writes a conversion, not a transition, so
      // the checks ticked by hand are recorded on its note instead.
      oppPayload.conversion_note =
        (isSkip
          ? `${leadId} moved directly from Stage ${currentStage} to Opportunity Stage ${target}, skipping its own remaining stages — ${reason.trim()}`
          : `${leadId} moved to Opportunities from Stage ${currentStage}.`) +
        (attestations.codes.length ? ` Confirmed by hand: ${attestations.codes.join(', ')}.` : '')

      const createdOpp = await api.post<Record<string, unknown>>('/opportunities', oppPayload)
      return String(createdOpp.data.id)
    },
    onSuccess: async (opportunityId) => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['record', 'leads', leadId] }),
        queryClient.invalidateQueries({ queryKey: ['list', 'leads'] }),
        queryClient.invalidateQueries({ queryKey: ['collection', 'leads'] }),
        queryClient.invalidateQueries({ queryKey: ['list', 'opportunities'] }),
        queryClient.invalidateQueries({ queryKey: ['collection', 'opportunities'] }),
      ])
      reset()
      // Straight to the new record — no intermediate "here's what happened"
      // screen. The effects list below the Move to picker already said what
      // would happen, before the click that just fired it.
      navigate(`/opportunities/${opportunityId}`)
    },
  })

  const pending = advanceWithinLeads.isPending || moveToOpportunity.isPending
  const isError = advanceWithinLeads.isError || moveToOpportunity.isError
  const alreadyConverted = alreadyConvertedOf(moveToOpportunity.error)

  // The unconditional close: called once a mutation has actually settled, so
  // there is nothing left to guard against.
  const reset = () => {
    setReason('')
    advanceWithinLeads.reset()
    moveToOpportunity.reset()
    onClose()
  }

  // The guarded close: for the user dismissing the dialog themselves (Cancel,
  // Escape, the backdrop) while a save may still be in flight. Read fresh at
  // call time via `pending`, which DOM/Radix rebinds on every render — unlike
  // a callback closed over inside a mutation's onSuccess, which would freeze
  // on whatever `pending` was when that render fired the mutation (always
  // `true`), and so would never actually close the dialog after a save.
  const handleClose = () => {
    if (pending) return
    reset()
  }

  const confirm = () => {
    if (crossesToOpportunities) moveToOpportunity.mutate()
    else advanceWithinLeads.mutate()
  }

  return (
    <Dialog open={open} onOpenChange={(next) => !next && handleClose()}>
      <DialogContent className="max-w-lg max-h-[85vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Move {displayNameOf(values)} to another stage</DialogTitle>
          <DialogDescription className="sr-only">Choose the stage this lead moves to.</DialogDescription>
        </DialogHeader>

        <div className="space-y-3 text-sm">
          <Bullets
            className="text-muted-foreground"
            items={[
              'You can move forward, skip ahead or go back.',
              'Skipping or going back needs a short reason.',
              OPPORTUNITY_ENTRY && `Moving to ${OPPORTUNITY_ENTRY.name} turns it into an Opportunity.`,
            ]}
          />
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

          {crossesToOpportunities && (
            <div className="rounded-md border px-3 py-1.5">
              <p className="font-medium">When you move it:</p>
              <Bullets
                items={[
                  `An Opportunity opens at Stage ${target} – ${targetOption?.name ?? ''}.`,
                  "It shows this lead's client and project details. Nothing to re-enter.",
                  `This lead is locked and marked ${labelForValue(fieldOf('leads', 'lead_status')?.picklist, 'CONVERTED')}.`,
                  'The move is kept in History.',
                ]}
              />
            </div>
          )}
          {/* Shown for the cross into Opportunities too: leaving Stage 3 and
              entering Stage 4 have criteria like any other move, and that was
              the one move that showed none of them. */}
          <ReadinessPanel
              module="leads"
              values={values}
              from={currentStage}
              to={target}
              attested={attestations.attested}
              onToggleAttested={attestations.toggle}
              onJumpToField={
                onJumpToField &&
                ((field) => {
                  handleClose()
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

        {/* Already converted — by an earlier press, or on another screen — is
            not a failure to retry: the dialog offers the record it became
            instead of Confirm. */}
        {alreadyConverted ? (
          <p className="text-sm text-destructive">{alreadyConverted.message}</p>
        ) : (
          isError && (
            <ErrorNotice
              error={advanceWithinLeads.error ?? moveToOpportunity.error}
              fallback="The stage wasn't changed. Try again."
              suffix="The stage wasn't changed."
            />
          )
        )}

        <DialogFooter>
          <Button type="button" variant="outline" onClick={handleClose} disabled={pending}>
            {alreadyConverted ? 'Close' : 'Cancel'}
          </Button>
          {alreadyConverted ? (
            alreadyConverted.target_module &&
            alreadyConverted.target_id && (
              <Button
                type="button"
                onClick={() => {
                  const path = `/${alreadyConverted.target_module}/${alreadyConverted.target_id}`
                  reset()
                  navigate(path)
                }}
              >
                Open the {alreadyConverted.target_module === 'deals' ? 'Deal' : 'Opportunity'}
              </Button>
            )
          ) : (
            <Button type="button" onClick={confirm} disabled={!canConfirm || pending}>
              {pending
                ? crossesToOpportunities
                  ? 'Moving…'
                  : 'Updating…'
                : crossesToOpportunities
                  ? `Move to Opportunities, Stage ${target}`
                  : `Move to Stage ${target}`}
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
