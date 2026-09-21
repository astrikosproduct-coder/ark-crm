import { Link } from 'react-router-dom'
import { UsersIcon } from 'lucide-react'

import { Bullets } from '@/components/ui/notice'
import { stageLabel } from '@/lib/pipeline'
import { localAmount } from '@/lib/revenue'
import { pathOfRecord, pursuitStatusLabel, usePursuitGroup } from '@/lib/pursuitGroups'

/**
 * A pursuit group, read-only and by name — for a screen that is ABOUT the
 * group rather than inside one of its pursuits: a deal registration's Conflict
 * tab. Changing the primary or removing a pursuit stays on a pursuit's Related
 * tab (PursuitGroupPanel), where the record being changed is in front of you.
 */
export function PursuitGroupSummary({ groupId }: { groupId: string }) {
  const { data: group, isLoading } = usePursuitGroup(groupId)

  if (isLoading) return <p className="text-muted-foreground text-sm">Loading the pursuit group…</p>
  if (!group) return null

  return (
    <div className="space-y-2">
      <p className="flex items-center gap-2 font-medium">
        <UsersIcon className="size-4" />
        {group.name ?? 'Pursuit group'}
      </p>

      {group.alerts.map((alert) => (
        <div key={alert.code} className="text-amber-700 dark:text-amber-400">
          <p>{alert.message}</p>
          <Bullets items={alert.details ?? []} />
        </div>
      ))}

      {group.members.length === 0 ? (
        <p className="text-muted-foreground">No pursuit has been created from either registration yet.</p>
      ) : (
        <div className="overflow-x-auto rounded-md border">
          <table className="w-full text-sm">
            <thead className="bg-muted/50 text-muted-foreground text-left text-xs">
              <tr>
                <th className="px-3 py-2 font-medium">Pursuit</th>
                <th className="px-3 py-2 font-medium">Partner</th>
                <th className="px-3 py-2 font-medium">Stage</th>
                <th className="px-3 py-2 font-medium">Status</th>
                <th className="px-3 py-2 text-right font-medium">Value</th>
                <th className="px-3 py-2 font-medium">Role</th>
              </tr>
            </thead>
            <tbody className="divide-y">
              {group.members.map((m) => (
                <tr key={m.pursuit}>
                  <td className="px-3 py-2">
                    <Link className="font-medium underline-offset-2 hover:underline" to={pathOfRecord(m.record_id)}>
                      {m.name ?? 'Untitled pursuit'}
                    </Link>
                  </td>
                  <td className="px-3 py-2">{m.partner_name ?? '—'}</td>
                  <td className="px-3 py-2">{stageLabel(m.stage_number) || '—'}</td>
                  <td className="px-3 py-2">{pursuitStatusLabel(m.module, m.status)}</td>
                  {/* No strikethrough on a real figure — see RevenueAmount. */}
                  <td className="px-3 py-2 text-right tabular-nums">
                    {localAmount(m.revenue)}
                  </td>
                  <td className="px-3 py-2">{m.is_primary ? 'Primary' : 'Secondary'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
