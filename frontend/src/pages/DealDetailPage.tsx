import { currentUserId } from '@/lib/currentUser'
import { useNavigate } from 'react-router-dom'
import { useMutation, useMutationState, useQuery, useQueryClient } from '@tanstack/react-query'
import { ArrowRightIcon, SparklesIcon } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { RecordListView } from '@/components/list/RecordListView'
import { contactListCell } from '@/components/contacts/contactListCell'
import { PipelineRecordPage } from '@/components/pipeline/PipelineRecordPage'
import type { PipelineModuleSpec, PipelineRecordContext } from '@/components/pipeline/types'
import { api } from '@/lib/api'
import { money } from '@/lib/format'
import {
  dealStageKeyOf,
  probabilityMidpoint,
  stageKeyOf,
  stagesFor,
  type Transition,
} from '@/lib/pipeline'
import { displayNameOf } from '@/lib/spec'
import type { Values } from '@/lib/spec/conditions'

const MODULE = 'deals'
/**
 * The last stage a Deal carries. See dealsPipeline.stages.
 *
 * Deals own Stages 7-9 as of the split — module_split.json ranges are the
 * authority, never applies_to in spec/stages.json, which is still wrong (see
 * register_corrections). dealsPipeline.stages reads stagesFor('deals')
 * directly rather than a hardcoded range, so Stage 7 — Close and its fields
 * (PO Number, Contract Signed Date, Payment Schedule Confirmed) are reachable
 * on the rail, not just present in the spec with nowhere to click.
 */
const LAST_STAGE = 9
/** Expansion re-enters the pipeline here, not at Stage 0 — see the mutation. */
const EXPANSION_ENTRY_STAGE = 3
/** Lets the banner watch a mutation the actions slot owns. See DealBanner. */
const EXPANSION_MUTATION = 'expansion-lead'

/** The Lead this Deal was converted from, when it names one. */
function useParentLead(ctx: PipelineRecordContext) {
  const parentLead = ctx.values?.parent_lead
  const { data } = useQuery({
    queryKey: ['record', 'leads', parentLead],
    queryFn: async () => (await api.get<Values>(`/leads/${parentLead}`)).data,
    enabled: Boolean(parentLead),
  })
  return { id: typeof parentLead === 'string' ? parentLead : undefined, record: data }
}

function DealHeader({ ctx }: { ctx: PipelineRecordContext }) {
  const navigate = useNavigate()
  const parent = useParentLead(ctx)
  const contractValue = ctx.values?.contract_value

  return (
    <>
      {typeof contractValue === 'number' && <span>Contract value: ${money(contractValue)}</span>}
      {parent.record && (
        <button
          type="button"
          className="text-primary underline underline-offset-2"
          onClick={() => navigate(`/leads/${parent.id}`)}
        >
          From {parent.id}
        </button>
      )}
    </>
  )
}

/**
 * Stage 9 is Expansion, and an expansion is a new pursuit rather than more of
 * this one — so it becomes a Lead. It enters at Stage 3 (Prescription) rather
 * than Stage 0, because the client relationship and the integration already
 * exist; that jump is a skip, and it carries its reason like any other.
 */
function useCreateExpansionLead(ctx: PipelineRecordContext) {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const parent = useParentLead(ctx)

  const mutation = useMutation({
    mutationKey: [EXPANSION_MUTATION, ctx.id],
    mutationFn: async () => {
      const parentLead = parent.record
      if (!ctx.id || !ctx.values || !parentLead) throw new Error('Parent lead not loaded')
      const now = new Date().toISOString()
      const reason =
        'Expansion lead — the client relationship and the integration already exist, so this enters directly at Stage 3 (Prescription) rather than Stage 0, per the journey doc.'

      const payload: Values = {
        opportunity_name: `${displayNameOf(parentLead)} — Expansion`,
        project_stage: stageKeyOf(EXPANSION_ENTRY_STAGE),
        probability_pct: probabilityMidpoint(EXPANSION_ENTRY_STAGE),
        lead_status: 'OPEN',
        opportunity_type: 'EXPANSION',
        parent_deal: ctx.id,
        end_client: parentLead.end_client ?? null,
        customer_partner_si: parentLead.customer_partner_si ?? null,
        deal_source: parentLead.deal_source ?? null,
        pre_bid_alliance_partner: parentLead.pre_bid_alliance_partner ?? null,
        alliance_structure: parentLead.alliance_structure ?? null,
        // The stakeholder map: leads.demo_attendees is the only childlist that
        // plausibly carries it — see spec/extensions.json's note on that field.
        demo_attendees: Array.isArray(parentLead.demo_attendees) ? parentLead.demo_attendees : [],
        stage_skip_reason: reason,
        created_date: now,
        created_by: currentUserId(),
        modified_date: now,
        modified_by: currentUserId(),
      }

      const created = await api.post<Record<string, unknown>>('/leads', payload)
      const newId = String(created.data.id)

      const transition: Transition = {
        module: 'leads',
        record_id: newId,
        from: 0,
        to: EXPANSION_ENTRY_STAGE,
        reason,
        is_skip: true,
        is_reversal: false,
        actor: currentUserId(),
        timestamp: now,
      }
      await api.post('/transitions', transition)


      return newId
    },
    onSuccess: async (newId) => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['list', 'leads'] }),
        queryClient.invalidateQueries({ queryKey: ['collection', 'leads'] }),
      ])
      navigate(`/leads/${newId}`, { state: { editOnOpen: true } })
    },
  })

  return { mutation, hasParent: Boolean(parent.record) }
}

