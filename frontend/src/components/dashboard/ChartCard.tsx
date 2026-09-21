import { useState, type ReactNode } from 'react'
import { ChartColumnIcon, InfoIcon, Table2Icon } from 'lucide-react'

import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { cn } from '@/lib/utils'

/** A chart's table twin — the same numbers, already formatted, readable without hovering. */
export interface TableView {
  columns: string[]
  rows: string[][]
}

/**
 * One dashboard component: a surface with a title, its definition behind an ⓘ,
 * and a toggle between the chart and its table. Every chart gets the table
 * view — a tooltip is never the only way to read a value.
 *
 * THE DEFINITION MOVED BEHIND THE ⓘ (18 Sep 2026)
 * -----------------------------------------------
 * Every card carried its scope as a prose subtitle, averaging about 110
 * characters — "Live primary pursuits by the stage they are in now, in USD,
 * expected to close in the selected period. The number after the value is the
 * record count." Eight of those, plus a page-level scope paragraph, put roughly
 * 300 words of methodology above the data on the one screen where management
 * spends its time.
 *
 * Not one word of it was wrong, and none of it has been softened: every
 * sentence is still here, verbatim, one click away. What changed is that
 * something needed 2% of the time stopped being read 100% of the time. A
 * number whose definition is one click away is still an honest number; a
 * number nobody reaches because its footnote came first is not.
 *
 * `subtitle` survives for the rare genuinely short line. Anything that reads
 * like a sentence belongs in `info`.
 */
export function ChartCard({
  title,
  subtitle,
  info,
  table,
  className,
  children,
}: {
  title: string
  /** A few words at most. A sentence belongs in `info`. */
  subtitle?: ReactNode
  /** What this widget counts and what it leaves out — behind the ⓘ. */
  info?: ReactNode
  table?: TableView
  className?: string
  children: ReactNode
}) {
  const [asTable, setAsTable] = useState(false)

  return (
    <section className={cn('bg-card text-card-foreground flex min-w-0 flex-col rounded-lg p-4 shadow-sm', className)}>
      <header className="mb-3 flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h2 className="text-section flex items-center gap-1.5 font-semibold">
            <span className="min-w-0 truncate">{title}</span>
            {info && (
              <Popover>
                <PopoverTrigger
                  type="button"
                  aria-label={`What ${title} counts`}
                  className="text-muted-foreground hover:text-foreground shrink-0"
                >
                  <InfoIcon className="size-3.5" />
                </PopoverTrigger>
                <PopoverContent align="start" className="text-meta w-80 leading-relaxed font-normal">
                  {info}
                </PopoverContent>
              </Popover>
            )}
          </h2>
          {subtitle && <p className="text-muted-foreground text-meta mt-0.5">{subtitle}</p>}
        </div>
        {table && (
          <button
            type="button"
            onClick={() => setAsTable((v) => !v)}
            aria-pressed={asTable}
            aria-label={asTable ? 'Show as chart' : 'Show as table'}
            title={asTable ? 'Show as chart' : 'Show as table'}
            className="text-muted-foreground hover:bg-accent hover:text-foreground flex size-7 shrink-0 items-center justify-center rounded-md transition-colors"
          >
            {asTable ? <ChartColumnIcon className="size-4" /> : <Table2Icon className="size-4" />}
          </button>
        )}
      </header>
      {asTable && table ? <DataTable {...table} /> : children}
    </section>
  )
}

function DataTable({ columns, rows }: TableView) {
  if (rows.length === 0) return <EmptyChart>Nothing to show.</EmptyChart>
  return (
    <div className="overflow-x-auto">
      <table className="text-label w-full tabular-nums">
        <thead>
          <tr className="text-muted-foreground border-border border-b text-left">
            {columns.map((c, i) => (
              <th key={c} className={cn('py-1.5 pr-3 font-medium whitespace-nowrap', i > 0 && 'text-right')}>
                {c}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, r) => (
            <tr key={r} className="border-border border-b last:border-0">
              {row.map((cell, i) => (
                <td key={i} className={cn('py-1.5 pr-3', i > 0 && 'text-right whitespace-nowrap')}>
                  {cell}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export function EmptyChart({ children }: { children: ReactNode }) {
  return <p className="text-muted-foreground text-label py-8 text-center">{children}</p>
}
