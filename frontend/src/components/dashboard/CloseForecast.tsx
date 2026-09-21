import { EmptyChart } from '@/components/dashboard/ChartCard'
import { monthLabel, seriesLabel } from '@/components/dashboard/format'
import type { Bucket, DashboardData, PipelineModule } from '@/components/dashboard/types'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { usd } from '@/lib/revenue'

/** Plot height in px — segments are sized in px so the 2px gaps never overflow it. */
const PLOT_PX = 160
const GAP_PX = 2

/**
 * Stack order, baseline up: the firmest money sits on the axis. The legend
 * lists the same series top-down, matching what the eye meets first. Colours
 * are fixed per module, never per rank — see index.css --chart-*.
 */
const STACK: { module: PipelineModule; className: string }[] = [
  { module: 'deals', className: 'bg-chart-deals' },
  { module: 'opportunities', className: 'bg-chart-opportunities' },
  { module: 'leads', className: 'bg-chart-leads' },
]

function records(n: number): string {
  return `${n} record${n === 1 ? '' : 's'}`
}

/**
 * Revenue expected to close each month, stacked by where the pursuit is:
 * Estimated Value (Leads), Opportunity Revenue (Opportunities), Actual Revenue
 * (Deals). One axis, one unit. Weighted value is in the readout and the table.
 */
export function CloseForecast({
  forecast,
  labels,
  ranged,
}: {
  forecast: DashboardData['forecast']
  labels: DashboardData['revenue_labels']
  ranged: boolean
}) {
  const { months } = forecast
  const max = Math.max(0, ...months.map((m) => m.usd))
  const hasAny = months.some((m) => m.count > 0)
  const columns = { gridTemplateColumns: `repeat(${months.length}, minmax(2.25rem, 1fr))` }
  const last = months[months.length - 1]

  return (
    <div className="flex flex-col gap-3">
      <div className="text-muted-foreground text-meta flex flex-wrap gap-x-4 gap-y-1">
        {[...STACK].reverse().map((s) => (
          <span key={s.module} className="flex items-center gap-1.5">
            <span className={`size-2.5 rounded-[2px] ${s.className}`} />
            {seriesLabel(labels, s.module)}
          </span>
        ))}
      </div>

      {hasAny ? (
        <div className="overflow-x-auto">
          <div className="border-border grid items-end gap-1 border-b" style={{ ...columns, height: PLOT_PX }}>
            {months.map((m) => {
              const parts = STACK.filter((s) => m.by_module[s.module].usd > 0)
              const room = max > 0 ? PLOT_PX - GAP_PX * Math.max(0, parts.length - 1) : 0
              return (
                <Tooltip key={m.month}>
                  <TooltipTrigger asChild>
                    <div
                      tabIndex={0}
                      className="hover:bg-accent/60 focus-visible:ring-ring flex h-full flex-col-reverse items-center rounded-t outline-none focus-visible:ring-2"
                      style={{ gap: GAP_PX }}
                    >
                      {parts.map((s, i) => (
                        <span
                          key={s.module}
                          className={`w-6 ${s.className} ${i === parts.length - 1 ? 'rounded-t-[4px]' : ''}`}
                          style={{ height: Math.max(2, (m.by_module[s.module].usd / max) * room) }}
                        />
                      ))}
                    </div>
                  </TooltipTrigger>
                  <TooltipContent side="top">
                    <div className="font-semibold">{monthLabel(m.month, 'MMM yyyy')}</div>
                    {[...STACK].reverse().map((s) => (
                      <div key={s.module}>
                        {seriesLabel(labels, s.module)}: {usd(m.by_module[s.module].usd)}
                      </div>
                    ))}
                    <div>
                      Total {usd(m.usd)} · {records(m.count)}
                    </div>
                    <div>Weighted {usd(m.weighted_usd)}</div>
                  </TooltipContent>
                </Tooltip>
              )
            })}
          </div>
          <div className="text-muted-foreground text-meta mt-1 grid gap-1 text-center tabular-nums" style={columns}>
            {months.map((m) => (
              <span key={m.month}>{monthLabel(m.month, 'MMM yy')}</span>
            ))}
          </div>
        </div>
      ) : (
        <EmptyChart>
          {ranged ? 'Nothing is expected to close in this period.' : 'Nothing is expected to close in the next six months.'}
        </EmptyChart>
      )}

      {forecast.overdue && forecast.later && forecast.undated && (
        <dl className="text-meta grid gap-x-4 gap-y-1 sm:grid-cols-3">
          <Note label="Close month already passed" bucket={forecast.overdue} />
          <Note label={last ? `After ${monthLabel(last.month, 'MMM yyyy')}` : 'Later'} bucket={forecast.later} />
          <Note label="No close month" bucket={forecast.undated} />
        </dl>
      )}
    </div>
  )
}

function Note({ label, bucket }: { label: string; bucket: Bucket }) {
  return (
    <div>
      <dt className="text-muted-foreground">{label}</dt>
      <dd className="tabular-nums">
        {usd(bucket.usd)} · {records(bucket.count)}
      </dd>
    </div>
  )
}
