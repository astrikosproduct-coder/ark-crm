import { AlertTriangleIcon, CheckCircle2Icon, XCircleIcon } from 'lucide-react'

import type { SeriesTone, TileConfig } from '@/components/dashboard/config'
import { toneVar } from '@/components/dashboard/config'
import { compactUsd, monthLabel } from '@/components/dashboard/format'
import type { QuarterMeter } from '@/components/dashboard/types'

/**
 * A band is a state, so it never travels by colour alone: an icon and a word
 * ride with it (teal on track, amber watch, crimson behind).
 */
const BAND: Record<NonNullable<QuarterMeter['band']>, { tone: SeriesTone; label: string; Icon: typeof CheckCircle2Icon }> = {
  good: { tone: 'teal', label: 'On track', Icon: CheckCircle2Icon },
  warning: { tone: 'amber', label: 'Watch', Icon: AlertTriangleIcon },
  critical: { tone: 'crimson', label: 'Behind', Icon: XCircleIcon },
}

export function basisText(q: QuarterMeter): string {
  return q.basis === 'booked' ? 'Ended · measured on bookings' : 'Open · measured on forecast'
}

/**
 * Q1-Q4 of the fiscal year. An ended quarter is Booked ÷ Target, an open one
 * Forecast ÷ Target, and each says which. A quarter with no target says so —
 * there is no percentage of nothing.
 */
export function QuarterMeters({
  config,
  quarters,
  targetsNote,
  onSelect,
}: {
  config: TileConfig
  quarters: QuarterMeter[]
  /** Why no quarter has a target, when a filter is the reason. */
  targetsNote: string | null
  onSelect?: (quarter: QuarterMeter) => void
}) {
  return (
    <div className="space-y-2">
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4" aria-label={config.title}>
        {quarters.map((q) => {
          const band = q.band ? BAND[q.band] : null
          return (
            <button
              key={q.key}
              type="button"
              onClick={() => onSelect?.(q)}
              className="bg-muted/40 hover:bg-accent/60 focus-visible:ring-ring flex min-w-0 cursor-pointer flex-col gap-1.5 rounded-md p-3 text-left outline-none focus-visible:ring-2"
            >
              <div className="flex items-baseline justify-between gap-2">
                <span className="text-label font-semibold">{q.label}</span>
                <span className="text-muted-foreground text-meta">
                  {monthLabel(q.start, 'MMM')}–{monthLabel(q.end, 'MMM yyyy')}
                </span>
              </div>
              {q.pct === null ? (
                <p className="text-label py-1">No target set</p>
              ) : (
                <p className="text-2xl leading-tight font-semibold tabular-nums">{q.pct}%</p>
              )}
              <div className="bg-muted h-2 overflow-hidden rounded-full">
                {q.pct !== null && band && (
                  <div className="h-full rounded-full" style={{ width: `${Math.min(100, Math.max(q.pct, 1))}%`, background: toneVar(band.tone) }} />
                )}
              </div>
              {band && (
                <span className="text-meta flex items-center gap-1">
                  <band.Icon className="size-3.5" style={{ color: toneVar(band.tone) }} aria-hidden />
                  {band.label}
                </span>
              )}
              <span className="text-muted-foreground text-meta">
                {basisText(q)}: {compactUsd(q.value)}
                {q.target !== null && ` of ${compactUsd(q.target)}`}
              </span>
            </button>
          )
        })}
      </div>
      {targetsNote && <p className="text-muted-foreground text-meta">{targetsNote}</p>}
    </div>
  )
}
