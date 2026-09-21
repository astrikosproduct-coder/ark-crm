import { useState } from 'react'
import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { isAxiosError } from 'axios'

import { AtRiskList, DueList } from '@/components/dashboard/ActionLists'
import { BarRows, type BarRow, type BarTone } from '@/components/dashboard/BarRows'
import { ChartCard, EmptyChart } from '@/components/dashboard/ChartCard'
import { CloseForecast } from '@/components/dashboard/CloseForecast'
import { monthLabel, seriesLabel } from '@/components/dashboard/format'
import { KpiTile, type Delta } from '@/components/dashboard/KpiTile'
import type { DashboardData, DashboardFilters } from '@/components/dashboard/types'
import { PageLayout } from '@/components/layout/PageLayout'
import { Input } from '@/components/ui/input'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { api } from '@/lib/api'
import { InfoIcon } from 'lucide-react'

import { date, money } from '@/lib/format'
import { moduleFor } from '@/lib/modules'
import { usd } from '@/lib/revenue'
import { fieldOf, optionsFor } from '@/lib/spec'
import { cn } from '@/lib/utils'

const ALL = '__all__'
const CUSTOM = '__custom__'

/** The RAG picklist keys as the app's status tones — the same mapping lib/rag.ts draws as a stripe. */
const RAG_TONE: Record<string, BarTone> = { GREEN: 'success', AMBER: 'warning', RED: 'destructive' }

function plural(n: number, word: string): string {
  return `${n} ${word}${n === 1 ? '' : 's'}`
}

