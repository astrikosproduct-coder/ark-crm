import { useMemo, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  AlertTriangleIcon,
  CheckCircle2Icon,
  ClockIcon,
  ExternalLinkIcon,
  PencilIcon,
  TargetIcon,
} from 'lucide-react'

import { Button } from '@/components/ui/button'
import { PageLayout } from '@/components/layout/PageLayout'
import { RecordForm } from '@/components/form/RecordForm'
import { RecordEditor } from '@/components/record/RecordEditor'
import { UnsavedBadge } from '@/components/record/UnsavedBadge'
import { AcknowledgeDialog } from '@/components/partners/AcknowledgeDialog'
import { ConflictPanel } from '@/components/partners/ConflictPanel'
import { RegistrationStatusChip } from '@/components/partners/RegistrationStatusChip'
import { NEW_RECORD_ID } from '@/hooks/useRecordForm'
import { api } from '@/lib/api'
import { logAutomation } from '@/lib/automation'
import { date as fmtDate, money } from '@/lib/format'
import {
  ACK_SLA_DAYS,
  ackSlaText,
  collidingRegistrations,
  daysRemainingText,
  registrationState,
} from '@/lib/partners'
import { displayNameOf, idOf, withRecordId } from '@/lib/spec'
import { cn } from '@/lib/utils'
import { useDiscardToken } from '@/store/useDraftStore'

const MODULE = 'partners'
const COLLECTION = 'registrations'
const SECTION = 'DEAL REGISTRATION'

type Row = Record<string, unknown>

