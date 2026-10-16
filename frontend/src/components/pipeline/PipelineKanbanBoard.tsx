import { useEffect, useMemo, useState, type ReactNode } from 'react'
import { createPortal } from 'react-dom'
import { useNavigate } from 'react-router-dom'
import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { GripVerticalIcon, SearchIcon, SlidersHorizontalIcon, XIcon } from 'lucide-react'

import { useListToolbarSlot } from '@/components/layout/shellSlots'
import { ListCell, type ListRow } from '@/components/list/ListCell'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Sheet, SheetContent, SheetHeader, SheetTitle } from '@/components/ui/sheet'
import { api } from '@/lib/api'
import { stageNumberOf, stagesFor } from '@/lib/pipeline'
import { ragAccent } from '@/lib/rag'
import { revenueOf, stageTotal, stageTotalExplained, usd } from '@/lib/revenue'
import { fieldOf, fieldOptions, kanbanBoard, labelForValue, listViewFor } from '@/lib/spec'
import { cn } from '@/lib/utils'
import { useViewPreference, type KanbanSettings } from '@/lib/viewPreferences'
import type { FieldSpec } from '@/types/field'

/** At most this many fields on a card under its name — Zoho's limit is about the same. */
const MAX_CARD_FIELDS = 6
/** A board is categorized by one choice per record. */
const CATEGORY_TYPES = new Set(['picklist', 'lookup'])
const STAGE = '__stage'
const NONE = '__none'

/**
 * A column's total: the revenue rule's USD (lib/revenue.ts), or — Weighted
 * value — each counted record's USD times its own Probability % (a fraction),
 * the Dashboard's weighted rule. Secondaries and finished work add nothing
 * either way, because the server's `counted` already says so.
 */
