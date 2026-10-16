import { PRIORITY_ICONS } from '@/components/opportunities/priorityIcons'
import { priorityFlagOf } from '@/lib/priorityFlags'
import { cn } from '@/lib/utils'

/**
 * The mark for an Opportunity's priority pick — see priorityIcons.ts for which
 * icon means which.
 *
 * THE RANK IS THE MARK (18 Sep 2026)
 * ----------------------------------
 * This was a grey icon and "#3" in muted 12px text, which made the CEO's own
 * picks the quietest thing on a card — fainter than the client name, on records
 * the company has decided matter more than any other. The rank now draws as a
 * filled chip, because the NUMBER is the information and the icon is decoration
 * around it.
 *
 * ONE STYLE FOR EVERY RANK (Release 1.2, 15 Oct 2026). The top three drew
 * solid and the rest outlined, which read as two kinds of pick rather than an
 * order; every rank is now the same solid chip, and the number carries the order.
 *
 * NO HUE AT ALL — the chip is pure contrast (foreground on background), never
 * red, amber or green. Colour on these screens belongs to the Overall RAG
 * stripe and nothing else may borrow it; a coloured rank badge would have a
 * reader asking whether #1 was also somehow "green". Contrast says "important"
 * without entering that argument.
 */

export interface PriorityFlagMarkProps {
  row: Record<string, unknown> | undefined
  /**
   * `compact` — icon + the rank chip, for a kanban card or a list row, where
   * space is short and the icon has already been learnt.
   * `full` — icon + "Low Hanging" + the chip, for the record title, where there
   * is room and a first-time reader needs the words.
   */
  variant: 'compact' | 'full'
  className?: string
}

/** Renders nothing when the record holds no pick. */
export function PriorityFlagMark({ row, variant, className }: PriorityFlagMarkProps) {
  const held = priorityFlagOf(row)
  if (!held) return null

  const Icon = PRIORITY_ICONS[held.pick.flag]
  // The icon alone does not explain itself to someone new, so the full meaning
  // is always one hover away, and always read out by a screen reader.
  const meaning = held.rank === null ? held.pick.label : `${held.pick.label} · rank ${held.rank}`

  return (
    <span
      title={meaning}
      aria-label={meaning}
      className={cn('inline-flex shrink-0 items-center gap-1 text-xs whitespace-nowrap', className)}
    >
      {Icon && <Icon aria-hidden className="text-muted-foreground size-3.5" />}
      {variant === 'full' && <span className="text-muted-foreground font-normal">{held.pick.label}</span>}
      {held.rank !== null && (
        <span
          aria-hidden
          className={cn(
            'bg-foreground text-background inline-flex h-4 min-w-4 items-center justify-center rounded px-1 text-[11px] leading-none font-semibold tabular-nums'
          )}
        >
          {held.rank}
        </span>
      )}
    </span>
  )
}

/**
 * A fixed-width slot for list rows, so names stay in one column whether or not
 * the row holds a pick. Wide enough for the widest mark.
 *
 * It renders AFTER the name now, not before. Sitting in front, it pushed every
 * name in the list a fixed distance off the left edge — including the great
 * majority of rows holding no pick at all — so the column read as indented for
 * the benefit of at most fifteen records. A name starts where a name should
 * start, and the mark follows it.
 */
export function PriorityFlagSlot({ row }: { row: Record<string, unknown> }) {
  return (
    <span className="inline-block w-10 shrink-0 align-middle">
      <PriorityFlagMark row={row} variant="compact" />
    </span>
  )
}
