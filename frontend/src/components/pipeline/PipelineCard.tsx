import type { ReactNode } from 'react'
import { AlertTriangleIcon } from 'lucide-react'

import { cn } from '@/lib/utils'

/**
 * One Kanban card, the same shape on Leads, Opportunities and Deals (UX
 * roadmap, 17 Sep 2026): what a reader needs to pick a card out of a column,
 * and nothing they would have to open it for anyway.
 *
 *   Name                               [mark]
 *   End Client
 *   Value                      Probability / Go-Live
 *   Owner name                            ⚠ 42d
 *
 * Three lines of information and a quiet footer — no taller than the card it
 * replaced. The footer only draws when there is an owner or a warning.
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
  client,
  value,
  aside,
  asideTitle,
  owner,
  staleDays,
  mark,
}: {
  name: string
  client: string | null | undefined
  value: ReactNode
  aside: ReactNode
  asideTitle?: string
  owner: string | null | undefined
  /** Days since the last update, when it is past the staleness line. */
  staleDays: number | null
  /** A small mark after the name — the Low Hanging / Top 10 flag. */
  mark?: ReactNode
}) {
  return (
    <>
      <div className="flex items-center justify-between gap-2">
        <p className="min-w-0 truncate font-medium">{name}</p>
        {mark}
      </div>
      <p className="text-muted-foreground truncate text-xs">{client || '—'}</p>
      <div className="mt-1 flex items-center justify-between gap-2 text-xs">
        {value}
        <span className="text-muted-foreground tabular-nums" title={asideTitle}>
          {aside}
        </span>
      </div>
      {(owner || staleDays !== null) && (
        <div className="text-muted-foreground mt-1 flex items-center justify-between gap-2 text-xs">
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

