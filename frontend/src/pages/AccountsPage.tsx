import { useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import { ListPageLayout } from '@/components/layout/ListPageLayout'
import { ListFilterBar, ScopePicker } from '@/components/list/ListFilterBar'
import { ModuleActions } from '@/components/list/ModuleActions'
import { RecordListView } from '@/components/list/RecordListView'
import { useListFilters } from '@/lib/listFilters'

export function AccountsPage() {
  const navigate = useNavigate()
  const filters = useListFilters({ view: 'accounts' })
  const listFilter = useMemo(() => filters.params(), [filters])

  return (
    <ListPageLayout
      title="Accounts"
      scope={<ScopePicker filters={filters} />}
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
      views={[
        {
          key: 'list',
          label: 'List',
          toolbar: <ListFilterBar filters={filters} plural="Accounts" showScope={false} searchPlaceholder="Search name, region or segment…" />,
          content: (
            <>
              <RecordListView
                fill
                module="accounts"
                collection="accounts"
                basePath="/accounts"
                filter={listFilter}
                hideSearch
                columnChoices={[...filters.common, ...filters.others].map((f) => f.field)}
              />
            </>
          ),
        },
      ]}
    />
  )
}
