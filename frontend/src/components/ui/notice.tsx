import type { ReactNode } from 'react'

import { refusalOf, type RefusalOptions } from '@/lib/errors'
import { cn } from '@/lib/utils'

/**
 * The copy rules for every dialog and message (CLAUDE.md, "Dialog and message
 * copy"): one short lead sentence, then bullets — one idea each. Readable is
 * not roomy: bullets sit tight under the lead, at the text size of the
 * surrounding dialog, with no extra padding added for them.
 */

const TONE = {
  plain: '',
  muted: 'text-muted-foreground',
  error: 'text-destructive',
  warning: 'text-amber-700 dark:text-amber-400',
  info: 'text-sky-700 dark:text-sky-400',
} as const

export type NoticeTone = keyof typeof TONE

/** A bullet list with the dialog's own text size. Renders nothing when empty. */
export function Bullets({ items, className }: { items: ReactNode[]; className?: string }) {
  const shown = items.filter((item) => item !== null && item !== undefined && item !== false && item !== '')
  if (shown.length === 0) return null
  return (
    <ul className={cn('list-disc space-y-0.5 pl-4 marker:text-current/60', className)}>
      {shown.map((item, i) => (
        <li key={i}>{item}</li>
      ))}
    </ul>
  )
}

/** A lead sentence and its bullets, in one tone. */
export function Notice({
  lead,
  bullets = [],
  tone = 'plain',
  boxed = false,
  className,
  children,
}: {
  lead?: ReactNode
  bullets?: ReactNode[]
  tone?: NoticeTone
  /** A tinted box, for a notice that sits among form controls. */
  boxed?: boolean
  className?: string
  children?: ReactNode
}) {
  return (
    <div
      className={cn(
        'space-y-0.5 text-sm',
        TONE[tone],
        boxed && 'rounded-md border px-3 py-1.5',
        boxed && tone === 'warning' && 'border-amber-500/40 bg-amber-500/10',
        boxed && tone === 'info' && 'border-sky-500/40 bg-sky-500/10',
        boxed && tone === 'error' && 'border-destructive/40 bg-destructive/5',
        className
      )}
    >
      {lead && <p>{lead}</p>}
      <Bullets items={bullets} />
      {children}
    </div>
  )
}

/**
 * A failed request, as the server explained it: its sentence and its bullets.
 * `suffix` adds one more bullet of the screen's own — "Nothing was changed."
 */
export function ErrorNotice({
  error,
  suffix,
  className,
  ...options
}: { error: unknown; suffix?: string; className?: string } & RefusalOptions) {
  if (!error) return null
  const refusal = refusalOf(error, options)
  return (
    <Notice
      tone="error"
      lead={refusal.message}
      bullets={suffix ? [...refusal.details, suffix] : refusal.details}
      className={className}
    />
  )
}
