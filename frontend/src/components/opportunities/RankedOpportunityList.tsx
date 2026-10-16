import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { EllipsisIcon, PlusIcon, XIcon } from 'lucide-react'
import { isAxiosError } from 'axios'
import { useLayoutEffect, useMemo, useRef, useState } from 'react'

import { Button } from '@/components/ui/button'
import { Command, CommandEmpty, CommandInput, CommandItem, CommandList } from '@/components/ui/command'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { ChooseFieldsDialog } from '@/components/list/ChooseFieldsDialog'
import { ListCell, NUMERIC_TYPES, type ListRow } from '@/components/list/ListCell'
import { ColumnMenu, ViewSettings } from '@/components/list/RecordListView'
import { ReadThroughText, opportunityListCell } from '@/components/opportunities/opportunityListCell'
import { api } from '@/lib/api'
import { PRIORITY_FLAGS } from '@/lib/priorityFlags'
import { revenueOf, usd } from '@/lib/revenue'
import { fieldOf, idOf, kanbanBoard } from '@/lib/spec'
import { cn } from '@/lib/utils'
import { useViewPreference, type ListSettings } from '@/lib/viewPreferences'
import type { FieldSpec } from '@/types/field'

/**
 * The default columns, in order. The register's own fields — read off it, so
 * a label changed in Administration reads the same here — and only the ones
 * it has. A person may choose others (View Settings -> Manage Columns).
 */
const COLUMNS = [
  'opportunity_name',
  'end_client',
  'customer_partner_si',
  'project_stage',
  'total_value_tcv',
  'probability_pct',
  'sales_owner',
]

/** Each list's key for a person's own columns (user_view_preferences — letters and _ only). */
const VIEW_KEYS: Record<string, string> = {
  is_low_hanging: 'list:opportunities_low_hanging',
  is_top_10: 'list:opportunities_top_ten',
}

const NOT_A_COLUMN = new Set(['childlist', 'autonumber', 'file'])

interface Props {
  /** e.g. 'is_low_hanging' */
  flagField: string
  /** e.g. 'low_hanging_rank' */
  rankField: string
  cap: number
  /**
   * The page's filter and search, as the List sends them. Applied only while
   * `narrowed` (a condition or a search is on): the slots then show just the
   * picks that match, so the filter bar means the same here as on the List.
   */
  filter?: Record<string, string | string[]>
  narrowed?: boolean
  /** The fields a person may add as columns — the page's filter fields, as the List's. */
  columnChoices?: FieldSpec[]
}

function messageOf(err: unknown, fallback: string): string {
  if (!isAxiosError(err)) return fallback
  const detail = (err.response?.data as { detail?: unknown } | undefined)?.detail
  if (typeof detail === 'string') return detail
  if (detail && typeof detail === 'object' && typeof (detail as { message?: unknown }).message === 'string') {
    return (detail as { message: string }).message
  }
  return fallback
}

/**
 * A fixed-length, rank-ordered view of one priority pick — Low Hanging or Top
 * 10 — showing every slot from 1 to `cap`, filled or open.
 *
 * Release 1.2 (15 Oct 2026), as the List looks and works:
 *   - three cards on top: slots filled, Revenue, Weighted (the revenue rule);
 *   - the List's records box and cells, with View Settings (Manage Columns,
 *     Wrap / Clip) kept per person, as the List's are;
 *   - drag a pick onto another slot: an open slot takes it, a
 *     filled one swaps — one request (PUT /opportunities/priority/{flag});
 *   - an open slot adds an opportunity in place; one on the OTHER list moves
 *     here, as the record's own page does (the two are mutually exclusive),
 *     and the picker says so before it is chosen;
 *   - a whole row opens the opportunity; Remove is behind ⋯ and a question.
 */
