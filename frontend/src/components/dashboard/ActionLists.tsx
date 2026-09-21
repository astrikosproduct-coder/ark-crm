import { Link } from 'react-router-dom'
import { AlertTriangleIcon } from 'lucide-react'

import { ChartCard, EmptyChart } from '@/components/dashboard/ChartCard'
import type { DashboardData, DashboardItem, DueItem } from '@/components/dashboard/types'
import { date } from '@/lib/format'
import { moduleFor } from '@/lib/modules'
import { usd } from '@/lib/revenue'
import { fieldOf, optionsFor } from '@/lib/spec'

const KIND_LABEL: Record<DueItem['kind'], string> = {
  milestone: 'Next milestone',
  submission: 'Bid submission deadline',
  payment: 'Payment milestone',
  guarantee: 'Guarantee expires',
}

/** Where each kind's detail value is a picklist key, the field that names its picklist. */
const KIND_DETAIL_FIELD: Partial<Record<DueItem['kind'], [string, string]>> = {
  submission: ['opportunities', 'rfp_type'],
  payment: ['administration', 'milestone'],
  guarantee: ['deals', 'guarantee_—_type'],
}

function detailOf(item: DueItem): string {
  if (!item.detail) return ''
  const ref = KIND_DETAIL_FIELD[item.kind]
  if (!ref) return item.detail
  const picklist = fieldOf(ref[0], ref[1])?.picklist
  return optionsFor(picklist).find((o) => o.key === item.detail)?.label ?? item.detail
}

function RecordCell({ item }: { item: DashboardItem }) {
  const module = moduleFor(item.module)?.label ?? item.module
  return (
    <div className="min-w-0">
      <Link to={`/${item.module}/${item.record_id}`} className="text-link block truncate hover:underline">
        {item.name}
      </Link>
      <div className="text-muted-foreground text-meta truncate">
        {module} · {item.record_id}
        {item.stage !== null && ` · ${item.stage} ${item.stage_name ?? ''}`}
      </div>
    </div>
  )
}

function value(item: DashboardItem): string {
  return item.usd === null ? '—' : usd(item.usd)
}

function shown(total: number, count: number): string | null {
  return total > count ? `Showing ${count} of ${total}.` : null
}

export function DueList({
  due,
  windowDays,
  range,
}: {
  due: DashboardData['due']
  windowDays: number
  /** The selected period as text, or null for the default window. */
  range: string | null
}) {
  return (
    <ChartCard
      title={range ? `Due ${range}` : `Due in the next ${windowDays} days`}
      info={
        range
          ? 'Next milestones, bid deadlines, payment milestones and guarantee expiries on live records, by due date. Earliest first.'
          : 'Next milestones, bid deadlines, payment milestones and guarantee expiries on live records. Overdue first.'
      }
    >
      {due.items.length === 0 ? (
        <EmptyChart>Nothing due.</EmptyChart>
      ) : (
        <div className="overflow-x-auto">
          <table className="text-label w-full">
            <thead>
              <tr className="text-muted-foreground border-border border-b text-left">
                <th className="py-1.5 pr-3 font-medium">Date</th>
                <th className="py-1.5 pr-3 font-medium">Record</th>
                <th className="py-1.5 pr-3 font-medium">What</th>
                <th className="py-1.5 text-right font-medium">Value</th>
              </tr>
            </thead>
            <tbody>
              {due.items.map((item, i) => (
                <tr key={`${item.record_id}-${item.kind}-${i}`} className="border-border border-b align-top last:border-0">
                  <td className="py-1.5 pr-3 whitespace-nowrap tabular-nums">
                    {date(item.date)}
                    {item.overdue && (
                      <span className="text-meta mt-0.5 flex items-center gap-1">
                        <AlertTriangleIcon className="text-warning size-3" />
                        Overdue
                      </span>
                    )}
                  </td>
                  <td className="max-w-56 py-1.5 pr-3">
                    <RecordCell item={item} />
                  </td>
                  <td className="py-1.5 pr-3">
                    {KIND_LABEL[item.kind]}
                    {detailOf(item) && <div className="text-muted-foreground text-meta">{detailOf(item)}</div>}
                  </td>
                  <td className="py-1.5 text-right whitespace-nowrap tabular-nums">{value(item)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {shown(due.total, due.items.length) && (
        <p className="text-muted-foreground text-meta mt-2">{shown(due.total, due.items.length)}</p>
      )}
    </ChartCard>
  )
}

export function AtRiskList({ atRisk, stuckAfterDays }: { atRisk: DashboardData['at_risk']; stuckAfterDays: number }) {
  return (
    <ChartCard
      title="Red and stuck"
      info={`Live records rated Red, or in the same stage for more than ${stuckAfterDays} days. Largest first.`}
    >
      {atRisk.items.length === 0 ? (
        <EmptyChart>Nothing is Red or stuck.</EmptyChart>
      ) : (
        <div className="overflow-x-auto">
          <table className="text-label w-full">
            <thead>
              <tr className="text-muted-foreground border-border border-b text-left">
                <th className="py-1.5 pr-3 font-medium">Record</th>
                <th className="py-1.5 pr-3 font-medium">BD Owner</th>
                <th className="py-1.5 text-right font-medium">Value</th>
              </tr>
            </thead>
            <tbody>
              {atRisk.items.map((item) => (
                <tr key={`${item.module}-${item.record_id}`} className="border-border border-b align-top last:border-0">
                  <td className="max-w-56 py-1.5 pr-3">
                    <RecordCell item={item} />
                  </td>
                  <td className="py-1.5 pr-3">{item.owner ?? '—'}</td>
                  <td className="py-1.5 text-right whitespace-nowrap tabular-nums">{value(item)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {shown(atRisk.total, atRisk.items.length) && (
        <p className="text-muted-foreground text-meta mt-2">{shown(atRisk.total, atRisk.items.length)}</p>
      )}
    </ChartCard>
  )
}
