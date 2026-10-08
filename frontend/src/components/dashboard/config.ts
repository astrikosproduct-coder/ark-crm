/**
 * What each dashboard tile shows, as data.
 *
 * Every chart component takes one of these objects and nothing hardcoded of
 * its own: title, measure, dimension, chart type, the field caption and the
 * definition behind the ⓘ. The visuals are fixed for Phase 1 (28 Sep 2026); a
 * later widget builder will produce objects of this same shape — `id` is the
 * server tile it reads (backend/app/routers/dashboard.py TILES), and the
 * drill-down sends the same id back.
 */

/** A series colour — a theme token in src/index.css, never a hex value. */
export type SeriesTone = 'navy' | 'teal' | 'amber' | 'crimson' | 'plum' | 'slate'

export type Measure = 'usd' | 'weighted_usd' | 'count'

export type ChartKind = 'bar' | 'column' | 'donut' | 'line' | 'meter' | 'table'

export interface TileConfig {
  /** The server tile this reads, and the id the drill-down sends back. */
  id: string
  title: string
  chart: ChartKind
  /** What the length / angle / height encodes. Counts go in the tooltip. */
  measure: Measure
  /** What the marks split by, in words. */
  dimension: string
  /** The exact fields, printed small in mono under the title. */
  caption: string
  /** The ⓘ popover: what is summed, what is split, what is left out. */
  definition: { measure: string; dimension: string; exclusions: string[] }
  /** One-hue charts: the hue. Categorical charts leave it out. */
  tone?: SeriesTone
  /** Categorical charts: a value's fixed colour, where the brief names one. */
  colors?: Record<string, SeriesTone>
  /** The noun for the empty state — "No {empty} yet." */
  empty: string
  /** Set when there are no records behind a mark to list. */
  noDrill?: boolean
  /** Open on the table rather than the chart. */
  tableFirst?: boolean
  /** Leave the weighted value out of the tooltip — losses carry none. */
  unweighted?: boolean
}

/**
 * Categorical hues in fixed order, by the value's place in its picklist —
 * never by rank, so a filter never repaints a survivor. Crimson is kept out:
 * it means loss. A fifth value onwards folds into Other.
 */
export const CATEGORICAL: SeriesTone[] = ['navy', 'teal', 'amber', 'plum']

export const toneVar = (tone: SeriesTone) => `var(--series-${tone})`

const OPEN_PIPELINE = 'Open and On Hold Leads and Opportunities, primary pursuits only, in USD at the stamped FX rate.'
const CLOSING = 'Records whose Expected Close Month is outside the period, or who have none, are left out when a period is set.'
const UNPRICED = 'A record with no value, currency or FX rate counts as $0 and is flagged.'

