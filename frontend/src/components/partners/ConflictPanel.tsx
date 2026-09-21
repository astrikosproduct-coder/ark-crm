import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { AlertTriangleIcon, CheckCircle2Icon, ExternalLinkIcon, PencilIcon } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import { RecordForm } from '@/components/form/RecordForm'
import { RecordEditor } from '@/components/record/RecordEditor'
import { PursuitGroupSummary } from '@/components/pursuits/PursuitGroupSummary'
import { api } from '@/lib/api'
import { ErrorNotice } from '@/components/ui/notice'
import { date as fmtDate } from '@/lib/format'
import { adjudicationLoser, adjudicationWinner } from '@/lib/partners'
import { MIN_REASON } from '@/lib/pursuitGroups'
import { invalidateRegistrationWorld, type PossibleConflictMatch, useConflictCheck } from '@/lib/registrations'
import { fieldsInSet, labelForValue, partnerRegistration } from '@/lib/spec'
import type { Values } from '@/lib/spec/conditions'
import { cn } from '@/lib/utils'

const MODULE = 'partners'
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
 * registration of a similar project was saved (app/registration_matching.py).
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
      <div className="space-y-4 py-3">
        <div className="rounded-lg border p-4 text-sm">
          <p className="font-medium">No competing registration</p>
          <p className="text-muted-foreground mt-1">
            No other partner has registered{' '}
            <span className="text-foreground">{String(registration.project_name ?? 'this project')}</span>
            {client ? (
              <>
                {' '}
                at <span className="text-foreground">{client}</span>
              </>
            ) : null}
            . Exclusivity is granted per client and project, so a different project at the same client is not a
            conflict.
          </p>
          <p className="text-muted-foreground mt-2">
            When a second partner registers a similar project, ARK asks on save and raises the conflict here.
          </p>
        </div>
        <CriteriaReference />
      </div>
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