/** A Lead field's picklist, so every filter offers exactly what the Lead form offers. */
function leadOptions(apiName: string) {
  return optionsFor(fieldOf('leads', apiName)?.picklist).map((o) => ({ value: o.key, label: o.label }))
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

/**
 * The management dashboard — Phase 1 skeleton, for the CEO and management.
 *
 * Every number comes from GET /api/dashboard (backend/app/routers/dashboard.py),
 * computed with the same revenue rule as the Kanban boards, so a total here
 * reconciles with the board it summarises. Only the live PostgreSQL modules are
 * read; Gates, Quotes and POCs stay off until they migrate.
 *
 * The date range filters each widget by the date it is about — Expected Close
 * Month, date lost, or due date — and the scope line under the filters says so.
 */
export function DashboardPage() {
  const [filters, setFilters] = useState<DashboardFilters>({})
  // What the date inputs show. Copied into `filters` only while it is a valid
  // range, so an inverted range never reaches the server or blanks the page.
  const [draft, setDraft] = useState({ from: '', to: '' })
  // From / To are shown only once Custom range is chosen from the Period filter.
  const [custom, setCustom] = useState(false)
  const inverted = Boolean(draft.from && draft.to && draft.from > draft.to)

  const { data, error, isLoading, isError, isFetching, isPlaceholderData, refetch } = useQuery({
    queryKey: ['dashboard', filters],
    queryFn: async () => (await api.get<DashboardData>('/dashboard', { params: filters })).data,
    // A filter change keeps the previous render, dimmed, instead of flashing empty.
    placeholderData: keepPreviousData,
  })

  const setFilter = (key: keyof DashboardFilters) => (value: string) =>
    setFilters((f) => ({ ...f, [key]: value === ALL ? undefined : value }))

  const setRange = (from: string, to: string) => {
    setDraft({ from, to })
    if (from && to && from > to) return
    setFilters((f) => ({ ...f, date_from: from || undefined, date_to: to || undefined }))
  }

  const presets = data?.quarters ?? []
  const preset = presets.find((q) => q.start === draft.from && q.end === draft.to)
  const period = custom ? CUSTOM : !draft.from && !draft.to ? ALL : preset ? preset.start : CUSTOM
  const onPeriod = (value: string) => {
    // Custom keeps whatever dates are set (a quarter just picked, say) as a starting point.
    setCustom(value === CUSTOM)
    if (value === CUSTOM) return
    if (value === ALL) return setRange('', '')
    const q = presets.find((p) => p.start === value)
    if (q) setRange(q.start, q.end)
  }

  const clearAll = () => {
    setCustom(false)
    setDraft({ from: '', to: '' })
    setFilters({})
  }

  const filtered = Object.values(filters).some(Boolean) || Boolean(draft.from || draft.to)
  const ranged = Boolean(data && (data.range.from || data.range.to))

  return (
    <PageLayout
      wide
      title="Dashboard"
      subtitle={data ? `As of ${date(data.as_of)}` : undefined}
      tabs={[
        {
          key: 'overview',
          label: 'Overview',
          content: (
            <div className="space-y-4 pt-3">
              <div className="space-y-2">
                <div className="flex flex-wrap items-center gap-2">
                  <Select value={period} onValueChange={onPeriod}>
                    <SelectTrigger className="w-56" aria-label="Period">
                      <SelectValue placeholder="All dates" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value={ALL}>All dates</SelectItem>
                      {presets.map((q) => (
                        <SelectItem key={q.start} value={q.start}>
                          {q.label} ({monthLabel(q.start, 'MMM')}–{monthLabel(q.end, 'MMM')}){q.current ? ' · this quarter' : ''}
                        </SelectItem>
                      ))}
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
                </div>
                <div className="flex flex-wrap items-center gap-2">
                  <FilterSelect label="All regions" value={filters.region} onChange={setFilter('region')} options={leadOptions('destination_region')} />
                  <FilterSelect label="All segments" value={filters.segment} onChange={setFilter('segment')} options={leadOptions('segment')} />
                  <FilterSelect
                    label="All BD owners"
                    value={filters.owner}
                    onChange={setFilter('owner')}
                    options={(data?.owners ?? []).map((o) => ({ value: o.id, label: o.name }))}
                  />
                  <FilterSelect
                    label="All opportunity types"
                    value={filters.opportunity_type}
                    onChange={setFilter('opportunity_type')}
                    options={leadOptions('opportunity_type')}
                  />
                  {filtered && (
                    <button type="button" onClick={clearAll} className="text-link text-label px-2 hover:underline">
                      Clear filters
                    </button>
                  )}
                  {/* The scope paragraph used to sit under these controls and
                      run to forty words, on the screen where the fold matters
                      most. It is unchanged and one click away — it is about the
                      range control, so it lives on it. */}
                  {data && <ScopeNote data={data} />}
                </div>
                {inverted && <p className="text-destructive text-meta">The From date must be on or before the To date.</p>}
              </div>

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
                <div className={cn('space-y-4 transition-opacity', isFetching && isPlaceholderData && 'opacity-60')}>
                  <Kpis data={data} ranged={ranged} />
                  {/* Forecast full width: it is the one chart read left to
                      right over time, and at half a screen its months were
                      three characters wide. Everything else pairs up — the old
                      three-across row squeezed RAG, ageing and loss reasons
                      into a third each, which is where this page stopped being
                      readable. */}
                  <Forecast data={data} ranged={ranged} />
                  <div className="grid gap-4 lg:grid-cols-2">
                    <StageFunnel data={data} ranged={ranged} />
                    <LossReasons data={data} ranged={ranged} />
                  </div>
                  <div className="grid gap-4 lg:grid-cols-2">
                    <RagBreakdown data={data} ranged={ranged} />
                    <StageAgeing data={data} ranged={ranged} />
                  </div>
                  <div className="grid gap-4 xl:grid-cols-2">
                    <DueList
                      due={data.due}
                      windowDays={data.thresholds.due_window_days}
                      range={ranged ? rangeText(data.range.from, data.range.to) : null}
                    />
                    <AtRiskList atRisk={data.at_risk} stuckAfterDays={data.thresholds.stuck_after_days} />
                  </div>
                </div>
              )}
            </div>
          ),
        },
      ]}
    />
  )
}

