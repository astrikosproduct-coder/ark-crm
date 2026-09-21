import { format, parseISO } from 'date-fns'

import type { DashboardData, PipelineModule } from '@/components/dashboard/types'
import { moduleFor } from '@/lib/modules'

/** 'YYYY-MM-DD' is a calendar fact — parsed as a local date, never converted. */
export function monthLabel(month: string, pattern: string): string {
  return format(parseISO(month), pattern)
}

/** "Opportunity Revenue (Opportunities)" — the revenue rule's label and the module it belongs to. */
export function seriesLabel(labels: DashboardData['revenue_labels'], module: PipelineModule): string {
  return `${labels[module]} (${moduleFor(module)?.label ?? module})`
}
