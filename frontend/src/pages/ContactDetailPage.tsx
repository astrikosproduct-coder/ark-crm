import { useMemo, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { PencilIcon } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { PageLayout } from '@/components/layout/PageLayout'
import { RecordForm } from '@/components/form/RecordForm'
import { RecordEditor } from '@/components/record/RecordEditor'
import { UnsavedBadge } from '@/components/record/UnsavedBadge'
import {
  ConfidentialChip,
  ContactRoleBadge,
  isConfidentialContact,
} from '@/components/contacts/ContactRoleBadge'
import { NEW_RECORD_ID } from '@/hooks/useRecordForm'
import { api } from '@/lib/api'
import { displayNameOf, withRecordId } from '@/lib/spec'
import { ComingSoon } from '@/pages/ComingSoon'
import { useDiscardToken } from '@/store/useDraftStore'

const MODULE = 'contacts'
const COLLECTION = 'contacts'

export function ContactDetailPage() {
  const { id } = useParams<{ id: string }>()
  const [editing, setEditing] = useState(false)
  const draftId = id ?? NEW_RECORD_ID
  const discardToken = useDiscardToken(MODULE, draftId)

  const { data, isLoading, isError, dataUpdatedAt } = useQuery({
    queryKey: ['record', COLLECTION, id],
    queryFn: async () => (await api.get<Record<string, unknown>>(`/${COLLECTION}/${id}`)).data,
    enabled: Boolean(id),
  })

  const values = useMemo(() => (data ? withRecordId(MODULE, data) : undefined), [data])

  // Resolved for the subtitle only. The form engine renders the lookup itself.
  const { data: account } = useQuery({
    queryKey: ['record', 'accounts', values?.account],
    queryFn: async () =>
      (await api.get<Record<string, unknown>>(`/accounts/${values?.account}`)).data,
    enabled: typeof values?.account === 'string' && Boolean(values.account),
  })

  if (isError) {
    return (
      <PageLayout
        title={id ?? 'Contact'}
        tabs={[
          {
            key: 'missing',
            label: 'Overview',
            content: <p className="py-6 text-sm text-destructive">No contact with id {id}.</p>,
          },
        ]}
      />
    )
  }

  return (
    <PageLayout
      title={
        <>
          {values ? displayNameOf(values) : (id ?? '')}
          {values && <ContactRoleBadge value={values.contact_role} />}
          {values && isConfidentialContact(values) && <ConfidentialChip />}
          <UnsavedBadge module={MODULE} recordId={draftId} />
        </>
      }
      subtitle={
        <span className="flex flex-wrap items-center gap-2">
          <span>{id}</span>
          {typeof values?.job_title === 'string' && values.job_title && (
            <span>· {values.job_title}</span>
          )}
          {account && (
            <>
              <span>·</span>
              <Link className="underline underline-offset-2" to={`/accounts/${values?.account}`}>
                {displayNameOf(account)}
              </Link>
            </>
          )}
        </span>
      }
      actions={
        !editing && (
          <Button variant="outline" onClick={() => setEditing(true)} disabled={isLoading}>
            <PencilIcon className="size-4" />
            Edit
          </Button>
        )
      }
      tabs={[
        {
          key: 'overview',
          label: 'Overview',
          content: isLoading ? (
            <p className="py-6 text-sm text-muted-foreground">Loading…</p>
          ) : editing ? (
            // Keyed on the fetch, not just the id — see AccountDetailPage.
            <RecordEditor
              key={`edit:${id}:${dataUpdatedAt}:${discardToken}`}
              module={MODULE}
              collection={COLLECTION}
              recordId={id}
              initialValues={values}
              onSaved={() => setEditing(false)}
              onCancel={() => setEditing(false)}
            />
          ) : (
            <div className="py-3">
              <RecordForm
                key={`view:${id}:${dataUpdatedAt}`}
                module={MODULE}
                mode="view"
                values={values}
              />
            </div>
          ),
        },
        { key: 'activity', label: 'Activity', content: <ComingSoon label="Activity" /> },
      ]}
    />
  )
}
