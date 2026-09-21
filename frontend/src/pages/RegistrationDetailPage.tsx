import { useMemo, useState } from 'react'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  AlertTriangleIcon,
  BanIcon,
  CheckCircle2Icon,
  ClockIcon,
  ExternalLinkIcon,
  PencilIcon,
  TargetIcon,
  Trash2Icon,
} from 'lucide-react'

import { Button } from '@/components/ui/button'
import { PageLayout } from '@/components/layout/PageLayout'
import { RecordForm } from '@/components/form/RecordForm'
import { RecordEditor } from '@/components/record/RecordEditor'
import { AcknowledgeDialog } from '@/components/partners/AcknowledgeDialog'
import { ConflictPanel } from '@/components/partners/ConflictPanel'
import { DeleteRegistrationDialog } from '@/components/partners/DeleteRegistrationDialog'
import { RegistrationStatusChip } from '@/components/partners/RegistrationStatusChip'
import { WithdrawRegistrationDialog } from '@/components/partners/WithdrawRegistrationDialog'
import { RecordTimelineTab, type RelatedTrail } from '@/components/pipeline/RecordTimelineTab'
import { PursuitSaveResolver } from '@/components/pursuits/PursuitSaveResolver'
import { api } from '@/lib/api'
import { ErrorNotice } from '@/components/ui/notice'
import { date as fmtDate, money } from '@/lib/format'
import { ackSlaText, daysRemainingText, registrationState } from '@/lib/partners'
import { answerableRefusalOf } from '@/lib/pursuitGroups'
import {
  invalidateRegistrationWorld,
  LIVE_REGISTRATION_STATUSES,
  usePossibleConflicts,
} from '@/lib/registrations'
import { displayNameOf, idOf, withRecordId } from '@/lib/spec'
import type { AuditRow } from '@/lib/timeline'
import { cn } from '@/lib/utils'

const MODULE = 'partners'
const COLLECTION = 'registrations'
const SECTION = 'DEAL REGISTRATION'
const CONFLICT_SECTION = 'CONFLICT ADJUDICATION'

type Row = Record<string, unknown>
type Labels = Record<string, string> | undefined

