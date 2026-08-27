import { useNavigate } from 'react-router-dom'
import { PlusIcon } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { PageLayout } from '@/components/layout/PageLayout'
import { RecordListView } from '@/components/list/RecordListView'

export function AccountsPage() {
  const navigate = useNavigate()

  return (
    <PageLayout
      wide
      title="Accounts"
      subtitle="End Clients, Partners / SIs, consultants and OEMs. One organisation can be more than one of these at once."
      actions={
        <Button onClick={() => navigate('/accounts/new')}>
          <PlusIcon className="size-4" />
          New account
        </Button>
      }
      tabs={[
        {
          key: 'list',
          label: 'List',
          content: (
            <RecordListView module="accounts" collection="accounts" basePath="/accounts" />
          ),
        },
      ]}
    />
  )
}
