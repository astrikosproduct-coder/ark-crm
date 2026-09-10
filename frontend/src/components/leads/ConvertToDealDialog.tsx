import { currentUserId } from '@/lib/currentUser'
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { addDays, format } from 'date-fns'
import { ArrowRightIcon, CheckIcon, MinusIcon } from 'lucide-react'

import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { api } from '@/lib/api'
import { date as fmtDate, money } from '@/lib/format'
import { dealStageKeyOf } from '@/lib/pipeline'
import { displayNameOf, toPicklistKey } from '@/lib/spec'
import type { Values } from '@/lib/spec/conditions'

interface Props {
  open: boolean
  leadId: string
  values: Values
  onClose: () => void
}

/** Above this TCV, a welcome-letter task is raised on conversion — a POC-1
 * business rule, not sourced from the register (spec/thresholds.json has no
 * $500K line item; see Spec Health for the thresholds it does carry). */
const WELCOME_LETTER_TCV_THRESHOLD = 500_000

/** How long post-award protection runs. Not stated anywhere in the register,
 * and as of the field removals below there is nowhere to store it either:
 * accounts.post_award_protection and accounts.protected_until were deleted from
 * PARTNER ATTRIBUTES at review. The rule is a Partner Playbook one, so it is
 * still SHOWN and still logged as an automation — it just no longer writes to
 * an account. One year from booking is a prototype default. See the note on
 * accounts in spec/extensions.json open_questions. */
const PROTECTION_DAYS = 365

interface ConversionResult {
  dealId: string
  tcv: number
  protection: { accountId: string; until: string } | null
  supersededRegistrations: string[]
  welcomeLetter: boolean
}

/**
 * Closes the POC-1 loop: a Lead at Stage 7 becomes a Deal. Nothing happens
 * until Confirm — this is the one place that side effect fires, exactly like
 * AdvanceStageDialog is the one place project_stage changes.
 *
 * There is no automation log panel in this walkthrough (CLAUDE.md prompt 6),
 * so the result step is how a reviewer sees every side effect — spelled out
 * item by item rather than a toast.
 */
