import type { ReactNode } from 'react'
import { AlertTriangleIcon, ArrowDownRightIcon, ArrowRightIcon, ArrowUpRightIcon } from 'lucide-react'

import { cn } from '@/lib/utils'

/** What a number did against the period before it. */
export interface Delta {
  /** This period's figure and the previous one's, in the same unit. */
  now: number
  before: number
  /** What to call the period compared against — "Q1 FY2026-27", or null. */
  label: string | null
  /**
   * Whether going UP is good news. True for pipeline, false for Closed Lost —
   * without it a tile would colour a worsening number green.
   */
  upIsGood?: boolean
}

/**
 * One headline number: a label, the value, how it moved, and at most one
 * supporting line.
 *
 * ONE LINE, NOT THREE (18 Sep 2026). These tiles carried up to three lines of
 * scope each — the record count, then the Leads figure, then the Opportunities
 * figure — so six tiles put roughly twenty lines of small text above the fold
 * and every number had to compete with its own footnotes. A breakdown is a
 * chart, not a stack of sentences: the split now draws as a bar, and the scope
 * moved behind the page's ⓘ where it is read when it is wanted.
 *
 * A caveat names what someone can go and DO ("4 pursuits still need a value"),
 * never how the sum treated them ("counted at $0"). Our arithmetic is not the
 * reader's problem; their missing data is.
 */
export function KpiTile({
  label,
  value,
  line,
  delta,
  caveat,
  children,
}: {
  label: string
  value: string
  /** At most one. Anything longer belongs behind the page's ⓘ. */
  line?: ReactNode
  delta?: Delta | null
  caveat?: string | null
  /** A small visual under the number — the pipeline split bar, say. */
  children?: ReactNode
}) {
  return (
    <section className="bg-card text-card-foreground flex min-w-0 flex-col rounded-lg p-4 shadow-sm">
      <h2 className="text-muted-foreground text-label">{label}</h2>
      <div className="mt-1 flex flex-wrap items-baseline gap-x-2">
        <p className="text-2xl leading-tight font-semibold break-words">{value}</p>
        {delta && <DeltaMark delta={delta} />}
      </div>
      {children}
      {line && <p className="text-muted-foreground text-meta mt-1">{line}</p>}
      {caveat && (
        <p className="text-meta mt-2 flex items-start gap-1.5">
          <AlertTriangleIcon className="text-warning mt-px size-3.5 shrink-0" />
          <span>{caveat}</span>
        </p>
      )}
    </section>
  )
}

/**
 * "↗ 12% vs Q1 FY2026-27".
 *
 * THE CASE THAT NEEDS CARE is a previous period of zero. A percentage change
 * from nothing is not infinite and it is not 100% — it is undefined, and
 * printing either would be a confident lie on the one screen that cannot
 * afford one. So growth from zero reads "new", and zero to zero reads "no
 * change". Both are true sentences; neither pretends to be a ratio.
 */
function DeltaMark({ delta }: { delta: Delta }) {
  const { now, before, label, upIsGood = true } = delta
  const against = label ? `vs ${label}` : 'vs the period before'

  if (before === 0) {
    return (
      <span className="text-muted-foreground text-xs">
        {now === 0 ? 'no change' : 'new'} {against}
      </span>
    )
  }

  const change = (now - before) / Math.abs(before)
  const pct = Math.abs(Math.round(change * 100))
  if (pct === 0) {
    return (
      <span className="text-muted-foreground text-xs">
        <ArrowRightIcon aria-hidden className="mr-0.5 inline size-3" />
        level {against}
      </span>
    )
  }

  const up = change > 0
  const good = up === upIsGood
  const Icon = up ? ArrowUpRightIcon : ArrowDownRightIcon
  return (
    <span
      className={cn('text-xs font-medium', good ? 'text-success' : 'text-destructive')}
      title={`${pct}% ${up ? 'higher' : 'lower'} than ${label ?? 'the period before'}`}
    >
      <Icon aria-hidden className="mr-0.5 inline size-3" />
      {pct}% <span className="text-muted-foreground font-normal">{against}</span>
    </span>
  )
}
