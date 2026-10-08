import { useId, useState } from 'react'

import type { SeriesTone, TileConfig } from '@/components/dashboard/config'
import { toneVar } from '@/components/dashboard/config'
import { compactUsd, measureOf, plural, share, toneOf } from '@/components/dashboard/format'
import type { Group } from '@/components/dashboard/types'
import { cn } from '@/lib/utils'

export interface Slice {
  key: string
  label: string
  value: number
  count: number
  /** Distinct accounts, where the tile counts them. */
  distinct?: number
  tone: SeriesTone
  /** Hatched — "Other", the values past the fixed hues. */
  hatched: boolean
  /** The group keys under this slice — several for Other. */
  keys: string[]
}

const SIZE = 150
const R_OUTER = 72
const R_INNER = 48

/**
 * The slices a tile's groups become. A value keeps the hue its picklist
 * position gives it; values past the fixed hues fold into one hatched "Other",
 * so no hue is ever generated and none is cycled. Unset stays its own slate
 * slice — never hidden from the total.
 */
export function slicesOf(config: TileConfig, groups: Group[]): Slice[] {
  const slices: Slice[] = []
  const other: Slice = { key: 'other', label: 'Other', value: 0, count: 0, distinct: 0, tone: 'slate', hatched: true, keys: [] }
  for (const g of groups) {
    const value = measureOf(config, g)
    if (value <= 0 && g.count === 0) continue
    const tone = toneOf(config, g)
    if (tone === null) {
      other.value += value
      other.count += g.count
      other.distinct = (other.distinct ?? 0) + (g.distinct ?? 0)
      other.keys.push(g.key)
      other.label = `Other (${other.keys.length})`
      continue
    }
    slices.push({ key: g.key, label: g.label, value, count: g.count, distinct: g.distinct, tone, hatched: false, keys: [g.key] })
  }
  if (other.keys.length) {
    // Before Not set, which stays last.
    const unset = slices.findIndex((s) => s.tone === 'slate')
    slices.splice(unset === -1 ? slices.length : unset, 0, other)
  }
  return slices
}

function arc(start: number, end: number): string {
  // Angles in turns from 12 o'clock, clockwise.
  const point = (turn: number, r: number) => {
    const a = turn * 2 * Math.PI - Math.PI / 2
    return `${SIZE / 2 + r * Math.cos(a)} ${SIZE / 2 + r * Math.sin(a)}`
  }
  const large = end - start > 0.5 ? 1 : 0
  return [
    `M ${point(start, R_OUTER)}`,
    `A ${R_OUTER} ${R_OUTER} 0 ${large} 1 ${point(end, R_OUTER)}`,
    `L ${point(end, R_INNER)}`,
    `A ${R_INNER} ${R_INNER} 0 ${large} 0 ${point(start, R_INNER)}`,
    'Z',
  ].join(' ')
}

function detail(slice: Slice, total: number, distinctNoun?: string): string {
  const parts = [plural(slice.count, 'record')]
  if (distinctNoun && slice.distinct !== undefined) parts.push(plural(slice.distinct, distinctNoun))
  const pct = share(slice.value, total)
  if (pct !== null) parts.push(`${pct}%`)
  return parts.join(' · ')
}

/**
 * A donut of one measure over one dimension. Hovering a slice or its legend
 * entry puts that slice's value, count and share in the centre; clicking
 * either opens its records.
 */
