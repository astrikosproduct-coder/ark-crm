/**
 * The shape of GET /api/dashboard and /api/dashboard/records — see
 * backend/app/routers/dashboard.py, which computes every number. Nothing on the
 * dashboard is added up in the browser.
 */

export type PipelineModule = 'leads' | 'opportunities' | 'deals'

/** A group of records: how many, their USD, and USD x each one's Probability %. */
export interface Bucket {
  count: number
  usd: number
  weighted_usd: number
}

/** One bar, slice or row of a grouped tile. `key` is what the drill-down sends back. */
export interface Group extends Bucket {
  key: string
  label: string
  /** The value's place in its picklist — what fixes its colour. Unset values sort last. */
  order: number
  /** Distinct partners / accounts in the group, where the tile counts them. */
  distinct?: number
}

/** Group keys that are not values. Both draw in the neutral grey. */
export const NOT_SET = '__none__'
export const OTHERS = '__others__'
export const NO_PARTNER = '__no_partner__'

export interface PeriodPreset {
  kind: 'fiscal_year' | 'quarter'
  label: string
  start: string
  end: string
  current: boolean
}

export interface StageGroup extends Bucket {
  key: string
  stage: number
  name: string
  module: string | null
}

export interface MonthColumn extends Bucket {
  key: string
  label: string
}

export interface SnapshotMonth {
  key: string
  label: string
  /** Null when no snapshot was taken that month — drawn as a gap. */
  snapshot_date: string | null
  usd: number | null
  weighted_usd: number | null
  count: number | null
}

export interface PerformanceMonth {
  month: string
  /** Cumulative USD. Null where the series has no point: no targets, the future, the past. */
  target: number | null
  booked: number | null
  forecast: number | null
  prior: number | null
}

export interface QuarterMeter {
  key: string
  label: string
  start: string
  end: string
  /** An ended quarter is measured on bookings, an open one on forecast. */
  basis: 'booked' | 'forecast'
  value: number
  booked: number
  target: number | null
  pct: number | null
  band: 'good' | 'warning' | 'critical' | null
}

export interface Performance {
  fiscal_year: string
  prior_fiscal_year: string
  start: string
  end: string
  months: PerformanceMonth[]
  quarters: QuarterMeter[]
  targets: { available: boolean; set: boolean; blocked_by: string[] }
  booked_in_year: Bucket & { unpriced: number }
  booked_after_now: Bucket
  forecast_left_out: Bucket
}

/** The filters the page offers. Every one reaches every tile. */
export interface DashboardFilters {
  /** 'current_fy' — the page opens on this fiscal year without knowing when it starts. */
  period?: string
  /** 'YYYY-MM-DD', inclusive. */
  date_from?: string
  date_to?: string
  /** Booking Region. */
  region?: string
  segment?: string
  /** The Lead's Segment Category and Subsegment (Release 1.2). */
  segment_category?: string
  subsegment?: string
  owner?: string
  opportunity_type?: string
  deal_source?: string
  /** Customer (Partner / SI), an account id. */
  partner?: string
}

export type SliceFilter = Exclude<keyof DashboardFilters, 'period' | 'date_from' | 'date_to'>

export interface DashboardData {
  as_of: string
  /** The instant the server computed this answer. */
  generated_at: string
  /** left_out: counted records with no Expected Close Month, dropped because a range is set. */
  range: { from: string | null; to: string | null; left_out: number }
  /**
   * The same KPIs over the period immediately before this one, or null when
   * the range has no length to step back by. See previous_period().
   */
  comparison: {
    from: string
    to: string
    label: string | null
    kpis: { pipeline: Bucket; actual: Bucket; won: Bucket; lost: Bucket }
  } | null
  periods: PeriodPreset[]
  fiscal_year_start_month: number
  /** Estimated Value / Opportunity Revenue / Actual Revenue — backend/app/revenue.py. */
  revenue_labels: Record<PipelineModule, string>
  /** The slice filters the server ACTUALLY computed with, echoed back. */
  filters: Record<SliceFilter, string | null>
  owners: { id: string; name: string }[]
  partners: { id: string; name: string }[]
  kpis: {
    pipeline: Bucket & { by_module: Record<'leads' | 'opportunities', Bucket>; unpriced: number }
    actual: Bucket & { unpriced: number }
    /** Counted Deals whose PO Received Date is in the period. */
    won: Bucket & { unpriced: number }
    lost: Bucket
  }
  performance: Performance
  tiles: {
    'pipeline.stage': StageGroup[]
    'pipeline.close_month': { columns: MonthColumn[]; earlier: Bucket; later: Bucket }
    'pipeline.segment': Group[]
    'pipeline.delivery_region': Group[]
    'pipeline.month_end': { available: boolean; reason: string | null; dimension: string | null; months: SnapshotMonth[] }
    'partners.partner': Group[]
    'partners.deal_source': Group[]
    'partners.tier': Group[]
    'accounts.end_client': Group[]
    'accounts.customer_class': Group[]
    'winloss.reason': Group[]
  }
}

export interface DrillItem {
  module: PipelineModule
  record_id: string
  name: string
  stage: number | null
  stage_name: string | null
  status: string | null
  owner: string | null
  usd: number | null
  weighted_usd: number
  flag: 'no_value' | 'no_currency' | 'no_fx_rate' | null
}

export interface DrillResult extends Bucket {
  tile: string
  keys: string[]
  items: DrillItem[]
}

/** What a click asks for: a tile, the keys under the mark, and what to call the list. */
export interface DrillRequest {
  tile: string
  keys: string[]
  title: string
}
