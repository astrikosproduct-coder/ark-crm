import { compactUsd } from '@/components/dashboard/format'
import type { SeriesTone, TileConfig } from '@/components/dashboard/config'
import { toneVar } from '@/components/dashboard/config'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'

export interface ColumnDatum {
  key: string
  label: string
  /** Null is a GAP — nothing drawn, never a zero-height column. */
  value: number | null
  tone: SeriesTone
  tooltip: string[]
}

/** Plot height in px. */
const PLOT_PX = 170

/**
 * Vertical columns over an ordered axis — months. One series, one axis: the
 * value is the column, the count is in the tooltip. A null value leaves its
 * slot empty and says why on hover, so a missing month never reads as $0.
 */
export function ColumnChart({
  config,
  columns,
  onSelect,
}: {
  config: TileConfig
  columns: ColumnDatum[]
  onSelect?: (column: ColumnDatum) => void
}) {
  const max = Math.max(0, ...columns.map((c) => c.value ?? 0))
  const clickable = Boolean(onSelect) && !config.noDrill
  const grid = { gridTemplateColumns: `repeat(${columns.length}, minmax(2.75rem, 1fr))` }

  return (
    <div className="flex gap-2">
      {/* The value axis: top and middle gridline labels, in text ink. */}
      <div className="text-muted-foreground text-meta flex flex-col justify-between pb-5 text-right tabular-nums" style={{ height: PLOT_PX + 20 }}>
        <span>{compactUsd(max)}</span>
        <span>{compactUsd(max / 2)}</span>
        <span>$0</span>
      </div>
      <div className="min-w-0 flex-1 overflow-x-auto">
        <div className="relative" style={{ height: PLOT_PX }}>
          <div className="border-border pointer-events-none absolute inset-x-0 top-0 border-t border-dashed" />
          <div className="border-border pointer-events-none absolute inset-x-0 top-1/2 border-t border-dashed" />
          <div className="border-border absolute inset-0 grid items-end gap-1 border-b" style={grid}>
            {columns.map((c) => {
              const gap = c.value === null
              return (
                <Tooltip key={c.key}>
                  <TooltipTrigger asChild>
                    <button
                      type="button"
                      aria-disabled={!clickable || gap}
                      onClick={() => clickable && !gap && onSelect?.(c)}
                      aria-label={c.tooltip.join(', ')}
                      className="hover:bg-accent/60 focus-visible:ring-ring flex h-full items-end justify-center rounded-t outline-none focus-visible:ring-2 aria-disabled:cursor-default cursor-pointer"
                    >
                      {!gap && (c.value ?? 0) > 0 && (
                        <span
                          className="w-7 rounded-t-[4px]"
                          style={{ height: Math.max(2, ((c.value ?? 0) / (max || 1)) * PLOT_PX), background: toneVar(c.tone) }}
                        />
                      )}
                    </button>
                  </TooltipTrigger>
                  <TooltipContent side="top">
                    {c.tooltip.map((line, i) => (
                      <div key={i} className={i === 0 ? 'font-semibold' : undefined}>
                        {line}
                      </div>
                    ))}
                    {clickable && !gap && <div className="mt-0.5 opacity-80">Click to list the records</div>}
                  </TooltipContent>
                </Tooltip>
              )
            })}
          </div>
        </div>
        <div className="text-muted-foreground text-meta mt-1 grid gap-1 text-center" style={grid}>
          {columns.map((c) => (
            <span key={c.key} className="truncate" title={c.label}>
              {c.label}
            </span>
          ))}
        </div>
      </div>
    </div>
  )
}
