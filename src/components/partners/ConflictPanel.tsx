import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { AlertTriangleIcon, CheckCircle2Icon, PencilIcon } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { RecordForm } from '@/components/form/RecordForm'
import { RecordEditor } from '@/components/record/RecordEditor'
import { api } from '@/lib/api'
import { logAutomation } from '@/lib/automation'
import { date as fmtDate } from '@/lib/format'
import { adjudicationFor, adjudicationLoser, adjudicationWinner } from '@/lib/partners'
import { fieldsInSet, partnerRegistration } from '@/lib/spec'
import type { Values } from '@/lib/spec/conditions'
import { cn } from '@/lib/utils'

const MODULE = 'partners'
const SECTION = 'CONFLICT ADJUDICATION'
const COLLECTION = 'conflicts'

/**
 * Conflict adjudication — Partner Playbook §6.2.
 *
 * Every field on this panel comes from the register's own CONFLICT ADJUDICATION
 * section: the three criteria at orders 19–21, then decision, decision_date,
 * decided_by and both_partners_notified. WHICH of them a person fills is
 * declared in spec/extensions.json — partner_registration.adjudication_criteria
 * and adjudication_outcome — not listed in this component. CLAUDE.md rule 3.
 *
 * An adjudication is a RECORD OF ITS OWN, not a patch on a registration: the
 * register gives it a conflict_id and two lookups, registration_a and
 * registration_b. It is written to the `conflicts` collection through /api like
 * every other record. The pair is stamped from the collision that raised it
 * rather than typed, because the two sides are already known.
 *
 * What the register still does not say, and this screen therefore does not
 * assume: whether ARK raises the conflict automatically or a person does, and
 * whether a decision supersedes the losing registration. Both are on Spec
 * Health, and the supersede is offered as an explicit action rather than
 * applied as a silent side effect.
 */
