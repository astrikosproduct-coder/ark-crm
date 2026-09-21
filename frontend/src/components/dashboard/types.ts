/**
 * The shape of GET /api/dashboard — see backend/app/routers/dashboard.py, which
 * computes every number. Nothing on the dashboard is added up in the browser.
 */

export type PipelineModule = 'leads' | 'opportunities' | 'deals'

/** A group of records: how many, their USD, and USD x each one's Probability %. */
export interface Bucket {
  count: number
  usd: number
  weighted_usd: number
}

export interface DashboardItem {
  module: PipelineModule
  record_id: string
  name: string
  stage: number | null
  stage_name: string | null
  usd: number | null
  flag: 'no_value' | 'no_currency' | 'no_fx_rate' | null
  owner: string | null
  rag: string | null
  days_in_stage: number
  days_since_update: number
}

export interface DueItem extends DashboardItem {
  kind: 'milestone' | 'submission' | 'payment' | 'guarantee'
  date: string
  detail: string | null
  overdue: boolean
}

export interface RiskItem extends DashboardItem {
  reasons: ('red' | 'stuck')[]
}

export interface QuarterPreset {
  label: string
  start: string
  end: string
  current: boolean
}

export interface ForecastMonth extends Bucket {
  month: string
  by_module: Record<PipelineModule, Bucket>
}

export interface DashboardData {
  as_of: string
  /** left_out: counted records with no Expected Close Month, dropped because a range is set. */
  range: { from: string | null; to: string | null; left_out: number }
  /**
   * The same figures over the period immediately before this one, so a tile can
   * say "up or down" and not only "how much".
   *
   * NULL whenever the range has no length to step back by — all dates, or a
   * range with one end open. A delta against nothing is not a small
   * inaccuracy, it is a made-up number in the place a CXO trusts most, so the
   * tiles simply show no delta. `label` names the period when it is a fiscal
   * quarter ("Q1 FY2026-27") and is null for a hand-typed range, which has no
   * name to give. See previous_period() in backend/app/routers/dashboard.py.
   */
  comparison: {
    from: string
    to: string
    label: string | null
    kpis: { pipeline: Bucket; actual: Bucket; lost: Bucket }
  } | null
  quarters: QuarterPreset[]
  fiscal_year_start_month: number
  /** Estimated Value / Opportunity Revenue / Actual Revenue — backend/app/revenue.py. */
  revenue_labels: Record<PipelineModule, string>
  thresholds: { stale_after_days: number; stuck_after_days: number; due_window_days: number }
  /**
   * The slice filters the server ACTUALLY computed with, echoed back. Read
   * these rather than local state when explaining an empty widget — they can
   * never describe a filter the numbers were not computed under.
   */
  filters: {
    region: string | null
    segment: string | null
    owner: string | null
    opportunity_type: string | null
  }
  owners: { id: string; name: string }[]
  kpis: {
    pipeline: Bucket & {
      by_module: Record<'leads' | 'opportunities', Bucket>
      unpriced: number
    }
    actual: Bucket & { unpriced: number }
    lost: Bucket
    stale: Bucket
  }
  funnel: (Bucket & { stage: number; name: string; module: string | null })[]
  /** overdue / later / undated are null when a range is set — everything is inside it. */
  forecast: {
    months: ForecastMonth[]
    overdue: Bucket | null
    later: Bucket | null
    undated: Bucket | null
  }
  rag: (Bucket & { rag: string | null })[]
  ageing: (Bucket & { bucket: string })[]
  loss_reasons: (Bucket & { reason: string | null; stages: Record<string, number> })[]
  due: { total: number; items: DueItem[] }
  at_risk: { total: number; items: RiskItem[] }
}

export interface DashboardFilters {
  region?: string
  segment?: string
  owner?: string
  opportunity_type?: string
  /** 'YYYY-MM-DD', inclusive. */
  date_from?: string
  date_to?: string
}