/**
 * What the date range does to the page — behind an ⓘ on the range control.
 *
 * The range means a DIFFERENT DATE per widget, which is the one thing about
 * this page a reader genuinely has to be told and the last thing they want
 * told every time they look at it. It sat under the filters as a forty-word
 * paragraph; the words are unchanged, the position is not.
 *
 * The dead calendar-quarter branch is gone: FISCAL_YEAR_START_MONTH is 4, so
 * "until the fiscal year is confirmed" could never render.
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
          <p>Every record, whenever it is expected to close.</p>
        ) : (
          <>
            <p>Period {rangeText(from, to)}, read as a different date per widget:</p>
            <ul className="mt-1.5 list-disc space-y-0.5 pl-4">
              <li>Revenue, stage, RAG, ageing and stale — by Expected Close Month.</li>
              <li>Closed Lost — by the date it was lost.</li>
              <li>The due list — by due date.</li>
            </ul>
            {left_out > 0 && (
              <p className="mt-1.5">
                {plural(left_out, 'record')} with no Expected Close Month {left_out === 1 ? 'is' : 'are'} left out.
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
 * Why a widget is empty — which is three different facts wearing one sentence.
 *
 * "No live pursuits yet" about a company with a full pipeline and a Region
 * filter on is not a small imprecision: it is the screen telling a CXO the
 * business has no work. Emptiness that a FILTER caused has to say so, because
 * the filter is the thing they can undo. The same distinction the History tab
 * now makes, for the same reason.
 *
 * Filters are read off what the SERVER echoed back, not off local state, so
 * the sentence can never describe a filter the numbers were not computed with.
 */
function nothingHere(data: DashboardData, thing: string): string {
  const filtered = Object.values(data.filters).some(Boolean)
  const ranged = Boolean(data.range.from || data.range.to)
  if (filtered) return `No ${thing} match these filters.`
  if (ranged) return `No ${thing} in this period.`
  return `No ${thing} yet.`
}

/**
 * The headline row.
 *
 * FIVE TILES, NOT SIX, AND ONE LINE EACH (18 Sep 2026)
 * ----------------------------------------------------
 * Six tiles on a three-column grid wrapped to two rows and read as a table of
 * contents. "Stale records" left the row entirely — it is a WORKLIST, not a
 * headline: nobody reports it to a board, and someone has to go and act on it,
 * which is what the At Risk panel at the foot of the page is for.
 *
 * Won stays, and stays blank, at the user's instruction (18 Sep 2026): the
 * field that proves a win has not been chosen yet, and the empty tile is the
 * reminder. It is deliberately NOT filled with Booking Date — see the note in
 * backend/app/routers/dashboard.py.
 *
 * DELTAS ONLY WHEN THERE IS SOMETHING TO COMPARE. `data.comparison` is null
 * unless the chosen period has two ends, so on "All dates" no tile claims a
 * movement. That is the point: a delta against nothing would be invention on
 * the screen that can least afford it.
 */
function Kpis({ data, ranged }: { data: DashboardData; ranged: boolean }) {
  const { pipeline, actual, lost } = data.kpis
  const labels = data.revenue_labels
  const before = data.comparison?.kpis
  const against = data.comparison?.label ?? null
  const delta = (now: number, was: number | undefined, upIsGood = true): Delta | null =>
    was === undefined ? null : { now, before: was, label: against, upIsGood }

  const leadShare = pipeline.usd > 0 ? (pipeline.by_module.leads.usd / pipeline.usd) * 100 : 0

  return (
    <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
      <KpiTile
        label="Open pipeline"
        value={usd(pipeline.usd)}
        delta={delta(pipeline.usd, before?.pipeline.usd)}
        line={`${plural(pipeline.count, 'pursuit')}${closing(ranged)}`}
        caveat={pipeline.unpriced > 0 ? `${plural(pipeline.unpriced, 'pursuit')} still needs a value, currency or exchange rate` : null}
      >
        {/* The Leads / Opportunities split, as one bar rather than two more
            lines of text. Hover names both figures; the shape alone answers
            "how much of this is still early". */}
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
        label="Closed Lost"
        value={money(lost.count)}
        delta={delta(lost.count, before?.lost.count, false)}
        line={`${usd(lost.usd)} of pursuit value`}
      />
      {/* Deliberately empty, and deliberately still here. */}
      <KpiTile label="Won" value="—" line="No field records the day the PO is received yet" />
    </div>
  )
}

