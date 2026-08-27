import { useNavigate } from 'react-router-dom'
import { PlusIcon } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { PageLayout } from '@/components/layout/PageLayout'
import { RecordListView } from '@/components/list/RecordListView'
import { contactListCell } from '@/components/contacts/contactListCell'

export function ContactsPage() {
  const navigate = useNavigate()

  return (
    <PageLayout
      wide
      title="Contacts"
      subtitle="People at an account, coloured by the role they play in a pursuit."
      actions={
        <Button onClick={() => navigate('/contacts/new')}>
          <PlusIcon className="size-4" />
          New contact
        </Button>
      }
      tabs={[
        {
          key: 'list',
          label: 'List',
          content: (
            <RecordListView
              module="contacts"
              collection="contacts"
              basePath="/contacts"
              renderCell={contactListCell}
            />
          ),
        },
      ]}
    />
  )
}
