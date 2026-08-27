import { useEffect, useMemo, useState, type ReactNode } from 'react'
import { useNavigate } from 'react-router-dom'
import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { ArrowDownIcon, ArrowUpIcon, ChevronsUpDownIcon, SearchIcon } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { ListCell, NUMERIC_TYPES, type ListRow } from '@/components/list/ListCell'
import { api } from '@/lib/api'
import { idOf, listViewFor } from '@/lib/spec'
import { cn } from '@/lib/utils'
import type { FieldSpec } from '@/types/field'

const PAGE_SIZES = [10, 25, 50]

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
  emptyMessage?: string
  pageSize?: number
}

/**
 * The list screen for any module that declares a list_views entry in
 * spec/extensions.json. Which columns appear, what the text filter searches and
 * what the default sort is are all spec, never props and never literals here —
 * CLAUDE.md rule 3.
 *
 * Paging, sorting and searching are all done by the server. This component
 * holds the query parameters and renders what comes back, which is exactly what
 * it will do once MSW is replaced.
 */
export function RecordListView({
  module,
  collection,
  basePath,
  filter,
  hiddenColumns,
  renderCell,
  emptyMessage,
  pageSize = 25,
}: RecordListViewProps) {
  const navigate = useNavigate()
  const view = listViewFor(module)

  const [search, setSearch] = useState('')
  const [q, setQ] = useState('')
  const [page, setPage] = useState(1)
  const [limit, setLimit] = useState(pageSize)
  const [sort, setSort] = useState(() => view?.default_sort ?? '')
  const [order, setOrder] = useState<'asc' | 'desc'>('asc')

  // Debounced so a five-letter search is one request, not five.
  useEffect(() => {
    const t = setTimeout(() => {
      setQ(search)
      setPage(1)
    }, 250)
    return () => clearTimeout(t)
  }, [search])

  const columns = useMemo(
    () => (view?.fields ?? []).filter((f) => !hiddenColumns?.includes(f.api_name)),
    [view, hiddenColumns]
  )

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
  const total = data?.total ?? 0
  const lastPage = Math.max(1, Math.ceil(total / limit))
  const first = total === 0 ? 0 : (page - 1) * limit + 1
  const last = Math.min(page * limit, total)

  const toggleSort = (field: FieldSpec) => {
    if (sort === field.api_name) {
      setOrder(order === 'asc' ? 'desc' : 'asc')
    } else {
      setSort(field.api_name)
      setOrder('asc')
    }
    setPage(1)
  }

  return (
    <div className="space-y-3 py-3">
      <div className="relative max-w-sm">
        <SearchIcon className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground" />
        <Input
          className="pl-9"
          placeholder={`Filter ${view.search.length ? view.search.join(', ') : 'anything'}…`}
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
      </div>

      <div className="overflow-x-auto rounded-lg border">
        <table className="w-full text-sm">
          <thead className="bg-muted/50">
            <tr>
              {columns.map((f) => (
                <th key={f.qref} className="p-0 text-left font-medium whitespace-nowrap">
                  <button
                    type="button"
                    onClick={() => toggleSort(f)}
                    className={cn(
                      'flex w-full items-center gap-1 px-3 py-2 hover:text-foreground',
                      NUMERIC_TYPES.has(f.type) && 'justify-end',
                      sort === f.api_name ? 'text-foreground' : 'text-muted-foreground'
                    )}
                  >
                    {f.label}
                    {sort !== f.api_name ? (
                      <ChevronsUpDownIcon className="size-3 opacity-40" />
                    ) : order === 'asc' ? (
                      <ArrowUpIcon className="size-3" />
                    ) : (
                      <ArrowDownIcon className="size-3" />
                    )}
                  </button>
                </th>
              ))}
            </tr>
          </thead>

          <tbody className={cn(isPlaceholderData && 'opacity-60')}>
            {isLoading && (
              <tr>
                <td colSpan={columns.length} className="px-3 py-6 text-center text-muted-foreground">
                  Loading…
                </td>
              </tr>
            )}

            {isError && (
              <tr>
                <td colSpan={columns.length} className="px-3 py-6 text-center text-destructive">
                  Could not load {collection}
                </td>
              </tr>
            )}

            {!isLoading && !isError && rows.length === 0 && (
              <tr>
                <td colSpan={columns.length} className="px-3 py-6 text-center text-muted-foreground">
                  {q ? `Nothing matches “${q}”` : (emptyMessage ?? 'No records yet')}
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
                  className="cursor-pointer border-t outline-none hover:bg-muted/40 focus-visible:bg-muted/40"
                >
                  {columns.map((f) => (
                    <td
                      key={f.qref}
                      className={cn(
                        'px-3 py-2 align-middle',
                        NUMERIC_TYPES.has(f.type) && 'text-right'
                      )}
                    >
                      {renderCell?.(f, row) ?? <ListCell field={f} row={row} />}
                    </td>
                  ))}
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>

      <div className="flex flex-wrap items-center justify-between gap-3 text-sm text-muted-foreground">
        <span>
          {first}–{last} of {total}
        </span>

        <div className="flex items-center gap-2">
          <Select
            value={String(limit)}
            onValueChange={(v) => {
              setLimit(Number(v))
              setPage(1)
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

          <Button
            type="button"
            variant="outline"
            size="sm"
            disabled={page <= 1}
            onClick={() => setPage((p) => Math.max(1, p - 1))}
          >
            Previous
          </Button>
          <span className="tabular-nums">
            {page} / {lastPage}
          </span>
          <Button
            type="button"
            variant="outline"
            size="sm"
            disabled={page >= lastPage}
            onClick={() => setPage((p) => p + 1)}
          >
            Next
          </Button>
        </div>
      </div>
    </div>
  )
}
