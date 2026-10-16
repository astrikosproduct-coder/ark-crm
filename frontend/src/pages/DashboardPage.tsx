import { useEffect, useRef, useState, type ReactNode } from 'react'
import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { isAxiosError } from 'axios'
import { InfoIcon } from 'lucide-react'

import { EmptyChart } from '@/components/dashboard/ChartCard'
import { AccountsTab, PartnersTab, PerformanceTab, PipelineTab, WinLossTab } from '@/components/dashboard/DashboardTabs'
import { monthLabel, seriesLabel } from '@/components/dashboard/format'
import { KpiTile, type Delta } from '@/components/dashboard/KpiTile'
import { RecordsSheet } from '@/components/dashboard/RecordsSheet'
import { DashboardProvider } from '@/components/dashboard/Tile'
import type { DashboardData, DashboardFilters, DrillRequest, PeriodPreset, SliceFilter } from '@/components/dashboard/types'
import { PageLayout } from '@/components/layout/PageLayout'
import { Input } from '@/components/ui/input'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { api } from '@/lib/api'
import { date, money } from '@/lib/format'
import { usd } from '@/lib/revenue'
import { fieldOf, optionsFor } from '@/lib/spec'
import { allowedChoices } from '@/lib/spec/dependencies'
import { useServerDay } from '@/lib/serverClock'
import { cn } from '@/lib/utils'

const ALL = '__all__'
const CUSTOM = '__custom__'

/** The page opens on this fiscal year (decided 28 Sep 2026), so Booked and Won agree on sight. */
const DEFAULT_FILTERS: DashboardFilters = { period: 'current_fy' }

function plural(n: number, word: string): string {
  return `${n} ${word}${n === 1 ? '' : 's'}`
}

/** A Lead field's picklist, so every filter offers exactly what the Lead form offers. */
function leadOptions(apiName: string) {
  return optionsFor(fieldOf('leads', apiName)?.picklist).map((o) => ({ value: o.key, label: o.label }))
}

/**
 * A Lead field's choices as the Lead form would offer them for these parent
 * values: Segment Category under the Segment chosen, Subsegment under the
 * Category. Everything when nothing above it is chosen.
 */
function dependentLeadOptions(apiName: string, values: Record<string, unknown>) {
  const allowed = allowedChoices('leads', apiName, values)
  const all = leadOptions(apiName)
  return allowed === null || allowed.length === 0 ? all : all.filter((o) => allowed.includes(o.value))
}

/** "01 Jan 2027 – 30 Apr 2027", or the one end that is set. */
function rangeText(from: string | null | undefined, to: string | null | undefined): string {
  if (from && to) return `${date(from)} – ${date(to)}`
  if (from) return `from ${date(from)}`
  if (to) return `up to ${date(to)}`
  return 'all dates'
}

function errorMessage(error: unknown): string {
  if (isAxiosError(error)) {
    const detail = error.response?.data?.detail
    if (detail && typeof detail === 'object' && typeof detail.message === 'string') return detail.message
  }
  return 'The dashboard could not be loaded.'
}

const presetKey = (p: Pick<PeriodPreset, 'start' | 'end'>) => `${p.start}|${p.end}`

/** Every slice filter the page offers — each reaches every tile on every tab. */
const SLICES: { key: SliceFilter; label: string; name: string; options: (data?: DashboardData) => { value: string; label: string }[] }[] = [
  { key: 'region', name: 'Booking Region', label: 'All booking regions', options: () => leadOptions('booking_region') },
  // Segment is the Lead's `theme` field since Release 1.1; the old Segment and a separate Theme filter are gone.
  { key: 'segment', name: 'Segment', label: 'All segments', options: () => leadOptions('theme') },
  // Release 1.2: the Lead's Segment Category and Subsegment. The row narrows each
  // to the choice above it (categoryOptions / subsegmentOptions in the page).
  { key: 'segment_category', name: 'Segment Category', label: 'All segment categories', options: () => leadOptions('segment_category') },
  { key: 'subsegment', name: 'Subsegment', label: 'All subsegments', options: () => leadOptions('subsegment') },
  { key: 'owner', name: 'BD Owner', label: 'All BD owners', options: (d) => (d?.owners ?? []).map((o) => ({ value: o.id, label: o.name })) },
  { key: 'opportunity_type', name: 'Opportunity Type', label: 'All opportunity types', options: () => leadOptions('opportunity_type') },
  { key: 'partner', name: 'Partner', label: 'All partners', options: (d) => (d?.partners ?? []).map((p) => ({ value: p.id, label: p.name })) },
  { key: 'deal_source', name: 'Deal Source', label: 'All deal sources', options: () => leadOptions('deal_source') },
]

