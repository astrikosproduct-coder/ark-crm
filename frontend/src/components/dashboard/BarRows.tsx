import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { cn } from '@/lib/utils'

/**
 * `chart` is the dashboard's one data hue. The three status tones are only for
 * a value that MEANS good / attention / bad (RAG) and always sit beside a text
 * label — the app's red and amber are too close to be told apart by colour
 * alone, which the dataviz validator confirmed.
 */
export type BarTone = 'chart' | 'success' | 'warning' | 'destructive' | 'muted'

const TONE: Record<BarTone, string> = {
  chart: 'bg-chart-strong',
  success: 'bg-success',
  warning: 'bg-warning',
  destructive: 'bg-destructive',
  muted: 'bg-muted-foreground/40',
}

export interface BarRow {
  key: string
  label: string
  /** Drives the bar's length, relative to the longest row. */
  value: number
  /** Printed at the end of the row. */
  display: string
  /** Muted context after the value — usually the record count. */
  note?: string
  tone?: BarTone
  /** The hover / focus readout, first line emphasised. */
  tooltip: string[]
  /** A heading drawn above this row, to band rows (Leads / Opportunities / Deals). */
  group?: string
}

/**
 * Horizontal bars, one per row: label, bar, value. Horizontal because stage
 * names and loss reasons are long, and a label beside its bar needs no legend.
 * The whole row is the hover and focus target, not just the painted bar.
 */
export function BarRows({ rows }: { rows: BarRow[] }) {
  const max = Math.max(0, ...rows.map((r) => r.value))

  return (
    <div className="space-y-0.5">
      {rows.map((row) => {
        const pct = max > 0 ? (row.value / max) * 100 : 0
        return (
          <div key={row.key}>
            {row.group && (
              <div className="text-muted-foreground text-meta px-1 pt-2 pb-0.5 font-medium">{row.group}</div>
            )}
            <Tooltip>
              <TooltipTrigger asChild>
                <div
                  tabIndex={0}
                  className="hover:bg-accent/60 focus-visible:ring-ring grid grid-cols-[minmax(0,9.5rem)_1fr_auto] items-center gap-3 rounded px-1 py-1 outline-none focus-visible:ring-2"
                >
                  <span className="text-label truncate">{row.label}</span>
                  <span className="relative h-3">
                    {row.value > 0 && (
                      <span
                        className={cn('absolute inset-y-0 left-0 rounded-r-[4px]', TONE[row.tone ?? 'chart'])}
                        style={{ width: `max(${pct}%, 2px)` }}
                      />
                    )}
                  </span>
                  <span className="text-label text-right whitespace-nowrap tabular-nums">
                    {row.display}
                    {row.note && <span className="text-muted-foreground"> · {row.note}</span>}
                  </span>
                </div>
              </TooltipTrigger>
              <TooltipContent side="top">
                {row.tooltip.map((line, i) => (
                  <div key={i} className={i === 0 ? 'font-semibold' : undefined}>
                    {line}
                  </div>
                ))}
              </TooltipContent>
            </Tooltip>
          </div>
        )
      })}
    </div>
  )
}
