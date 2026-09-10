import { useMemo, type ReactNode } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'

import type { ListRow } from '@/components/list/ListCell'
import { api } from '@/lib/api'
import { stageNumberOf, stagesFor } from '@/lib/pipeline'

/**
 * The list-page pipeline board, shared by Leads, Opportunities and Deals.
 *
 * A stage's column always comes from stagesFor(module) — the 14-stage-review
 * split's own range for that module (Leads 0-3, Opportunities 4-6, Deals
 * 7-9) — never from a module's pre-split PipelineModuleSpec.stages, which the
 * record-detail rail deliberately keeps drawing 0-7/8-9 for now. A record
 * frozen at the top of its module's range (a converted Lead at Stage 3, say)
 * still shows here as a card in that column: this board does not filter it
 * out, it simply has nowhere further to put it.
 *
 * Card content is genuinely different per module — Opportunities read
 * opportunity_name/end_client through the parent chain, Deals have no
 * probability field, and so on — so it is left entirely to `renderCard`
 * rather than forced into one shared shape.
 */
export interface PipelineKanbanBoardProps {
  /** Register module whose split range drives the columns. */
  module: string
  /** Store collection behind /api. */
  collection: string
  /** Route prefix a card navigates to on click. */
  basePath: string
  /** Reads the row's raw stage picklist value (e.g. row.project_stage). */
  stageValueOf: (row: ListRow) => unknown
  /** Singular noun for the column count line — "lead", "opportunity", "deal". */
  noun: string
  /** Plural form, for irregular nouns ("opportunity" -> "opportunities"). Defaults to `${noun}s`. */
  nounPlural?: string
  /** A card's contents. The board supplies the clickable wrapper. */
  renderCard: (row: ListRow) => ReactNode
}

export function PipelineKanbanBoard({
  module,
  collection,
  basePath,
  stageValueOf,
  noun,
  nounPlural,
  renderCard,
}: PipelineKanbanBoardProps) {
  const navigate = useNavigate()
  const stages = stagesFor(module)

  const { data, isLoading, isError } = useQuery({
    queryKey: ['collection', collection],
    queryFn: async () => (await api.get<ListRow[]>(`/${collection}`)).data,
  })

  const byStage = useMemo(() => {
    const rows = data ?? []
    const map = new Map<number, ListRow[]>()
    for (const row of rows) {
      const stage = stageNumberOf(stageValueOf(row))
      if (stage === null) continue
      map.set(stage, [...(map.get(stage) ?? []), row])
    }
    return map
  }, [data, stageValueOf])

  if (isLoading) return <p className="py-6 text-sm text-muted-foreground">Loading…</p>
  if (isError) return <p className="py-6 text-sm text-destructive">Could not load {collection}</p>

  return (
    <div className="flex gap-3 overflow-x-auto py-3">
      {stages.map((stage) => {
        const rows = byStage.get(stage.stage) ?? []
        const band = stage.prob_min !== null && stage.prob_max !== null
          ? `${stage.prob_min}–${stage.prob_max}% · `
          : ''
        return (
          <div key={stage.stage} className="w-64 shrink-0 rounded-lg border bg-muted">
            <div className="border-b px-3 py-2">
              <p className="flex items-center gap-2 text-sm font-semibold">
                <span className="truncate">
                  {stage.stage} · {stage.name}
                </span>
                <span className="text-muted-foreground ml-auto text-xs tabular-nums">
                  {rows.length}
                </span>
              </p>
              <p className="text-xs text-muted-foreground">
                {band}
                {rows.length} {rows.length === 1 ? noun : (nounPlural ?? `${noun}s`)}
              </p>
            </div>
            <div className="space-y-2 p-2">
              {rows.length === 0 && <p className="px-1 py-4 text-center text-xs text-muted-foreground">Empty</p>}
              {rows.map((row) => (
                <button
                  key={String(row.id)}
                  type="button"
                  onClick={() => navigate(`${basePath}/${row.id}`)}
                  className="bg-raised block w-full rounded-lg border p-3 text-left text-sm hover:bg-accent"
                >
                  {renderCard(row)}
                </button>
              ))}
            </div>
          </div>
        )
      })}
    </div>
  )
}