/**
 * The management dashboard — five tabs, one filter row.
 *
 * Every number comes from GET /api/dashboard (backend/app/routers/dashboard.py),
 * computed with the same revenue rule as the Kanban boards. The filter row is
 * the same on every tab and its state lives here, so switching tabs keeps it;
 * every filter reaches every tile. What each tile draws is a config object
 * (components/dashboard/config.ts); clicking a mark opens the records behind
 * it (RecordsSheet).
 */
export function DashboardPage() {
  const [filters, setFilters] = useState<DashboardFilters>(DEFAULT_FILTERS)
  // What the date inputs show. Copied into `filters` only while it is a valid
  // range, so an inverted range never reaches the server or blanks the page.
  const [draft, setDraft] = useState({ from: '', to: '' })
  // From / To are shown only once Custom range is chosen from the Period filter.
  const [custom, setCustom] = useState(false)
  const [drill, setDrill] = useState<DrillRequest | null>(null)
  const inverted = Boolean(draft.from && draft.to && draft.from > draft.to)

  const { data, error, isLoading, isError, isFetching, isPlaceholderData, refetch } = useQuery({
    queryKey: ['dashboard', filters],
    queryFn: async () => (await api.get<DashboardData>('/dashboard', { params: filters })).data,
    // A filter change keeps the previous render, dimmed, instead of flashing empty.
    placeholderData: keepPreviousData,
  })

  // When the SERVER's day turns, refetch — so "this fiscal year", "this quarter"
  // and every meter's ended / open basis move on by themselves in a tab left
  // open overnight. Only a change counts: learning the day on load does not.
  const serverDay = useServerDay()
  const seenDay = useRef<string | null>(null)
  useEffect(() => {
    if (!serverDay) return
    if (seenDay.current && seenDay.current !== serverDay) void refetch()
    seenDay.current = serverDay
  }, [serverDay, refetch])

  const setFilter = (key: SliceFilter) => (value: string) => setFilters((f) => ({ ...f, [key]: value === ALL ? undefined : value }))

  // Segment -> Segment Category -> Subsegment narrow one another, as on the
  // Lead form; a new Segment drops a Category (and Subsegment) outside it.
  const categoryOptions = dependentLeadOptions('segment_category', { theme: filters.segment })
  const subsegmentOptions = filters.segment_category
    ? dependentLeadOptions('subsegment', { segment_category: filters.segment_category })
    : dependentLeadOptions('subsegment', { segment_category: categoryOptions.map((o) => o.value) })
  const setSegment = (value: string) =>
    setFilters((f) => {
      const segment = value === ALL ? undefined : value
      const categories = dependentLeadOptions('segment_category', { theme: segment }).map((o) => o.value)
      const category = f.segment_category && categories.includes(f.segment_category) ? f.segment_category : undefined
      const subsegments = dependentLeadOptions('subsegment', { segment_category: category ?? categories }).map((o) => o.value)
      const subsegment = f.subsegment && subsegments.includes(f.subsegment) ? f.subsegment : undefined
      return { ...f, segment, segment_category: category, subsegment }
    })
  const setCategory = (value: string) =>
    setFilters((f) => {
      const category = value === ALL ? undefined : value
      const subsegments = category ? dependentLeadOptions('subsegment', { segment_category: category }).map((o) => o.value) : null
      const subsegment = f.subsegment && (!subsegments || subsegments.includes(f.subsegment)) ? f.subsegment : undefined
      return { ...f, segment_category: category, subsegment }
    })

  const setRange = (from: string, to: string) => {
    setDraft({ from, to })
    if (from && to && from > to) return
    setFilters((f) => ({ ...f, period: undefined, date_from: from || undefined, date_to: to || undefined }))
  }

  const presets = data?.periods ?? []
  const currentFy = presets.find((p) => p.kind === 'fiscal_year' && p.current)
  const matched = presets.find((p) => p.start === filters.date_from && p.end === filters.date_to)
  const period = custom
    ? CUSTOM
    : filters.period === 'current_fy'
      ? currentFy
        ? presetKey(currentFy)
        : 'current_fy'
      : !filters.date_from && !filters.date_to
        ? ALL
        : matched
          ? presetKey(matched)
          : CUSTOM
  const onPeriod = (value: string) => {
    setCustom(value === CUSTOM)
    if (value === CUSTOM) {
      // Custom starts from whatever period was showing.
      setDraft({ from: data?.range.from ?? '', to: data?.range.to ?? '' })
      return
    }
    if (value === ALL) return setRange('', '')
    const p = presets.find((q) => presetKey(q) === value)
    if (p) setRange(p.start, p.end)
  }

  const clearAll = () => {
    setCustom(false)
    setDraft({ from: '', to: '' })
    setFilters(DEFAULT_FILTERS)
  }

  const sliced = SLICES.some((s) => filters[s.key])
  const moved = sliced || filters.period !== DEFAULT_FILTERS.period || custom
  const ranged = Boolean(data && (data.range.from || data.range.to))

  // The filters in words, from what the SERVER computed with — every ⓘ lists them.
  const filterLines = data
    ? [
        ...(ranged ? [`Period ${rangeText(data.range.from, data.range.to)}`] : []),
        ...SLICES.filter((s) => data.filters[s.key]).map((s) => {
          const value = data.filters[s.key]!
          return `${s.name}: ${s.options(data).find((o) => o.value === value)?.label ?? value}`
        }),
      ]
    : []

  const filterRow = (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center gap-2">
        <Select value={period} onValueChange={onPeriod}>
          <SelectTrigger className="w-64" aria-label="Period">
            <SelectValue placeholder="This fiscal year" />
          </SelectTrigger>
          <SelectContent>
            {!currentFy && <SelectItem value="current_fy">This fiscal year</SelectItem>}
            {presets.map((p) => (
              <SelectItem key={presetKey(p)} value={presetKey(p)}>
                {p.label} ({monthLabel(p.start, 'MMM yy')}–{monthLabel(p.end, 'MMM yy')})
                {p.current ? (p.kind === 'fiscal_year' ? ' · this year' : ' · this quarter') : ''}
              </SelectItem>
            ))}
            <SelectItem value={ALL}>All dates</SelectItem>
            <SelectItem value={CUSTOM}>Custom range</SelectItem>
          </SelectContent>
        </Select>
        {period === CUSTOM && (
          <>
            <label className="text-muted-foreground text-label flex items-center gap-1.5">
              From
              <Input
                type="date"
                className="w-40"
                value={draft.from}
                max={draft.to || undefined}
                aria-invalid={inverted || undefined}
                onChange={(e) => setRange(e.target.value, draft.to)}
              />
            </label>
            <label className="text-muted-foreground text-label flex items-center gap-1.5">
              To
              <Input
                type="date"
                className="w-40"
                value={draft.to}
                min={draft.from || undefined}
                aria-invalid={inverted || undefined}
                onChange={(e) => setRange(draft.from, e.target.value)}
              />
            </label>
          </>
        )}
        {data && <ScopeNote data={data} />}
      </div>
      <div className="flex flex-wrap items-center gap-2">
        {SLICES.map((s) => (
          <FilterSelect
            key={s.key}
            label={s.label}
            value={filters[s.key]}
            onChange={s.key === 'segment' ? setSegment : s.key === 'segment_category' ? setCategory : setFilter(s.key)}
            options={
              s.key === 'segment_category' ? categoryOptions : s.key === 'subsegment' ? subsegmentOptions : s.options(data)
            }
          />
        ))}
        {moved && (
          <button type="button" onClick={clearAll} className="text-link text-label px-2 hover:underline">
            Clear filters
          </button>
        )}
      </div>
      {inverted && <p className="text-destructive text-meta">The From date must be on or before the To date.</p>}
    </div>
  )

  /** A tab: the shared filter row, then the tab's own tiles — or why there are none. */
  const tab = (content: (data: DashboardData) => ReactNode) => (
    <div className="space-y-4 pt-3">
      {filterRow}
      {isLoading && <EmptyChart>Loading the dashboard…</EmptyChart>}
      {isError && (
        <EmptyChart>
          {errorMessage(error)}{' '}
          <button type="button" onClick={() => refetch()} className="text-link hover:underline">
            Try again
          </button>
        </EmptyChart>
      )}
      {data && !isError && (
        <DashboardProvider value={{ data, filterLines, drill: setDrill }}>
          <div className={cn('space-y-4 transition-opacity', isFetching && isPlaceholderData && 'opacity-60')}>{content(data)}</div>
        </DashboardProvider>
      )}
    </div>
  )

  return (
    <>
      <PageLayout
        wide
        titleInTopBar
        title="Dashboard"
        tabs={[
          {
            key: 'performance',
            label: 'Performance',
            content: tab((d) => (
              <>
                <Kpis data={d} ranged={ranged} />
                <PerformanceTab />
              </>
            )),
          },
          { key: 'pipeline', label: 'Pipeline', content: tab(() => <PipelineTab />) },
          { key: 'partners', label: 'Partners', content: tab(() => <PartnersTab />) },
          { key: 'accounts', label: 'Accounts', content: tab(() => <AccountsTab />) },
          { key: 'win-loss', label: 'Win & loss', content: tab(() => <WinLossTab />) },
        ]}
      />
      <RecordsSheet request={drill} filters={filters} onClose={() => setDrill(null)} />
    </>
  )
}

