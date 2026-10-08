import { format, parseISO } from 'date-fns'

import { CATEGORICAL, type SeriesTone, type TileConfig } from '@/components/dashboard/config'
import { NOT_SET, NO_PARTNER, OTHERS, type DashboardData, type Group, type PipelineModule } from '@/components/dashboard/types'
import { moduleFor } from '@/lib/modules'

/** 'YYYY-MM-DD' is a calendar fact — parsed as a local date, never converted. */
export function monthLabel(month: string, pattern: string): string {
  return format(parseISO(month), pattern)
}

/** "Opportunity Revenue (Opportunities)" — the revenue rule's label and the module it belongs to. */
export function seriesLabel(labels: DashboardData['revenue_labels'], module: PipelineModule): string {
  return `${labels[module]} (${moduleFor(module)?.label ?? module})`
}

/**
 * Chart money: $1.2M from a million, $250K below it, $640 under a thousand.
 * Never a raw float. The KPI cards keep their own full figures.
 */
export function compactUsd(value: number | null | undefined): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return '—'
  const sign = value < 0 ? '−' : ''
  const v = Math.abs(value)
  if (v >= 1_000_000) return `${sign}$${(v / 1_000_000).toFixed(1)}M`
  if (v >= 1_000) return `${sign}$${Math.round(v / 1_000)}K`
  return `${sign}$${Math.round(v)}`
}

export function plural(n: number, word: string): string {
  return `${Math.round(n).toLocaleString('en-US')} ${word}${n === 1 ? '' : 's'}`
}

/** A whole per cent of a whole, or null when there is no whole to divide by. */
export function share(part: number, whole: number): number | null {
  return whole > 0 ? Math.round((part / whole) * 100) : null
}

/** The value a tile's config says its marks encode. */
export function measureOf(config: TileConfig, bucket: { usd: number; weighted_usd: number; count: number }): number {
  return bucket[config.measure]
}

export function isNeutral(key: string): boolean {
  return key === NOT_SET || key === NO_PARTNER || key === OTHERS
}

/**
 * A group's colour. Unset, No partner and Others are the neutral slate. A
 * one-hue chart uses its tone; a categorical one fixes the colour by the value's
 * place in its picklist (or the config's named colour), never by rank.
 */
export function toneOf(config: TileConfig, group: Pick<Group, 'key' | 'order'>): SeriesTone | null {
  if (isNeutral(group.key)) return 'slate'
  if (config.colors?.[group.key]) return config.colors[group.key]
  if (config.tone) return config.tone
  return CATEGORICAL[group.order] ?? null
}
