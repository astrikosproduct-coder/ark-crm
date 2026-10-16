import type { ReactNode } from 'react'
import { AlertTriangleIcon } from 'lucide-react'

import { cn } from '@/lib/utils'

/**
 * One Kanban card, the same shape on Leads, Opportunities and Deals (UX
 * roadmap, 17 Sep 2026): what a reader needs to pick a card out of a column,
 * and nothing they would have to open it for anyway.
 *
 *   Name, up to two lines              [mark]
 *   End Client
 *   Partner
 *   Value                      Probability / Go-Live
 *   ────────────────────────────────────────────
 *   Owner name                            ⚠ 42d
 *
 * ROOMIER, AND NOTHING CUT (Release 1.2, 15 Oct 2026): the name wraps to two
 * lines and each company has a line of its own, so a reader sees the words
 * rather than an ellipsis; the owner sits in a footer under a hairline. The
 * footer only draws when there is an owner or a warning.
 *
 * NO INITIALS DISC (18 Sep 2026). The owner's name used to sit behind a small
 * round badge of their initials. On a board of twenty cards that is twenty
 * coloured circles competing with the names beside them, and the name was
 * already there and already legible — the badge added a second way to say the
 * same thing and a first way to get it wrong (one initial for a mononym, two
 * for a double-barrelled surname).
 */
export function PipelineCard({
  name,
  clients,
  value,
  aside,
  asideTitle,
  owner,
  staleDays,
  mark,
}: {
  name: string
  /**
   * The End Client, then the Partner — one line each (Release 1.2: a shared
   * "A · B" line was cut off at the card's width). Empty ones are left out.
   */
  clients: (string | null | undefined)[]
  value: ReactNode
  aside: ReactNode
  asideTitle?: string
  owner: string | null | undefined
  /** Days since the last update, when it is past the staleness line. */
  staleDays: number | null
  /** A small mark after the name — the Low Hanging / Top 10 flag. */
  mark?: ReactNode
}) {
  const shown = clients.filter((c): c is string => Boolean(c))
  return (
    <>
      <div className="flex items-start justify-between gap-2">
        {/* Up to two lines, not one cut short; the whole name on hover. */}
        <p className="min-w-0 font-semibold leading-snug line-clamp-2 break-words" title={name}>
          {name}
        </p>
        {mark && <span className="shrink-0 pt-0.5">{mark}</span>}
      </div>
      <div className="text-muted-foreground mt-1.5 space-y-0.5 text-xs">
        {shown.length ? (
          shown.map((client, i) => (
            <p key={i} className="truncate" title={client}>
              {client}
            </p>
          ))
        ) : (
          <p>—</p>
        )}
      </div>
      <div className="mt-2.5 flex items-center justify-between gap-2 text-sm">
        <span className="font-medium">{value}</span>
        <span className="text-muted-foreground text-xs tabular-nums" title={asideTitle}>
          {aside}
        </span>
      </div>
      {(owner || staleDays !== null) && (
        <div className="border-border text-muted-foreground mt-2.5 flex items-center justify-between gap-2 border-t pt-2 text-xs">
          {owner ? (
            <span className="min-w-0 truncate" title={owner}>
              {owner}
            </span>
          ) : (
            <span />
          )}
          {staleDays !== null && (
            <span
              className={cn('flex shrink-0 items-center gap-1 text-amber-700 dark:text-amber-400')}
              title={`No update for ${staleDays} days`}
            >
              <AlertTriangleIcon className="size-3" />
              {staleDays}d
            </span>
          )}
        </div>
      )}
    </>
  )
}
