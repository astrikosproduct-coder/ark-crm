import { useMemo, type ReactNode } from 'react'
import { useNavigate } from 'react-router-dom'
import { keepPreviousData, useQuery } from '@tanstack/react-query'

import type { ListRow } from '@/components/list/ListCell'
import { api } from '@/lib/api'
import { stageNumberOf, stagesFor } from '@/lib/pipeline'
import { ragAccent } from '@/lib/rag'
import { revenueOf, stageTotal, stageTotalExplained, usd } from '@/lib/revenue'
import { fieldOf, fieldOptions, kanbanBoard, labelForValue } from '@/lib/spec'
import { cn } from '@/lib/utils'

/**
 * The list-page pipeline board, shared by Leads, Opportunities and Deals.
 *
 * NO ARITHMETIC COMMENTARY ON THE BOARD (18 Sep 2026). Column headers show the
 * stage, the count and the total. They no longer show how many records the
 * total skipped or why, and no amount anywhere is struck through. Those were
 * notes to ourselves about data quality wearing the clothes of product copy.
 * The rules behind the totals are unchanged — see lib/revenue.ts.
 *
 * A stage's column always comes from stagesFor(module) — the 14-stage-review
 * split's own range for that module (Leads 0-3, Opportunities 4-6, Deals
 * 7-9) — never from a module's pre-split PipelineModuleSpec.stages, which the
 * record-detail rail deliberately keeps drawing 0-7/8-9 for now.
 *
 * After the stages come the TERMINAL status columns — Closed Lost and
 * Converted, as spec/extensions.json `kanban` declares them. A finished record
 * goes there whatever stage it reached, so a Lead converted at Stage 3 is in
 * Converted, not still counted as a Stage 3 card. Their total is shown muted,
 * because the pipeline figure above covers open work.
 *
 * Under each stage name sits that stage's revenue in USD — the sum of what the
 * server says each row contributes (row.revenue, see lib/revenue.ts), so only
 * open and on-hold PRIMARY pursuits count and a secondary pursuit of the same
 * project never inflates a column. Hovering the total says what it left out.
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
  /** The shared filter bar's parameters, WITHOUT the stage — the columns are the stages. */
  filter?: Record<string, string | string[]>
}

/**
 * Does the current filter let this status through? Reads the two forms the list
 * contract uses — repeated `<field>` is "any of", `<field>_ne` is "none of"
 * (backend/app/list_query.py) — and says yes when neither is present.
 */
function statusAdmits(
  filter: Record<string, string | string[]> | undefined,
  field: string
): (key: string) => boolean {
  const list = (value: string | string[] | undefined) =>
    value === undefined ? null : Array.isArray(value) ? value : [value]
  const only = list(filter?.[field])
  const not = list(filter?.[`${field}_ne`])
  return (key) => (only ? only.includes(key) : true) && (not ? !not.includes(key) : true)
}

