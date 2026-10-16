import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { AlertTriangleIcon, CheckCircle2Icon, ExternalLinkIcon, PencilIcon } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import { FormSection } from '@/components/form/RecordForm'
import { RecordEditor } from '@/components/record/RecordEditor'
import { RecordFormProvider } from '@/hooks/useRecordForm'
import { PursuitGroupSummary } from '@/components/pursuits/PursuitGroupSummary'
import { api } from '@/lib/api'
import { ErrorNotice } from '@/components/ui/notice'
import { date as fmtDate } from '@/lib/format'
import { adjudicationLoser } from '@/lib/partners'
import { MIN_REASON } from '@/lib/pursuitGroups'
import { invalidateRegistrationWorld, type PossibleConflictMatch, useConflictCheck } from '@/lib/registrations'
import { labelForValue, partnerRegistration } from '@/lib/spec'
import type { Values } from '@/lib/spec/conditions'

const MODULE = 'conflicts'
const SECTION = 'CONFLICT ADJUDICATION'
const COLLECTION = 'conflicts'

/**
 * What a person fills on an adjudication, from the sidecar — assess, then
 * decide. Who Registered First is in the set but read-only: the server derives
 * it from the two Submitted Dates.
 */
const FILLABLE = [
  ...partnerRegistration.adjudication_criteria.fields,
  ...partnerRegistration.adjudication_outcome.fields,
]

type Labels = Record<string, string> | undefined

const partnerOf = (registration: Values | undefined): string =>
  (registration?.__labels as Labels)?.partner ?? 'Another partner'

/**
 * Conflict adjudication — Partner Playbook §6.2.
 *
 * Every conflict here is a RECORD, raised by the server when the second
 * registration at the same End Client was saved (app/registration_matching.py).
 * Nothing is detected in the browser any more. What remains to show are:
 *
 *   possible conflicts   registrations saved before the check existed, or
 *                        whose details changed since — offered once each:
 *                        raise it, or say why it is a different project
 *   conflict records     open (awaiting a decision) or decided
 *
 * Every party is named — partner and project — never by a REG-, CONF- or PG-
 * id, which is how a CRM reads to the people using it.
 */
export function ConflictPanel({
  registration,
  conflicts,
  registrations,
  candidates,
}: {
  registration: Values | undefined
  /** Conflict records naming this registration on either side. */
  conflicts: Values[]
  /** Every registration, for names and dates. */
  registrations: Values[]
  candidates: PossibleConflictMatch[]
}) {
  if (!registration) {
    return <p className="text-muted-foreground py-6 text-sm">Loading…</p>
  }

  if (conflicts.length === 0 && candidates.length === 0) {
    const client = (registration.__labels as Labels)?.end_client
    return (
      <p className="text-muted-foreground py-6 text-sm">
        No other partner is registered at {client ?? 'this End Client'}. If one registers, ARK asks on save whether
        it is the same project.
      </p>
    )
  }

  return (
    <div className="space-y-4 py-3">
      {candidates.map((match) => (
        <CandidateCard key={match.registration_id} registrationId={String(registration.id)} match={match} />
      ))}
      {conflicts.map((conflict) => (
        <AdjudicationCard key={String(conflict.id)} conflict={conflict} registrations={registrations} />
      ))}
    </div>
  )
}

/**
 * A possible conflict nobody has answered — offered once. The same two answers
 * the save dialog gives, one registration at a time.
 */
function CandidateCard({ registrationId, match }: { registrationId: string; match: PossibleConflictMatch }) {
  const check = useConflictCheck(registrationId)
  const [declining, setDeclining] = useState(false)
  const [reason, setReason] = useState('')

  return (
    <div className="space-y-2 rounded-lg border border-amber-500/40 bg-amber-500/10 p-4 text-sm">
      <p className="flex items-center gap-2 font-medium">
        <AlertTriangleIcon className="size-4" />
        {match.same_partner ? 'Possible duplicate registration' : 'Possible conflict — not raised yet'}
      </p>
      <p>
        <span className="font-medium">{match.partner_name ?? 'Another partner'}</span> registered{' '}
        <span className="font-medium">{match.project_name}</span>
        {match.end_client_name ? ` at ${match.end_client_name}` : ''}
        {match.submitted_date ? `, submitted ${fmtDate(match.submitted_date)}` : ''}.
      </p>

      {declining ? (
        <div className="space-y-2">
          <Textarea
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            placeholder="Why is this a different project? (required)"
            rows={2}
          />
          <div className="flex flex-wrap justify-end gap-2">
            <Button type="button" size="sm" variant="outline" onClick={() => setDeclining(false)}>
              Back
            </Button>
            <Button
              type="button"
              size="sm"
              disabled={check.isPending || reason.trim().length < MIN_REASON}
              onClick={() =>
                check.mutate({
                  raise_conflict_with: [],
                  not_conflict_with: [match.registration_id],
                  not_conflict_reason: reason.trim(),
                })
              }
            >
              {check.isPending ? 'Saving…' : 'Save as a different project'}
            </Button>
          </div>
        </div>
      ) : (
        <div className="flex flex-wrap items-center justify-end gap-2">
          {match.same_partner && (
            <Link
              className="text-link mr-auto inline-flex items-center gap-1 underline underline-offset-2"
              to={`/partners/registrations/${match.registration_id}`}
            >
              Open that registration
              <ExternalLinkIcon className="size-3.5" />
            </Link>
          )}
          <Button type="button" size="sm" variant="outline" onClick={() => setDeclining(true)}>
            Different project…
          </Button>
          {!match.same_partner && (
            <Button
              type="button"
              size="sm"
              disabled={check.isPending}
              onClick={() => check.mutate({ raise_conflict_with: [match.registration_id], not_conflict_with: [] })}
            >
              {check.isPending ? 'Raising…' : 'Same project — raise conflict'}
            </Button>
          )}
        </div>
      )}

      {check.isError && <ErrorNotice error={check.error} />}
    </div>
  )
}