export const TILES = {
  booking: {
    id: 'performance.booked',
    title: 'Cumulative order booking against plan',
    chart: 'line',
    measure: 'usd',
    dimension: 'Fiscal month',
    caption: 'sales_targets.target_amount_usd · deals.contract_value by po_received_date · weighted value by expected_close_month',
    definition: {
      measure:
        'Running totals in USD. Target: current sales targets, draft and locked, never superseded. Booked: Contract Value of counted Deals by PO Received Date — the Won card, month by month. Forecast: Booked to date plus the weighted value (value × Probability %) of open records by Expected Close Month. Prior FY: Booked for the year before.',
      dimension: 'The twelve months of the fiscal year holding the period’s start.',
      exclusions: [
        'Booked has no point after this month.',
        'Forecast leaves out records whose close month has passed or is not set.',
        'Targets are set per BD Owner, so they cannot be drawn under a Region, Segment, Theme, Deal Source, Partner or Opportunity Type filter.',
        UNPRICED,
      ],
    },
    empty: 'bookings',
  },
  quarters: {
    id: 'performance.quarter',
    title: 'Quarter attainment',
    chart: 'meter',
    measure: 'usd',
    dimension: 'Fiscal quarter',
    caption: 'deals.contract_value by po_received_date · weighted value by expected_close_month ÷ sales_targets.target_amount_usd',
    definition: {
      measure:
        'An ended quarter: Booked ÷ Target. An open quarter: Forecast ÷ Target, where Forecast is Booked in the quarter so far plus the weighted value of open records closing in its remaining months.',
      dimension: 'Q1 to Q4 of the fiscal year, from the company’s fiscal calendar.',
      exclusions: ['A quarter with no target shows “No target set”.', 'Bands: 95% and over on track, 70–94% watch, under 70% behind.'],
    },
    empty: 'quarters',
  },
  stage: {
    id: 'pipeline.stage',
    title: 'Stage funnel',
    chart: 'bar',
    measure: 'usd',
    dimension: 'Stage',
    caption: 'leads.estimated_value · opportunities.total_value_tcv · deals.contract_value by stage',
    definition: {
      measure: `${OPEN_PIPELINE} Deals add their Contract Value until their project is closed.`,
      dimension: 'The stage each record is in now, grouped by the module that owns it.',
      exclusions: [CLOSING, UNPRICED],
    },
    tone: 'navy',
    empty: 'live pursuits',
  },
  closeMonth: {
    id: 'pipeline.close_month',
    title: 'Pipeline by expected close month',
    chart: 'column',
    measure: 'usd',
    dimension: 'Expected Close Month',
    caption: 'leads.estimated_value · opportunities.total_value_tcv by expected_close_month',
    definition: {
      measure: OPEN_PIPELINE,
      dimension: 'The next six months from this month, within the period, and a column for records with no close month.',
      exclusions: ['Records closing before or after the months shown are counted below the chart.', UNPRICED],
    },
    tone: 'navy',
    empty: 'open pipeline',
  },
  segment: {
    id: 'pipeline.segment',
    title: 'Pipeline by segment',
    chart: 'donut',
    measure: 'usd',
    dimension: 'Segment',
    caption: 'pipeline value by leads.segment',
    definition: { measure: OPEN_PIPELINE, dimension: 'Segment, on the Lead each record descends from.', exclusions: [CLOSING, UNPRICED] },
    empty: 'open pipeline',
  },
  theme: {
    id: 'pipeline.theme',
    title: 'Pipeline by theme',
    chart: 'donut',
    measure: 'usd',
    dimension: 'Theme',
    caption: 'pipeline value by leads.theme',
    definition: { measure: OPEN_PIPELINE, dimension: 'Theme, on the Lead each record descends from.', exclusions: [CLOSING, UNPRICED] },
    empty: 'open pipeline',
  },
  deliveryRegion: {
    id: 'pipeline.delivery_region',
    title: 'Pipeline by delivery region',
    chart: 'donut',
    measure: 'usd',
    dimension: 'Destination Region',
    caption: 'pipeline value by leads.destination_region — where the work is delivered, not where it books',
    definition: {
      measure: OPEN_PIPELINE,
      dimension: 'Destination Region: where the work is delivered. Money is reported by Booking Region everywhere else.',
      exclusions: [CLOSING, UNPRICED],
    },
    empty: 'open pipeline',
  },
  monthEnd: {
    id: 'pipeline.month_end',
    title: 'Open pipeline at each month-end',
    chart: 'column',
    measure: 'usd',
    dimension: 'Month',
    caption: 'pipeline_snapshots.open_value_usd',
    definition: {
      measure: 'The open pipeline as it stood when the month-end snapshot was taken — Open and On Hold Leads and Opportunities, in USD.',
      dimension: 'The latest snapshot in each month. A month with none is a gap, never zero.',
      exclusions: [
        'Snapshots are kept whole, or for one BD Owner, Booking Region or Segment — not under any other filter.',
        'Snapshots keep totals, not records, so a column has no list to open.',
      ],
    },
    tone: 'navy',
    empty: 'month-end snapshots',
    noDrill: true,
  },
  partner: {
    id: 'partners.partner',
    title: 'Pipeline by partner',
    chart: 'bar',
    measure: 'usd',
    dimension: 'Customer (Partner / SI)',
    caption: 'pipeline value by customer_partner_si',
    definition: {
      measure: OPEN_PIPELINE,
      dimension: 'Customer (Partner / SI): the ten largest, then Others. A Deal uses its own locked copy.',
      exclusions: [CLOSING, UNPRICED],
    },
    tone: 'navy',
    empty: 'partner pipeline',
  },
  dealSource: {
    id: 'partners.deal_source',
    title: 'Partner-sourced vs direct',
    chart: 'donut',
    measure: 'usd',
    dimension: 'Deal Source',
    caption: 'pipeline value by leads.deal_source',
    definition: { measure: OPEN_PIPELINE, dimension: 'Deal Source, on the Lead.', exclusions: [CLOSING, UNPRICED] },
    colors: { PARTNER_SOURCED: 'teal', DIRECT: 'navy' },
    empty: 'open pipeline',
  },
  tier: {
    id: 'partners.tier',
    title: 'Tier against contribution',
    chart: 'table',
    measure: 'usd',
    dimension: 'Partner Tier',
    caption: 'accounts.partner_tier of customer_partner_si · pipeline value · share %',
    definition: {
      measure: `${OPEN_PIPELINE} Share is of the whole open pipeline under these filters.`,
      dimension: 'The Partner Tier of each record’s Customer (Partner / SI). No partner is its own row, so shares add to 100%.',
      exclusions: [CLOSING, UNPRICED],
    },
    tone: 'navy',
    empty: 'open pipeline',
    tableFirst: true,
  },
  endClient: {
    id: 'accounts.end_client',
    title: 'Top 10 accounts by pipeline',
    chart: 'bar',
    measure: 'usd',
    dimension: 'End Client',
    caption: 'pipeline value by leads.end_client',
    definition: {
      measure: OPEN_PIPELINE,
      dimension: 'End Client, on the Lead: the ten largest, then Others.',
      exclusions: [CLOSING, UNPRICED],
    },
    tone: 'navy',
    empty: 'open pipeline',
  },
  customerClass: {
    id: 'accounts.customer_class',
    title: 'Customer class mix',
    chart: 'donut',
    measure: 'usd',
    dimension: 'Customer Class',
    caption: 'pipeline value by accounts.customer_class of end_client',
    definition: {
      measure: OPEN_PIPELINE,
      dimension: 'The Customer Class of each record’s End Client. The tooltip counts distinct accounts.',
      exclusions: [CLOSING, UNPRICED],
    },
    empty: 'open pipeline',
  },
  lossReason: {
    id: 'winloss.reason',
    title: 'Why we lose',
    chart: 'bar',
    measure: 'usd',
    dimension: 'Closed Lost Reason Code',
    caption: 'lost value by closed_lost_reason_code',
    definition: {
      measure: 'Closed Lost primary pursuits, by the value they carried when lost, in USD.',
      dimension: 'Closed Lost Reason Code, as recorded at the stage the pursuit was lost.',
      exclusions: ['With a period set, only pursuits lost in it — by the date they were lost.'],
    },
    tone: 'crimson',
    empty: 'losses',
    unweighted: true,
  },
} satisfies Record<string, TileConfig>
