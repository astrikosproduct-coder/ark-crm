import { EyeOffIcon } from 'lucide-react'

import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { labelForValue, optionsFor } from '@/lib/spec'
import { cn } from '@/lib/utils'

/**
 * The contact's role, read as text.
 *
 * The codes are not written here — they are the leading token of each key in
 * the `contacts__contact_role` picklist (DECM_DECISION_MAKER → DECM), which is
 * how CLAUDE.md and the register both refer to them. A sixth role added to the
 * picklist appears immediately rather than disappearing.
 *
 * There used to be a colour per role, on a tinted pill. Gone: a role is a
 * field value, and it now reads like every other one.
 */
const PICKLIST = 'contacts__contact_role'

/** The short code of a contact_role value, e.g. DECM_DECISION_MAKER → DECM. */
export function roleCodeOf(value: unknown): string {
  if (typeof value !== 'string' || !value) return ''
  const hit = optionsFor(PICKLIST).find((o) => o.key === value || o.label === value)
  return (hit?.key ?? value).split('_')[0].toUpperCase()
}

/** Roles whose contacts are treated as confidential intelligence sources. */
const CONFIDENTIAL_ROLE = 'INTEL'

export function isConfidentialContact(contact: Record<string, unknown>): boolean {
  return roleCodeOf(contact.contact_role) === CONFIDENTIAL_ROLE || contact.confidential === true
}

export function ContactRoleBadge({ value, className }: { value: unknown; className?: string }) {
  const code = roleCodeOf(value)
  if (!code) return <span className="text-muted-foreground">—</span>

  const label = labelForValue(PICKLIST, value)
  // Labels read "DECM Decision Maker" — the badge carries the code, the tooltip
  // carries the rest, so a column of five badges stays scannable.
  const rest = label.replace(new RegExp(`^${code}\\s*`, 'i'), '')

  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <span className={cn('whitespace-nowrap', className)}>{code}</span>
      </TooltipTrigger>
      <TooltipContent>{rest || label}</TooltipContent>
    </Tooltip>
  )
}

/**
 * Shown against any INTEL contact. The register ALSO carries a `confidential`
 * checkbox on contacts, marked System — two sources for one fact. Both are
 * honoured here and the duplication is flagged on the Spec Health page.
 */
export function ConfidentialChip({ className }: { className?: string }) {
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <span className={cn('inline-flex items-center gap-1 whitespace-nowrap', className)}>
          <EyeOffIcon className="size-3.5" />
          Confidential
        </span>
      </TooltipTrigger>
      <TooltipContent className="max-w-xs">
        Intel provider. Do not name this contact in anything that leaves Astrikos.
      </TooltipContent>
    </Tooltip>
  )
}
