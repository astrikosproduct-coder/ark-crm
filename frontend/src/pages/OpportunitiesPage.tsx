import { useMemo } from 'react'

import { PageLayout } from '@/components/layout/PageLayout'
import { ModuleActions } from '@/components/list/ModuleActions'
import { RecordListView } from '@/components/list/RecordListView'
import { OpportunityKanbanBoard } from '@/components/opportunities/OpportunityKanbanBoard'
import { opportunityListCell } from '@/components/opportunities/opportunityListCell'
import { RankedOpportunityList } from '@/components/opportunities/RankedOpportunityList'
import { PRIORITY_ICONS } from '@/components/opportunities/priorityIcons'
import { ListFilterBar } from '@/components/list/ListFilterBar'
import { useListFilters } from '@/lib/listFilters'
import { ragAccent } from '@/lib/rag'

/** The same mark a flagged opportunity carries, so the tab teaches what it means. */
function PriorityTabIcon({ flag }: { flag: string }) {
  const Icon = PRIORITY_ICONS[flag]
  return Icon ? <Icon aria-hidden className="size-3.5" /> : null
}

export function OpportunitiesPage() {
  // One filter for List and Kanban, held in the URL — see lib/listFilters.ts.
  const filters = useListFilters({ view: 'opportunities', stageField: 'project_stage' })
  const listFilter = useMemo(() => filters.params({ withStage: true }), [filters])
  const boardFilter = useMemo(() => filters.params({ withStage: false }), [filters])

  // No "New opportunity" (removed 7 Oct 2026): Leads are the one door. An
  // Opportunity is a Lead moved past Stage 3 — one made by hand had no Lead,
  // so its End Client, Partner and the rest "From the Lead" stayed blank.
  // Deals have never had one either. The server refuses it too.
  return (
    <PageLayout
      wide
      title="Opportunities"
      actions={
        <ModuleActions
          module="opportunities"
          plural="Opportunities"
          noun="opportunity"
          exportFilter={() => listFilter}
        />
      }
      tabs={[
        {
          key: 'list',
          label: 'List',
          content: (
            <>
              <ListFilterBar filters={filters} plural="Opportunities" searchPlaceholder="Search name or client…" />
              <RecordListView
                module="opportunities"
                collection="opportunities"
                basePath="/opportunities"
                filter={listFilter}
                hideSearch
                renderCell={opportunityListCell}
                rowAccent={ragAccent}
                pageSize={25}
                emptyMessage="No opportunities yet. Move a Lead past Stage 3 to create one."
              />
            </>
          ),
        },
        {
          key: 'pipeline',
          label: 'Kanban',
          content: (
            <>
              <ListFilterBar filters={filters} plural="Opportunities" showStage={false} searchPlaceholder="Search name or client…" />
              <OpportunityKanbanBoard filter={boardFilter} />
            </>
          ),
        },
        {
          key: 'low-hanging',
          label: 'Low Hanging',
          icon: <PriorityTabIcon flag="is_low_hanging" />,
          content: <RankedOpportunityList flagField="is_low_hanging" rankField="low_hanging_rank" cap={5} />,
        },
        {
          key: 'top-10',
          label: 'Top 10',
          icon: <PriorityTabIcon flag="is_top_10" />,
          content: <RankedOpportunityList flagField="is_top_10" rankField="top_10_rank" cap={10} />,
        },
      ]}
    />
  )
}