/** The register's three criteria, shown when there is nothing to adjudicate. */
function CriteriaReference() {
  const criteria = fieldsInSet(partnerRegistration.adjudication_criteria)

  return (
    <div className="rounded-lg border">
      <div className="border-b px-4 py-3">
        <p className="text-sm font-semibold tracking-wide">{SECTION}</p>
        <p className="text-muted-foreground mt-0.5 text-sm">
          Three criteria are weighed. Registration order alone does not decide the outcome.
        </p>
      </div>
      <ol className="divide-y">
        {criteria.map((field, i) => (
          <li key={field.qref} className="flex gap-3 px-4 py-3 text-sm">
            <span className="text-muted-foreground tabular-nums">{i + 1}</span>
            <div className="min-w-0">
              <p className="font-medium">{field.label}</p>
              <p className="text-muted-foreground">{field.description}</p>
            </div>
          </li>
        ))}
      </ol>
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
      <p className="text-muted-foreground">
        {match.same_partner
          ? 'The same partner registered a similar project. If it is a separate project, say why.'
          : 'Another partner registered a similar project at the same client. Raise a conflict if it is the same project.'}
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

/** One side of the pair: partner, project, when it was submitted, and whether it won. */
function SlotRow({ slot, registration, won }: { slot: 'A' | 'B'; registration: Values | undefined; won: boolean | null }) {
  const status = String(registration?.registration_status ?? '')
  return (
    <div
      className={cn(
        'flex flex-wrap items-center gap-x-2 gap-y-1 rounded-md border px-3 py-2 text-sm',
        won === true && 'border-emerald-500/50 bg-emerald-500/10',
        won === false && 'opacity-60'
      )}
    >
      <span className="text-muted-foreground shrink-0 font-medium">Registration {slot}</span>
      {registration ? (
        <>
          <Link className="underline underline-offset-2" to={`/partners/registrations/${String(registration.id)}`}>
            {partnerOf(registration)}
          </Link>
          <span aria-hidden>·</span>
          <span className="min-w-0">{String(registration.project_name ?? '')}</span>
          <span aria-hidden>·</span>
          <span className="text-muted-foreground">
            submitted {registration.submitted_date ? fmtDate(registration.submitted_date) : 'date not recorded'}
          </span>
          {(status === 'WITHDRAWN' || status === 'SUPERSEDED') && (
            <span className="text-muted-foreground">
              · {labelForValue('partners__registration_status', status)}
            </span>
          )}
        </>
      ) : (
        <span className="text-muted-foreground">This registration was deleted.</span>
      )}
      {won === true && (
        <span className="ml-auto font-medium text-emerald-700 dark:text-emerald-400">Awarded</span>
      )}
    </div>
  )
}

function AdjudicationCard({ conflict, registrations }: { conflict: Values; registrations: Values[] }) {
  const queryClient = useQueryClient()
  // An open conflict opens straight into the form: there is nothing to read yet.
  const [editing, setEditing] = useState(!conflict.decision)

  const a = registrations.find((r) => r.id === conflict.registration_a)
  const b = registrations.find((r) => r.id === conflict.registration_b)
  const primary = registrations.find((r) => r.id === conflict.primary_registration)

  const winner = adjudicationWinner(conflict)
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

  return (
    <div className="rounded-lg border">
      <div className="flex flex-wrap items-center justify-between gap-2 border-b px-4 py-3">
        <div className="min-w-0">
          <p className="text-sm font-semibold">
            {String(conflict.name ?? `Conflict: ${partnerOf(a)} vs ${partnerOf(b)}`)}
          </p>
          <p className="text-muted-foreground mt-0.5 text-sm">
            {decided
              ? `Decided${conflict.decision_date ? ` ${fmtDate(conflict.decision_date)}` : ''}: ${labelForValue('partners__decision', conflict.decision)}.`
              : 'Awaiting adjudication — assess the criteria, then record the decision and the evidence behind it.'}
          </p>
        </div>
        {!editing && (
          <Button variant="outline" size="sm" onClick={() => setEditing(true)}>
            <PencilIcon className="size-4" />
            Edit adjudication
          </Button>
        )}
      </div>

      {/* Both pursued — neither registration lost, so there is nothing to
          supersede. There is a pursuit group instead, which keeps the two
          pursuits from both reaching the pipeline. First on the card: it is
          the outcome, and it was easy to miss below the form. */}
      {!editing && String(conflict.decision ?? '') === 'BOTH_PURSUED' && (
        <div className="px-4 pt-3">
          <div className="space-y-2 rounded-md border border-sky-500/40 bg-sky-500/10 p-3 text-sm">
            <p className="font-medium">Both registrations are pursued</p>
            <p className="text-muted-foreground">
              Only {primary ? `${partnerOf(primary)}'s` : "the primary registration's"} pursuit counts toward pipeline.
              Each registration's lead joins the pursuit group when it is created; the primary can be changed from
              any pursuit's Related tab.
            </p>
            {typeof conflict.pursuit_group === 'string' && <PursuitGroupSummary groupId={conflict.pursuit_group} />}
          </div>
        </div>
      )}

      <div className="space-y-2 px-4 py-3">
        <SlotRow slot="A" registration={a} won={winner ? winner === String(a?.id) : null} />
        <SlotRow slot="B" registration={b} won={winner ? winner === String(b?.id) : null} />
        <p className="text-muted-foreground text-xs">Registration A is the one submitted first.</p>
      </div>

      <div className="border-t px-4 py-3">
        {editing ? (
          <RecordEditor
            key={`edit:${String(conflict.id)}`}
            module={MODULE}
            collection={COLLECTION}
            recordId={String(conflict.id)}
            initialValues={conflict}
            sections={[SECTION]}
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
        ) : (
          <RecordForm
            key={`view:${String(conflict.id)}:${String(conflict.modified_date ?? '')}`}
            module={MODULE}
            mode="view"
            values={conflict}
            sections={[SECTION]}
          />
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
