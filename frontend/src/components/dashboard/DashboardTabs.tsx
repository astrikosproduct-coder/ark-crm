import { BarChart, type BarDatum } from '@/components/dashboard/BarChart'
import { BookingCurve, CURVE_SERIES, LegendLine } from '@/components/dashboard/BookingCurve'
import { EmptyChart } from '@/components/dashboard/ChartCard'
import { ColumnChart, type ColumnDatum } from '@/components/dashboard/ColumnChart'
import { TILES, type TileConfig } from '@/components/dashboard/config'
import { DonutChart, slicesOf } from '@/components/dashboard/DonutChart'
import { compactUsd, isNeutral, measureOf, monthLabel, plural, share, toneOf } from '@/components/dashboard/format'
import { basisText, QuarterMeters } from '@/components/dashboard/QuarterMeters'
import { nothingHere, Tile, useDashboard } from '@/components/dashboard/Tile'
import { NOT_SET, type Group } from '@/components/dashboard/types'
import { moduleFor } from '@/lib/modules'

/** The filters a target cannot be split by, in the words the filter row uses. */
const FILTER_NAMES: Record<string, string> = {
  region: 'Region',
  segment: 'Segment',
  opportunity_type: 'Opportunity Type',
  deal_source: 'Deal Source',
  partner: 'Partner',
}

function barsOf(config: TileConfig, groups: Group[]): BarDatum[] {
  return groups.map((g) => ({
    key: g.key,
    label: g.label,
    value: measureOf(config, g),
    display: compactUsd(g.usd),
    tone: toneOf(config, g) ?? 'slate',
    tooltip: [
      g.label,
      `${compactUsd(g.usd)} · ${plural(g.count, 'record')}`,
      ...(config.unweighted ? [] : [`Weighted ${compactUsd(g.weighted_usd)}`]),
    ],
  }))
}

function groupTable(config: TileConfig, groups: Group[]) {
  return {
    columns: [config.dimension, 'Records', 'USD', ...(config.unweighted ? [] : ['Weighted'])],
    rows: groups.map((g) => [g.label, String(g.count), compactUsd(g.usd), ...(config.unweighted ? [] : [compactUsd(g.weighted_usd)])]),
  }
}

/** A tile over grouped rows, drawn as bars, with its empty state and its drill-down. */
function GroupBars({ config, groups }: { config: TileConfig; groups: Group[] }) {
  const { data, drill } = useDashboard()
  return (
    <Tile config={config} table={groupTable(config, groups)}>
      {groups.some((g) => g.count > 0) ? (
        <BarChart
          config={config}
          rows={barsOf(config, groups)}
          onSelect={(row) => drill({ tile: config.id, keys: [row.key], title: `${config.title}: ${row.label}` })}
        />
      ) : (
        <EmptyChart>{nothingHere(data, config.empty)}</EmptyChart>
      )}
    </Tile>
  )
}

function GroupDonut({ config, groups, distinctNoun }: { config: TileConfig; groups: Group[]; distinctNoun?: string }) {
  const { data, drill } = useDashboard()
  const slices = slicesOf(config, groups)
  const total = slices.reduce((sum, s) => sum + s.value, 0)
  return (
    <Tile
      config={config}
      table={{
        columns: [config.dimension, 'Records', ...(distinctNoun ? ['Accounts'] : []), 'USD', 'Share'],
        rows: groups.map((g) => [
          g.label,
          String(g.count),
          ...(distinctNoun ? [String(g.distinct ?? 0)] : []),
          compactUsd(g.usd),
          `${share(g.usd, total) ?? 0}%`,
        ]),
      }}
    >
      {slices.length > 0 && total > 0 ? (
        <DonutChart
          config={config}
          slices={slices}
          distinctNoun={distinctNoun}
          onSelect={(s) => drill({ tile: config.id, keys: s.keys, title: `${config.title}: ${s.label}` })}
        />
      ) : (
        <EmptyChart>{slices.length > 0 ? 'Every record here is still without a value.' : nothingHere(data, config.empty)}</EmptyChart>
      )}
    </Tile>
  )
}

