import { useQuery } from '@tanstack/react-query'

import { StageChip } from '@/components/leads/StageChip'
import { api } from '@/lib/api'
import { date as fmtDate } from '@/lib/format'
import type { Transition } from '@/lib/pipeline'
import { displayNameOf } from '@/lib/spec'
import type { Values } from '@/lib/spec/conditions'

/**
 * Every recorded stage move on one record, newest first.
 *
 * A transition is the only thing that may move a stage, so this table is the
 * whole story of where a record has been — including the skips and reversals,
 * each with the reason the dialog demanded at the time.
 */
export function StageHistoryTab({
  transitions,
  emptyMessage,
}: {
  transitions: Transition[] | undefined
  emptyMessage: string
}) {
  const { data: users } = useQuery({
    queryKey: ['collection', 'users'],
    queryFn: async () => (await api.get<Values[]>('/users')).data,
  })
  const nameOf = (userId: string) => {
    const user = users?.find((row) => row.id === userId)
    return user ? displayNameOf(user) : userId
  }

  const rows = [...(transitions ?? [])].sort((a, b) => b.timestamp.localeCompare(a.timestamp))

  if (!transitions) return <p className="py-6 text-sm text-muted-foreground">Loading…</p>

  if (rows.length === 0) {
    return <p className="py-6 text-sm text-muted-foreground">{emptyMessage}</p>
  }

  return (
    <div className="overflow-x-auto rounded-lg border">
      <table className="w-full text-sm">
        <thead className="bg-muted/50 text-label">
          <tr>
            <th className="px-3 py-2 text-left font-medium">When</th>
            <th className="px-3 py-2 text-left font-medium">From</th>
            <th className="px-3 py-2 text-left font-medium">To</th>
            <th className="px-3 py-2 text-left font-medium">Actor</th>
            <th className="px-3 py-2 text-left font-medium">Reason</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((t, i) => (
            <tr key={i} className="border-t align-top">
              <td className="px-3 py-2 whitespace-nowrap">{fmtDate(t.timestamp)}</td>
              <td className="px-3 py-2">
                <StageChip value={t.from} />
              </td>
              <td className="px-3 py-2">
                <StageChip value={t.to} />
                {t.is_skip && <span className="text-muted-foreground"> · skip</span>}
                {t.is_reversal && <span className="text-muted-foreground"> · reversal</span>}
              </td>
              <td className="px-3 py-2">{nameOf(t.actor)}</td>
              <td className="px-3 py-2 text-muted-foreground">{t.reason ?? '—'}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
