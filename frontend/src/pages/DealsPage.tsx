import { useMemo } from 'react'

import { KanbanIcon, ListIcon } from 'lucide-react'

import { ListPageLayout } from '@/components/layout/ListPageLayout'
import { ModuleActions } from '@/components/list/ModuleActions'
import { RecordListView } from '@/components/list/RecordListView'
import { DealKanbanBoard } from '@/components/deals/DealKanbanBoard'
import { dealListCell } from '@/components/deals/dealListCell'
import { ListFilterBar, ScopePicker } from '@/components/list/ListFilterBar'
import { useListFilters } from '@/lib/listFilters'
import { ragAccent } from '@/lib/rag'

export function DealsPage() {
  // One filter for List and Kanban, held in the URL — see lib/listFilters.ts.
  const filters = useListFilters({ view: 'deals', stageField: 'deal_stage' })
  const listFilter = useMemo(() => filters.params({ withStage: true }), [filters])
  const boardFilter = useMemo(() => filters.params({ withStage: false }), [filters])

  return (
    <ListPageLayout
      pageKey="deals"
      title="Deals"
      scope={<ScopePicker filters={filters} />}
      actions={<ModuleActions module="deals" plural="Deals" noun="deal" exportFilter={() => listFilter} />}
      views={[
        {
          key: 'list',
          label: 'List',
          icon: <ListIcon className="size-4" />,
          toolbar: <ListFilterBar filters={filters} plural="Deals" showScope={false} searchPlaceholder="Search name, client or code…" />,
          content: (
            <>
              <RecordListView
                fill
                module="deals"
                columnChoices={[...filters.common, ...filters.others].map((f) => f.field)}
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
          icon: <KanbanIcon className="size-4" />,
          toolbar: (
            <ListFilterBar filters={filters} plural="Deals" showStage={false} showScope={false} searchPlaceholder="Search name, client or code…" />
          ),
          content: (
            <>
              <DealKanbanBoard filter={boardFilter} fields={[...filters.common, ...filters.others].map((f) => f.field)} />
            </>
          ),
        },
      ]}
    />
  )
}