/** One side of the pair, as a line of text — shown while editing, where the form has no A / B fields. */
function SlotLine({ slot, registration }: { slot: 'A' | 'B'; registration: Values | undefined }) {
  return (
    <p className="text-sm">
      <span className="text-muted-foreground">Registration {slot} · </span>
      {registration ? (
        <>
          <Link className="underline-offset-2 hover:underline" to={`/partners/registrations/${String(registration.id)}`}>
            {partnerOf(registration)}
          </Link>
          {` · ${String(registration.project_name ?? '')}`}
          {registration.submitted_date ? (
            <span className="text-muted-foreground"> · submitted {fmtDate(registration.submitted_date)}</span>
          ) : null}
        </>
      ) : (
        <span className="text-muted-foreground">deleted</span>
      )}
    </p>
  )
}

function AdjudicationCard({ conflict, registrations }: { conflict: Values; registrations: Values[] }) {
  const queryClient = useQueryClient()
  // An open conflict opens straight into the form: there is nothing to read yet.
  const [editing, setEditing] = useState(!conflict.decision)

  const a = registrations.find((r) => r.id === conflict.registration_a)
  const b = registrations.find((r) => r.id === conflict.registration_b)

  const loser = adjudicationLoser(conflict)
  const loserRecord = loser === String(a?.id) ? a : loser === String(b?.id) ? b : undefined
  const loserStatus = String(loserRecord?.registration_status ?? '')

  const supersede = useMutation({
    mutationFn: async () => {
      if (!loser) return
      await api.put(`/registrations/${loser}`, { registration_status: 'SUPERSEDED' })
    },
    onSuccess: () => invalidateRegistrationWorld(queryClient),
  })

  const decided = Boolean(conflict.decision)
  const bothPursued = String(conflict.decision ?? '') === 'BOTH_PURSUED'

  return (
    // One record, laid out as Zoho lays one out: a header line, then flat
    // parts under small headings — no box inside a box (14 Oct 2026).
    <div className="bg-card space-y-5 rounded-lg px-5 py-4 shadow-sm">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="font-semibold">
            {partnerOf(a)} vs {partnerOf(b)}
          </p>
          <p className="text-muted-foreground text-sm">
            {decided
              ? [labelForValue('partners__decision', conflict.decision), conflict.decision_date && fmtDate(conflict.decision_date)]
                  .filter(Boolean)
                  .join(' · ')
              : 'Awaiting a decision'}
          </p>
        </div>
        {!editing && (
          <Button variant="outline" size="sm" onClick={() => setEditing(true)}>
            <PencilIcon className="size-4" />
            Edit adjudication
          </Button>
        )}
      </div>

      {/* Both pursued: the pursuit group is the outcome, so it comes first.
          Its Role column says which pursuit counts. */}
      {!editing && bothPursued && typeof conflict.pursuit_group === 'string' && (
        <div className="space-y-2">
          <p className="text-sm font-semibold">Pursuits</p>
          <PursuitGroupSummary groupId={conflict.pursuit_group} hideName />
        </div>
      )}

      <div>
        {editing ? (
          <>
            <div className="mb-4 space-y-1">
              <SlotLine slot="A" registration={a} />
              <SlotLine slot="B" registration={b} />
            </div>
            <RecordEditor
              key={`edit:${String(conflict.id)}`}
              module={MODULE}
              collection={COLLECTION}
              recordId={String(conflict.id)}
              initialValues={conflict}
              sections={[SECTION]}
              sectionTitle="Adjudication"
              flat
              only={FILLABLE}
              // Stamped, never typed: the pair IS the collision that raised this.
              stamp={{ registration_a: conflict.registration_a, registration_b: conflict.registration_b }}
              saveLabel={decided ? 'Save adjudication' : 'Record adjudication'}
              onSaved={() => {
                setEditing(false)
                void invalidateRegistrationWorld(queryClient)
              }}
              onCancel={() => setEditing(false)}
            />
          </>
        ) : (
          <RecordFormProvider
            key={`view:${String(conflict.id)}:${String(conflict.modified_date ?? '')}`}
            module={MODULE}
            mode="view"
            initialValues={conflict}
          >
            <FormSection module={MODULE} section={SECTION} title="Adjudication" flat />
          </RecordFormProvider>
        )}

        {!editing && loser && loserRecord && loserStatus !== 'SUPERSEDED' && loserStatus !== 'WITHDRAWN' && (
          <div className="mt-3 rounded-md border border-amber-500/40 bg-amber-500/10 p-3 text-sm">
            <p className="font-medium">{partnerOf(loserRecord)}'s registration has not been superseded</p>
            <p className="text-muted-foreground mt-1">
              The decision does not supersede the other registration on its own, so it is offered here rather than
              applied silently.
            </p>
            <Button
              className="mt-2"
              variant="outline"
              size="sm"
              onClick={() => supersede.mutate()}
              disabled={supersede.isPending}
            >
              {supersede.isPending ? 'Marking…' : `Mark ${partnerOf(loserRecord)}'s registration Superseded`}
            </Button>
            {supersede.isError && <ErrorNotice className="mt-1" error={supersede.error} />}
          </div>
        )}

        {!editing && loserRecord && loserStatus === 'SUPERSEDED' && (
          <p className="text-muted-foreground mt-3 flex items-center gap-2 text-sm">
            <CheckCircle2Icon className="size-4 text-emerald-600 dark:text-emerald-400" />
            {partnerOf(loserRecord)}'s registration is marked Superseded.
          </p>
        )}
      </div>
    </div>
  )
}
