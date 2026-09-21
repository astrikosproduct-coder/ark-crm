import { useState } from 'react'
import { Link } from 'react-router-dom'
import { UsersIcon } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { ChangePrimaryDialog } from '@/components/pursuits/ChangePrimaryDialog'
import { RemoveFromGroupDialog } from '@/components/pursuits/RemoveFromGroupDialog'
import type { PipelineRecordContext } from '@/components/pipeline/types'
import { stageLabel } from '@/lib/pipeline'
import { localAmount } from '@/lib/revenue'
import { pathOfRecord, type PursuitMember, pursuitStatusLabel, usePursuitGroup } from '@/lib/pursuitGroups'
import { cn } from '@/lib/utils'

/**
 * The Related tab's Pursuit Group section: every partner's pursuit of this same
 * project, which one counts, and the two things a person may do about it.
 *
 * Replaces "Related pursuits", which listed leads naming this one as their
 * parent_pursuit — a field that could not follow a pursuit past conversion and
 * is logically deleted now. A group is read the same from a Lead, an
 * Opportunity or a Deal, because each member is described by the live end of
 * its own chain.
 */
export function PursuitGroupPanel({ ctx }: { ctx: PipelineRecordContext }) {
  const groupId = typeof ctx.values?.pursuit_group === 'string' ? ctx.values.pursuit_group : null
  const { data: group, isLoading } = usePursuitGroup(groupId)
  const [changing, setChanging] = useState(false)
  const [removing, setRemoving] = useState<PursuitMember | null>(null)

  return (
    <section className="space-y-3">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h3 className="flex items-center gap-2 text-sm font-semibold">
            <UsersIcon className="size-4" />
            Pursuit Group{group?.name ? ` — ${group.name}` : ''}
          </h3>
          <p className="text-sm text-muted-foreground">
            {groupId
              ? `The same project at ${group?.end_client_name ?? 'this End Client'}, through more than one partner. Only the primary counts in the pipeline total.`
              : 'Not in a group. This pursuit counts in the pipeline total on its own.'}
          </p>
        </div>
        {group && group.members.some((m) => !m.is_primary && m.is_open) && (
          <Button variant="outline" size="sm" onClick={() => setChanging(true)}>
            Change primary
          </Button>
        )}
      </div>

      {groupId && isLoading && <p className="text-sm text-muted-foreground">Loading the group…</p>}

      {group && (
        <div className="overflow-x-auto rounded-md border">
          <table className="w-full text-sm">
            <thead className="bg-muted/50 text-left text-xs text-muted-foreground">
              <tr>
                <th className="px-3 py-2 font-medium">Pursuit</th>
                <th className="px-3 py-2 font-medium">Partner</th>
                <th className="px-3 py-2 font-medium">Stage</th>
                <th className="px-3 py-2 font-medium">Status</th>
                <th className="px-3 py-2 text-right font-medium">Value</th>
                <th className="px-3 py-2 font-medium">Role</th>
                <th className="px-3 py-2" />
              </tr>
            </thead>
            <tbody className="divide-y">
              {group.members.map((m) => {
                const here = m.chain.some((c) => c.record_id === ctx.id)
                return (
                  <tr key={m.pursuit} className={cn(here && 'bg-accent/40')}>
                    <td className="px-3 py-2">
                      <Link className="font-medium underline-offset-2 hover:underline" to={pathOfRecord(m.record_id)}>
                        {m.name ?? 'Untitled pursuit'}
                      </Link>
                    </td>
                    <td className="px-3 py-2">{m.partner_name ?? '—'}</td>
                    <td className="px-3 py-2">{stageLabel(m.stage_number) || '—'}</td>
                    <td className="px-3 py-2">{pursuitStatusLabel(m.module, m.status)}</td>
                    {/* No strikethrough on a real figure — see RevenueAmount. */}
                    <td className="px-3 py-2 text-right tabular-nums" title={m.revenue?.label}>
                      {localAmount(m.revenue)}
                    </td>
                    <td className="px-3 py-2">
                      {m.is_primary ? (
                        <span className="rounded bg-primary/15 px-1.5 py-0.5 text-xs text-primary">Primary</span>
                      ) : (
                        <span className="rounded bg-muted px-1.5 py-0.5 text-xs text-muted-foreground">Secondary</span>
                      )}
                    </td>
                    <td className="px-3 py-2 text-right">
                      <Button variant="ghost" size="sm" onClick={() => setRemoving(m)}>
                        Remove
                      </Button>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}

      {group && (
        <ChangePrimaryDialog open={changing} groupId={group.group_id} onClose={() => setChanging(false)} />
      )}
      {group && removing && (
        <RemoveFromGroupDialog open group={group} member={removing} onClose={() => setRemoving(null)} />
      )}
    </section>
  )
}