export function ConflictPanel({
  registration,
  colliding,
  conflicts,
  nameOf,
  onRecorded,
}: {
  registration: Values | undefined
  colliding: Values[]
  conflicts: Values[]
  nameOf: (id: unknown) => string
  onRecorded: () => void
}) {
  if (!registration) {
    return <p className="text-muted-foreground py-6 text-sm">Loading…</p>
  }

  if (colliding.length === 0) {
    return (
      <div className="space-y-4 py-3">
        <div className="rounded-lg border p-4 text-sm">
          <p className="font-medium">No competing registration</p>
          <p className="text-muted-foreground mt-1">
            No other partner has registered{' '}
            <span className="text-foreground">
              {String(registration.project_name ?? 'this project')}
            </span>{' '}
            at <span className="text-foreground">{nameOf(registration.end_client)}</span>.
            Exclusivity is granted per client and project combination, so a different project at
            the same client is not a conflict.
          </p>
          <p className="text-muted-foreground mt-2">
            The adjudication form appears here as soon as a second partner registers the same
            client and project.
          </p>
        </div>
        <CriteriaReference />
      </div>
    )
  }

  return (
    <div className="space-y-4 py-3">
      <div className="rounded-lg border border-amber-500/40 bg-amber-500/10 p-4 text-sm">
        <p className="flex items-center gap-2 font-medium">
          <AlertTriangleIcon className="size-4" />
          {colliding.length === 1
            ? 'Another partner has registered this client and project'
            : `${colliding.length} other partners have registered this client and project`}
        </p>
        <p className="text-muted-foreground mt-1">
          Detected, not raised. The register does not say whether ARK creates the conflict record
          or a person does — see Spec Health. Adjudicate each pair below.
        </p>
      </div>

      {/* One adjudication per PAIR. The register's record has exactly two
          sides, so three colliding registrations are three adjudications rather
          than one record holding a list. */}
      {colliding.map((other) => (
        <AdjudicationCard
          key={String(other.id)}
          a={registration}
          b={other}
          existing={adjudicationFor(registration.id, other.id, conflicts)}
          nameOf={nameOf}
          onRecorded={onRecorded}
        />
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
          The BD Director weighs three criteria, in the register at orders 19–21. Registration
          order alone does not decide the outcome.
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

/** Which registration fills each of the register's two slots, and who won. */
function SlotRow({
  slot,
  registration,
  nameOf,
  won,
}: {
  slot: 'A' | 'B'
  registration: Values
  nameOf: (id: unknown) => string
  won: boolean | null
}) {
  return (
    <div
      className={cn(
        'flex flex-wrap items-center gap-x-2 gap-y-1 rounded-md border px-3 py-2 text-sm',
        won === true && 'border-emerald-500/50 bg-emerald-500/10',
        won === false && 'opacity-60'
      )}
    >
      <span className="text-muted-foreground shrink-0 font-medium">Registration {slot}</span>
      <Link
        className="underline underline-offset-2"
        to={`/partners/registrations/${String(registration.id)}`}
      >
        {String(registration.id)}
      </Link>
      <span aria-hidden>·</span>
      <span>{nameOf(registration.partner)}</span>
      <span aria-hidden>·</span>
      <span className="text-muted-foreground">
        submitted {fmtDate(registration.submitted_date)}
      </span>
      {won === true && (
        <span className="ml-auto font-medium text-emerald-700 dark:text-emerald-400">Awarded</span>
      )}
    </div>
  )
}

function AdjudicationCard({
  a,
  b,
  existing,
  nameOf,
  onRecorded,
}: {
  a: Values
  b: Values
  existing: Values | undefined
  nameOf: (id: unknown) => string
  onRecorded: () => void
}) {
  const [editing, setEditing] = useState(false)
  const queryClient = useQueryClient()

  // Both field sets come from the sidecar, so what a person fills is spec
  // rather than component code. Order matters on screen: assess, then decide.
  const fillable = useMemo(
    () => [
      ...partnerRegistration.adjudication_criteria.fields,
      ...partnerRegistration.adjudication_outcome.fields,
    ],
    []
  )

  const winner = adjudicationWinner(existing)
  const loser = adjudicationLoser(existing)
  const loserRecord = loser === String(a.id) ? a : loser === String(b.id) ? b : undefined
  const loserSuperseded = String(loserRecord?.registration_status ?? '') === 'SUPERSEDED'

  const supersede = useMutation({
    mutationFn: async () => {
      if (!loser) return
      await api.put(`/registrations/${loser}`, { registration_status: 'SUPERSEDED' })
    },
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['collection', 'registrations'] }),
        queryClient.invalidateQueries({ queryKey: ['record', 'registrations'] }),
        queryClient.invalidateQueries({ queryKey: ['list', 'registrations'] }),
      ])
      void logAutomation({
        type: 'record_update',
        target: String(loser),
        detail: `Marked ${loser} Superseded following adjudication ${String(existing?.id ?? '')}`,
        module: 'partners',
      })
      onRecorded()
    },
  })

  return (
    <div className="rounded-lg border">
      <div className="flex flex-wrap items-center justify-between gap-2 border-b px-4 py-3">
        <div className="min-w-0">
          <p className="text-sm font-semibold tracking-wide">
            {SECTION}
            {existing ? ` · ${String(existing.id)}` : ''}
          </p>
          <p className="text-muted-foreground mt-0.5 text-sm">
            {existing
              ? 'Recorded against this pair.'
              : 'Assess the three criteria, then award the deal to one registration.'}
          </p>
        </div>
        {existing && !editing && (
          <Button variant="outline" size="sm" onClick={() => setEditing(true)}>
            <PencilIcon className="size-4" />
            Edit adjudication
          </Button>
        )}
      </div>

      <div className="space-y-2 px-4 py-3">
        <SlotRow
          slot="A"
          registration={a}
          nameOf={nameOf}
          won={winner ? winner === String(a.id) : null}
        />
        <SlotRow
          slot="B"
          registration={b}
          nameOf={nameOf}
          won={winner ? winner === String(b.id) : null}
        />
        <p className="text-muted-foreground text-xs">
          The register names the two sides Registration A and Registration B, and its Decision
          picklist is written in those terms. Which registration fills which slot is stamped from
          the collision, never typed.
        </p>
      </div>

      {existing && !editing ? (
        <div className="border-t px-4 py-3">
          <RecordForm
            key={`view:${String(existing.id)}`}
            module={MODULE}
            mode="view"
            values={existing}
            sections={[SECTION]}
          />

          {loser && !loserSuperseded && (
            <div className="mt-3 rounded-md border border-amber-500/40 bg-amber-500/10 p-3 text-sm">
              <p className="font-medium">{loser} has not been superseded</p>
              <p className="text-muted-foreground mt-1">
                Nothing in the register says an adjudication supersedes the registration that lost,
                so it is offered here rather than applied silently — see Spec Health.
              </p>
              <Button
                className="mt-2"
                variant="outline"
                size="sm"
                onClick={() => supersede.mutate()}
                disabled={supersede.isPending}
              >
                {supersede.isPending ? 'Marking…' : `Mark ${loser} Superseded`}
              </Button>
            </div>
          )}

          {loser && loserSuperseded && (
            <p className="text-muted-foreground mt-3 flex items-center gap-2 text-sm">
              <CheckCircle2Icon className="size-4 text-emerald-600 dark:text-emerald-400" />
              {loser} is marked Superseded.
            </p>
          )}
        </div>
      ) : (
        <div className="border-t px-4">
          <RecordEditor
            key={`edit:${String(existing?.id ?? 'new')}:${String(b.id)}`}
            module={MODULE}
            collection={COLLECTION}
            recordId={existing ? String(existing.id) : undefined}
            initialValues={existing ?? { registration_a: a.id, registration_b: b.id }}
            sections={[SECTION]}
            only={fillable}
            sectionTitle="Adjudication"
            // Stamped, never typed: the pair IS the collision that raised this.
            stamp={{ registration_a: a.id, registration_b: b.id }}
            saveLabel={existing ? 'Save adjudication' : 'Record adjudication'}
            onSaved={() => {
              setEditing(false)
              void logAutomation({
                type: 'notification',
                target: `${String(a.id)} / ${String(b.id)}`,
                detail: `Would notify both partners of the adjudication outcome for "${String(
                  a.project_name ?? ''
                )}"`,
                module: 'partners',
              })
              onRecorded()
            }}
            onCancel={() => setEditing(false)}
          />
        </div>
      )}
    </div>
  )
}
