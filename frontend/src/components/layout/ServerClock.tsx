import { ClockIcon } from 'lucide-react'

import { useServerClock } from '@/lib/serverClock'
import { companyClockTime, companyDate } from '@/lib/time'

/**
 * The server's date and time, running, in company time — "28 Sep 2026 ·
 * 06:18:52 PM IST". The backend's clock, never the laptop's: see
 * lib/serverClock.ts. Shows nothing until the first reading arrives, rather
 * than a laptop time that would then jump.
 */
export function ServerClock() {
  const clock = useServerClock()
  if (!clock) return null
  const instant = new Date(clock.now)
  return (
    <div
      className="text-muted-foreground hidden items-center gap-1.5 px-2 text-sm whitespace-nowrap tabular-nums md:flex"
      title="Server time — what every record is stamped with"
      aria-label={`Server time ${companyDate(instant)} ${companyClockTime(clock.now)} ${clock.label}`}
    >
      <ClockIcon className="size-3.5" aria-hidden />
      <span>{companyDate(instant)}</span>
      <span aria-hidden>·</span>
      <span>
        {companyClockTime(clock.now)} {clock.label}
      </span>
    </div>
  )
}