function DealActions({ ctx }: { ctx: PipelineRecordContext }) {
  const { mutation, hasParent } = useCreateExpansionLead(ctx)

  return (
    <>
      {ctx.currentStage === LAST_STAGE && (
        <Button
          variant="outline"
          onClick={() => mutation.mutate()}
          disabled={!hasParent || mutation.isPending}
        >
          <SparklesIcon className="size-4" />
          {mutation.isPending ? 'Creating…' : 'Create Expansion Lead'}
        </Button>
      )}
      <Button onClick={ctx.openAdvance} disabled={ctx.isLoading || !ctx.values}>
        <ArrowRightIcon className="size-4" />
        {ctx.currentStage >= LAST_STAGE
          ? 'Change stage'
          : `Advance to Stage ${ctx.currentStage + 1}`}
      </Button>
    </>
  )
}

/**
 * The button that fires this mutation is in the Actions slot and the message
 * belongs full-width under the header, so the two are separate components with
 * no parent between them. useMutationState is how one watches the other without
 * a second useMutation, which would observe a different mutation entirely and
 * never report the failure the user actually caused.
 */
function DealBanner({ ctx }: { ctx: PipelineRecordContext }) {
  const failures = useMutationState({
    filters: { mutationKey: [EXPANSION_MUTATION, ctx.id], status: 'error' },
    select: (m) => m.state.error,
  })
  if (!failures.length) return null

  return (
    <p className="mb-2 text-sm text-destructive">
      Could not create the expansion lead — the parent lead may not be loaded yet.
    </p>
  )
}

function DealRelated({ ctx }: { ctx: PipelineRecordContext }) {
  if (!ctx.values) return null

  const endClientId = typeof ctx.values.end_client === 'string' ? ctx.values.end_client : undefined

  return (
    <div className="space-y-3">
      <p className="text-sm text-muted-foreground">
        {ctx.endClient
          ? `Contacts at ${displayNameOf(ctx.endClient)} — carried from the Lead's End Client.`
          : 'No End Client set.'}
      </p>
      {endClientId ? (
        <RecordListView
          module="contacts"
          collection="contacts"
          basePath="/contacts"
          filter={{ account: endClientId }}
          hiddenColumns={['account']}
          renderCell={contactListCell}
          pageSize={10}
          emptyMessage="No contacts at this account yet."
        />
      ) : (
        <p className="text-sm text-muted-foreground">No End Client set.</p>
      )}
    </div>
  )
}

export const dealsPipeline: PipelineModuleSpec = {
  module: MODULE,
  collection: 'deals',
  basePath: '/deals',
  noun: 'deal',
  stages: stagesFor(MODULE),
  stageKeyOf: dealStageKeyOf,
  // A booked Deal is at 100%; there is no band left to judge.
  writesProbability: false,
  // The Deals sheet had no reason fields of its own when these screens were
  // built, so a Deal's reason lives only on the Transition record. The split has
  // since placed CROSS-CUTTING on all three modules, so deals now HAS
  // stage_skip_reason and stage_reversal_reason — wiring them up would change
  // what a Deal stores, which is a decision rather than a refactor.
  stamp: () => ({ modified_by_date: new Date().toISOString() }),
  detailsHeading: 'On conversion, and system fields',
  showProbabilityBand: false,
  tabs: ['current', 'details', 'related', 'history'],
  Header: DealHeader,
  Actions: DealActions,
  Banner: DealBanner,
  Related: DealRelated,
}

export function DealDetailPage() {
  return <PipelineRecordPage spec={dealsPipeline} />
}
