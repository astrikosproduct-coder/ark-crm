import { useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import { PageLayout } from '@/components/layout/PageLayout'
import { ModuleActions } from '@/components/list/ModuleActions'
import { RecordListView } from '@/components/list/RecordListView'
import { LeadKanbanBoard } from '@/components/leads/LeadKanbanBoard'
import { leadListCell } from '@/components/leads/leadListCell'
import { ListFilterBar } from '@/components/list/ListFilterBar'
import { useListFilters } from '@/lib/listFilters'
import { ragAccent } from '@/lib/rag'

export function LeadsPage() {
  const navigate = useNavigate()
  // One filter for List and Kanban, held in the URL — see lib/listFilters.ts.
  const filters = useListFilters({ view: 'leads', stageField: 'project_stage' })
  const listFilter = useMemo(() => filters.params({ withStage: true }), [filters])
  const boardFilter = useMemo(() => filters.params({ withStage: false }), [filters])

  return (
    <PageLayout
      wide
      title="Leads"
      actions={
        <ModuleActions
          module="leads"
          plural="Leads"
          noun="lead"
          createLabel="New lead"
          onCreate={() => navigate('/leads/new')}
          exportFilter={() => listFilter}
          importNote="Leads are imported at Stage 0 · Connect. Move them forward in ARK, where each move's checks are recorded."
        />
      }
      tabs={[
        {
          key: 'list',
          label: 'List',
          content: (
            <>
              <ListFilterBar filters={filters} plural="Leads" searchPlaceholder="Search name or client…" />
              <RecordListView
                module="leads"
                collection="leads"
                basePath="/leads"
                filter={listFilter}
                hideSearch
                renderCell={leadListCell}
                rowAccent={ragAccent}
                pageSize={25}
                emptyMessage="No leads yet."
              />
            </>
          ),
        },
        {
          key: 'pipeline',
          label: 'Kanban',
          content: (
            <>
              <ListFilterBar filters={filters} plural="Leads" showStage={false} searchPlaceholder="Search name or client…" />
              <LeadKanbanBoard filter={boardFilter} />
            </>
          ),
        },
      ]}
    />
  )
}
