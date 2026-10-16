import { forwardRef, useEffect, useLayoutEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { useNavigate } from 'react-router-dom'
import { keepPreviousData, useQuery } from '@tanstack/react-query'
import {
  ArrowDownIcon,
  ArrowUpIcon,
  CheckIcon,
  ChevronLeftIcon,
  ChevronRightIcon,
  Columns3Icon,
  EyeIcon,
  EyeOffIcon,
  MenuIcon,
  PinIcon,
  PinOffIcon,
  RotateCcwIcon,
  SearchIcon,
  SettingsIcon,
  SlidersHorizontalIcon,
} from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { ChooseFieldsDialog } from '@/components/list/ChooseFieldsDialog'
import { ListCell, NUMERIC_TYPES, type ListRow } from '@/components/list/ListCell'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { api } from '@/lib/api'
import { PAGE_SIZES, useViewPreference, type ListSettings } from '@/lib/viewPreferences'
import { fieldOf, fieldsNamed, idOf, listViewFor, type ListView } from '@/lib/spec'
import { cn } from '@/lib/utils'
import type { FieldSpec } from '@/types/field'

/** A column a list can show: a value on the row, not a table or a record number. */
const NOT_A_COLUMN = new Set(['childlist', 'autonumber', 'file'])

/**
 * The label a search key is shown under in the filter box.
 *
 * A list view's `module` is its list_views KEY, which is not always a module
 * that owns the fields: `registrations` is described by the partners module,
 * and Partner records by accounts. fieldOf(module, name) found nothing for
 * either, so the box read "Filter project_name, partner, end_client…". The
 * view's own columns are the fields a reader sees, so they answer first; then
 * the modules those columns come from, for a key that is searched but not shown.
 */
function searchLabelOf(view: ListView, module: string, name: string): string {
  const column = view.fields.find((f) => f.api_name === name)
  if (column) return column.label
  for (const owner of new Set(view.fields.map((f) => f.module))) {
    const hit = fieldsNamed(owner, name)[0]
    if (hit) return hit.label
  }
  return fieldOf(module, name)?.label ?? name
}

export interface RecordListViewProps {
  /** Module in fields.json whose list_views entry supplies the columns. */
  module: string
  /** Store collection the rows come from. */
  collection: string
  /** Where a row click goes: `${basePath}/${id}`. */
  basePath: string
  /**
   * Server-side equality filters, e.g. { account: 'ACC-001' }. An array value
   * matches any of its entries — { account_type: ['PARTNER_SI', 'OEM…'] }.
   */
  filter?: Record<string, string | string[]>
  /** api_names to leave out — a column that is constant in a filtered list. */
  hiddenColumns?: string[]
  /** Override the rendering of one cell. Return undefined to fall through. */
  renderCell?: (field: FieldSpec, row: ListRow) => ReactNode | undefined
  /**
   * Classes for a coloured stripe down the left edge of a row — the pipeline
   * modules pass ragAccent, so a Red pursuit is marked here exactly as it is
   * on its Kanban card and its record header. Return '' for no stripe. Opt-in:
   * Accounts and Contacts carry no such judgement and pass nothing.
   */
  rowAccent?: (row: ListRow) => string
  emptyMessage?: string
  pageSize?: number
  /**
   * Hide the filter box. For an embedded list that is ALREADY filtered to one
   * parent — the contact panels on a Related tab — where the result is a
   * handful of rows a reader can see at once, so a search box over them offers
   * to narrow something that is not wide.
   *
   * Opt-in, and deliberately not inferred from the row count: a list that grows
   * a search box once it passes some threshold changes shape under the user,
   * and the full-page lists this component also serves need theirs whether they
   * hold three rows today or three hundred.
   */
  hideSearch?: boolean
  /**
   * Hide the footer — the total, the rows-per-page selector and the page
   * chevrons. Same case as `hideSearch`: an embedded list already narrowed to
   * one parent holds a handful of rows, and paging controls over two of them
   * are chrome for a problem the list does not have.
   *
   * The list still pages internally on `pageSize`, so a parent with more rows
   * than that shows the first page rather than an unbounded table. Pass it only
   * where that ceiling is acceptable.
   */
  hidePager?: boolean
  /**
   * The fields a person may add as columns — Zoho's Manage Columns (Release
   * 1.2). Given, the list gets View Settings and each person's own columns,
   * widths, rows per page and clip/wrap, stored against them in PostgreSQL;
   * everyone else keeps the default view. A list page passes its filter
   * panel's fields, so a list offers exactly what it can be filtered by.
   */
  columnChoices?: FieldSpec[]
  /**
   * Fill the space it is given and scroll inside it — a module's own list page
   * (ListPageLayout), as Zoho's records box: the header row stays put, the
   * footer sits inside the box. Embedded lists leave it off and grow with their rows.
   */
  fill?: boolean
}

/**
 * The list screen for any module that declares a list_views entry in
 * spec/extensions.json. Which columns appear, what the text filter searches and
 * what the default sort is are all spec, never props and never literals here —
 * CLAUDE.md rule 3.
 *
 * Paging, sorting and searching are all done by the server. This component
 * holds the query parameters and renders what comes back.
 */
export function RecordListView({
  module,
  collection,
  basePath,
  filter,
  hiddenColumns,
  renderCell,
  rowAccent,
  emptyMessage,
  pageSize = 25,
  hideSearch,
  hidePager,
  columnChoices,
  fill,
}: RecordListViewProps) {
  const navigate = useNavigate()
  const view = listViewFor(module)
  const customizable = Boolean(columnChoices)
  const prefs = useViewPreference<ListSettings>(customizable ? `list:${module}` : undefined)
  const mine = prefs.settings ?? {}
  const [managing, setManaging] = useState(false)

  const [search, setSearch] = useState('')
  const [q, setQ] = useState('')
  const [page, setPage] = useState(1)
  const [limit, setLimit] = useState(pageSize)
  const [sort, setSort] = useState(() => view?.default_sort ?? '')
  const [order, setOrder] = useState<'asc' | 'desc'>('asc')

  // A different filter is a different result set: page 3 of the old one may
  // not exist in the new one. Keyed on the filter's content, not its identity,
  // because a parent rebuilds the object on every render.
  const filterKey = JSON.stringify(filter ?? {})
  useEffect(() => setPage(1), [filterKey])

  // Debounced so a five-letter search is one request, not five.
  useEffect(() => {
    const t = setTimeout(() => {
      setQ(search)
      setPage(1)
    }, 250)
    return () => clearTimeout(t)
  }, [search])

  // Every column this list can show: its default columns, then the fields the
  // page offers — each once, by api_name.
  const available = useMemo(() => {
    const out: FieldSpec[] = []
    for (const f of [...(view?.fields ?? []), ...(columnChoices ?? [])]) {
      if (NOT_A_COLUMN.has(f.type) || out.some((o) => o.api_name === f.api_name)) continue
      out.push(f)
    }
    return out
  }, [view, columnChoices])

  // This person's columns, read against what the register still has; the
  // default view's when they have chosen none. Pinned ones first.
  const pinned = useMemo(() => mine.pinned ?? [], [mine.pinned])
  const columns = useMemo(() => {
    const chosen = (mine.columns ?? [])
      .map((name) => available.find((f) => f.api_name === name))
      .filter((f): f is FieldSpec => Boolean(f))
    const shown = (chosen.length ? chosen : (view?.fields ?? [])).filter((f) => !hiddenColumns?.includes(f.api_name))
    return [
      ...pinned.map((name) => shown.find((f) => f.api_name === name)).filter((f): f is FieldSpec => Boolean(f)),
      ...shown.filter((f) => !pinned.includes(f.api_name)),
    ]
  }, [mine.columns, available, view, hiddenColumns, pinned])
  const pinnedShown = columns.filter((f) => pinned.includes(f.api_name)).map((f) => f.api_name)
  const pinnedKey = pinnedShown.join(',')
  /** The record's name: always shown, so it can't be hidden. */
  const nameColumn = view?.fields[0]?.api_name

  // Rows per page: theirs once it arrives.
  useEffect(() => {
    if (mine.page_size) setLimit(mine.page_size)
  }, [mine.page_size])

  const widths = mine.widths ?? {}
  const wrap = mine.wrap ?? true
  const [dragWidth, setDragWidth] = useState<{ name: string; width: number } | null>(null)
  const widthOf = (name: string) => (dragWidth?.name === name ? dragWidth.width : widths[name])
  const headerRefs = useRef<Record<string, HTMLTableCellElement | null>>({})

  // Where each pinned column sits: the widths of the pinned ones before it,
  // measured, so a column sized by its content still lines up.
  const [pinLeft, setPinLeft] = useState<Record<string, number>>({})
  useLayoutEffect(() => {
    const names = pinnedKey ? pinnedKey.split(',') : []
    const measure = () => {
      const next: Record<string, number> = {}
      let left = 0
      for (const name of names) {
        next[name] = left
        left += headerRefs.current[name]?.getBoundingClientRect().width ?? 0
      }
      setPinLeft((prev) => (JSON.stringify(prev) === JSON.stringify(next) ? prev : next))
    }
    measure()
    const observer = new ResizeObserver(measure)
    for (const name of names) {
      const cell = headerRefs.current[name]
      if (cell) observer.observe(cell)
    }
    return () => observer.disconnect()
  }, [pinnedKey])
  const isPinned = (name: string) => pinnedShown.includes(name)
  const lastPinned = pinnedShown[pinnedShown.length - 1]

  const togglePin = (name: string) =>
    prefs.save({
      ...mine,
      pinned: pinned.includes(name) ? pinned.filter((n) => n !== name) : [...pinned, name],
    })
  const hideColumn = (name: string) =>
    prefs.save({
      ...mine,
      columns: columns.map((f) => f.api_name).filter((n) => n !== name),
      pinned: pinned.filter((n) => n !== name),
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

  const params = useMemo(() => {
    const p: Record<string, string | string[]> = {
      _page: String(page),
      _limit: String(limit),
    }
    if (sort) {
      p._sort = sort
      p._order = order
    }
    if (q) {
      p.q = q
      if (view?.search?.length) p._search = view.search.join(',')
    }
    return { ...p, ...filter }
  }, [page, limit, sort, order, q, view, filter])

  const { data, isLoading, isError, isPlaceholderData } = useQuery({
    queryKey: ['list', collection, params],
    queryFn: async () => {
      const res = await api.get<ListRow[]>(`/${collection}`, { params })
      return {
        rows: res.data,
        total: Number(res.headers['x-total-count'] ?? res.data.length),
      }
    },
    placeholderData: keepPreviousData,
  })

  if (!view) {
    return (
      <div className="rounded-lg border border-dashed p-6 text-sm text-muted-foreground">
        <span className="font-medium text-foreground">No list view defined.</span> Add a{' '}
        <code className="font-mono text-xs">list_views.{module}</code> entry to
        spec/extensions.json — this screen will not invent a column set.
      </div>
    )
  }

  const rows = data?.rows ?? []
  const filtered = Object.keys(filter ?? {}).length > 0
  const total = data?.total ?? 0
  const lastPage = Math.max(1, Math.ceil(total / limit))
  const first = total === 0 ? 0 : (page - 1) * limit + 1
  const last = Math.min(page * limit, total)

  const sortBy = (field: FieldSpec, next: 'asc' | 'desc') => {
    setSort(field.api_name)
    setOrder(next)
    setPage(1)
  }

  const footer = (
    <>
        {/* Footer reads as the reference's does — "Total Records N" left, the
            shown range and chevrons right (§5a.3). */}
        <div
          className={cn(
            'text-muted-foreground flex flex-wrap items-center justify-between gap-3 text-sm',
            // In the box, under a hairline, as Zoho's.
            fill && 'border-border shrink-0 border-t px-4 py-1.5'
          )}
          hidden={hidePager}
        >
          <span>
            Total Records <span className="text-foreground font-medium">{total}</span>
          </span>

          <div className="flex items-center gap-2">
            <Select
              value={String(limit)}
              onValueChange={(v) => {
                setLimit(Number(v))
                setPage(1)
                if (customizable) prefs.save({ ...mine, page_size: Number(v) })
              }}
            >
              <SelectTrigger className="h-8 w-[92px]">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {PAGE_SIZES.map((n) => (
                  <SelectItem key={n} value={String(n)}>
                    {n} / page
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>

            <span className="tabular-nums">
              {first} to {last}
            </span>
            <Button
              type="button"
              variant="ghost"
              size="icon"
              aria-label="Previous page"
              disabled={page <= 1}
              onClick={() => setPage((p) => Math.max(1, p - 1))}
            >
              <ChevronLeftIcon className="size-4" />
            </Button>
            <Button
              type="button"
              variant="ghost"
              size="icon"
              aria-label="Next page"
              disabled={page >= lastPage}
              onClick={() => setPage((p) => p + 1)}
            >
              <ChevronRightIcon className="size-4" />
            </Button>
          </div>
        </div>
    </>
  )

  return (
    <div className={cn(fill ? 'flex min-h-0 flex-1 flex-col' : 'space-y-3 py-3')}>
      {!hideSearch && (
        <div className="relative max-w-sm">
          <SearchIcon className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            className="pl-9"
            placeholder={`Filter ${
              view.search.length ? view.search.map((name) => searchLabelOf(view, module, name)).join(', ') : 'anything'
            }…`}
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>
      )}

      {/* A surface, not a bordered box, and no vertical rules inside it: the
          columns are held apart by their own padding. The header keeps one
          hairline under it because a table without it loses where the data
          starts; rows separate on hover and on the zebra ground instead. */}
      <div className={cn('bg-card overflow-hidden rounded-lg shadow-sm', fill && 'flex min-h-0 flex-1 flex-col')}>
        <div className={cn('overflow-auto', fill && 'min-h-0 flex-1')}>
        <table className="w-full border-separate border-spacing-0 text-sm">
          <thead className="text-label">
            <tr>
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
                    'group/col border-border bg-card relative border-b p-0 text-left font-semibold whitespace-nowrap',
                    // The header row stays put while the box scrolls.
                    fill && 'sticky top-0 z-20',
                    isPinned(f.api_name) && 'sticky z-30',
                    f.api_name === lastPinned && 'shadow-[inset_-1px_0_0_var(--border)]'
                  )}
                >
                  <div
                    className={cn(
                      'flex w-full items-center gap-1 py-3 pr-2 pl-4',
                      NUMERIC_TYPES.has(f.type) && 'flex-row-reverse',
                      sort === f.api_name ? 'text-foreground' : 'text-muted-foreground'
                    )}
                  >
                    <span className={cn('min-w-0 flex-1 truncate', NUMERIC_TYPES.has(f.type) && 'text-right')}>
                      {f.label}
                    </span>
                    <ColumnMenu
                      label={f.label}
                      sorted={sort === f.api_name ? order : null}
                      pinned={customizable ? isPinned(f.api_name) : undefined}
                      canHide={customizable ? f.api_name !== nameColumn && columns.length > 1 : undefined}
                      onSort={(next) => sortBy(f, next)}
                      onPin={() => togglePin(f.api_name)}
                      onHide={() => hideColumn(f.api_name)}
                    />
                  </div>
                  {/* A thin rule between headers, as Zoho draws them. */}
                  {(customizable || i < columns.length - 1) && (
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
              {customizable && (
                <th className={cn('border-border bg-card sticky right-0 z-30 w-10 border-b p-0 text-right', fill && 'top-0')}>
                  <ViewSettings
                    wrap={wrap}
                    hasWidths={Object.keys(widths).length > 0}
                    hasOwn={prefs.settings !== null}
                    onManage={() => setManaging(true)}
                    onResetWidths={() => prefs.save({ ...mine, widths: {} })}
                    onWrap={(next) => prefs.save({ ...mine, wrap: next })}
                    onReset={() => {
                      prefs.reset()
                      setLimit(pageSize)
                      setPage(1)
                    }}
                  />
                </th>
              )}
            </tr>
          </thead>

          <tbody className={cn(isPlaceholderData && 'opacity-60')}>
            {isLoading && (
              <tr>
                <td colSpan={columns.length + (customizable ? 1 : 0)} className="px-4 py-8 text-center text-muted-foreground">
                  Loading…
                </td>
              </tr>
            )}

            {isError && (
              <tr>
                <td colSpan={columns.length + (customizable ? 1 : 0)} className="px-4 py-8 text-center text-destructive">
                  Could not load {collection}
                </td>
              </tr>
            )}

            {/* An empty module explains itself rather than saying "no records"
                — ARK_brand_UI.md §5a.4. The explanation is the caller's
                emptyMessage, so each screen says what its entity is. */}
            {!isLoading && !isError && rows.length === 0 && (
              <tr>
                <td colSpan={columns.length + (customizable ? 1 : 0)} className="px-6 py-12 text-center">
                  <p className="text-section text-foreground font-bold">
                    {q || filtered ? 'No matches' : `No ${module.replace(/_/g, ' ')} yet`}
                  </p>
                  <p className="text-muted-foreground mx-auto mt-1.5 max-w-md">
                    {q
                      ? `Nothing matches “${q}”.`
                      : filtered
                        ? 'Nothing matches these filters.'
                        : (emptyMessage ?? 'Nothing has been recorded here yet.')}
                  </p>
                </td>
              </tr>
            )}

            {rows.map((row) => {
              const id = idOf(row)
              return (
                <tr
                  key={id}
                  tabIndex={0}
                  role="link"
                  onClick={() => navigate(`${basePath}/${id}`)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') navigate(`${basePath}/${id}`)
                  }}
                  className={cn(
                    'group/row cursor-pointer outline-none even:bg-raised/60 hover:bg-accent focus-visible:bg-accent',
                    // A deactivated record is still listed — it is history, not
                    // a deletion — but it reads as retired rather than current.
                    row.active === false && 'text-muted-foreground opacity-60'
                  )}
                >
                  {columns.map((f, i) => (
                    <td
                      key={f.qref}
                      style={{
                        ...(widthOf(f.api_name)
                          ? { width: widthOf(f.api_name), minWidth: widthOf(f.api_name), maxWidth: widthOf(f.api_name) }
                          : {}),
                        ...(isPinned(f.api_name) ? { left: pinLeft[f.api_name] ?? 0 } : {}),
                      }}
                      className={cn(
                        'px-4 py-3 align-middle',
                        isPinned(f.api_name) &&
                          'bg-card group-even/row:bg-[color-mix(in_srgb,var(--raised)_60%,var(--card))] group-hover/row:bg-accent group-focus-visible/row:bg-accent sticky z-10',
                        f.api_name === lastPinned && 'shadow-[inset_-1px_0_0_var(--border)]',
                        // Clip Text: one line, cut with an ellipsis. Wrap is today's look.
                        !wrap && 'max-w-[22rem] truncate whitespace-nowrap',
                        NUMERIC_TYPES.has(f.type) && 'text-right',
                        // The list view's first column is the record's name —
                        // it reads as the link into the record, as it does on
                        // every CRM list screen.
                        i === 0 && 'text-link font-medium',
                        // The RAG stripe rides that same first cell: a <tr>
                        // cannot carry a left border under border-collapse.
                        i === 0 && rowAccent?.(row)
                      )}
                    >
                      {renderCell?.(f, row) ?? <ListCell field={f} row={row} />}
                    </td>
                  ))}
                  {customizable && <td />}
                </tr>
              )
            })}
          </tbody>
        </table>
        </div>
        {fill && footer}
      </div>
      {!fill && footer}

      {customizable && (
        <ChooseFieldsDialog
          open={managing}
          title="Manage Columns"
          fields={available}
          selected={columns.map((f) => f.api_name)}
          locked={view.fields[0] ? [view.fields[0].api_name] : []}
          onClose={() => setManaging(false)}
          onSave={(chosen) => {
            setManaging(false)
            prefs.save({ ...mine, columns: chosen })
          }}
        />
      )}
    </div>
  )
}

/**
 * View Settings, held at the right end of the header row — as Zoho draws it:
 * Manage Columns, Reset Column Size, View Mode (Wrap / Clip Text, a submenu)
 * and back to the default view. Rows per page is the footer's. Every choice
 * is this person's own.
 */
export function ViewSettings({
  wrap,
  hasWidths,
  hasOwn,
  onManage,
  onResetWidths,
  onWrap,
  onReset,
}: {
  wrap: boolean
  /** Leave out, with onResetWidths, on a view whose columns can't be resized. */
  hasWidths?: boolean
  hasOwn: boolean
  onManage: () => void
  onResetWidths?: () => void
  onWrap: (wrap: boolean) => void
  onReset: () => void
}) {
  const [open, setOpen] = useState(false)
  const [modeOpen, setModeOpen] = useState(false)
  const act = (fn: () => void) => () => {
    fn()
    setModeOpen(false)
    setOpen(false)
  }
  return (
    <Popover
      open={open}
      onOpenChange={(next) => {
        setOpen(next)
        if (!next) setModeOpen(false)
      }}
    >
      <PopoverTrigger asChild>
        <Button
          type="button"
          variant="ghost"
          size="icon"
          aria-label="View settings"
          title="View settings"
          className="data-[state=open]:bg-accent"
        >
          <SlidersHorizontalIcon className="size-4" />
        </Button>
      </PopoverTrigger>
      <PopoverContent align="end" className="w-64 p-1.5">
        <MenuItem icon={SettingsIcon} onClick={act(onManage)} onMouseEnter={() => setModeOpen(false)}>
          Manage Columns
        </MenuItem>
        {onResetWidths && (
          <MenuItem icon={Columns3Icon} disabled={!hasWidths} onClick={act(onResetWidths)} onMouseEnter={() => setModeOpen(false)}>
            Reset Column Size
          </MenuItem>
        )}
        <MenuSeparator />
        <Popover open={modeOpen} onOpenChange={setModeOpen}>
          <PopoverTrigger asChild>
            <MenuItem
              icon={EyeIcon}
              active={modeOpen}
              onClick={() => setModeOpen(true)}
              onMouseEnter={() => setModeOpen(true)}
              trailing={
                <span className="flex items-center gap-1 font-semibold">
                  {wrap ? 'Wrap Text' : 'Clip Text'}
                  <ChevronRightIcon className="text-muted-foreground size-4" />
                </span>
              }
            >
              View Mode
            </MenuItem>
          </PopoverTrigger>
          <PopoverContent side="left" align="start" sideOffset={6} className="w-40 p-1.5">
            {[
              { value: true, label: 'Wrap Text' },
              { value: false, label: 'Clip Text' },
            ].map((mode) => (
              <MenuItem
                key={mode.label}
                icon={wrap === mode.value ? CheckIcon : undefined}
                onClick={act(() => onWrap(mode.value))}
              >
                {mode.label}
              </MenuItem>
            ))}
          </PopoverContent>
        </Popover>
        <MenuSeparator />
        <MenuItem icon={RotateCcwIcon} disabled={!hasOwn} onClick={act(onReset)} onMouseEnter={() => setModeOpen(false)}>
          Reset to default view
        </MenuItem>
      </PopoverContent>
    </Popover>
  )
}

/**
 * A column's own menu — the ☰ that shows when the header is hovered, as in
 * Zoho: sort it, pin it at the left, hide it. Pin and Hide are a person's own
 * layout, so a list without one (`pinned`/`canHide` undefined) offers sorting only.
 */
export function ColumnMenu({
  label,
  sorted,
  pinned,
  canHide,
  onSort,
  onPin,
  onHide,
}: {
  label: string
  sorted?: 'asc' | 'desc' | null
  pinned?: boolean
  canHide?: boolean
  /** Leave out on a view with an order of its own (Low Hanging / Top 10's ranks): no Asc / Desc. */
  onSort?: (order: 'asc' | 'desc') => void
  onPin: () => void
  onHide: () => void
}) {
  const [open, setOpen] = useState(false)
  const act = (fn: () => void) => () => {
    fn()
    setOpen(false)
  }
  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <button
          type="button"
          aria-label={`${label}: column menu`}
          className={cn(
            'text-muted-foreground hover:bg-accent hover:text-foreground focus-visible:opacity-100 grid size-6 shrink-0 place-items-center rounded-full opacity-0 transition-opacity group-hover/col:opacity-100',
            open && 'bg-accent text-foreground opacity-100'
          )}
        >
          <MenuIcon className="size-3.5" />
        </button>
      </PopoverTrigger>
      <PopoverContent align="start" className="w-48 p-1.5">
        {onSort && (
          <>
            <MenuItem icon={ArrowUpIcon} active={sorted === 'asc'} onClick={act(() => onSort('asc'))}>
              Asc
            </MenuItem>
            <MenuItem icon={ArrowDownIcon} active={sorted === 'desc'} onClick={act(() => onSort('desc'))}>
              Desc
            </MenuItem>
          </>
        )}
        {pinned !== undefined && (
          <MenuItem icon={pinned ? PinOffIcon : PinIcon} onClick={act(onPin)}>
            {pinned ? 'Unpin Column' : 'Pin Column'}
          </MenuItem>
        )}
        {canHide !== undefined && (
          <MenuItem icon={EyeOffIcon} disabled={!canHide} onClick={act(onHide)}>
            Hide Column
          </MenuItem>
        )}
      </PopoverContent>
    </Popover>
  )
}

/** One row of a list menu: an icon, the words, and anything to their right. */
const MenuItem = forwardRef<
  HTMLButtonElement,
  React.ComponentProps<'button'> & {
    icon?: React.ComponentType<{ className?: string }>
    active?: boolean
    trailing?: ReactNode
  }
>(function MenuItem({ icon: Icon, active, trailing, children, className, ...props }, ref) {
  return (
    <button
      ref={ref}
      type="button"
      className={cn(
        'hover:bg-accent focus-visible:bg-accent flex w-full items-center gap-3 rounded-md px-2.5 py-2 text-left text-sm outline-none disabled:pointer-events-none disabled:opacity-45',
        active && 'bg-accent',
        className
      )}
      {...props}
    >
      <span className="text-muted-foreground grid size-4 shrink-0 place-items-center">
        {Icon && <Icon className="size-4" />}
      </span>
      <span className="flex-1">{children}</span>
      {trailing}
    </button>
  )
})

function MenuSeparator() {
  return <div role="separator" className="border-border my-1.5 border-t" />
}