function StageFunnel({ data, ranged }: { data: DashboardData; ranged: boolean }) {
  let previous: string | null = null
  const rows: BarRow[] = data.funnel.map((s) => {
    const group = s.module !== previous ? (moduleFor(s.module ?? '')?.label ?? s.module ?? undefined) : undefined
    previous = s.module
    const label = `${s.stage} ${s.name}`
    return {
      key: String(s.stage),
      label,
      value: s.usd,
      display: usd(s.usd),
      note: String(s.count),
      group,
      tooltip: [label, `${usd(s.usd)} · ${plural(s.count, 'record')}`, `Weighted ${usd(s.weighted_usd)}`],
    }
  })

  return (
    <ChartCard
      title="Pipeline by stage"
      info={`Live primary pursuits by the stage they are in now, in USD${closing(ranged)}. The number after the value is the record count.`}
      table={{
        columns: ['Stage', 'Module', 'Records', 'USD', 'Weighted'],
        rows: data.funnel.map((s) => [`${s.stage} ${s.name}`, moduleFor(s.module ?? '')?.label ?? '', String(s.count), usd(s.usd), usd(s.weighted_usd)]),
      }}
    >
      {data.funnel.some((s) => s.count > 0) ? <BarRows rows={rows} /> : <EmptyChart>{nothingHere(data, 'live pursuits')}</EmptyChart>}
    </ChartCard>
  )
}

function Forecast({ data, ranged }: { data: DashboardData; ranged: boolean }) {
  const { forecast, revenue_labels: labels } = data
  const extra = [
    forecast.overdue && ['Close month passed', forecast.overdue],
    forecast.later && ['Later', forecast.later],
    forecast.undated && ['No close month', forecast.undated],
  ].filter((x): x is [string, NonNullable<typeof forecast.overdue>] => Boolean(x))

  return (
    <ChartCard
      title="Expected revenue by close month"
      info={
        ranged
          ? `Open Leads and Opportunities and counted Deals, by Expected Close Month, ${rangeText(data.range.from, data.range.to)}. USD.`
          : 'Open Leads and Opportunities and counted Deals, by Expected Close Month, next six months. USD.'
      }
      table={{
        columns: ['Month', seriesLabel(labels, 'leads'), seriesLabel(labels, 'opportunities'), seriesLabel(labels, 'deals'), 'Total', 'Weighted'],
        rows: [
          ...forecast.months.map((m) => [
            monthLabel(m.month, 'MMM yyyy'),
            usd(m.by_module.leads.usd),
            usd(m.by_module.opportunities.usd),
            usd(m.by_module.deals.usd),
            usd(m.usd),
            usd(m.weighted_usd),
          ]),
          ...extra.map(([label, b]) => [label, '', '', '', usd(b.usd), usd(b.weighted_usd)]),
        ],
      }}
    >
      <CloseForecast forecast={forecast} labels={labels} ranged={ranged} />
    </ChartCard>
  )
}

