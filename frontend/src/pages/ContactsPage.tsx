import { useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import { ListPageLayout } from '@/components/layout/ListPageLayout'
import { ListFilterBar, ScopePicker } from '@/components/list/ListFilterBar'
import { ModuleActions } from '@/components/list/ModuleActions'
import { RecordListView } from '@/components/list/RecordListView'
import { contactListCell } from '@/components/contacts/contactListCell'
import { useListFilters } from '@/lib/listFilters'

export function ContactsPage() {
  const navigate = useNavigate()
  const filters = useListFilters({ view: 'contacts' })
  const listFilter = useMemo(() => filters.params(), [filters])

  return (
    <ListPageLayout
      title="Contacts"
      scope={<ScopePicker filters={filters} />}
      actions={
        <ModuleActions
          module="contacts"
          plural="Contacts"
          noun="contact"
          createLabel="New contact"
          onCreate={() => navigate('/contacts/new')}
          exportFilter={() => listFilter}
        />
      }
      views={[
        {
          key: 'list',
          label: 'List',
          toolbar: <ListFilterBar filters={filters} plural="Contacts" showScope={false} searchPlaceholder="Search name, title, email or account…" />,
          content: (
            <>
              <RecordListView
                fill
                module="contacts"
                columnChoices={[...filters.common, ...filters.others].map((f) => f.field)}
                collection="contacts"
                basePath="/contacts"
                filter={listFilter}
                hideSearch
                renderCell={contactListCell}
              />
            </>
          ),
        },
      ]}
    />
  )
}