function weightedTotal(rows: ListRow[]): number {
  return rows.reduce((sum, row) => {
    const r = revenueOf(row)
    if (!r?.counted || r.usd === null) return sum
    const p = typeof row.probability_pct === 'number' ? row.probability_pct : 0
    return sum + r.usd * p
  }, 0)
}

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
  /**
   * The fields a person may categorize by and put on a card — the page's filter
   * fields (Release 1.2). Given, the board gets its own View Settings, kept per
   * person in PostgreSQL; everyone else keeps the default board.
   */
  fields?: FieldSpec[]
  /**
   * What the module's own card shows under the name, in order — the Selected
   * list a person starts from in Kanban View Settings. Saved unchanged, it
   * keeps the module's own card.
   */
  defaultCardFields?: string[]
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
  fields,
  defaultCardFields = [],
}: PipelineKanbanBoardProps) {
  const stages = stagesFor(module)
  // On a list page, View Settings sits on the toolbar line; elsewhere, above the board.
  const toolSlot = useListToolbarSlot()
  const filtered = Object.keys(filter ?? {}).length > 0
  const prefs = useViewPreference<KanbanSettings>(fields ? `kanban:${module}` : undefined)
  const mine = prefs.settings ?? {}
  const aggregate = mine.aggregate_by ?? 'value'
  const weighted = aggregate === 'weighted'
  /** Aggregate By "None": the columns show their count and no total. */
  const showTotals = aggregate !== 'none'
  const totalOf = (rows: ListRow[]) => (weighted ? weightedTotal(rows) : stageTotal(rows).usd)
  const totalTitle = (rows: ListRow[]) =>
    weighted
      ? 'Weighted value: each open, counted record in USD times its own Probability.'
      : stageTotalExplained(stageTotal(rows))

  // What a person may choose from: single-choice fields to categorize by, any
  // showable field for a card. All from the page — never named here.
  const categories = useMemo(() => (fields ?? []).filter((f) => CATEGORY_TYPES.has(f.type)), [fields])
  const nameField = listViewFor(module)?.fields[0]
  // The card always opens with the record's name, so it is not a choice.
  // The default card's fields are offered too, even one the filter panel leaves out.
  const defaultKey = defaultCardFields.join(',')
  const cardChoices = useMemo(() => {
    const out = (fields ?? []).filter(
      (f) => !['childlist', 'autonumber', 'file'].includes(f.type) && f.api_name !== nameField?.api_name
    )
    for (const name of defaultKey ? defaultKey.split(',') : []) {
      const f = fieldOf(module, name)
      if (f && !out.some((o) => o.api_name === name)) out.push(f)
    }
    return out
  }, [fields, nameField, module, defaultKey])
  const defaults = defaultCardFields.filter((name) => cardChoices.some((f) => f.api_name === name))
  const categorizeBy = categories.find((f) => f.api_name === mine.categorize_by)
  const cardFields = (mine.card_fields ?? [])
    .map((name) => cardChoices.find((f) => f.api_name === name))
    .filter((f): f is FieldSpec => Boolean(f))
  const card = (row: ListRow) =>
    cardFields.length ? <ChosenFieldsCard row={row} nameField={nameField} fields={cardFields} /> : renderCard(row)

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

  // Categorized by a field instead of the stage: one column per choice, in the
  // field's own order (a lookup's by name), then the records with none.
  const categoryColumns = useMemo(() => {
    if (!categorizeBy) return null
    const name = categorizeBy.api_name
    const groups = new Map<string, ListRow[]>()
    for (const row of data ?? []) {
      const value = row[name]
      const key = value === null || value === undefined || value === '' ? NONE : String(value)
      groups.set(key, [...(groups.get(key) ?? []), row])
    }
    const keys =
      categorizeBy.type === 'picklist'
        ? fieldOptions(categorizeBy).map((o) => o.key)
        : [...groups.keys()]
            .filter((k) => k !== NONE)
            .sort((a, b) => labelOf(a).localeCompare(labelOf(b)))
    function labelOf(key: string): string {
      if (categorizeBy!.type === 'picklist') return labelForValue(categorizeBy!.picklist, key)
      const row = groups.get(key)?.[0]
      return String((row?.__labels as Record<string, string> | undefined)?.[name] ?? key)
    }
    const columns = keys.map((key) => ({ key, label: labelOf(key), rows: groups.get(key) ?? [] }))
    if (groups.has(NONE)) columns.push({ key: NONE, label: `No ${categorizeBy.label}`, rows: groups.get(NONE) ?? [] })
    return columns
  }, [categorizeBy, data])

  if (isLoading) return <p className="py-6 text-sm text-muted-foreground">Loading…</p>
  if (isError) return <p className="py-6 text-sm text-destructive">Could not load {collection}</p>

  const drawer = fields ? (
      <KanbanSettingsDrawer
        iconOnly={Boolean(toolSlot)}
        categories={categories}
        categorizeBy={categorizeBy ? categorizeBy.api_name : STAGE}
        aggregate={aggregate}
        nameField={nameField}
        cardChoices={cardChoices}
        // Nothing chosen yet: Selected starts from what the card shows today.
        cardFields={cardFields.length ? cardFields.map((f) => f.api_name) : defaults}
        hasOwn={prefs.settings !== null}
        onSave={(next) =>
          prefs.save({
            ...mine,
            categorize_by: next.categorizeBy === STAGE ? undefined : next.categorizeBy,
            aggregate_by: next.aggregate,
            // The default fields, unchanged, keep the module's own card.
            card_fields: next.cardFields.join(',') === defaults.join(',') ? undefined : next.cardFields,
          })
        }
        onReset={() => prefs.reset()}
      />
  ) : null
  const settings = drawer ? (
    toolSlot ? createPortal(drawer, toolSlot) : <div className="flex justify-end">{drawer}</div>
  ) : null

  if (categoryColumns) {
    return (
      <>
        {settings}
        <div className={cn('flex min-h-0 flex-1 gap-4 overflow-x-auto pb-1', isPlaceholderData && 'opacity-60')}>
          {categoryColumns.map((column) => (
            <div key={column.key} className="bg-card flex w-76 shrink-0 flex-col rounded-lg shadow-sm">
              <div className="border-b px-4 py-3">
                <p className="flex items-center gap-2 text-sm font-semibold">
                  <span className="truncate" title={column.label}>
                    {column.label}
                  </span>
                  <span className="bg-primary/15 text-primary rounded-full px-1.5 text-xs tabular-nums">
                    {column.rows.length}
                  </span>
                </p>
                {showTotals && (
                  <p className="mt-1 text-base font-semibold tabular-nums" title={totalTitle(column.rows)}>
                    {usd(totalOf(column.rows))}
                  </p>
                )}
              </div>
              <CardList rows={column.rows} basePath={basePath} renderCard={card} filtered={filtered} />
            </div>
          ))}
        </div>
      </>
    )
  }

  return (
    <>
    {settings}
    <div className={cn('flex min-h-0 flex-1 gap-4 overflow-x-auto pb-1', isPlaceholderData && 'opacity-60')}>
      {stages.map((stage) => {
        const rows = byStage.get(stage.stage) ?? []
        const band = stage.probability_pct !== null ? `${stage.probability_pct}%` : null
        return (
          <div key={stage.stage} className="bg-card flex w-76 shrink-0 flex-col rounded-lg shadow-sm">
            <div className="border-b px-4 py-3">
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
              {showTotals && (
                <p className="mt-1 text-base font-semibold tabular-nums" title={totalTitle(rows)}>
                  {usd(totalOf(rows))}
                </p>
              )}
            </div>
            <CardList rows={rows} basePath={basePath} renderCard={card} filtered={filtered} />
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
          <div key={column.key} className="bg-muted/40 flex w-76 shrink-0 flex-col rounded-lg">
            <div className="border-b border-dashed px-4 py-3">
              <p className="text-muted-foreground flex items-center gap-2 text-sm font-semibold">
                <span className="truncate">{column.label}</span>
                <span
                  className="bg-muted rounded-full px-1.5 text-xs tabular-nums"
                  title={`${rows.length} ${rows.length === 1 ? noun : (nounPlural ?? `${noun}s`)}`}
                >
                  {rows.length}
                </span>
              </p>
              {showTotals && (
                <p
                  className="text-muted-foreground mt-1 text-base font-semibold tabular-nums"
                  title="Finished pursuits. The pipeline total covers open work."
                >
                  {usd(parked)}
                </p>
              )}
            </div>
            <CardList rows={rows} basePath={basePath} renderCard={card} filtered={filtered} />
          </div>
        )
      })}
    </div>
    </>
  )
}