// ---------------------------------------------------------------------------
// 1  Performance — the KPI row sits above this, in DashboardPage
// ---------------------------------------------------------------------------

export function PerformanceTab() {
  const { data, drill } = useDashboard()
  const p = data.performance
  const blocked = p.targets.blocked_by.map((f) => FILTER_NAMES[f] ?? f)
  const targetsNote = !p.targets.available
    ? `Targets are set per BD Owner, so none is drawn while filtering by ${blocked.join(', ')}.`
    : !p.targets.set
      ? `No sales targets are set for ${p.fiscal_year} yet.`
      : null
  const plotted = p.months.some((m) => [m.target, m.booked, m.forecast, m.prior].some((v) => (v ?? 0) > 0))
  const curve = TILES.booking
  const extra = [
    ...(p.forecast_left_out.count > 0
      ? [`${plural(p.forecast_left_out.count, 'open record')} (${compactUsd(p.forecast_left_out.weighted_usd)} weighted) with a passed or missing close month.`]
      : []),
    ...(p.booked_after_now.count > 0
      ? [`${plural(p.booked_after_now.count, 'deal')} (${compactUsd(p.booked_after_now.usd)}) with a PO date later this year — in Won, plotted when the month comes.`]
      : []),
  ]

  return (
    <div className="space-y-4">
      <Tile
        config={curve}
        extra={extra}
        table={{
          columns: ['Month', 'Target', 'Booked', 'Forecast', `Prior FY (${p.prior_fiscal_year})`],
          rows: p.months.map((m) => [
            monthLabel(m.month, 'MMM yyyy'),
            compactUsd(m.target),
            compactUsd(m.booked),
            compactUsd(m.forecast),
            compactUsd(m.prior),
          ]),
        }}
      >
        <div className="space-y-2">
          <div className="text-meta flex flex-wrap items-center gap-x-4 gap-y-1">
            <span className="font-medium">{p.fiscal_year}</span>
            {CURVE_SERIES.map((s) => (
              <span key={s.key} className="flex items-center gap-1.5">
                <LegendLine series={s} />
                {s.key === 'prior' ? `Prior FY (${p.prior_fiscal_year})` : s.label}
              </span>
            ))}
          </div>
          {plotted ? (
            <BookingCurve
              config={curve}
              months={p.months}
              onSelectMonth={(m) =>
                m.booked !== null
                  ? drill({ tile: 'performance.booked', keys: [m.month], title: `Booked in ${monthLabel(m.month, 'MMMM yyyy')}` })
                  : m.forecast !== null
                    ? drill({ tile: 'performance.forecast', keys: [m.month], title: `Expected to close in ${monthLabel(m.month, 'MMMM yyyy')}` })
                    : undefined
              }
            />
          ) : (
            <EmptyChart>{`No bookings, forecast or targets for ${p.fiscal_year} yet.`}</EmptyChart>
          )}
          {/* The tie-out, on screen: this is the Won card's own figure for the year. */}
          <p className="text-muted-foreground text-meta">
            Booked in {p.fiscal_year}: {compactUsd(p.booked_in_year.usd)} · {plural(p.booked_in_year.count, 'deal')} by PO Received Date
            {p.booked_in_year.unpriced > 0 && ` · ${plural(p.booked_in_year.unpriced, 'deal')} still without a value`}
            {targetsNote && ` · ${targetsNote}`}
          </p>
        </div>
      </Tile>

      <Tile
        config={TILES.quarters}
        table={{
          columns: ['Quarter', 'Basis', 'Booked', 'Measured', 'Target', 'Attainment'],
          rows: p.quarters.map((q) => [
            `${q.label} (${monthLabel(q.start, 'MMM')}–${monthLabel(q.end, 'MMM')})`,
            q.basis === 'booked' ? 'Bookings' : 'Forecast',
            compactUsd(q.booked),
            compactUsd(q.value),
            q.target === null ? 'No target set' : compactUsd(q.target),
            q.pct === null ? 'No target set' : `${q.pct}%`,
          ]),
        }}
      >
        <QuarterMeters
          config={TILES.quarters}
          quarters={p.quarters}
          targetsNote={targetsNote}
          onSelect={(q) => drill({ tile: 'performance.quarter', keys: [q.key], title: `${q.label} ${p.fiscal_year} — ${basisText(q).toLowerCase()}` })}
        />
      </Tile>
    </div>
  )
}

