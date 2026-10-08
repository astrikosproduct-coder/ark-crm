import type { TileConfig, SeriesTone } from '@/components/dashboard/config'
import { toneVar } from '@/components/dashboard/config'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'

export interface BarDatum {
  key: string
  label: string
  /** Drives the bar's length, relative to the longest row. */
  value: number
  /** Printed at the end of the row. */
  display: string
  tone: SeriesTone
  /** The hover / focus readout, first line emphasised — it carries the full label. */
  tooltip: string[]
  /** A heading drawn above this row, to band rows (Leads / Opportunities / Deals). */
  group?: string
}

/**
 * Horizontal bars, one per row: label, bar, value. Horizontal because stage
 * names, partners and loss reasons are long; the label column has a fixed
 * width and truncates, so a long name never wraps into the plot — the tooltip
 * carries it whole. The whole row is the hover, focus and click target.
 */
export function BarChart({
  config,
  rows,
  onSelect,
}: {
  config: TileConfig
  rows: BarDatum[]
  onSelect?: (row: BarDatum) => void
}) {
  const max = Math.max(0, ...rows.map((r) => r.value))
  const clickable = Boolean(onSelect) && !config.noDrill

  return (
    <div className="space-y-0.5" role="list" aria-label={config.title}>
      {rows.map((row) => {
        const pct = max > 0 ? (row.value / max) * 100 : 0
        return (
          <div key={row.key} role="listitem">
            {row.group && <div className="text-muted-foreground text-meta px-1 pt-2 pb-0.5 font-medium">{row.group}</div>}
            <Tooltip>
              <TooltipTrigger asChild>
                <button
                  type="button"
                  aria-disabled={!clickable}
                  onClick={() => clickable && onSelect?.(row)}
                  aria-label={row.tooltip.join(', ')}
                  className="hover:bg-accent/60 focus-visible:ring-ring grid w-full grid-cols-[minmax(0,11rem)_1fr_auto] items-center gap-3 rounded px-1 py-1 text-left outline-none focus-visible:ring-2 cursor-pointer aria-disabled:cursor-default"
                >
                  <span className="text-label truncate">{row.label}</span>
                  <span className="relative h-3">
                    {row.value > 0 && (
                      <span
                        className="absolute inset-y-0 left-0 rounded-r-[4px]"
                        style={{ width: `max(${pct}%, 2px)`, background: toneVar(row.tone) }}
                      />
                    )}
                  </span>
                  <span className="text-label text-right whitespace-nowrap tabular-nums">{row.display}</span>
                </button>
              </TooltipTrigger>
              <TooltipContent side="top">
                {row.tooltip.map((line, i) => (
                  <div key={i} className={i === 0 ? 'font-semibold' : undefined}>
                    {line}
                  </div>
                ))}
                {clickable && <div className="mt-0.5 opacity-80">Click to list the records</div>}
              </TooltipContent>
            </Tooltip>
          </div>
        )
      })}
    </div>
  )
}