export function RegistrationDetailPage() {
  const { id } = useParams<{ id: string }>()
  const [search] = useSearchParams()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [editing, setEditing] = useState(false)
  const [acknowledging, setAcknowledging] = useState(false)
  const [withdrawing, setWithdrawing] = useState(false)
  const [deleting, setDeleting] = useState(false)
  /**
   * Tracked because the header Edit button only edits the REGISTRATION.
   * Pressing it from the Conflict tab opened an editor on a tab the reader was
   * not looking at, so it read as a button that did nothing. The adjudication
   * has its own Edit inside the Conflict panel. `?tab=conflict` lands here
   * straight after a save that raised a conflict.
   */
  const [tab, setTab] = useState(() => search.get('tab') ?? 'registration')

  const { data, isLoading, isError, dataUpdatedAt } = useQuery({
    queryKey: ['record', COLLECTION, id],
    queryFn: async () => (await api.get<Row>(`/${COLLECTION}/${id}`)).data,
    enabled: Boolean(id),
  })

  // Shared cache key with LookupCombobox, so the names on this page cost no
  // extra request once any lookup on the record has been opened.
  const { data: accounts } = useQuery({
    queryKey: ['collection', 'accounts'],
    queryFn: async () => (await api.get<Row[]>('/accounts')).data,
    staleTime: 30_000,
  })

  const { data: allRegistrations } = useQuery({
    queryKey: ['collection', COLLECTION],
    queryFn: async () => (await api.get<Row[]>(`/${COLLECTION}`)).data,
    staleTime: 30_000,
  })

  // Conflict records. Raised by the server when a similar project is saved —
  // see backend/app/registration_matching.py.
  const { data: allConflicts } = useQuery({
    queryKey: ['collection', 'conflicts'],
    queryFn: async () => (await api.get<Row[]>('/conflicts')).data,
    staleTime: 30_000,
  })

  const { data: candidates } = usePossibleConflicts(id)

  const values = useMemo(() => (data ? withRecordId(MODULE, data) : undefined), [data])
  const state = useMemo(() => registrationState(values), [values])
  const labels = values?.__labels as Labels

  const nameOf = (accountId: unknown): string => {
    const hit = (accounts ?? []).find((a) => idOf(a) === accountId)
    return hit ? displayNameOf(hit) : String(accountId ?? '—')
  }

  const partnerName = labels?.partner ?? nameOf(values?.partner)
  const clientName = labels?.end_client ?? nameOf(values?.end_client)
  const createdByName = labels?.created_by
  const registrationName = String(values?.name ?? values?.project_name ?? '')

  const statusKey = String(values?.registration_status ?? '')
  const withdrawn = statusKey === 'WITHDRAWN'
  const canWithdraw = Boolean(values) && LIVE_REGISTRATION_STATUSES.has(statusKey)

  const conflicts = useMemo(
    () => (allConflicts ?? []).filter((c) => c.registration_a === id || c.registration_b === id),
    [allConflicts, id]
  )

  // Every conflict recorded against this registration — their audit trails
  // merge into the History tab, named by the partners involved.
  const conflictTrails = useMemo<RelatedTrail[]>(
    () =>
      conflicts.map((c) => ({
        auditModule: 'conflicts',
        recordId: String(c.id),
        module: MODULE,
        sections: [CONFLICT_SECTION],
        noun: String(c.name ?? 'conflict adjudication'),
      })),
    [conflicts]
  )

  /**
   * Create the lead this registration protects: end client and partner from
   * the registration, deal_source Partner-sourced, and
   * leads.partner_deal_registration pointing back here. The registration's own
   * linked_lead is written in the same move, so the two sides agree.
   */
  const createLead = useMutation({
    // `extra` answers the server when another open pursuit already names this
    // End Client — join its group, or say why this is a different project. A
    // registration in a "Both pursued" conflict never asks: the lead joins that
    // conflict's group on its own. See PursuitSaveResolver.
    mutationFn: async (extra?: Row) => {
      const lead = (
        await api.post<Row>('/leads', {
          ...extra,
          opportunity_name: values?.project_name ?? '',
          end_client: values?.end_client ?? null,
          customer_partner_si: values?.partner ?? null,
          deal_source: 'PARTNER_SOURCED',
          partner_deal_registration: id,
          // No not_duplicate_reason from the registration here. The server
          // applies Partners' "different project" answer, and only to the
          // pursuits it was given about; any other open pursuit at this End
          // Client is still asked about, with that answer pre-filled. See
          // backend/app/pursuits.py::guard_possible_duplicate.
          estimated_value: values?.estimated_value ?? null,
          // One Currency field on both records, so the lead's value is in the
          // registration's currency. Blank falls to the server's USD.
          currency: values?.currency ?? null,
          project_stage: '0_CONNECT',
        })
      ).data
      const leadId = idOf(lead)
      await api.patch(`/${COLLECTION}/${id}`, { linked_lead: leadId })
      return leadId
    },
    // A refusal can mean the lead already exists — REGISTRATION_HAS_LEAD, from
    // an earlier press whose response never arrived. Refetching swaps Create
    // lead for the Open lead button.
    onError: () => void invalidateRegistrationWorld(queryClient),
    onSuccess: async (leadId) => {
      await invalidateRegistrationWorld(queryClient)
      // Straight into Edit: a lead made from a registration still has required
      // Stage 0 fields the registration cannot supply.
      navigate(`/leads/${leadId}`, { state: { editOnOpen: true } })
    },
  })

  if (isError) {
    return (
      <PageLayout
        back
        title="Registration"
        tabs={[
          {
            key: 'missing',
            label: 'Registration',
            content: <p className="py-6 text-sm text-destructive">This deal registration does not exist.</p>,
          },
        ]}
      />
    )
  }

  const linkedLead = typeof values?.linked_lead === 'string' ? values.linked_lead : ''

  return (
    <>
    <PageLayout
      back
      title={
        <>
          {String(values?.project_name ?? '')}
          <span aria-hidden className="text-muted-foreground font-normal">-</span>
          <RegistrationStatusChip
            state={state}
            showDays
            className="text-muted-foreground text-base font-normal"
          />
        </>
      }
      subtitle={
        values ? (
          <span className="flex flex-wrap items-center gap-x-2 gap-y-1">
            {values.partner ? (
              <Link className="hover:text-foreground underline underline-offset-2" to={`/partners/${values.partner}`}>
                {partnerName}
              </Link>
            ) : (
              <span className="text-destructive">No partner</span>
            )}
            <span aria-hidden>→</span>
            <Link className="hover:text-foreground underline underline-offset-2" to={`/accounts/${values.end_client}`}>
              {clientName}
            </Link>
            {typeof values.estimated_value === 'number' && (
              <>
                <span aria-hidden>·</span>
                <span>
                  {typeof values.currency === 'string' && values.currency ? `${values.currency} ` : ''}
                  {money(values.estimated_value)} estimated
                </span>
              </>
            )}
            {/* When it was ENTERED, server-stamped — not Submitted Date, which is
                the partner's own date and may legitimately be earlier. Absent
                on registrations created before migration 0024 recorded it. */}
            {typeof values.created_date === 'string' && (
              <>
                <span aria-hidden>·</span>
                <span>
                  Registered {fmtDate(values.created_date)}
                  {createdByName && ` by ${createdByName}`}
                </span>
              </>
            )}
          </span>
        ) : undefined
      }
      actions={
        !editing && (
          <>
            {state.protected && !linkedLead && (
              <Button onClick={() => createLead.mutate(undefined)} disabled={createLead.isPending}>
                <TargetIcon className="size-4" />
                {createLead.isPending ? 'Creating…' : 'Create lead'}
              </Button>
            )}
            {linkedLead && (
              <Button variant="outline" onClick={() => navigate(`/leads/${linkedLead}`)}>
                <ExternalLinkIcon className="size-4" />
                {labels?.linked_lead ?? 'Open lead'}
              </Button>
            )}
            {tab === 'registration' && !withdrawn && (
              <Button variant="outline" onClick={() => setEditing(true)} disabled={isLoading}>
                <PencilIcon className="size-4" />
                Edit
              </Button>
            )}
            {canWithdraw && (
              <Button variant="outline" onClick={() => setWithdrawing(true)}>
                <BanIcon className="size-4" />
                Withdraw
              </Button>
            )}
            {values && (
              <Button variant="outline" onClick={() => setDeleting(true)}>
                <Trash2Icon className="size-4" />
                Delete
              </Button>
            )}
          </>
        )
      }
      activeTab={tab}
      onTabChange={setTab}
      tabs={[
        {
          key: 'registration',
          label: 'Registration',
          content: isLoading || !values ? (
            <p className="py-6 text-sm text-muted-foreground">Loading…</p>
          ) : (
            <div className="space-y-3 py-3">
              <LifecycleBanner
                state={state}
                onAcknowledge={() => setAcknowledging(true)}
                acknowledgedDate={values.acknowledged_date}
                withdrawnDate={values.withdrawn_date}
                withdrawalReason={values.withdrawal_reason}
              />

              {createLead.isError && !answerableRefusalOf(createLead.error) && (
                <ErrorNotice error={createLead.error} fallback="The lead wasn't created. Try again." />
              )}
              {createLead.isError && (
                <PursuitSaveResolver
                  error={createLead.error}
                  pending={createLead.isPending}
                  retry={(extra) => createLead.mutate(extra)}
                />
              )}

              {editing ? (
                <RecordEditor
                  key={`edit:${id}:${dataUpdatedAt}`}
                  module={MODULE}
                  collection={COLLECTION}
                  recordId={id}
                  initialValues={values}
                  sections={[SECTION]}
                  onSaved={(_savedId, record) => {
                    setEditing(false)
                    void invalidateRegistrationWorld(queryClient)
                    if (Array.isArray(record.raised_conflicts) && record.raised_conflicts.length > 0) {
                      setTab('conflict')
                    }
                  }}
                  onCancel={() => setEditing(false)}
                />
              ) : (
                <RecordForm
                  key={`view:${id}:${dataUpdatedAt}`}
                  module={MODULE}
                  mode="view"
                  values={values}
                  sections={[SECTION]}
                />
              )}

              <AcknowledgeDialog
                open={acknowledging}
                registration={values}
                partnerName={partnerName}
                clientName={clientName}
                onClose={() => setAcknowledging(false)}
              />
            </div>
          ),
        },
        {
          key: 'conflict',
          label:
            conflicts.length + (candidates?.length ?? 0) > 0
              ? `Conflict (${conflicts.length + (candidates?.length ?? 0)})`
              : 'Conflict',
          content: (
            <ConflictPanel
              registration={values}
              conflicts={conflicts}
              registrations={allRegistrations ?? []}
              candidates={withdrawn ? [] : (candidates ?? [])}
            />
          ),
        },
        {
          key: 'history',
          label: 'History',
          content: id ? (
            <div className="py-3">
              <RecordTimelineTab
                module={MODULE}
                recordId={id}
                noun="registration"
                sections={[SECTION]}
                showConversions={false}
                related={conflictTrails}
                summaryOf={registrationSummary}
              />
            </div>
          ) : null,
        },
      ]}
    />

    {values && id && (
      <>
        <WithdrawRegistrationDialog
          open={withdrawing}
          registrationId={id}
          registrationName={registrationName}
          onClose={() => setWithdrawing(false)}
        />
        <DeleteRegistrationDialog
          open={deleting}
          registrationId={id}
          registrationName={registrationName}
          canWithdraw={canWithdraw}
          onWithdrawInstead={() => {
            setDeleting(false)
            setWithdrawing(true)
          }}
          onClose={() => setDeleting(false)}
          onDeleted={() => navigate('/partners', { replace: true })}
        />
      </>
    )}
    </>
  )
}