export function DonutChart({
  config,
  slices,
  distinctNoun,
  onSelect,
}: {
  config: TileConfig
  slices: Slice[]
  /** "account" — what `distinct` counts, for the readout. */
  distinctNoun?: string
  onSelect?: (slice: Slice) => void
}) {
  const hatch = useId().replace(/:/g, '')
  const [active, setActive] = useState<string | null>(null)
  const total = slices.reduce((sum, s) => sum + s.value, 0)
  const focus = slices.find((s) => s.key === active) ?? null
  const clickable = Boolean(onSelect) && !config.noDrill

  let turn = 0
  const drawn = slices.map((s) => {
    const start = turn
    turn += total > 0 ? s.value / total : 0
    return { slice: s, start, end: turn }
  })

  return (
    <div className="flex flex-wrap items-center gap-4">
      <svg viewBox={`0 0 ${SIZE} ${SIZE}`} width={SIZE} height={SIZE} role="img" aria-label={config.title} className="shrink-0">
        <defs>
          <pattern id={hatch} width="6" height="6" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
            <rect width="6" height="6" fill={toneVar('slate')} />
            <line x1="0" y1="0" x2="0" y2="6" stroke="var(--card)" strokeWidth="2" />
          </pattern>
        </defs>
        {drawn.map(({ slice, start, end }) =>
          end - start >= 0.9999 ? (
            <circle
              key={slice.key}
              cx={SIZE / 2}
              cy={SIZE / 2}
              r={(R_OUTER + R_INNER) / 2}
              fill="none"
              stroke={slice.hatched ? `url(#${hatch})` : toneVar(slice.tone)}
              strokeWidth={R_OUTER - R_INNER}
              onMouseEnter={() => setActive(slice.key)}
              onMouseLeave={() => setActive(null)}
              onClick={() => clickable && onSelect?.(slice)}
              className={cn(clickable && 'cursor-pointer')}
            />
          ) : (
            end > start && (
              <path
                key={slice.key}
                d={arc(start, end)}
                fill={slice.hatched ? `url(#${hatch})` : toneVar(slice.tone)}
                // The 2px surface gap between slices.
                stroke="var(--card)"
                strokeWidth={2}
                opacity={focus && focus.key !== slice.key ? 0.45 : 1}
                onMouseEnter={() => setActive(slice.key)}
                onMouseLeave={() => setActive(null)}
                onClick={() => clickable && onSelect?.(slice)}
                className={cn(clickable && 'cursor-pointer')}
              />
            )
          ),
        )}
        <text x={SIZE / 2} y={SIZE / 2 - 4} textAnchor="middle" className="fill-foreground text-[15px] font-semibold tabular-nums">
          {compactUsd(focus ? focus.value : total)}
        </text>
        <text x={SIZE / 2} y={SIZE / 2 + 13} textAnchor="middle" className="fill-muted-foreground text-[10px]">
          {focus ? (focus.label.length > 16 ? `${focus.label.slice(0, 15)}…` : focus.label) : 'Total'}
        </text>
      </svg>

      <ul className="min-w-0 flex-1 space-y-0.5">
        {slices.map((s) => (
          <li key={s.key}>
            <button
              type="button"
              aria-disabled={!clickable}
              onClick={() => clickable && onSelect?.(s)}
              onMouseEnter={() => setActive(s.key)}
              onMouseLeave={() => setActive(null)}
              onFocus={() => setActive(s.key)}
              onBlur={() => setActive(null)}
              title={`${s.label}: ${compactUsd(s.value)} · ${detail(s, total, distinctNoun)}`}
              className={cn(
                'hover:bg-accent/60 focus-visible:ring-ring grid w-full grid-cols-[auto_minmax(0,1fr)_auto] items-center gap-2 rounded px-1 py-0.5 text-left outline-none focus-visible:ring-2',
                clickable ? 'cursor-pointer' : 'cursor-default',
              )}
            >
              <span
                className="size-2.5 rounded-[2px]"
                style={
                  s.hatched
                    ? { background: `repeating-linear-gradient(45deg, var(--series-slate) 0 2px, var(--card) 2px 4px)` }
                    : { background: toneVar(s.tone) }
                }
              />
              <span className="text-label truncate">{s.label}</span>
              <span className="text-label text-right whitespace-nowrap tabular-nums">
                {compactUsd(s.value)}
                <span className="text-muted-foreground"> · {share(s.value, total) ?? 0}%</span>
              </span>
            </button>
          </li>
        ))}
      </ul>
      {/* Always one line, so hovering never moves the layout. */}
      <p className="text-muted-foreground text-meta w-full truncate" aria-live="polite">
        {focus
          ? `${focus.label}: ${compactUsd(focus.value)} · ${detail(focus, total, distinctNoun)}`
          : `${plural(slices.reduce((n, s) => n + s.count, 0), 'record')} · ${compactUsd(total)}`}
      </p>
    </div>
  )
}