export function RegistrationDetailPage() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [editing, setEditing] = useState(false)
  const [acknowledging, setAcknowledging] = useState(false)
  /**
   * Tracked because the header Edit button only edits the REGISTRATION.
   * Pressing it from the Conflict tab opened an editor on a tab the reader was
   * not looking at, so it read as a button that did nothing. The adjudication
   * has its own Edit inside the Conflict panel.
   */
  const [tab, setTab] = useState('registration')

  const draftId = id ?? NEW_RECORD_ID
  const discardToken = useDiscardToken(MODULE, draftId)

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

  // Adjudications already recorded. A separate collection because the register
  // makes CONFLICT ADJUDICATION its own record, with its own autonumber and two
  // lookups back to the registrations it weighs.
  const { data: allConflicts } = useQuery({
    queryKey: ['collection', 'conflicts'],
    queryFn: async () => (await api.get<Row[]>('/conflicts')).data,
    staleTime: 30_000,
  })

  const values = useMemo(() => (data ? withRecordId(MODULE, data) : undefined), [data])
  const state = useMemo(() => registrationState(values), [values])

  const nameOf = (accountId: unknown): string => {
    const hit = (accounts ?? []).find((a) => idOf(a) === accountId)
    return hit ? displayNameOf(hit) : String(accountId ?? '—')
  }

  const partnerName = nameOf(values?.partner)
  const clientName = nameOf(values?.end_client)

  const conflicts = useMemo(
    () => (values ? collidingRegistrations(values, allRegistrations ?? []) : []),
    [values, allRegistrations]
  )

  /**
   * Create the lead this registration protects.
   *
   * The Leads detail page does not exist yet, so this lands on the generic
   * spec-driven screen — but the record it writes is the real thing: end client
   * and partner from the registration, deal_source Partner-sourced, and
   * leads.partner_deal_registration pointing back here. The registration's own
   * linked_lead is written in the same move, so the two sides agree.
   */
  const createLead = useMutation({
    mutationFn: async () => {
      const lead = (
        await api.post<Row>('/leads', {
          opportunity_name: values?.project_name ?? '',
          end_client: values?.end_client ?? null,
          customer_partner_si: values?.partner ?? null,
          deal_source: 'PARTNER_SOURCED',
          partner_deal_registration: id,
          estimated_value: values?.estimated_value ?? null,
          project_stage: '0_CONNECT',
        })
      ).data
      const leadId = idOf(lead)
      await api.put(`/${COLLECTION}/${id}`, { ...values, linked_lead: leadId })
      return leadId
    },
    onSuccess: async (leadId) => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['record', COLLECTION, id] }),
        queryClient.invalidateQueries({ queryKey: ['collection', COLLECTION] }),
        queryClient.invalidateQueries({ queryKey: ['list', COLLECTION] }),
        queryClient.invalidateQueries({ queryKey: ['list', 'leads'] }),
        queryClient.invalidateQueries({ queryKey: ['collection', 'leads'] }),
      ])
      void logAutomation({
        type: 'record_update',
        target: leadId,
        module: 'leads',
        detail: `Lead ${leadId} created from registration ${id} — partner-sourced, exclusivity to ${fmtDate(
          state.expiry
        )}`,
      })
      navigate(`/leads/${leadId}`)
    },
  })

  if (isError) {
    return (
      <PageLayout
        title={id ?? 'Registration'}
        tabs={[
          {
            key: 'missing',
            label: 'Registration',
            content: (
              <p className="py-6 text-sm text-destructive">No deal registration with id {id}.</p>
            ),
          },
        ]}
      />
    )
  }

  const linkedLead = typeof values?.linked_lead === 'string' ? values.linked_lead : ''

  return (
    <PageLayout
      title={
        <>
          {String(values?.project_name ?? id ?? '')}
          <RegistrationStatusChip state={state} showDays />
          <UnsavedBadge module={MODULE} recordId={draftId} />
        </>
      }
      subtitle={
        values ? (
          <span className="flex flex-wrap items-center gap-x-2 gap-y-1">
            <span>{id}</span>
            <span aria-hidden>·</span>
            <Link className="hover:text-foreground underline underline-offset-2" to={`/partners/${values.partner}`}>
              {partnerName}
            </Link>
            <span aria-hidden>→</span>
            <Link className="hover:text-foreground underline underline-offset-2" to={`/accounts/${values.end_client}`}>
              {clientName}
            </Link>
            {typeof values.estimated_value === 'number' && (
              <>
                <span aria-hidden>·</span>
                <span>{money(values.estimated_value)} estimated</span>
              </>
            )}
          </span>
        ) : (
          id
        )
      }
      actions={
        !editing && (
          <>
            {state.protected && !linkedLead && (
              <Button onClick={() => createLead.mutate()} disabled={createLead.isPending}>
                <TargetIcon className="size-4" />
                {createLead.isPending ? 'Creating…' : 'Create lead'}
              </Button>
            )}
            {linkedLead && (
              <Button variant="outline" onClick={() => navigate(`/leads/${linkedLead}`)}>
                <ExternalLinkIcon className="size-4" />
                {linkedLead}
              </Button>
            )}
            {tab === 'registration' && (
              <Button variant="outline" onClick={() => setEditing(true)} disabled={isLoading}>
                <PencilIcon className="size-4" />
                Edit
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
              />

              {createLead.isError && (
                <p className="text-sm text-destructive">The lead could not be created.</p>
              )}

              {editing ? (
                <RecordEditor
                  key={`edit:${id}:${dataUpdatedAt}:${discardToken}`}
                  module={MODULE}
                  collection={COLLECTION}
                  recordId={id}
                  initialValues={values}
                  sections={[SECTION]}
                  onSaved={() => setEditing(false)}
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
          label: conflicts.length ? `Conflict (${conflicts.length})` : 'Conflict',
          content: (
            <ConflictPanel
              registration={values}
              colliding={conflicts}
              conflicts={allConflicts ?? []}
              nameOf={nameOf}
              onRecorded={() => {
                void queryClient.invalidateQueries({ queryKey: ['collection', 'conflicts'] })
              }}
            />
          ),
        },
      ]}
    />
  )
}

/**
 * Amber until acknowledged, green after.
 *
 * The amber state carries the deadline and the action, because a registration
 * sitting unacknowledged is the failure §6.2 is written to prevent — being the
 * partner's first call depends on answering inside the window.
 */
function LifecycleBanner({
  state,
  onAcknowledge,
  acknowledgedDate,
}: {
  state: ReturnType<typeof registrationState>
  onAcknowledge: () => void
  acknowledgedDate: unknown
}) {
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

        <div className="min-w-0 flex-1">
          <p className="font-medium">
            {state.ackOverdue
              ? `Acknowledgement overdue — was due ${fmtDate(state.ackDueBy)}`
              : `Acknowledgement due within ${ACK_SLA_DAYS} days`}
          </p>
          <p className="text-muted-foreground">
            {state.ackDueBy ? (
              <>
                {ackSlaText(state)}. Due by {fmtDate(state.ackDueBy)}. Exclusivity has not started —
                it runs from the acknowledgement, not the submission.
              </>
            ) : (
              <>{ackSlaText(state)}.</>
            )}
          </p>
        </div>

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

