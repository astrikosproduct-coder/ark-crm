import { AlertTriangleIcon } from 'lucide-react'

import { Badge } from '@/components/ui/badge'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { date as fmtDate } from '@/lib/format'
import { daysRemainingText, type ExclusivityState, type RegistrationState } from '@/lib/partners'
import { cn } from '@/lib/utils'

/**
 * Active / Expiring / Expired / Superseded, derived from the exclusivity dates.
 *
 * The colour follows the derived state, not registration_status, because the
 * two can disagree — see registrationState(). When they do, the chip carries a
 * warning triangle and the tooltip says which way.
 */
const STATE_STYLE: Record<ExclusivityState, string> = {
  active: 'border-emerald-500/40 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300',
  expiring: 'border-amber-500/40 bg-amber-500/10 text-amber-700 dark:text-amber-300',
  expired: 'border-rose-500/40 bg-rose-500/10 text-rose-700 dark:text-rose-300',
  superseded: 'border-slate-500/40 bg-slate-500/10 text-slate-700 dark:text-slate-300',
  rejected: 'border-slate-500/40 bg-slate-500/10 text-slate-700 dark:text-slate-300',
  unacknowledged: 'border-sky-500/40 bg-sky-500/10 text-sky-700 dark:text-sky-300',
}

export function RegistrationStatusChip({
  state,
  showDays = false,
  className,
}: {
  state: RegistrationState
  /** Append "· 12 days left". Used in the page header, not in a list cell. */
  showDays?: boolean
  className?: string
}) {
  const disagrees = state.storedStatusDisagrees

  const chip = (
    <Badge variant="outline" className={cn('gap-1', STATE_STYLE[state.state], className)}>
      {disagrees && <AlertTriangleIcon className="size-3" />}
      {state.label}
      {showDays && state.daysRemaining !== null && ` · ${daysRemainingText(state)}`}
    </Badge>
  )

  const explain = disagrees
    ? `Derived from the dates: ${disagrees}. Nothing in the register expires a registration — see Spec Health.`
    : state.expiry
      ? `Exclusivity to ${fmtDate(state.expiry)} · ${daysRemainingText(state)}`
      : state.ackDueBy
        ? `Acknowledgement due by ${fmtDate(state.ackDueBy)}`
        : null

  if (!explain) return chip

  return (
    <Tooltip>
      <TooltipTrigger asChild>{chip}</TooltipTrigger>
      <TooltipContent className="max-w-xs">{explain}</TooltipContent>
    </Tooltip>
  )
}