export function RankedOpportunityList({ flagField, rankField, cap, filter, narrowed, columnChoices }: Props) {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [error, setError] = useState<string | null>(null)
  const [removing, setRemoving] = useState<{ row: ListRow; rank: number } | null>(null)
  const [dragFrom, setDragFrom] = useState<number | null>(null)
  const [dragOver, setDragOver] = useState<number | null>(null)
  const [managing, setManaging] = useState(false)
  const pick = PRIORITY_FLAGS.find((p) => p.flag === flagField)
  const label = pick?.label ?? 'this list'
  const other = PRIORITY_FLAGS.find((p) => p.flag !== flagField)
  // The rank is a register field too ("Top 10 Rank"): the first column, always
  // shown — Manage Columns lists it locked, as it does the name.
  const rankSpec = fieldOf('opportunities', rankField)

  // ---- this person's columns
  const prefs = useViewPreference<ListSettings>(columnChoices ? VIEW_KEYS[flagField] : undefined)
  const mine = prefs.settings ?? {}
  const defaults = useMemo(
    () => COLUMNS.map((name) => fieldOf('opportunities', name)).filter((f): f is FieldSpec => Boolean(f)),
    []
  )
  const available = useMemo(() => {
    const out: FieldSpec[] = []
    for (const f of [...(rankSpec ? [rankSpec] : []), ...defaults, ...(columnChoices ?? [])]) {
      if (NOT_A_COLUMN.has(f.type) || out.some((o) => o.api_name === f.api_name)) continue
      out.push(f)
    }
    return out
  }, [rankSpec, defaults, columnChoices])
  const columns = useMemo(() => {
    const chosen = (mine.columns ?? [])
      .filter((name) => name !== rankField) // drawn first, always — not one of the chosen
      .map((name) => available.find((f) => f.api_name === name))
      .filter((f): f is FieldSpec => Boolean(f))
    const all = chosen.length ? chosen : defaults
    // Pinned ones first, held at the left after the rank — as on the List.
    const pinned = mine.pinned ?? []
    return [
      ...pinned.map((name) => all.find((f) => f.api_name === name)).filter((f): f is FieldSpec => Boolean(f)),
      ...all.filter((f) => !pinned.includes(f.api_name)),
    ]
  }, [mine.columns, mine.pinned, available, defaults, rankField])
  const wrap = mine.wrap ?? true
  const customizable = Boolean(columnChoices)

  // ---- pin, hide and resize, from each header's menu and its right edge (as the List's)
  const pinnedShown = columns.filter((f) => (mine.pinned ?? []).includes(f.api_name)).map((f) => f.api_name)
  const pinnedKey = pinnedShown.join(',')
  const lastPinned = pinnedShown[pinnedShown.length - 1]
  const isPinned = (name: string) => pinnedShown.includes(name)
  const widths = mine.widths ?? {}
  const [dragWidth, setDragWidth] = useState<{ name: string; width: number } | null>(null)
  const widthOf = (name: string) => (dragWidth?.name === name ? dragWidth.width : widths[name])
  const headerRefs = useRef<Record<string, HTMLTableCellElement | null>>({})
  const rankHeader = useRef<HTMLTableCellElement | null>(null)

  // Where each pinned column sits: after the rank column and the pinned ones before it.
  const [pinLeft, setPinLeft] = useState<Record<string, number>>({})
  useLayoutEffect(() => {
    const names = pinnedKey ? pinnedKey.split(',') : []
    const measure = () => {
      const next: Record<string, number> = {}
      let left = rankHeader.current?.getBoundingClientRect().width ?? 0
      for (const name of names) {
        next[name] = left
        left += headerRefs.current[name]?.getBoundingClientRect().width ?? 0
      }
      setPinLeft((prev) => (JSON.stringify(prev) === JSON.stringify(next) ? prev : next))
    }
    measure()
    const observer = new ResizeObserver(measure)
    for (const cell of [rankHeader.current, ...names.map((n) => headerRefs.current[n])]) {
      if (cell) observer.observe(cell)
    }
    return () => observer.disconnect()
  }, [pinnedKey])

  const togglePin = (name: string) => {
    const pinned = mine.pinned ?? []
    prefs.save({ ...mine, pinned: pinned.includes(name) ? pinned.filter((n) => n !== name) : [...pinned, name] })
  }
  const hideColumn = (name: string) =>
    prefs.save({
      ...mine,
      columns: columns.map((f) => f.api_name).filter((n) => n !== name),
      pinned: (mine.pinned ?? []).filter((n) => n !== name),
    })

  /** Drag a header's right edge; the width is saved when the mouse is let go. */
  const startResize = (name: string, event: React.MouseEvent) => {
    event.preventDefault()
    event.stopPropagation()
    const startX = event.clientX
    const startWidth = headerRefs.current[name]?.getBoundingClientRect().width ?? 160
    let width = startWidth
    const move = (e: MouseEvent) => {
      width = Math.min(800, Math.max(60, Math.round(startWidth + e.clientX - startX)))
      setDragWidth({ name, width })
    }
    const up = () => {
      document.removeEventListener('mousemove', move)
      document.removeEventListener('mouseup', up)
      setDragWidth(null)
      prefs.save({ ...mine, widths: { ...widths, [name]: width } })
    }
    document.addEventListener('mousemove', move)
    document.addEventListener('mouseup', up)
  }

  // ---- data
  const { data, isLoading, isError } = useQuery({
    queryKey: ['collection', 'opportunities'],
    queryFn: async () => (await api.get<ListRow[]>('/opportunities')).data,
  })

  // Which opportunities the filter lets through — asked of the same endpoint
  // the List uses, so the two can never disagree.
  const matching = useQuery({
    queryKey: ['collection', 'opportunities', filter ?? {}],
    enabled: Boolean(narrowed),
    queryFn: async () => (await api.get<ListRow[]>('/opportunities', { params: filter })).data,
  })
  const matches = narrowed ? new Set((matching.data ?? []).map((row) => idOf(row))) : null

  const refresh = () =>
    Promise.all([
      queryClient.invalidateQueries({ queryKey: ['collection', 'opportunities'] }),
      queryClient.invalidateQueries({ queryKey: ['list', 'opportunities'] }),
      queryClient.invalidateQueries({ queryKey: ['record', 'opportunities'] }),
    ])

  const unmark = useMutation({
    mutationFn: async (id: string) => (await api.put(`/opportunities/${id}`, { [flagField]: false })).data,
    onSuccess: async () => {
      setError(null)
      setRemoving(null)
      await refresh()
    },
    onError: (err) => {
      setRemoving(null)
      setError(messageOf(err, `Could not remove this opportunity from ${label}.`))
    },
  })

  const add = useMutation({
    mutationFn: async ({ id, rank }: { id: string; rank: number }) =>
      (await api.put(`/opportunities/${id}`, { [flagField]: true, [rankField]: rank })).data,
    onSuccess: async () => {
      setError(null)
      await refresh()
    },
    onError: (err) => setError(messageOf(err, `Could not add this opportunity to ${label}.`)),
  })

  const reorder = useMutation({
    mutationFn: async (ranks: Record<string, number>) => {
      await api.put(`/opportunities/priority/${flagField}`, { ranks })
    },
    onSuccess: async () => {
      setError(null)
      await refresh()
    },
    onError: (err) => setError(messageOf(err, `Could not change the order of ${label}.`)),
  })

  if (isLoading) return <p className="py-6 text-sm text-muted-foreground">Loading…</p>
  if (isError) return <p className="py-6 text-sm text-destructive">Could not load opportunities.</p>

  const byRank = new Map<number, ListRow>()
  for (const row of data ?? []) {
    if (!row[flagField]) continue
    const rank = Number(row[rankField])
    if (Number.isFinite(rank)) byRank.set(rank, row)
  }
  const picks = [...byRank.values()]
  const shown = matches ? picks.filter((row) => matches.has(idOf(row))) : picks
  const hidden = picks.length - shown.length

  // What may be added: open work not on this list already.
  const finished = new Set(kanbanBoard.terminal_statuses)
  const candidates = (data ?? []).filter((row) => !row[flagField] && !finished.has(String(row.lead_status ?? '')))

  // The revenue rule, as the board totals: counted records only, in USD;
  // Weighted is each one's USD times its own Probability (a fraction).
  let revenue = 0
  let weighted = 0
  for (const row of shown) {
    const r = revenueOf(row)
    if (!r?.counted || r.usd === null) continue
    revenue += r.usd
    weighted += r.usd * (typeof row.probability_pct === 'number' ? row.probability_pct : 0)
  }

  /** A pick dropped on a slot: an open slot takes it, a filled one swaps with it. */
  const drop = (target: number) => {
    const from = dragFrom
    setDragFrom(null)
    setDragOver(null)
    if (from === null || from === target) return
    const moving = byRank.get(from)
    if (!moving) return
    const there = byRank.get(target)
    reorder.mutate(there ? { [idOf(moving)]: target, [idOf(there)]: from } : { [idOf(moving)]: target })
  }

  const span = columns.length + 2
  const clip = !wrap && 'max-w-[22rem] truncate whitespace-nowrap'

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-3">
      {/* The three figures, as cards above the list. */}
      <div className="grid shrink-0 gap-3 sm:grid-cols-3">
        <SummaryCard label="Slots filled">
          <span className="tabular-nums">{picks.length}</span>
          <span className="text-muted-foreground text-base font-normal"> of {cap}</span>
          <div className="bg-muted mt-2 h-1.5 overflow-hidden rounded-full">
            <div className="bg-primary h-full rounded-full" style={{ width: `${(picks.length / cap) * 100}%` }} />
          </div>
        </SummaryCard>
        <SummaryCard label="Revenue" note={hidden > 0 ? `${hidden} hidden by your filter` : undefined}>
          <span className="tabular-nums">{usd(revenue)}</span>
        </SummaryCard>
        <SummaryCard
          label="Weighted"
          title="Each counted opportunity's revenue in USD times its own Probability."
          note={hidden > 0 ? `${hidden} hidden by your filter` : undefined}
        >
          <span className="tabular-nums">{usd(weighted)}</span>
        </SummaryCard>
      </div>

      {error && <p className="text-sm text-destructive">{error}</p>}

      <div className="bg-card flex min-h-0 flex-1 flex-col overflow-hidden rounded-lg shadow-sm">
        <div className={cn('min-h-0 flex-1 overflow-auto', reorder.isPending && 'opacity-60')}>
          <table className="w-full border-separate border-spacing-0 text-sm">
            <thead className="text-label">
              <tr>
                <th
                  ref={rankHeader}
                  className={cn(
                    'border-border bg-card sticky top-0 left-0 z-30 w-24 border-b px-4 py-3 text-left font-semibold whitespace-nowrap text-muted-foreground',
                    !lastPinned && 'shadow-[inset_-1px_0_0_var(--border)]'
                  )}
                >
                  {rankSpec?.label ?? 'Rank'}
                </th>
                {columns.map((f, i) => (
                  <th
                    key={f.qref}
                    ref={(el) => {
                      headerRefs.current[f.api_name] = el
                    }}
                    style={{
                      ...(widthOf(f.api_name) ? { width: widthOf(f.api_name), minWidth: widthOf(f.api_name) } : {}),
                      ...(isPinned(f.api_name) ? { left: pinLeft[f.api_name] ?? 0 } : {}),
                    }}
                    className={cn(
                      'group/col border-border bg-card sticky top-0 z-10 border-b p-0 text-left font-semibold whitespace-nowrap text-muted-foreground',
                      isPinned(f.api_name) && 'z-30',
                      f.api_name === lastPinned && 'shadow-[inset_-1px_0_0_var(--border)]'
                    )}
                  >
                    <div className={cn('flex w-full items-center gap-1 py-3 pr-2 pl-4', NUMERIC_TYPES.has(f.type) && 'flex-row-reverse')}>
                      <span className={cn('min-w-0 flex-1 truncate', NUMERIC_TYPES.has(f.type) && 'text-right')}>{f.label}</span>
                      {customizable && (
                        // No Asc / Desc here: the ranks are this list's order.
                        <ColumnMenu
                          label={f.label}
                          pinned={isPinned(f.api_name)}
                          canHide={f.api_name !== defaults[0]?.api_name && columns.length > 1}
                          onPin={() => togglePin(f.api_name)}
                          onHide={() => hideColumn(f.api_name)}
                        />
                      )}
                    </div>
                    {i < columns.length - 1 && (
                      <span aria-hidden className="bg-border pointer-events-none absolute top-1/2 right-0 h-5 w-px -translate-y-1/2" />
                    )}
                    {customizable && (
                      <span
                        aria-hidden
                        onMouseDown={(e) => startResize(f.api_name, e)}
                        className="hover:bg-primary/40 absolute top-0 right-0 h-full w-1.5 cursor-col-resize"
                      />
                    )}
                  </th>
                ))}
                <th className="border-border bg-card sticky top-0 right-0 z-20 w-12 border-b p-0 text-right shadow-[inset_1px_0_0_var(--border)]">
                  {columnChoices && (
                    <ViewSettings
                      wrap={wrap}
                      hasOwn={prefs.settings !== null}
                      hasWidths={Object.keys(widths).length > 0}
                      onResetWidths={() => prefs.save({ ...mine, widths: {} })}
                      onManage={() => setManaging(true)}
                      onWrap={(next) => prefs.save({ ...mine, wrap: next })}
                      onReset={() => prefs.reset()}
                    />
                  )}
                </th>
              </tr>
            </thead>
            <tbody>
              {Array.from({ length: cap }, (_, i) => i + 1).map((rank) => {
                const row = byRank.get(rank)
                // Filtered: only the picks that match; an open slot matches nothing.
                if (matches && (!row || !matches.has(idOf(row)))) return null
                const dropTarget = {
                  onDragOver: (e: React.DragEvent) => {
                    if (dragFrom === null) return
                    e.preventDefault()
                    if (dragOver !== rank) setDragOver(rank)
                  },
                  onDragLeave: () => setDragOver((current) => (current === rank ? null : current)),
                  onDrop: (e: React.DragEvent) => {
                    e.preventDefault()
                    drop(rank)
                  },
                }
                const over = dragOver === rank && dragFrom !== null && dragFrom !== rank
                // One style for every rank, as the mark on the List and the
                // cards: a solid chip. An open slot's is the same chip, muted.
                const badge = (
                  <span
                    title={row ? 'Drag to another slot to change its rank' : undefined}
                    className={cn(
                      'inline-flex h-6 min-w-6 items-center justify-center rounded-md px-1.5 text-xs font-semibold tabular-nums',
                      row ? 'bg-foreground text-background cursor-grab' : 'bg-muted text-muted-foreground'
                    )}
                  >
                    {rank}
                  </span>
                )
                if (!row) {
                  return (
                    <tr key={rank} {...dropTarget} className={cn('group/row', over && 'bg-primary/10')}>
                      <td
                        className={cn(
                          'border-border bg-card group-hover/row:bg-accent sticky left-0 z-20 border-b px-4 py-3',
                          !lastPinned && 'shadow-[inset_-1px_0_0_var(--border)]'
                        )}
                      >
                        {badge}
                      </td>
                      <td colSpan={span - 1} className="border-border text-muted-foreground border-b px-4 py-2">
                        <span className="flex flex-wrap items-center gap-3">
                          <span className="italic">{over ? `Drop to move it to #${rank}` : 'Open'}</span>
                          {!over && (
                            <AddPick
                              rank={rank}
                              label={label}
                              other={other}
                              candidates={candidates}
                              busy={add.isPending}
                              onPick={(id) => add.mutate({ id, rank })}
                            />
                          )}
                        </span>
                      </td>
                    </tr>
                  )
                }
                const id = idOf(row)
                return (
                  <tr
                    key={rank}
                    tabIndex={0}
                    role="link"
                    draggable
                    onDragStart={(e) => {
                      e.dataTransfer.effectAllowed = 'move'
                      setDragFrom(rank)
                    }}
                    onDragEnd={() => {
                      setDragFrom(null)
                      setDragOver(null)
                    }}
                    {...dropTarget}
                    onClick={() => navigate(`/opportunities/${id}`)}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter') navigate(`/opportunities/${id}`)
                    }}
                    className={cn(
                      'group/row hover:bg-accent focus-visible:bg-accent cursor-pointer outline-none',
                      dragFrom === rank && 'opacity-50',
                      over && 'bg-primary/10'
                    )}
                  >
                    <td
                        className={cn(
                          'border-border bg-card group-hover/row:bg-accent sticky left-0 z-20 border-b px-4 py-3',
                          !lastPinned && 'shadow-[inset_-1px_0_0_var(--border)]'
                        )}
                      >
                        {badge}
                      </td>
                    {columns.map((f) => (
                      <td
                        key={f.qref}
                        style={{
                          ...(widthOf(f.api_name)
                            ? { width: widthOf(f.api_name), minWidth: widthOf(f.api_name), maxWidth: widthOf(f.api_name) }
                            : {}),
                          ...(isPinned(f.api_name) ? { left: pinLeft[f.api_name] ?? 0 } : {}),
                        }}
                        className={cn(
                          'border-border border-b px-4 py-3 align-middle',
                          clip,
                          NUMERIC_TYPES.has(f.type) && 'text-right tabular-nums',
                          f.api_name === 'opportunity_name' && 'text-link',
                          isPinned(f.api_name) && 'bg-card group-hover/row:bg-accent sticky z-10',
                          f.api_name === lastPinned && 'shadow-[inset_-1px_0_0_var(--border)]'
                        )}
                      >
                        {f.api_name === 'opportunity_name' ? (
                          <ReadThroughText row={row} apiName="opportunity_name" />
                        ) : (
                          (opportunityListCell(f, row) ?? <ListCell field={f} row={row} />)
                        )}
                      </td>
                    ))}
                    <td
                      className="border-border bg-card group-hover/row:bg-accent sticky right-0 z-10 border-b px-2 py-3 text-right shadow-[inset_1px_0_0_var(--border)]"
                      onClick={(e) => e.stopPropagation()}
                    >
                      <RowMenu label={label} onRemove={() => setRemoving({ row, rank })} />
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      </div>

      {columnChoices && (
        <ChooseFieldsDialog
          open={managing}
          title="Manage Columns"
          fields={available}
          selected={[...(rankSpec ? [rankField] : []), ...columns.map((f) => f.api_name)]}
          locked={[...(rankSpec ? [rankField] : []), ...(defaults[0] ? [defaults[0].api_name] : [])]}
          onClose={() => setManaging(false)}
          onSave={(chosen) => {
            setManaging(false)
            prefs.save({ ...mine, columns: chosen.filter((name) => name !== rankField) })
          }}
        />
      )}

      <Dialog open={removing !== null} onOpenChange={(open) => !open && setRemoving(null)}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>Remove from {label}?</DialogTitle>
            <DialogDescription>
              {removing
                ? `${String(removing.row.opportunity_name ?? 'This opportunity')} leaves the list. Slot #${removing.rank} becomes open.`
                : null}
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setRemoving(null)}>
              Keep it
            </Button>
            <Button
              variant="destructive"
              disabled={unmark.isPending}
              onClick={() => removing && unmark.mutate(idOf(removing.row))}
            >
              Remove from {label}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}

/** One figure above the list. */
function SummaryCard({
  label,
  title,
  note,
  children,
}: {
  label: string
  title?: string
  note?: string
  children: React.ReactNode
}) {
  return (
    <div className="bg-card rounded-lg px-4 py-3 shadow-sm" title={title}>
      <p className="text-muted-foreground text-label">{label}</p>
      <div className="mt-1 text-xl font-semibold">{children}</div>
      {note && <p className="text-muted-foreground mt-1 text-xs">{note}</p>}
    </div>
  )
}

/**
 * Add an opportunity to an open slot. Open work only; one on the OTHER list
 * says it will move — the two lists are mutually exclusive
 * (backend/app/priority_flags.py), as on the record's own page.
 */
function AddPick({
  rank,
  label,
  other,
  candidates,
  busy,
  onPick,
}: {
  rank: number
  label: string
  other?: { flag: string; rank: string; label: string }
  candidates: ListRow[]
  busy: boolean
  onPick: (id: string) => void
}) {
  const [open, setOpen] = useState(false)
  const sorted = [...candidates].sort((a, b) =>
    String(a.opportunity_name ?? '').localeCompare(String(b.opportunity_name ?? ''))
  )
  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button
          type="button"
          variant="ghost"
          size="sm"
          disabled={busy}
          className="text-link h-7 px-2 not-italic"
          onClick={(e) => e.stopPropagation()}
        >
          <PlusIcon className="size-3.5" />
          Add to #{rank}
        </Button>
      </PopoverTrigger>
      <PopoverContent align="start" className="w-96 p-0">
        <Command>
          <CommandInput placeholder="Find an opportunity…" />
          <CommandList className="max-h-72">
            <CommandEmpty>No open opportunity to add.</CommandEmpty>
            {sorted.map((row) => {
              const id = idOf(row)
              const elsewhere = other && row[other.flag] ? `On ${other.label} #${String(row[other.rank] ?? '?')} — moves to ${label}` : null
              return (
                <CommandItem
                  key={id}
                  value={`${String(row.opportunity_name ?? '')} ${String(row.__labels?.end_client ?? '')} ${id}`}
                  onSelect={() => {
                    setOpen(false)
                    onPick(id)
                  }}
                >
                  <span className="min-w-0 flex-1">
                    <span className="block truncate">{String(row.opportunity_name ?? 'Untitled')}</span>
                    <span className="text-muted-foreground block truncate text-xs">
                      {elsewhere ?? String(row.__labels?.end_client ?? '—')}
                    </span>
                  </span>
                </CommandItem>
              )
            })}
          </CommandList>
        </Command>
      </PopoverContent>
    </Popover>
  )
}

/** A pick's ⋯ menu: what can be done to it here, which is taking it off. */
function RowMenu({ label, onRemove }: { label: string; onRemove: () => void }) {
  const [open, setOpen] = useState(false)
  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button type="button" variant="ghost" size="icon" aria-label="More actions" className="data-[state=open]:bg-accent">
          <EllipsisIcon className="size-4" />
        </Button>
      </PopoverTrigger>
      <PopoverContent align="end" className="w-52 p-1.5">
        <button
          type="button"
          className="hover:bg-accent flex w-full items-center gap-3 rounded-md px-2.5 py-2 text-left text-sm"
          onClick={() => {
            setOpen(false)
            onRemove()
          }}
        >
          <XIcon className="text-muted-foreground size-4" />
          Remove from {label}
        </button>
      </PopoverContent>
    </Popover>
  )
}