/** A card of the fields a person chose — Zoho's Select Fields. Each value as a list cell draws it. */
function ChosenFieldsCard({ row, nameField, fields }: { row: ListRow; nameField?: FieldSpec; fields: FieldSpec[] }) {
  const name = nameField ? row[nameField.api_name] : undefined
  return (
    <>
      <p className="min-w-0 font-semibold leading-snug line-clamp-2 break-words" title={String(name ?? '')}>
        {String(name ?? 'Untitled')}
      </p>
      <div className="mt-1.5 space-y-1">
        {fields.map((f) => (
          // Two lines before a long value is cut; its field's name on hover.
          <div key={f.qref} className="text-muted-foreground line-clamp-2 text-xs break-words" title={f.label}>
            <ListCell field={f} row={row} />
          </div>
        ))}
      </div>
    </>
  )
}

interface KanbanChoice {
  categorizeBy: string
  aggregate: 'none' | 'value' | 'weighted'
  cardFields: string[]
}

const AGGREGATES: { value: KanbanChoice['aggregate']; label: string }[] = [
  { value: 'none', label: 'None' },
  { value: 'value', label: 'Value' },
  { value: 'weighted', label: 'Weighted value' },
]

/**
 * The board's View Settings, as Zoho's "Kanban View - Settings": a drawer from
 * the top with Categorize By, Aggregate By and Select Fields (Available beside
 * Selected), saved together. Every choice is this person's own.
 */
