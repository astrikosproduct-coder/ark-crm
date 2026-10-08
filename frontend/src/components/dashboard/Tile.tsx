import { createContext, useContext, type ReactNode } from 'react'

import { ChartCard, type TableView } from '@/components/dashboard/ChartCard'
import type { TileConfig } from '@/components/dashboard/config'
import type { DashboardData, DrillRequest } from '@/components/dashboard/types'
import { COMPANY_TZ_LABEL, companyDateTime } from '@/lib/time'

/** What every tile on the page shares: the answer, the filters in words, and the drill-down. */
export interface DashboardContextValue {
  data: DashboardData
  /** "Booking Region: MEA", one per filter in force — the period first. */
  filterLines: string[]
  drill: (request: DrillRequest) => void
}

const DashboardContext = createContext<DashboardContextValue | null>(null)

export const DashboardProvider = DashboardContext.Provider

export function useDashboard(): DashboardContextValue {
  const value = useContext(DashboardContext)
  if (!value) throw new Error('useDashboard outside the dashboard')
  return value
}

/**
 * The ⓘ popover of every tile: measure, dimension, the filters it was computed
 * under, what it leaves out, and when. Built from the tile's config and the
 * server's echo of the filters, so it can never describe a filter the numbers
 * were not computed with.
 */
function Definition({ config, extra }: { config: TileConfig; extra?: string[] }) {
  const { data, filterLines } = useDashboard()
  const exclusions = [...config.definition.exclusions, ...(extra ?? [])]
  return (
    <dl className="space-y-1.5">
      <div>
        <dt className="font-semibold">Measure</dt>
        <dd>{config.definition.measure}</dd>
      </div>
      <div>
        <dt className="font-semibold">Split by</dt>
        <dd>{config.definition.dimension}</dd>
      </div>
      <div>
        <dt className="font-semibold">Filters applied</dt>
        <dd>{filterLines.length ? filterLines.join(' · ') : 'None — every record.'}</dd>
      </div>
      {exclusions.length > 0 && (
        <div>
          <dt className="font-semibold">Leaves out</dt>
          <dd>
            <ul className="list-disc space-y-0.5 pl-4">
              {exclusions.map((line) => (
                <li key={line}>{line}</li>
              ))}
            </ul>
          </dd>
        </div>
      )}
      <div>
        <dt className="font-semibold">As of</dt>
        <dd>
          {companyDateTime(data.generated_at)} {COMPANY_TZ_LABEL}
        </dd>
      </div>
    </dl>
  )
}

/** One dashboard tile: its config's title and caption, its definition behind the ⓘ, its table twin. */
export function Tile({
  config,
  table,
  extra,
  className,
  children,
}: {
  config: TileConfig
  table: TableView
  /** Exclusions only this answer has — "3 records have no close month". */
  extra?: string[]
  className?: string
  children: ReactNode
}) {
  return (
    <ChartCard
      title={config.title}
      caption={config.caption}
      info={<Definition config={config} extra={extra} />}
      table={table}
      tableFirst={config.tableFirst}
      className={className}
    >
      {children}
    </ChartCard>
  )
}

/**
 * Why a tile is empty — three different facts. Emptiness a FILTER caused has to
 * say so, because the filter is the thing the reader can undo. Read off what
 * the server echoed back, never local state.
 */
export function nothingHere(data: DashboardData, thing: string): string {
  const filtered = Object.values(data.filters).some(Boolean)
  const ranged = Boolean(data.range.from || data.range.to)
  if (filtered) return `No ${thing} match these filters.`
  if (ranged) return `No ${thing} in this period.`
  return `No ${thing} yet.`
}
