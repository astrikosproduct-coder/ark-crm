import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { AlertTriangleIcon } from 'lucide-react'

import { EmptyChart } from '@/components/dashboard/ChartCard'
import { compactUsd, plural } from '@/components/dashboard/format'
import type { DashboardFilters, DrillRequest, DrillResult } from '@/components/dashboard/types'
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from '@/components/ui/sheet'
import { api } from '@/lib/api'
import { moduleFor } from '@/lib/modules'

/**
 * The records behind one bar, slice, point or meter — under the page's own
 * filters. The server groups them with the same code that drew the mark
 * (GET /api/dashboard/records), so the list always adds up to what was
 * clicked. A drawer, not a jump to a module list: a pipeline mark holds Leads
 * and Opportunities together, and no one list page shows both.
 */
export function RecordsSheet({
  request,
  filters,
  onClose,
}: {
  request: DrillRequest | null
  filters: DashboardFilters
  onClose: () => void
}) {
  const { data, isLoading, isError } = useQuery({
    queryKey: ['dashboard-records', request?.tile, request?.keys, filters],
    queryFn: async () =>
      (await api.get<DrillResult>('/dashboard/records', { params: { ...filters, tile: request!.tile, key: request!.keys } })).data,
    enabled: request !== null,
  })

  return (
    <Sheet open={request !== null} onOpenChange={(open) => !open && onClose()}>
      <SheetContent className="w-full max-w-lg overflow-y-auto sm:max-w-lg">
        <SheetHeader>
          <SheetTitle>{request?.title}</SheetTitle>
          <SheetDescription>
            {data ? `${plural(data.count, 'record')} · ${compactUsd(data.usd)} · weighted ${compactUsd(data.weighted_usd)}` : ' '}
          </SheetDescription>
        </SheetHeader>
        {isLoading && <EmptyChart>Loading the records…</EmptyChart>}
        {isError && <EmptyChart>The records could not be loaded. Close this and try again.</EmptyChart>}
        {data && data.items.length === 0 && <EmptyChart>No records sit behind this.</EmptyChart>}
        {data && data.items.length > 0 && (
          <table className="text-label w-full">
            <thead>
              <tr className="text-muted-foreground border-border border-b text-left">
                <th className="py-1.5 pr-3 font-medium">Record</th>
                <th className="py-1.5 pr-3 font-medium">BD Owner</th>
                <th className="py-1.5 text-right font-medium">Value</th>
              </tr>
            </thead>
            <tbody>
              {data.items.map((item) => (
                <tr key={`${item.module}-${item.record_id}`} className="border-border border-b align-top last:border-0">
                  <td className="max-w-64 py-1.5 pr-3">
                    <Link to={`/${item.module}/${item.record_id}`} onClick={onClose} className="text-link block truncate hover:underline">
                      {item.name}
                    </Link>
                    <div className="text-muted-foreground text-meta truncate">
                      {moduleFor(item.module)?.label ?? item.module}
                      {item.stage !== null && ` · ${item.stage} ${item.stage_name ?? ''}`}
                    </div>
                  </td>
                  <td className="py-1.5 pr-3">{item.owner ?? '—'}</td>
                  <td className="py-1.5 text-right whitespace-nowrap tabular-nums">
                    {item.usd === null ? (
                      <span className="text-meta inline-flex items-center gap-1">
                        <AlertTriangleIcon className="text-warning size-3" aria-hidden />
                        No value
                      </span>
                    ) : (
                      compactUsd(item.usd)
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </SheetContent>
    </Sheet>
  )
}
