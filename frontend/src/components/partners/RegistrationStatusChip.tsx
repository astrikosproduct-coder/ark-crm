import { AlertTriangleIcon } from 'lucide-react'

import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { date as fmtDate } from '@/lib/format'
import { daysRemainingText, type RegistrationState } from '@/lib/partners'
import { cn } from '@/lib/utils'

/**
 * Active / Expiring / Expired / Superseded, derived from the exclusivity dates.
 *
 * The state follows the dates, not registration_status, because the two can
 * disagree — see registrationState(). When they do, the text carries a warning
 * triangle and the tooltip says which way. There used to be a colour per state
 * on a tinted pill; it reads as plain text now, like every other value.
 */
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
    <span className={cn('inline-flex items-center gap-1 whitespace-nowrap', className)}>
      {disagrees && <AlertTriangleIcon className="size-3.5" />}
      {state.label}
      {showDays && state.daysRemaining !== null && ` · ${daysRemainingText(state)}`}
    </span>
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