/**
 * What the date range does to the page — behind an ⓘ on the range control.
 * The range means a DIFFERENT DATE per tile, which is the one thing about this
 * page a reader genuinely has to be told.
 */
function ScopeNote({ data }: { data: DashboardData }) {
  const { from, to, left_out } = data.range
  return (
    <Popover>
      <PopoverTrigger
        type="button"
        aria-label="What this period covers"
        className="text-muted-foreground hover:text-foreground flex items-center gap-1 px-1 text-xs"
      >
        <InfoIcon className="size-3.5" />
        {from || to ? rangeText(from, to) : 'All dates'}
      </PopoverTrigger>
      <PopoverContent align="start" className="text-meta w-80 leading-relaxed">
        {!from && !to ? (
          <p>Every record, whenever it is expected to close. Performance shows this fiscal year.</p>
        ) : (
          <>
            <p>Period {rangeText(from, to)}, read as a different date per tile:</p>
            <ul className="mt-1.5 list-disc space-y-0.5 pl-4">
              <li>Pipeline, revenue and every Pipeline, Partners and Accounts tile — by Expected Close Month.</li>
              <li>Won and the Booked line — by PO Received Date.</li>
              <li>Closed Lost and Why we lose — by the date it was lost.</li>
              <li>Performance — the fiscal year holding the period’s start, {data.performance.fiscal_year}.</li>
            </ul>
            {left_out > 0 && (
              <p className="mt-1.5">
                {plural(left_out, 'record')} with no Expected Close Month {left_out === 1 ? 'is' : 'are'} left out. The Pipeline tab shows them
                under “No month”.
              </p>
            )}
          </>
        )}
      </PopoverContent>
    </Popover>
  )
}

