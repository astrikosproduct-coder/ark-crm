import { useMemo } from 'react'

import { KanbanIcon, ListIcon } from 'lucide-react'

import { ListPageLayout } from '@/components/layout/ListPageLayout'
import { ModuleActions } from '@/components/list/ModuleActions'
import { RecordListView } from '@/components/list/RecordListView'
import { OpportunityKanbanBoard } from '@/components/opportunities/OpportunityKanbanBoard'
import { opportunityListCell } from '@/components/opportunities/opportunityListCell'
import { RankedOpportunityList } from '@/components/opportunities/RankedOpportunityList'
import { PRIORITY_ICONS } from '@/components/opportunities/priorityIcons'
import { ListFilterBar, ScopePicker } from '@/components/list/ListFilterBar'
import { useListFilters } from '@/lib/listFilters'
import { ragAccent } from '@/lib/rag'

/** The same mark a flagged opportunity carries, so the tab teaches what it means. */
function PriorityTabIcon({ flag }: { flag: string }) {
  const Icon = PRIORITY_ICONS[flag]
  return Icon ? <Icon aria-hidden className="size-4" /> : null
}

export function OpportunitiesPage() {
  // One filter for List and Kanban, held in the URL — see lib/listFilters.ts.
  const filters = useListFilters({ view: 'opportunities', stageField: 'project_stage' })
  const listFilter = useMemo(() => filters.params({ withStage: true }), [filters])
  const boardFilter = useMemo(() => filters.params({ withStage: false }), [filters])
  const narrowed = Boolean(filters.q) || Object.keys(filters.conditions).length > 0
  // The ranked views keep the List's filter bar, and the filter applies to them.
  const listToolbar = (
    <ListFilterBar filters={filters} plural="Opportunities" showScope={false} searchPlaceholder="Search name or client…" />
  )

  // No "New opportunity" (removed 7 Oct 2026): Leads are the one door. An
  // Opportunity is a Lead moved past Stage 3 — one made by hand had no Lead,
  // so its End Client, Partner and the rest "From the Lead" stayed blank.
  // Deals have never had one either. The server refuses it too.
  return (
    <ListPageLayout
      pageKey="opportunities"
      title="Opportunities"
      scope={<ScopePicker filters={filters} />}
      actions={
        <ModuleActions
          module="opportunities"
          plural="Opportunities"
          noun="opportunity"
          exportFilter={() => listFilter}
        />
      }
      views={[
        {
          key: 'list',
          label: 'List',
          icon: <ListIcon className="size-4" />,
          toolbar: listToolbar,
          content: (
            <>
              <RecordListView
                fill
                module="opportunities"
                columnChoices={[...filters.common, ...filters.others].map((f) => f.field)}
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
          icon: <KanbanIcon className="size-4" />,
          toolbar: (
            <ListFilterBar filters={filters} plural="Opportunities" showStage={false} showScope={false} searchPlaceholder="Search name or client…" />
          ),
          content: (
            <>
              <OpportunityKanbanBoard filter={boardFilter} fields={[...filters.common, ...filters.others].map((f) => f.field)} />
            </>
          ),
        },
        {
          key: 'low-hanging',
          label: 'Low Hanging',
          icon: <PriorityTabIcon flag="is_low_hanging" />,
          toolbar: listToolbar,
          content: (
            <RankedOpportunityList
              flagField="is_low_hanging"
              rankField="low_hanging_rank"
              cap={5}
              filter={listFilter}
              narrowed={narrowed}
              columnChoices={[...filters.common, ...filters.others].map((f) => f.field)}
            />
          ),
        },
        {
          key: 'top-10',
          label: 'Top 10',
          icon: <PriorityTabIcon flag="is_top_10" />,
          toolbar: listToolbar,
          content: (
            <RankedOpportunityList
              flagField="is_top_10"
              rankField="top_10_rank"
              cap={10}
              filter={listFilter}
              narrowed={narrowed}
              columnChoices={[...filters.common, ...filters.others].map((f) => f.field)}
            />
          ),
        },
      ]}
    />
  )
}