function KanbanSettingsDrawer({
  categories,
  categorizeBy,
  aggregate,
  nameField,
  cardChoices,
  cardFields,
  hasOwn,
  iconOnly,
  onSave,
  onReset,
}: {
  categories: FieldSpec[]
  categorizeBy: string
  aggregate: KanbanChoice['aggregate']
  nameField?: FieldSpec
  cardChoices: FieldSpec[]
  cardFields: string[]
  hasOwn: boolean
  /** On the toolbar line: the icon alone, as the list's View Settings. */
  iconOnly?: boolean
  onSave: (next: KanbanChoice) => void
  onReset: () => void
}) {
  const [open, setOpen] = useState(false)
  const [draft, setDraft] = useState<KanbanChoice>({ categorizeBy, aggregate, cardFields })

  // Each opening starts from what is saved.
  useEffect(() => {
    if (open) setDraft({ categorizeBy, aggregate, cardFields })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open])

  const row = 'grid items-center gap-2 sm:grid-cols-[9rem_minmax(0,22rem)]'
  return (
    <>
      {iconOnly ? (
        <Button
          type="button"
          variant="outline"
          size="icon"
          aria-label="View settings"
          title="View settings"
          onClick={() => setOpen(true)}
        >
          <SlidersHorizontalIcon className="size-4" />
        </Button>
      ) : (
        <Button type="button" variant="outline" size="sm" onClick={() => setOpen(true)}>
          <SlidersHorizontalIcon className="size-4" />
          View settings
        </Button>
      )}
      <Sheet open={open} onOpenChange={setOpen}>
        <SheetContent
          side="top"
          aria-describedby={undefined}
          className="right-4 w-[calc(100%-2rem)] max-w-2xl gap-0 p-0 sm:right-8"
        >
          <SheetHeader className="border-border border-b px-5 py-4">
            <SheetTitle>Kanban View - Settings</SheetTitle>
          </SheetHeader>

          <div className="min-h-0 flex-1 space-y-3 overflow-y-auto px-5 py-4">
            <div className={row}>
              <span className="text-muted-foreground text-sm sm:text-right">Categorize By</span>
              <Select value={draft.categorizeBy} onValueChange={(v) => setDraft({ ...draft, categorizeBy: v })}>
                <SelectTrigger className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value={STAGE}>Stage</SelectItem>
                  {categories.map((f) => (
                    <SelectItem key={f.qref} value={f.api_name}>
                      {f.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className={row}>
              <span className="text-muted-foreground text-sm sm:text-right">Aggregate By</span>
              <Select
                value={draft.aggregate}
                onValueChange={(v) => setDraft({ ...draft, aggregate: v as KanbanChoice['aggregate'] })}
              >
                <SelectTrigger className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {AGGREGATES.map((a) => (
                    <SelectItem key={a.value} value={a.value}>
                      {a.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <p className="pt-2 text-sm font-semibold">Select Fields</p>
            <SelectFields
              nameField={nameField}
              fields={cardChoices}
              selected={draft.cardFields}
              max={MAX_CARD_FIELDS}
              onChange={(chosen) => setDraft({ ...draft, cardFields: chosen })}
            />
          </div>

          <div className="border-border flex items-center gap-2 border-t px-5 py-3">
            <Button
              type="button"
              variant="ghost"
              size="sm"
              disabled={!hasOwn}
              onClick={() => {
                setOpen(false)
                onReset()
              }}
            >
              Reset to default board
            </Button>
            <div className="flex-1" />
            <Button type="button" variant="outline" onClick={() => setOpen(false)}>
              Cancel
            </Button>
            <Button
              type="button"
              onClick={() => {
                setOpen(false)
                onSave(draft)
              }}
            >
              Save
            </Button>
          </div>
        </SheetContent>
      </Sheet>
    </>
  )
}

/**
 * Zoho's Select Fields: Available on the left (search, click to add), Selected
 * on the right in card order (drag to reorder, × to take off). The record's
 * name heads Selected and can't be taken off — every card opens with it.
 */
function SelectFields({
  nameField,
  fields,
  selected,
  max,
  onChange,
}: {
  nameField?: FieldSpec
  fields: FieldSpec[]
  selected: string[]
  max: number
  onChange: (selected: string[]) => void
}) {
  const [search, setSearch] = useState('')
  const [dragging, setDragging] = useState<number | null>(null)
  const byName = new Map(fields.map((f) => [f.api_name, f]))
  const chosen = selected.map((name) => byName.get(name)).filter((f): f is FieldSpec => Boolean(f))
  const available = fields
    .filter((f) => !selected.includes(f.api_name))
    .filter((f) => !search || f.label.toLowerCase().includes(search.trim().toLowerCase()))
    .sort((a, b) => a.label.localeCompare(b.label))
  const full = selected.length >= max

  const drop = (to: number) => {
    if (dragging === null || dragging === to) return
    const next = [...selected]
    const [moved] = next.splice(dragging, 1)
    next.splice(to, 0, moved)
    onChange(next)
    setDragging(null)
  }

  const pane = 'border-border h-72 overflow-y-auto rounded-md border'
  return (
    <div className="grid gap-4 sm:grid-cols-2">
      <div className="min-w-0 space-y-1.5">
        <p className="text-muted-foreground text-sm">Available</p>
        <div className={cn(pane, 'flex flex-col')}>
          <div className="border-border relative border-b">
            <SearchIcon className="text-muted-foreground pointer-events-none absolute top-1/2 left-2.5 size-4 -translate-y-1/2" />
            <Input
              className="h-8 rounded-none border-0 pl-8 shadow-none focus-visible:ring-0"
              placeholder="Search"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
          </div>
          <ul className="min-h-0 flex-1 overflow-y-auto py-1">
            {available.map((f) => (
              <li key={f.qref}>
                <button
                  type="button"
                  disabled={full}
                  title={full ? `A card shows at most ${max} fields.` : 'Add to the card'}
                  onClick={() => onChange([...selected, f.api_name])}
                  className="hover:bg-accent w-full truncate px-3 py-1 text-left text-sm disabled:pointer-events-none disabled:opacity-50"
                >
                  {f.label}
                </button>
              </li>
            ))}
            {available.length === 0 && <li className="text-muted-foreground px-3 py-2 text-sm">No fields</li>}
          </ul>
        </div>
      </div>

      <div className="min-w-0 space-y-1.5">
        <p className="text-muted-foreground flex justify-between text-sm">
          <span>Selected</span>
          <span className="tabular-nums">
            {selected.length} of {max}
          </span>
        </p>
        <ul className={cn(pane, 'py-1')}>
          {nameField && (
            <li className="flex items-center gap-2 px-3 py-1 text-sm">
              <span className="size-4 shrink-0" />
              <span className="truncate">
                {nameField.label}
                <span className="text-destructive">*</span>
              </span>
            </li>
          )}
          {chosen.map((f, i) => (
            <li
              key={f.qref}
              draggable
              onDragStart={() => setDragging(i)}
              onDragOver={(e) => e.preventDefault()}
              onDrop={() => drop(i)}
              className={cn(
                'group/sel hover:bg-accent flex cursor-grab items-center gap-2 px-3 py-1 text-sm',
                dragging === i && 'opacity-50'
              )}
            >
              <GripVerticalIcon className="text-muted-foreground size-4 shrink-0" />
              <span className="min-w-0 flex-1 truncate">{f.label}</span>
              <button
                type="button"
                aria-label={`Take ${f.label} off the card`}
                onClick={() => onChange(selected.filter((n) => n !== f.api_name))}
                className="text-muted-foreground hover:text-foreground opacity-0 group-hover/sel:opacity-100 focus-visible:opacity-100"
              >
                <XIcon className="size-3.5" />
              </button>
            </li>
          ))}
          {chosen.length === 0 && (
            <li className="text-muted-foreground px-3 py-2 text-xs">
              Nothing else chosen: cards show their usual details.
            </li>
          )}
        </ul>
      </div>
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
    <div className="min-h-0 flex-1 space-y-3 overflow-y-auto p-3">
      {rows.length === 0 && (
        <p className="px-1 py-4 text-center text-xs text-muted-foreground">{filtered ? 'No matches' : 'Empty'}</p>
      )}
      {rows.map((row) => (
        <button
          key={String(row.id)}
          type="button"
          onClick={() => navigate(`${basePath}/${row.id}`)}
          className={cn(
            'bg-raised block w-full rounded-lg px-4 py-3 text-left text-sm shadow-xs transition-shadow hover:bg-accent hover:shadow-md',
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
              className="mt-2 inline-block rounded bg-muted px-1.5 py-0.5 text-[11px] text-muted-foreground"
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