// ---------------------------------------------------------------------------
// 2  Pipeline
// ---------------------------------------------------------------------------

function StageFunnel() {
  const { data, drill } = useDashboard()
  const config = TILES.stage
  const stages = data.tiles['pipeline.stage']
  let previous: string | null = null
  const rows: BarDatum[] = stages.map((s) => {
    const group = s.module !== previous ? (moduleFor(s.module ?? '')?.label ?? s.module ?? undefined) : undefined
    previous = s.module
    const label = `${s.stage} ${s.name}`
    return {
      key: s.key,
      label,
      value: s.usd,
      display: compactUsd(s.usd),
      tone: 'navy',
      group,
      tooltip: [label, `${compactUsd(s.usd)} · ${plural(s.count, 'record')}`, `Weighted ${compactUsd(s.weighted_usd)}`],
    }
  })
  return (
    <Tile
      config={config}
      table={{
        columns: ['Stage', 'Module', 'Records', 'USD', 'Weighted'],
        rows: stages.map((s) => [`${s.stage} ${s.name}`, moduleFor(s.module ?? '')?.label ?? '', String(s.count), compactUsd(s.usd), compactUsd(s.weighted_usd)]),
      }}
    >
      {stages.some((s) => s.count > 0) ? (
        <BarChart config={config} rows={rows} onSelect={(row) => drill({ tile: config.id, keys: [row.key], title: `Stage ${row.label}` })} />
      ) : (
        <EmptyChart>{nothingHere(data, config.empty)}</EmptyChart>
      )}
    </Tile>
  )
}

function CloseMonths() {
  const { data, drill } = useDashboard()
  const config = TILES.closeMonth
  const { columns, earlier, later } = data.tiles['pipeline.close_month']
  const extra = [
    ...(earlier.count > 0 ? [`${plural(earlier.count, 'record')} (${compactUsd(earlier.usd)}) whose close month has passed.`] : []),
    ...(later.count > 0 ? [`${plural(later.count, 'record')} (${compactUsd(later.usd)}) closing after the months shown.`] : []),
  ]
  const datums: ColumnDatum[] = columns.map((c) => ({
    key: c.key,
    label: c.key === NOT_SET ? 'No month' : monthLabel(c.key, 'MMM yy'),
    value: measureOf(config, c),
    tone: c.key === NOT_SET ? 'slate' : 'navy',
    tooltip: [c.label, `${compactUsd(c.usd)} · ${plural(c.count, 'record')}`, `Weighted ${compactUsd(c.weighted_usd)}`],
  }))
  return (
    <Tile
      config={config}
      extra={extra}
      table={{ columns: ['Close month', 'Records', 'USD', 'Weighted'], rows: columns.map((c) => [c.label, String(c.count), compactUsd(c.usd), compactUsd(c.weighted_usd)]) }}
    >
      {columns.some((c) => c.count > 0) ? (
        <ColumnChart
          config={config}
          columns={datums}
          onSelect={(c) => drill({ tile: config.id, keys: [c.key], title: `Expected to close: ${c.tooltip[0]}` })}
        />
      ) : (
        <EmptyChart>{nothingHere(data, config.empty)}</EmptyChart>
      )}
      {extra.length > 0 && <p className="text-muted-foreground text-meta mt-2">{extra.join(' ')}</p>}
    </Tile>
  )
}

