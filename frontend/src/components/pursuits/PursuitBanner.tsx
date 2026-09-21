import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { AlertTriangleIcon, InfoIcon } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { ChangePrimaryDialog } from '@/components/pursuits/ChangePrimaryDialog'
import type { PipelineRecordContext } from '@/components/pipeline/types'
import { api } from '@/lib/api'
import { Bullets } from '@/components/ui/notice'
import { refusalOf } from '@/lib/errors'
import { stageScopedKey } from '@/lib/stageScope'
import { type PursuitAlert, usePursuitGroup } from '@/lib/pursuitGroups'
import { cn } from '@/lib/utils'

/**
 * The group's notices, across the top of every member's record page.
 *
 * Computed by the server when the group is read (app/pursuits.py::alerts_for)
 * — nobody is emailed, nothing waits on a timer, and a notice appears for
 * whoever opens the record (CLAUDE.md hard rule 6).
 *
 * NOT LOGGED AS AN AUTOMATION. CLAUDE.md describes an automation log panel;
 * none exists in this build yet (other components' comments mention one, and
 * nothing writes to it). "Would have notified the BD Director" has nowhere to
 * go until it does, so it is not pretended here.
 */
export function PursuitBanner({ ctx }: { ctx: PipelineRecordContext }) {
  const groupId = typeof ctx.values?.pursuit_group === 'string' ? ctx.values.pursuit_group : null
  const { data: group } = usePursuitGroup(groupId)
  const [reviewing, setReviewing] = useState<PursuitAlert | null>(null)

  if (!group || group.alerts.length === 0) return null

  return (
    <div className="mb-4 space-y-2">
      {group.alerts.map((alert) => (
        <div
          key={`${alert.code}:${alert.pursuit ?? ''}`}
          className={cn(
            'flex flex-wrap items-center gap-2 rounded-lg border px-4 py-2 text-sm',
            alert.level === 'warning'
              ? 'border-amber-500/40 bg-amber-500/10 text-amber-700 dark:text-amber-400'
              : 'border-sky-500/40 bg-sky-500/10 text-sky-700 dark:text-sky-400'
          )}
        >
          {alert.level === 'warning' ? (
            <AlertTriangleIcon className="size-4 shrink-0" />
          ) : (
            <InfoIcon className="size-4 shrink-0" />
          )}
          <div className="min-w-0 flex-1">
            <p>
              <span className="font-medium">{group.name ?? 'Pursuit group'}: </span>
              {alert.message}
            </p>
            <Bullets items={alert.details ?? []} />
          </div>
          {alert.code === 'SECONDARY_AHEAD' && (
            <Button size="sm" variant="outline" onClick={() => setReviewing(alert)}>
              Review which counts
            </Button>
          )}
          {alert.code === 'PRIMARY_CLOSED' && (
            <Button size="sm" variant="outline" onClick={() => setReviewing(alert)}>
              Choose which counts
            </Button>
          )}
          {alert.code === 'WON_WITH_OPEN_SECONDARIES' && <CloseSecondaries groupId={group.group_id} alert={alert} members={group.members} />}
        </div>
      ))}

      <ChangePrimaryDialog
        open={reviewing !== null}
        groupId={group.group_id}
        initialRecordId={reviewing?.pursuit}
        onClose={() => setReviewing(null)}
      />
    </div>
  )
}

/**
 * "The primary is now a Deal — close the open secondaries as lost?" Each one
 * becomes Closed Lost with the reason code Partner conflict, recorded at the
 * stage it was lost at — the same per-stage key the record's own form writes.
 * Nothing happens until the button is pressed.
 */
function CloseSecondaries({
  groupId,
  alert,
  members,
}: {
  groupId: string
  alert: PursuitAlert
  members: { record_id: string; module: string; stage_number: number | null }[]
}) {
  const queryClient = useQueryClient()
  const close = useMutation({
    mutationFn: async () => {
      for (const recordId of alert.open ?? []) {
        const member = members.find((m) => m.record_id === recordId)
        if (!member) continue
        const patch: Record<string, unknown> = { lead_status: 'CLOSED_LOST' }
        if (member.stage_number !== null) {
          patch[stageScopedKey('closed_lost_reason_code', member.stage_number)] = 'PARTNER_CONFLICT'
        }
        await api.put(`/${member.module}/${recordId}`, patch)
      }
    },
    onSettled: () =>
      Promise.all([
        queryClient.invalidateQueries({ queryKey: ['pursuit-group', groupId] }),
        ...['leads', 'opportunities', 'deals'].flatMap((c) => [
          queryClient.invalidateQueries({ queryKey: ['list', c] }),
          queryClient.invalidateQueries({ queryKey: ['collection', c] }),
          queryClient.invalidateQueries({ queryKey: ['record', c] }),
        ]),
      ]),
  })

  return (
    <>
      <Button size="sm" variant="outline" disabled={close.isPending} onClick={() => close.mutate()}>
        {close.isPending
          ? 'Closing…'
          : `Close ${alert.open?.length ?? 0} as lost`}
      </Button>
      {close.isError && <span className="w-full text-destructive">{refusalOf(close.error).message}</span>}
    </>
  )
}