function RagBreakdown({ data, ranged }: { data: DashboardData; ranged: boolean }) {
  const picklist = fieldOf('leads', 'overall_rag')?.picklist
  const byKey = new Map(data.rag.map((b) => [b.rag, b]))
  const order = [...optionsFor(picklist).map((o) => ({ key: o.key as string | null, label: o.label })).reverse(), { key: null, label: 'Not rated' }]

  const rows: BarRow[] = order.map(({ key, label }) => {
    const b = byKey.get(key) ?? { count: 0, usd: 0, weighted_usd: 0 }
    return {
      key: key ?? 'none',
      label,
      value: b.usd,
      display: usd(b.usd),
      note: String(b.count),
      tone: key ? (RAG_TONE[key] ?? 'chart') : 'muted',
      tooltip: [label, `${usd(b.usd)} · ${plural(b.count, 'record')}`],
    }
  })

  return (
    <ChartCard
      title="Overall RAG"
      info={`Open pipeline by the owner's RAG rating, in USD${closing(ranged)}.`}
      table={{ columns: ['RAG', 'Records', 'USD'], rows: rows.map((r) => [r.label, r.note ?? '', r.display]) }}
    >
      {data.kpis.pipeline.count > 0 ? <BarRows rows={rows} /> : <EmptyChart>{nothingHere(data, 'open pipeline to rate')}</EmptyChart>}
    </ChartCard>
  )
}

function StageAgeing({ data, ranged }: { data: DashboardData; ranged: boolean }) {
  const rows: BarRow[] = data.ageing.map((b) => ({
    key: b.bucket,
    label: `${b.bucket} days`,
    value: b.count,
    display: plural(b.count, 'record'),
    note: usd(b.usd),
    tooltip: [`${b.bucket} days in the current stage`, `${plural(b.count, 'record')} · ${usd(b.usd)}`],
  }))

  return (
    <ChartCard
      title="Time in current stage"
      info={`Open pipeline by days since the record entered the stage it is in${closing(ranged)}.`}
      table={{ columns: ['Days in stage', 'Records', 'USD'], rows: data.ageing.map((b) => [b.bucket, String(b.count), usd(b.usd)]) }}
    >
      {data.kpis.pipeline.count > 0 ? <BarRows rows={rows} /> : <EmptyChart>{nothingHere(data, 'open pipeline')}</EmptyChart>}
    </ChartCard>
  )
}

function LossReasons({ data, ranged }: { data: DashboardData; ranged: boolean }) {
  const picklist = fieldOf('leads', 'closed_lost_reason_code')?.picklist
  const labelOf = (key: string | null) =>
    key === null ? 'No reason recorded' : (optionsFor(picklist).find((o) => o.key === key)?.label ?? key)
  const lostAt = (stages: Record<string, number>) =>
    Object.entries(stages)
      .map(([stage, n]) => `Stage ${stage} × ${n}`)
      .join(', ')

  const rows: BarRow[] = data.loss_reasons.map((b) => ({
    key: b.reason ?? 'none',
    label: labelOf(b.reason),
    value: b.count,
    display: String(b.count),
    note: usd(b.usd),
    tone: b.reason === null ? 'muted' : 'chart',
    tooltip: [labelOf(b.reason), `${plural(b.count, 'pursuit')} · ${usd(b.usd)}`, ...(lostAt(b.stages) ? [`Lost at ${lostAt(b.stages)}`] : [])],
  }))

  return (
    <ChartCard
      title="Why we lose"
      info={
        ranged
          ? `Closed Lost primary pursuits lost ${rangeText(data.range.from, data.range.to)}, by the reason recorded at the stage they were lost.`
          : 'All Closed Lost primary pursuits, by the reason recorded at the stage they were lost.'
      }
      table={{
        columns: ['Reason', 'Pursuits', 'USD', 'Lost at'],
        rows: data.loss_reasons.map((b) => [labelOf(b.reason), String(b.count), usd(b.usd), lostAt(b.stages) || '—']),
      }}
    >
      {rows.length > 0 ? <BarRows rows={rows} /> : <EmptyChart>{nothingHere(data, 'losses')}</EmptyChart>}
    </ChartCard>
  )
}
