import { useMemo } from 'react'

import { PageLayout } from '@/components/layout/PageLayout'
import { ModuleActions } from '@/components/list/ModuleActions'
import { RecordListView } from '@/components/list/RecordListView'
import { DealKanbanBoard } from '@/components/deals/DealKanbanBoard'
import { dealListCell } from '@/components/deals/dealListCell'
import { ListFilterBar } from '@/components/list/ListFilterBar'
import { useListFilters } from '@/lib/listFilters'
import { ragAccent } from '@/lib/rag'

export function DealsPage() {
  // One filter for List and Kanban, held in the URL — see lib/listFilters.ts.
  const filters = useListFilters({ view: 'deals', stageField: 'deal_stage' })
  const listFilter = useMemo(() => filters.params({ withStage: true }), [filters])
  const boardFilter = useMemo(() => filters.params({ withStage: false }), [filters])

  return (
    <PageLayout
      wide
      title="Deals"
      actions={<ModuleActions module="deals" plural="Deals" noun="deal" exportFilter={() => listFilter} />}
      tabs={[
        {
          key: 'list',
          label: 'List',
          content: (
            <>
              <ListFilterBar filters={filters} plural="Deals" searchPlaceholder="Search name, client or code…" />
              <RecordListView
                module="deals"
                collection="deals"
                basePath="/deals"
                filter={listFilter}
                hideSearch
                renderCell={dealListCell}
                rowAccent={ragAccent}
                pageSize={25}
                emptyMessage="No deals yet. Convert an Opportunity at Stage 6 to create one."
              />
            </>
          ),
        },
        {
          key: 'pipeline',
          label: 'Kanban',
          content: (
            <>
              <ListFilterBar filters={filters} plural="Deals" showStage={false} searchPlaceholder="Search name, client or code…" />
              <DealKanbanBoard filter={boardFilter} />
            </>
          ),
        },
      ]}
    />
  )
}