/**
 * The saves on a registration that mean more than the fields they wrote.
 *
 * Acknowledging stamps five fields in one PUT; without a headline the timeline
 * collapses it to "5 fields were updated", which hides the one event §6.2 is
 * about. Read off the diff itself, never off a flag the browser sent.
 */
function registrationSummary(row: AuditRow): string | undefined {
  const change = (field: string) => (row.changed ?? []).find((c) => c.field === field)
  const blank = (v: unknown) => v === null || v === undefined || v === ''

  const ack = change('acknowledged_date')
  if (ack && blank(ack.from) && !blank(ack.to)) return 'Registration was acknowledged'

  const status = change('registration_status')
  if (status?.to === 'WITHDRAWN') return 'Registration was withdrawn'
  if (status?.to === 'SUPERSEDED') return 'Registration was superseded'
  if (status?.to === 'REJECTED') return 'Registration was rejected'

  const lead = change('linked_lead')
  if (lead && blank(lead.from) && !blank(lead.to)) return 'A lead was created from this registration'

  if (change('not_conflict_with')) return 'Recorded as a different project from a similar registration'

  return undefined
}

function dayCount(n: number): string {
  return `${n} ${n === 1 ? 'day' : 'days'}`
}

/** "Acknowledgement due within 2 days" → "… 1 day" → "… today" → "overdue by 3 days". */
function ackCountdownText(daysLeft: number | null): string {
  if (daysLeft === null) return 'Acknowledgement due'
  if (daysLeft < 0) return `Acknowledgement overdue by ${dayCount(-daysLeft)}`
  if (daysLeft === 0) return 'Acknowledgement due today'
  return `Acknowledgement due within ${dayCount(daysLeft)}`
}