export function PipelineKanbanBoard({
  module,
  collection,
  basePath,
  stageValueOf,
  noun,
  nounPlural,
  renderCard,
  filter,
}: PipelineKanbanBoardProps) {
  const stages = stagesFor(module)
  const filtered = Object.keys(filter ?? {}).length > 0

  // Same endpoint and the same parameters as the List tab, so the two views
  // can never disagree about which pursuits a filter matches. Under the
  // 'collection' key, so every save that invalidates the collection refreshes
  // the board whatever it is filtered to.
  const { data, isLoading, isError, isPlaceholderData } = useQuery({
    queryKey: ['collection', collection, filter ?? {}],
    queryFn: async () => (await api.get<ListRow[]>(`/${collection}`, { params: filter })).data,
    placeholderData: keepPreviousData,
  })

  // The terminal columns this module can show: a status the sidecar calls
  // terminal, the module actually offers, AND the current filter admits.
  // exclude_options already keeps POC/Pilot Deal off Leads and Opportunities,
  // so nobody is given a column their records can never enter.
  //
  // The third test is what keeps the board honest under a scope: with "Open
  // leads" chosen, the request carries lead_status_ne=CONVERTED, so a Converted
  // column could only ever draw empty — an empty column reads as "nothing has
  // converted", which is the opposite of true. Read off the filter itself
  // rather than passed in again, because the filter IS the answer.
  const statusField = fieldOf(module, kanbanBoard.status_field)
  const terminalColumns = useMemo(() => {
    if (!statusField) return []
    const offered = new Set(fieldOptions(statusField).map((option) => option.key))
    const admits = statusAdmits(filter, statusField.api_name)
    return (kanbanBoard.terminal_statuses_by_module?.[module] ?? kanbanBoard.terminal_statuses)
      .filter((key) => offered.has(key) && admits(key))
      .map((key) => ({ key, label: labelForValue(statusField.picklist, key) }))
  }, [statusField, module, filter])

  // Status first, stage second. A finished pursuit sits in one place instead of
  // being parked in whichever stage it happened to reach — which also ends the
  // board's own contradiction: a Converted lead counted in a stage's card count
  // while the same column's total already excluded it (lib/revenue.ts).
  const { byStage, byStatus } = useMemo(() => {
    const stageMap = new Map<number, ListRow[]>()
    const statusMap = new Map<string, ListRow[]>()
    const terminal = new Set(terminalColumns.map((column) => column.key))
    for (const row of data ?? []) {
      const status = statusField ? String(row[statusField.api_name] ?? '') : ''
      if (terminal.has(status)) {
        statusMap.set(status, [...(statusMap.get(status) ?? []), row])
        continue
      }
      const stage = stageNumberOf(stageValueOf(row))
      if (stage === null) continue
      stageMap.set(stage, [...(stageMap.get(stage) ?? []), row])
    }
    return { byStage: stageMap, byStatus: statusMap }
  }, [data, stageValueOf, statusField, terminalColumns])

  if (isLoading) return <p className="py-6 text-sm text-muted-foreground">Loading…</p>
  if (isError) return <p className="py-6 text-sm text-destructive">Could not load {collection}</p>

  return (
    <div className={cn('flex gap-3 overflow-x-auto py-3', isPlaceholderData && 'opacity-60')}>
      {stages.map((stage) => {
        const rows = byStage.get(stage.stage) ?? []
        const band = stage.probability_pct !== null ? `${stage.probability_pct}%` : null
        const total = stageTotal(rows)
        return (
          <div key={stage.stage} className="bg-card w-64 shrink-0 rounded-lg shadow-sm">
            <div className="border-b px-3 py-2">
              <p className="flex items-center gap-2 text-sm font-semibold">
                <span className="truncate">
                  {stage.stage} · {stage.name}
                </span>
                <span
                  className="bg-primary/15 text-primary rounded-full px-1.5 text-xs tabular-nums"
                  title={`${rows.length} ${rows.length === 1 ? noun : (nounPlural ?? `${noun}s`)}`}
                >
                  {rows.length}
                </span>
                {band && (
                  <span
                    className="text-muted-foreground shrink-0 text-xs font-normal"
                    title={`Entering this stage sets Progression ${stage.progression_pct}% and Probability ${stage.probability_pct}%`}
                  >
                    • {band}
                  </span>
                )}
              </p>
              {/* The total, and nothing beside it. A running tally of what the
                  sum left out ("2 excluded · 3 incomplete") is bookkeeping about
                  our own data quality, and a column header is not where a
                  salesperson should meet it. What the total covers is still one
                  hover away. */}
              <p
                className="mt-0.5 text-base font-semibold tabular-nums"
                title={stageTotalExplained(total)}
              >
                {usd(total.usd)}
              </p>
            </div>
            <CardList rows={rows} basePath={basePath} renderCard={renderCard} filtered={filtered} />
          </div>
        )
      })}

      {terminalColumns.length > 0 && (
        <div aria-hidden className="border-border mx-1 shrink-0 self-stretch border-l border-dashed" />
      )}

      {terminalColumns.map((column) => {
        const rows = byStatus.get(column.key) ?? []
        const parked = rows.reduce((sum, row) => sum + (revenueOf(row)?.usd ?? 0), 0)
        return (
          <div key={column.key} className="bg-muted/40 w-64 shrink-0 rounded-lg">
            <div className="border-b border-dashed px-3 py-2">
              <p className="text-muted-foreground flex items-center gap-2 text-sm font-semibold">
                <span className="truncate">{column.label}</span>
                <span
                  className="bg-muted rounded-full px-1.5 text-xs tabular-nums"
                  title={`${rows.length} ${rows.length === 1 ? noun : (nounPlural ?? `${noun}s`)}`}
                >
                  {rows.length}
                </span>
              </p>
              <p
                className="text-muted-foreground mt-0.5 text-base font-semibold tabular-nums"
                title="Finished pursuits. The pipeline total covers open work."
              >
                {usd(parked)}
              </p>
            </div>
            <CardList rows={rows} basePath={basePath} renderCard={renderCard} filtered={filtered} />
          </div>
        )
      })}
    </div>
  )
}

/** One column's cards. Shared by stage and status columns so a card looks the same in either. */
function CardList({
  rows,
  basePath,
  renderCard,
  filtered,
}: {
  rows: ListRow[]
  basePath: string
  renderCard: (row: ListRow) => ReactNode
  filtered: boolean
}) {
  const navigate = useNavigate()
  return (
    <div className="space-y-2 p-2">
      {rows.length === 0 && (
        <p className="px-1 py-4 text-center text-xs text-muted-foreground">{filtered ? 'No matches' : 'Empty'}</p>
      )}
      {rows.map((row) => (
        <button
          key={String(row.id)}
          type="button"
          onClick={() => navigate(`${basePath}/${row.id}`)}
          className={cn(
            'bg-raised block w-full rounded-lg px-3 py-2 text-left text-sm hover:bg-accent',
            // Overall RAG, as a stripe down the left edge — see lib/rag.ts.
            ragAccent(row)
          )}
        >
          {renderCard(row)}
          {/* "Secondary" is the business's own word for this pursuit's place in
              its group, and it stays. "· not counted" did not: it explained our
              arithmetic rather than the deal. */}
          {row.pursuit_group && !row.is_primary_pursuit ? (
            <p
              className="mt-1 inline-block rounded bg-muted px-1.5 py-0.5 text-[11px] text-muted-foreground"
              title="Another partner is pursuing the same project, and theirs is the lead pursuit."
            >
              Secondary
            </p>
          ) : null}
        </button>
      ))}
    </div>
  )
}
