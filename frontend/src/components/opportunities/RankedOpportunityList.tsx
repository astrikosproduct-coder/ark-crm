import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { XIcon } from 'lucide-react'
import { isAxiosError } from 'axios'
import { useState } from 'react'

import { Button } from '@/components/ui/button'
import type { ListRow } from '@/components/list/ListCell'
import { StageChip } from '@/components/leads/StageChip'
import { ReadThroughLookup, ReadThroughText } from '@/components/opportunities/opportunityListCell'
import { api } from '@/lib/api'
import { money } from '@/lib/format'
import { fieldOf, idOf } from '@/lib/spec'

const END_CLIENT_TARGET = fieldOf('opportunities', 'end_client')?.lookup_target ?? null

interface Props {
  /** e.g. 'is_low_hanging' */
  flagField: string
  /** e.g. 'low_hanging_rank' */
  rankField: string
  cap: number
}

/**
 * A fixed-length, rank-ordered view of one priority pick — Low Hanging or Top
 * 10 — showing every slot from 1 to `cap`, filled or open. Marking a NEW
 * opportunity happens on the record's own page (the checkbox in HeaderStrip,
 * where the rank is assigned) — this view is for seeing the current picks at
 * a glance and freeing a slot, which is why "Unmark" lives here too.
 */
export function RankedOpportunityList({ flagField, rankField, cap }: Props) {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [error, setError] = useState<string | null>(null)

  const { data, isLoading, isError } = useQuery({
    queryKey: ['collection', 'opportunities'],
    queryFn: async () => (await api.get<ListRow[]>('/opportunities')).data,
  })

  const unmark = useMutation({
    mutationFn: async (id: string) => (await api.put(`/opportunities/${id}`, { [flagField]: false })).data,
    onSuccess: async () => {
      setError(null)
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['collection', 'opportunities'] }),
        queryClient.invalidateQueries({ queryKey: ['list', 'opportunities'] }),
        queryClient.invalidateQueries({ queryKey: ['record', 'opportunities'] }),
      ])
    },
    onError: (err) => {
      setError(
        isAxiosError(err)
          ? ((err.response?.data as { message?: string } | undefined)?.message ?? err.message)
          : 'Could not unmark this opportunity.'
      )
    },
  })

  if (isLoading) return <p className="py-6 text-sm text-muted-foreground">Loading…</p>
  if (isError) return <p className="py-6 text-sm text-destructive">Could not load opportunities.</p>

  const byRank = new Map<number, ListRow>()
  for (const row of data ?? []) {
    if (!row[flagField]) continue
    const rank = Number(row[rankField])
    if (Number.isFinite(rank)) byRank.set(rank, row)
  }

  return (
    <div className="space-y-2 py-3">
      <p className="text-sm text-muted-foreground">
        {byRank.size} of {cap} slots filled. Add one from the opportunity's own page — the checkbox sits
        right under its title.
      </p>

      {error && <p className="text-sm text-destructive">{error}</p>}

      <ol className="divide-y rounded-lg border">
        {Array.from({ length: cap }, (_, i) => i + 1).map((rank) => {
          const row = byRank.get(rank)
          return (
            <li key={rank} className="flex items-center gap-3 px-4 py-3">
              <span className="text-muted-foreground w-9 shrink-0 text-sm tabular-nums">
                #{rank}
              </span>

              {row ? (
                <>
                  <button
                    type="button"
                    className="min-w-0 flex-1 truncate text-left text-sm font-medium hover:underline"
                    onClick={() => navigate(`/opportunities/${idOf(row)}`)}
                  >
                    <ReadThroughText row={row} apiName="opportunity_name" />
                  </button>
                  <span className="hidden shrink-0 text-xs text-muted-foreground sm:block">
                    <ReadThroughLookup row={row} apiName="end_client" lookupTarget={END_CLIENT_TARGET} />
                  </span>
                  {typeof row.total_value_tcv === 'number' && (
                    <span className="shrink-0 text-xs tabular-nums text-muted-foreground">
                      ${money(row.total_value_tcv)}
                    </span>
                  )}
                  <StageChip value={row.project_stage} />
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    onClick={() => unmark.mutate(idOf(row))}
                    disabled={unmark.isPending}
                  >
                    <XIcon className="size-4" />
                    Unmark
                  </Button>
                </>
              ) : (
                <span className="flex-1 text-sm text-muted-foreground">Open</span>
              )}
            </li>
          )
        })}
      </ol>
    </div>
  )
}
