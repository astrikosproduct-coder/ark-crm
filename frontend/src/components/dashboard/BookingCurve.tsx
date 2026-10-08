import { useEffect, useRef, useState } from 'react'

import type { SeriesTone, TileConfig } from '@/components/dashboard/config'
import { toneVar } from '@/components/dashboard/config'
import { compactUsd, monthLabel } from '@/components/dashboard/format'
import type { PerformanceMonth } from '@/components/dashboard/types'

type SeriesKey = 'target' | 'booked' | 'forecast' | 'prior'

interface SeriesStyle {
  key: SeriesKey
  label: string
  tone: SeriesTone
  width: number
  /** SVG dash pattern — the lines differ by pattern as well as colour. */
  dash?: string
}

/**
 * Booked is the heaviest solid line; Target dashed, Forecast dotted, Prior FY
 * thin dash-dot. Pattern and weight tell them apart without colour, which the
 * validator says two of these hues need.
 */
export const CURVE_SERIES: SeriesStyle[] = [
  { key: 'target', label: 'Target', tone: 'navy', width: 2, dash: '7 4' },
  { key: 'booked', label: 'Booked', tone: 'amber', width: 3.25 },
  { key: 'forecast', label: 'Forecast', tone: 'teal', width: 2.25, dash: '0.5 5' },
  { key: 'prior', label: 'Prior FY', tone: 'slate', width: 1.25, dash: '9 3 2 3' },
]

const HEIGHT = 250
const PAD = { top: 12, right: 16, bottom: 26, left: 56 }

function useWidth<T extends HTMLElement>() {
  const ref = useRef<T>(null)
  const [width, setWidth] = useState(640)
  useEffect(() => {
    const el = ref.current
    if (!el) return
    const observer = new ResizeObserver(([entry]) => setWidth(Math.max(320, Math.floor(entry.contentRect.width))))
    observer.observe(el)
    return () => observer.disconnect()
  }, [])
  return [ref, width] as const
}

/** A round axis ceiling: 1, 2, 2.5 or 5 x a power of ten. */
function niceCeiling(value: number): number {
  if (value <= 0) return 1
  const power = 10 ** Math.floor(Math.log10(value))
  const step = [1, 2, 2.5, 5, 10].find((m) => m * power >= value) ?? 10
  return step * power
}

export function LegendLine({ series }: { series: SeriesStyle }) {
  return (
    <svg width="26" height="8" aria-hidden className="shrink-0">
      <line
        x1="1"
        y1="4"
        x2="25"
        y2="4"
        stroke={toneVar(series.tone)}
        strokeWidth={series.width}
        strokeDasharray={series.dash}
        strokeLinecap={series.key === 'forecast' ? 'round' : 'butt'}
      />
    </svg>
  )
}

/**
 * The cumulative S-curve: twelve fiscal months, running USD, four series. A
 * crosshair follows the pointer and reads all four for that month with the
 * gap to target; a click opens the month's booked (or, ahead of today,
 * forecast) records.
 */