function MonthEndHistory() {
  const { data } = useDashboard()
  const config = TILES.monthEnd
  const history = data.tiles['pipeline.month_end']
  const datums: ColumnDatum[] = history.months.map((m) => ({
    key: m.key,
    label: monthLabel(m.key, 'MMM yy'),
    value: m.usd,
    tone: 'navy',
    tooltip:
      m.usd === null
        ? [m.label, 'No snapshot this month']
        : [m.label, `${compactUsd(m.usd)} · ${plural(m.count ?? 0, 'record')}`, `Weighted ${compactUsd(m.weighted_usd)}`, `As at ${m.snapshot_date}`],
  }))
  return (
    <Tile
      config={config}
      table={{
        columns: ['Month', 'Snapshot', 'Records', 'USD', 'Weighted'],
        rows: history.months.map((m) => [
          m.label,
          m.snapshot_date ?? 'None taken',
          m.count === null ? '—' : String(m.count),
          compactUsd(m.usd),
          compactUsd(m.weighted_usd),
        ]),
      }}
    >
      {!history.available ? (
        <EmptyChart>{history.reason}</EmptyChart>
      ) : history.months.every((m) => m.usd === null) ? (
        <EmptyChart>No month-end snapshots in this period yet. One is written at the end of every month.</EmptyChart>
      ) : (
        <ColumnChart config={config} columns={datums} />
      )}
    </Tile>
  )
}

export function PipelineTab() {
  const { data } = useDashboard()
  return (
    <div className="space-y-4">
      <div className="grid gap-4 lg:grid-cols-2">
        <StageFunnel />
        <CloseMonths />
      </div>
      <div className="grid gap-4 lg:grid-cols-3">
        <GroupDonut config={TILES.segment} groups={data.tiles['pipeline.segment']} />
        <GroupDonut config={TILES.deliveryRegion} groups={data.tiles['pipeline.delivery_region']} />
      </div>
      <MonthEndHistory />
    </div>
  )
}

// ---------------------------------------------------------------------------
// 3  Partners
// ---------------------------------------------------------------------------

function TierContribution() {
  const { data, drill } = useDashboard()
  const config = TILES.tier
  const tiers = data.tiles['partners.tier']
  const total = tiers.reduce((sum, t) => sum + t.usd, 0)
  return (
    <Tile
      config={config}
      table={{
        columns: ['Partner Tier', 'Partners', 'Pipeline', 'Share'],
        rows: tiers.map((t) => [t.label, isNeutral(t.key) && t.key !== NOT_SET ? '—' : String(t.distinct ?? 0), compactUsd(t.usd), `${share(t.usd, total) ?? 0}%`]),
      }}
    >
      {tiers.some((t) => t.count > 0) ? (
        <BarChart
          config={config}
          rows={tiers.map((t) => ({
            key: t.key,
            label: t.label,
            value: t.usd,
            display: `${compactUsd(t.usd)} · ${share(t.usd, total) ?? 0}%`,
            tone: toneOf(config, t) ?? 'slate',
            tooltip: [t.label, `${plural(t.distinct ?? 0, 'partner')} · ${plural(t.count, 'record')}`, `${compactUsd(t.usd)} · ${share(t.usd, total) ?? 0}% of pipeline`],
          }))}
          onSelect={(row) => drill({ tile: config.id, keys: [row.key], title: `${config.title}: ${row.label}` })}
        />
      ) : (
        <EmptyChart>{nothingHere(data, config.empty)}</EmptyChart>
      )}
    </Tile>
  )
}

export function PartnersTab() {
  const { data } = useDashboard()
  return (
    <div className="space-y-4">
      <div className="grid gap-4 lg:grid-cols-2">
        <GroupBars config={TILES.partner} groups={data.tiles['partners.partner']} />
        <GroupDonut config={TILES.dealSource} groups={data.tiles['partners.deal_source']} />
      </div>
      <TierContribution />
    </div>
  )
}

// ---------------------------------------------------------------------------
// 4  Accounts
// ---------------------------------------------------------------------------

export function AccountsTab() {
  const { data } = useDashboard()
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <GroupBars config={TILES.endClient} groups={data.tiles['accounts.end_client']} />
      <GroupDonut config={TILES.customerClass} groups={data.tiles['accounts.customer_class']} distinctNoun="account" />
    </div>
  )
}

// ---------------------------------------------------------------------------
// 5  Win & loss
// ---------------------------------------------------------------------------

export function WinLossTab() {
  const { data } = useDashboard()
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <GroupBars config={TILES.lossReason} groups={data.tiles['winloss.reason']} />
    </div>
  )
}