/**
 * Amber until acknowledged, green after — and grey once the registration has
 * ended by a person's decision (withdrawn, superseded, rejected), where an
 * acknowledgement countdown would be a clock for something that is over.
 */
function LifecycleBanner({
  state,
  onAcknowledge,
  acknowledgedDate,
  withdrawnDate,
  withdrawalReason,
}: {
  state: ReturnType<typeof registrationState>
  onAcknowledge: () => void
  acknowledgedDate: unknown
  withdrawnDate: unknown
  withdrawalReason: unknown
}) {
  if (state.state === 'withdrawn' || state.state === 'superseded' || state.state === 'rejected') {
    return (
      <div className="bg-muted/50 flex flex-wrap items-start gap-3 rounded-lg border p-3 text-sm">
        <BanIcon className="text-muted-foreground mt-0.5 size-4 shrink-0" />
        <div className="min-w-0 flex-1">
          <p className="font-medium">
            {state.label}
            {state.state === 'withdrawn' && typeof withdrawnDate === 'string' ? ` ${fmtDate(withdrawnDate)}` : ''}
          </p>
          {state.state === 'withdrawn' && typeof withdrawalReason === 'string' && withdrawalReason && (
            <p className="text-muted-foreground">“{withdrawalReason}”</p>
          )}
          <p className="text-muted-foreground">This registration no longer confers exclusivity and is read-only.</p>
        </div>
      </div>
    )
  }

  if (!state.acknowledged) {
    return (
      <div
        className={cn(
          'flex flex-wrap items-center gap-3 rounded-lg border p-3 text-sm',
          state.ackOverdue
            ? 'border-rose-500/40 bg-rose-500/10'
            : 'border-amber-500/40 bg-amber-500/10'
        )}
      >
        {state.ackOverdue ? (
          <AlertTriangleIcon className="size-4 shrink-0 text-rose-600 dark:text-rose-400" />
        ) : (
          <ClockIcon className="size-4 shrink-0 text-amber-600 dark:text-amber-400" />
        )}

        {/* A live countdown to the due date, recomputed from today on every
            render — not the SLA constant. Submitted today reads 2, tomorrow 1,
            on the due date "today", after it "overdue by". */}
        <ul className="min-w-0 flex-1 list-disc space-y-0.5 pl-5">
          <li className="font-medium">{ackCountdownText(state.ackDaysLeft)}</li>
          {state.ackDueBy ? (
            <li>
              {state.ackOverdue ? 'Was due by' : 'Due by'} {fmtDate(state.ackDueBy)}.
            </li>
          ) : (
            <li>No submitted date, so no due date can be set.</li>
          )}
          <li>Exclusivity has not started — it runs from the acknowledgement, not the submission.</li>
        </ul>

        <Button size="sm" onClick={onAcknowledge}>
          Acknowledge now
        </Button>
      </div>
    )
  }

  return (
    <div className="flex flex-wrap items-center gap-3 rounded-lg border border-emerald-500/40 bg-emerald-500/10 p-3 text-sm">
      <CheckCircle2Icon className="size-4 shrink-0 text-emerald-600 dark:text-emerald-400" />
      <div className="min-w-0 flex-1">
        <p className="font-medium">
          Acknowledged {fmtDate(acknowledgedDate)}
          {state.expiry && ` · exclusive until ${fmtDate(state.expiry)}`}
        </p>
        <p className="text-muted-foreground">
          {ackSlaText(state)}.{' '}
          {state.protected
            ? `${daysRemainingText(state)}. Astrikos will not support a competing partner on this project while the window is open.`
            : state.state === 'expired'
              ? `The window ${daysRemainingText(state)}. Astrikos may now support a competing partner if the deal has not progressed.`
              : 'This registration no longer confers exclusivity.'}
        </p>
      </div>
    </div>
  )
}