export function BookingCurve({
  config,
  months,
  onSelectMonth,
}: {
  config: TileConfig
  months: PerformanceMonth[]
  onSelectMonth?: (month: PerformanceMonth) => void
}) {
  const [ref, width] = useWidth<HTMLDivElement>()
  const [hover, setHover] = useState<number | null>(null)

  const values = months.flatMap((m) => CURVE_SERIES.map((s) => m[s.key] ?? 0))
  const top = niceCeiling(Math.max(0, ...values))
  const plotW = width - PAD.left - PAD.right
  const plotH = HEIGHT - PAD.top - PAD.bottom
  const x = (i: number) => PAD.left + (months.length > 1 ? (i / (months.length - 1)) * plotW : plotW / 2)
  const y = (v: number) => PAD.top + plotH - (v / top) * plotH
  const ticks = [0, 0.25, 0.5, 0.75, 1].map((f) => f * top)

  /** A path that lifts the pen over nulls — the future, a year without targets. */
  const pathOf = (key: SeriesKey) => {
    let d = ''
    let pen = false
    months.forEach((m, i) => {
      const v = m[key]
      if (v === null || v === undefined) {
        pen = false
        return
      }
      d += `${pen ? 'L' : 'M'} ${x(i)} ${y(v)} `
      pen = true
    })
    return d.trim()
  }

  const focus = hover === null ? null : months[hover]
  const gapLine = (m: PerformanceMonth) => {
    const actual = m.booked ?? m.forecast
    if (m.target === null || actual === null) return null
    const gap = actual - m.target
    return `${gap >= 0 ? 'Ahead of' : 'Behind'} target by ${compactUsd(Math.abs(gap))}`
  }

  return (
    <div ref={ref} className="relative w-full">
      <svg width={width} height={HEIGHT} role="img" aria-label={config.title} className="block">
        {ticks.map((t) => (
          <g key={t}>
            <line x1={PAD.left} x2={width - PAD.right} y1={y(t)} y2={y(t)} stroke="var(--border)" strokeWidth={1} />
            <text x={PAD.left - 8} y={y(t) + 4} textAnchor="end" className="fill-muted-foreground text-[11px] tabular-nums">
              {compactUsd(t)}
            </text>
          </g>
        ))}
        {months.map((m, i) => (
          <text key={m.month} x={x(i)} y={HEIGHT - 8} textAnchor="middle" className="fill-muted-foreground text-[11px]">
            {monthLabel(m.month, 'MMM')}
          </text>
        ))}
        {focus !== null && hover !== null && (
          <line x1={x(hover)} x2={x(hover)} y1={PAD.top} y2={PAD.top + plotH} stroke="var(--muted-foreground)" strokeWidth={1} strokeDasharray="2 3" />
        )}
        {CURVE_SERIES.map((s) => (
          <path
            key={s.key}
            d={pathOf(s.key)}
            fill="none"
            stroke={toneVar(s.tone)}
            strokeWidth={s.width}
            strokeDasharray={s.dash}
            strokeLinecap={s.key === 'forecast' ? 'round' : 'butt'}
            strokeLinejoin="round"
          />
        ))}
        {/* Booked is the one series with markers: it is the fact the rest are measured by. */}
        {months.map((m, i) =>
          m.booked === null ? null : (
            <circle key={m.month} cx={x(i)} cy={y(m.booked)} r={hover === i ? 4.5 : 3} fill={toneVar('amber')} stroke="var(--card)" strokeWidth={2} />
          ),
        )}
        {/* Hit areas: one column per month, bigger than any mark. */}
        {months.map((m, i) => {
          const half = months.length > 1 ? plotW / (months.length - 1) / 2 : plotW / 2
          return (
            <rect
              key={m.month}
              x={x(i) - half}
              y={PAD.top}
              width={half * 2}
              height={plotH}
              fill="transparent"
              tabIndex={0}
              role="button"
              aria-label={`${monthLabel(m.month, 'MMMM yyyy')}: ${CURVE_SERIES.map((s) => `${s.label} ${compactUsd(m[s.key])}`).join(', ')}`}
              onMouseEnter={() => setHover(i)}
              onMouseLeave={() => setHover(null)}
              onFocus={() => setHover(i)}
              onBlur={() => setHover(null)}
              onClick={() => onSelectMonth?.(m)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' || e.key === ' ') {
                  e.preventDefault()
                  onSelectMonth?.(m)
                }
              }}
              className="cursor-pointer outline-none"
            />
          )
        })}
      </svg>

      {focus !== null && hover !== null && (
        <div
          className="bg-popover text-popover-foreground border-border pointer-events-none absolute top-2 z-10 w-52 rounded-md border px-3 py-2 text-xs shadow-md"
          style={x(hover) > width / 2 ? { left: Math.max(0, x(hover) - 220) } : { left: x(hover) + 12 }}
        >
          <div className="mb-1 font-semibold">{monthLabel(focus.month, 'MMMM yyyy')}</div>
          {CURVE_SERIES.map((s) => (
            <div key={s.key} className="flex items-center justify-between gap-2">
              <span className="flex items-center gap-1.5">
                <LegendLine series={s} />
                {s.label}
              </span>
              <span className="tabular-nums">{focus[s.key] === null ? '—' : compactUsd(focus[s.key])}</span>
            </div>
          ))}
          {gapLine(focus) && <div className="border-border mt-1 border-t pt-1">{gapLine(focus)}</div>}
        </div>
      )}
    </div>
  )
}
