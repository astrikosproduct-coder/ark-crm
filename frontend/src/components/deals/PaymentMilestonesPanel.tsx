import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { Button } from '@/components/ui/button'
import { FieldControl } from '@/components/form/FieldControl'
import type { PipelineRecordContext } from '@/components/pipeline/types'
import { ErrorNotice } from '@/components/ui/notice'
import { api } from '@/lib/api'
import { fieldOf } from '@/lib/spec'
import { childSpecFor } from '@/lib/spec/childSpec'
import type { Values } from '@/lib/spec/conditions'

/** Project Success — where a milestone is delivered, invoiced and paid. */
const DELIVERY_STAGE = 8

/** The payment schedule is the Opportunity's field; these rows are its rows. */
const SCHEDULE_FIELD = fieldOf('opportunities', 'payment_milestones')

function detailCodeOf(error: unknown): string | undefined {
  const response = (error as { response?: { data?: { detail?: { code?: string } } } })?.response
  return response?.data?.detail?.code
}

/**
 * Payment milestones on a Deal at Stage 8 — the delivery half of a schedule
 * agreed on the Opportunity at Stage 6.
 *
 * ONE SET OF ROWS, NOT A COPY. The table is opportunity_payment_milestones,
 * reached through the Deal's parent_opportunity: a percentage can then never
 * disagree with itself in two places, and the Opportunity stays read-only
 * where it should be. This screen may write four columns — Actual Date,
 * Invoice Date, Payment Received Date and Status — and the server refuses the
 * rest, because a delivery screen that could rewrite the payment schedule
 * would be a way to change the deal after it was signed.
 *
 * The columns are not written here either: they are the SAME child_spec
 * columns the Opportunity's table draws (spec/extensions.json,
 * captured_elsewhere), resolved through the same FieldControl every other
 * field on the screen goes through.
 */
export function DealPaymentMilestones({ ctx }: { ctx: PipelineRecordContext }) {
  const queryClient = useQueryClient()
  const [draft, setDraft] = useState<Values[] | null>(null)

  const spec = SCHEDULE_FIELD ? childSpecFor(SCHEDULE_FIELD) : undefined

  const { data, error, isLoading } = useQuery({
    queryKey: ['deal-milestones', ctx.id],
    queryFn: async () => (await api.get<Values[]>(`/deals/${ctx.id}/payment-milestones`)).data,
    enabled: Boolean(ctx.id) && ctx.stageToShow === DELIVERY_STAGE,
    retry: false,
  })

  const save = useMutation({
    mutationFn: async (rows: Values[]) =>
      (
        await api.put<Values[]>(
          `/deals/${ctx.id}/payment-milestones`,
          rows.map((row) => ({
            row_order: row.row_order,
            ...Object.fromEntries(
              (spec?.elsewhereColumns ?? []).map((c) => [c.field.api_name, row[c.field.api_name] ?? null])
            ),
          }))
        )
      ).data,
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['deal-milestones', ctx.id] })
      await queryClient.invalidateQueries({ queryKey: ['record', 'opportunities'] })
      setDraft(null)
    },
  })

  if (ctx.stageToShow !== DELIVERY_STAGE || !spec) return null

  // A Deal converted straight from a Lead never had an Opportunity, so there
  // is no agreed schedule to deliver against. Said plainly rather than drawn
  // as an empty table that looks like data nobody has entered yet.
  const code = detailCodeOf(error)
  if (code === 'NO_PARENT_OPPORTUNITY' || code === 'PARENT_OPPORTUNITY_MISSING') {
    return (
      <div className="bg-card mt-4 rounded-lg p-4 text-sm shadow-sm">
        <h3 className="text-sm font-semibold">Payment Milestones</h3>
        <p className="text-muted-foreground mt-1">
          No payment schedule was agreed on an Opportunity for this Deal. Milestones are captured at
          Stage 6 — Commercial Evaluation.
        </p>
      </div>
    )
  }

  const rows = draft ?? data ?? []
  const editing = draft !== null
  const columns = [...spec.columns, ...spec.elsewhereColumns]

  return (
    <div className="bg-card mt-4 space-y-3 rounded-lg p-4 shadow-sm">
      <div className="flex items-center justify-between gap-3">
        <div>
          <h3 className="text-sm font-semibold">Payment Milestones</h3>
          <p className="text-muted-foreground text-xs">
            The schedule was agreed on the Opportunity and is read-only here. Record when each
            milestone was delivered, invoiced and paid.
          </p>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          {editing ? (
            <>
              <Button variant="outline" size="sm" onClick={() => setDraft(null)} disabled={save.isPending}>
                Cancel
              </Button>
              <Button size="sm" onClick={() => save.mutate(rows)} disabled={save.isPending}>
                {save.isPending ? 'Saving…' : 'Save'}
              </Button>
            </>
          ) : (
            !ctx.readOnly &&
            (data?.length ?? 0) > 0 && (
              <Button variant="outline" size="sm" onClick={() => setDraft(data ?? [])}>
                Edit delivery
              </Button>
            )
          )}
        </div>
      </div>

      {save.isError && <ErrorNotice error={save.error} />}
      {error && !code && <ErrorNotice error={error} />}

      {isLoading ? (
        <p className="text-muted-foreground text-sm">Loading…</p>
      ) : rows.length === 0 ? (
        <p className="text-muted-foreground text-sm">
          No milestones were entered on the Opportunity's payment schedule.
        </p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full border-separate border-spacing-0 text-sm">
            <thead>
              <tr>
                {columns.map((c) => (
                  <th
                    key={c.key}
                    className="border-border text-muted-foreground border-b px-4 pt-1 pb-2.5 text-left font-semibold whitespace-nowrap"
                  >
                    {c.field.label}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((row, i) => (
                <tr key={String(row.row_order ?? i)} className="even:bg-raised/60 align-top">
                  {columns.map((c) => {
                    const agreed = spec.columns.includes(c)
                    return (
                      <td key={c.key} className="px-4 py-2.5">
                        <FieldControl
                          field={c.field}
                          scope={{
                            value: row[c.field.api_name],
                            set: (v) =>
                              setDraft(
                                rows.map((r, ri) => (ri === i ? { ...r, [c.field.api_name]: v } : r))
                              ),
                            invalid: false,
                            mode: agreed || !editing ? 'view' : 'edit',
                            id: `deal-milestone.${i}.${c.field.api_name}`,
                          }}
                        />
                      </td>
                    )
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