function FilterSelect({
  label,
  value,
  onChange,
  options,
}: {
  label: string
  value: string | undefined
  onChange: (value: string) => void
  options: { value: string; label: string }[]
}) {
  return (
    <Select value={value ?? ALL} onValueChange={onChange}>
      <SelectTrigger className="w-48" aria-label={label}>
        <SelectValue placeholder={label} />
      </SelectTrigger>
      <SelectContent>
        <SelectItem value={ALL}>{label}</SelectItem>
        {options.map((o) => (
          <SelectItem key={o.value} value={o.value}>
            {o.label}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  )
}

/** " expected to close in the selected period", when there is one. */
function closing(ranged: boolean): string {
  return ranged ? ', expected to close in the selected period' : ''
}

/**
 * The headline row — the first row of the Performance tab. Kept exactly as it
 * was on the Overview tab: same labels, same figures, same captions, same
 * order (28 Sep 2026). Only where it sits changed.
 *
 * Won is counted by PO Received Date, never Booking Date. DELTAS ONLY WHEN
 * THERE IS SOMETHING TO COMPARE: `data.comparison` is null unless the period
 * has two ends.
 */
function Kpis({ data, ranged }: { data: DashboardData; ranged: boolean }) {
  const { pipeline, actual, won, lost } = data.kpis
  const labels = data.revenue_labels
  const before = data.comparison?.kpis
  const against = data.comparison?.label ?? null
  const delta = (now: number, was: number | undefined, upIsGood = true): Delta | null =>
    was === undefined ? null : { now, before: was, label: against, upIsGood }

  const leadShare = pipeline.usd > 0 ? (pipeline.by_module.leads.usd / pipeline.usd) * 100 : 0

  return (
    <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
      <KpiTile
        label="Open pipeline"
        value={usd(pipeline.usd)}
        delta={delta(pipeline.usd, before?.pipeline.usd)}
        line={`${plural(pipeline.count, 'pursuit')}${closing(ranged)}`}
        caveat={pipeline.unpriced > 0 ? `${plural(pipeline.unpriced, 'pursuit')} still needs a value, currency or exchange rate` : null}
      >
        {pipeline.usd > 0 && (
          <div
            className="bg-muted mt-2 flex h-1.5 overflow-hidden rounded-full"
            title={`${seriesLabel(labels, 'leads')} ${usd(pipeline.by_module.leads.usd)} · ${seriesLabel(labels, 'opportunities')} ${usd(pipeline.by_module.opportunities.usd)}`}
          >
            <span className="bg-primary/50" style={{ width: `${leadShare}%` }} />
            <span className="bg-primary flex-1" />
          </div>
        )}
      </KpiTile>
      <KpiTile
        label="Weighted pipeline"
        value={usd(pipeline.weighted_usd)}
        delta={delta(pipeline.weighted_usd, before?.pipeline.weighted_usd)}
        line="Value × Probability %"
      />
      <KpiTile
        label={`${labels.deals} (Deals)`}
        value={usd(actual.usd)}
        delta={delta(actual.usd, before?.actual.usd)}
        line={`${plural(actual.count, 'deal')} · contract value${closing(ranged)}`}
        caveat={actual.unpriced > 0 ? `${plural(actual.unpriced, 'deal')} still needs a value, currency or exchange rate` : null}
      />
      <KpiTile
        label="Won"
        value={usd(won.usd)}
        delta={delta(won.usd, before?.won.usd)}
        line={`${plural(won.count, 'deal')} · PO received${ranged ? ' in the selected period' : ''}`}
        caveat={won.unpriced > 0 ? `${plural(won.unpriced, 'deal')} still needs a value, currency or exchange rate` : null}
      />
      <KpiTile
        label="Closed Lost"
        value={money(lost.count)}
        delta={delta(lost.count, before?.lost.count, false)}
        line={`${usd(lost.usd)} of pursuit value`}
      />
    </div>
  )
}