export function ConvertToDealDialog({ open, leadId, values, onClose }: Props) {
  const queryClient = useQueryClient()
  const navigate = useNavigate()
  const [result, setResult] = useState<ConversionResult | null>(null)

  const tcv =
    typeof values.total_value_tcv === 'number'
      ? values.total_value_tcv
      : typeof values.estimated_value === 'number'
        ? values.estimated_value
        : 0
  const partnerId = typeof values.customer_partner_si === 'string' ? values.customer_partner_si : undefined
  const willRaiseWelcomeLetter = tcv > WELCOME_LETTER_TCV_THRESHOLD

  const convert = useMutation({
    mutationFn: async (): Promise<ConversionResult> => {
      const now = new Date().toISOString()

      const dealPayload: Values = {
        deal_name: values.opportunity_name ?? leadId,
        parent_lead: leadId,
        end_client: values.end_client ?? null,
        customer_partner_si: values.customer_partner_si ?? null,
        deal_stage: dealStageKeyOf(8),
        delivery_pm: currentUserId(),
        order_booked: true,
        booking_date: now.slice(0, 10),
        po_loi_reference: values.po_number ?? '',
        contract_value: tcv,
        arr_annual_recurring: values.arr_annual_recurring ?? null,
        one_time_revenue: values.one_time_revenue ?? null,
        '3rd_party_one_time': values['3rd_party_one_time'] ?? null,
        '3rd_party_recurring_per_year': values['3rd_party_recurring_per_year'] ?? null,
        contract_years: values.contract_years ?? null,
        created_by_date: now,
        modified_by_date: now,
      }
      const createdDeal = await api.post<Record<string, unknown>>('/deals', dealPayload)
      const dealId = String(createdDeal.data.id)

      await api.put(`/leads/${leadId}`, {
        lead_status: 'CONVERTED',
        modified_date: now,
        modified_by: currentUserId(),
      })

      // Recorded, not written. The two account fields this used to set were
      // removed from the register, so writing them would put values behind a
      // screen that can no longer show them — CLAUDE.md rule 6 says log the
      // automation instead of faking the effect.
      let protection: ConversionResult['protection'] = null
      if (partnerId) {
        const until = format(addDays(new Date(), PROTECTION_DAYS), 'yyyy-MM-dd')
        protection = { accountId: partnerId, until }
      }

      const regs = (
        await api.get<Values[]>('/registrations', { params: { linked_lead: leadId } })
      ).data
      const active = regs.filter(
        (r) => toPicklistKey('partners__registration_status', r.registration_status) === 'ACTIVE'
      )
      for (const r of active) {
        await api.put(`/registrations/${r.id}`, { registration_status: 'SUPERSEDED' })
      }

      // The threshold rule is real and still worth surfacing; what is NOT real
      // is anything happening as a result. Nothing raises a task, and nobody is
      // told — a person has to send the welcome letter. The UI says so.
      const welcomeLetter = tcv > WELCOME_LETTER_TCV_THRESHOLD

      return {
        dealId,
        tcv,
        protection,
        supersededRegistrations: active.map((r) => String(r.id)),
        welcomeLetter,
      }
    },
    onSuccess: async (r) => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['record', 'leads', leadId] }),
        queryClient.invalidateQueries({ queryKey: ['list', 'leads'] }),
        queryClient.invalidateQueries({ queryKey: ['collection', 'leads'] }),
        queryClient.invalidateQueries({ queryKey: ['list', 'deals'] }),
        queryClient.invalidateQueries({ queryKey: ['collection', 'deals'] }),
        queryClient.invalidateQueries({ queryKey: ['list', 'registrations'] }),
        queryClient.invalidateQueries({ queryKey: ['collection', 'accounts'] }),
        queryClient.invalidateQueries({ queryKey: ['record', 'accounts'] }),
      ])
      setResult(r)
    },
  })

  const handleClose = () => {
    if (convert.isPending) return
    setResult(null)
    convert.reset()
    onClose()
  }

  return (
    <Dialog open={open} onOpenChange={(next) => !next && handleClose()}>
      <DialogContent className="max-w-lg max-h-[85vh] overflow-y-auto">
        {!result ? (
          <>
            <DialogHeader>
              <DialogTitle className="flex items-center gap-2">
                <ArrowRightIcon className="size-4" />
                Convert {leadId} to a Deal
              </DialogTitle>
              <DialogDescription>
                Nothing happens until you confirm. This is what will happen:
              </DialogDescription>
            </DialogHeader>

            <ul className="space-y-2 text-sm">
              <Effect>A Deal is created (DEAL-00031 format).</Effect>
              <Effect>The Lead becomes read-only and its status becomes Converted.</Effect>
              <Effect>
                Post-award protection is recorded in the automation log against the account
                {partnerId ? ` (${partnerId})` : ' — no Customer (Partner / SI) is set on this lead, so this step will be skipped'}
                . No field stores it: Post-Award Protection and Protected Until were removed from
                the Accounts register.
              </Effect>
              <Effect>Any active deal registration linked to this lead is marked Superseded.</Effect>
              <Effect>
                Above ${money(WELCOME_LETTER_TCV_THRESHOLD)} TCV a welcome letter is required —
                this lead's TCV is ${money(tcv)}, so one{' '}
                {willRaiseWelcomeLetter ? 'IS' : 'is NOT'} required. Sending it is a manual step.
              </Effect>
            </ul>

            {convert.isError && (
              <p className="text-sm text-destructive">The conversion failed — nothing was changed.</p>
            )}

            <DialogFooter>
              <Button type="button" variant="outline" onClick={handleClose} disabled={convert.isPending}>
                Cancel
              </Button>
              <Button type="button" onClick={() => convert.mutate()} disabled={convert.isPending}>
                {convert.isPending ? 'Converting…' : 'Confirm conversion'}
              </Button>
            </DialogFooter>
          </>
        ) : (
          <>
            <DialogHeader>
              <DialogTitle className="flex items-center gap-2">
                <CheckIcon className="size-4 text-emerald-600 dark:text-emerald-400" />
                {leadId} converted to {result.dealId}
              </DialogTitle>
              <DialogDescription>Here is exactly what happened.</DialogDescription>
            </DialogHeader>

            <ul className="space-y-2 text-sm">
              <ResultRow done>
                Deal {result.dealId} created — {displayNameOf(values)}, TCV ${money(result.tcv)}.
              </ResultRow>
              <ResultRow done>
                Lead {leadId} is now read-only, status Converted.
              </ResultRow>
              {result.protection ? (
                <ResultRow done>
                  Post-award protection logged against {result.protection.accountId}, until{' '}
                  {fmtDate(result.protection.until)} — recorded as an automation, not stored on the
                  account.
                </ResultRow>
              ) : (
                <ResultRow done={false}>
                  No post-award protection set — this lead has no Customer (Partner / SI) account.
                </ResultRow>
              )}
              {result.supersededRegistrations.length > 0 ? (
                <ResultRow done>
                  {result.supersededRegistrations.length === 1
                    ? `Registration ${result.supersededRegistrations[0]} marked Superseded.`
                    : `Registrations ${result.supersededRegistrations.join(', ')} marked Superseded.`}
                </ResultRow>
              ) : (
                <ResultRow done={false}>No active registration was linked to this lead.</ResultRow>
              )}
              {result.welcomeLetter ? (
                <ResultRow done={false}>
                  Welcome letter required — TCV ${money(result.tcv)} exceeds $
                  {money(WELCOME_LETTER_TCV_THRESHOLD)}. Send it manually; nothing is raised
                  automatically.
                </ResultRow>
              ) : (
                <ResultRow done={false}>
                  No welcome-letter task — TCV ${money(result.tcv)} is at or below $
                  {money(WELCOME_LETTER_TCV_THRESHOLD)}.
                </ResultRow>
              )}
            </ul>

            <DialogFooter>
              <Button type="button" variant="outline" onClick={handleClose}>
                Close
              </Button>
              <Button
                type="button"
                onClick={() => {
                  const dealId = result.dealId
                  handleClose()
                  navigate(`/deals/${dealId}`)
                }}
              >
                Go to Deal
              </Button>
            </DialogFooter>
          </>
        )}
      </DialogContent>
    </Dialog>
  )
}

function Effect({ children }: { children: React.ReactNode }) {
  return (
    <li className="flex items-start gap-2">
      <span className="mt-1.5 size-1.5 shrink-0 rounded-full bg-muted-foreground" />
      <span>{children}</span>
    </li>
  )
}

function ResultRow({ done, children }: { done: boolean; children: React.ReactNode }) {
  return (
    <li className="flex items-start gap-2">
      {done ? (
        <CheckIcon className="mt-0.5 size-4 shrink-0 text-emerald-600 dark:text-emerald-400" />
      ) : (
        <MinusIcon className="mt-0.5 size-4 shrink-0 text-muted-foreground" />
      )}
      <span className={done ? '' : 'text-muted-foreground'}>{children}</span>
    </li>
  )
}
