import { useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import { PageLayout } from '@/components/layout/PageLayout'
import { ListFilterBar } from '@/components/list/ListFilterBar'
import { ModuleActions } from '@/components/list/ModuleActions'
import { RecordListView } from '@/components/list/RecordListView'
import { contactListCell } from '@/components/contacts/contactListCell'
import { useListFilters } from '@/lib/listFilters'

export function ContactsPage() {
  const navigate = useNavigate()
  const filters = useListFilters({ view: 'contacts' })
  const listFilter = useMemo(() => filters.params(), [filters])

  return (
    <PageLayout
      wide
      title="Contacts"
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
      tabs={[
        {
          key: 'list',
          label: 'List',
          content: (
            <>
              <ListFilterBar filters={filters} plural="Contacts" searchPlaceholder="Search name, title, email or account…" />
              <RecordListView
                module="contacts"
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
