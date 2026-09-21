import { useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import { PageLayout } from '@/components/layout/PageLayout'
import { ListFilterBar } from '@/components/list/ListFilterBar'
import { ModuleActions } from '@/components/list/ModuleActions'
import { RecordListView } from '@/components/list/RecordListView'
import { useListFilters } from '@/lib/listFilters'

export function AccountsPage() {
  const navigate = useNavigate()
  const filters = useListFilters({ view: 'accounts' })
  const listFilter = useMemo(() => filters.params(), [filters])

  return (
    <PageLayout
      wide
      title="Accounts"
      actions={
        <ModuleActions
          module="accounts"
          plural="Accounts"
          noun="account"
          createLabel="New account"
          onCreate={() => navigate('/accounts/new')}
          exportFilter={() => listFilter}
        />
      }
      tabs={[
        {
          key: 'list',
          label: 'List',
          content: (
            <>
              <ListFilterBar filters={filters} plural="Accounts" searchPlaceholder="Search name, region or segment…" />
              <RecordListView module="accounts" collection="accounts" basePath="/accounts" filter={listFilter} hideSearch />
            </>
          ),
        },
      ]}
    />
  )
}
