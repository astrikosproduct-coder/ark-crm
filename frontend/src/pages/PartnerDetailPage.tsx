import { useMemo, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { Building2Icon, PencilIcon, PlusIcon } from 'lucide-react'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { PageLayout } from '@/components/layout/PageLayout'
import { RecordForm } from '@/components/form/RecordForm'
import { RecordEditor } from '@/components/record/RecordEditor'
import { RecordListView } from '@/components/list/RecordListView'
import { UnsavedBadge } from '@/components/record/UnsavedBadge'
import { contactListCell } from '@/components/contacts/contactListCell'
import { registrationListCell } from '@/components/partners/registrationListCell'
import { NEW_RECORD_ID } from '@/hooks/useRecordForm'
import { api } from '@/lib/api'
import { displayNameOf, isPartnerAccount, labelForValue, withRecordId } from '@/lib/spec'
import { useDiscardToken } from '@/store/useDraftStore'

// A partner IS an account. Both of these say accounts on purpose — there is no
// partners collection, because a second organisation record is exactly what
// this module must not create.
const MODULE = 'accounts'
const COLLECTION = 'accounts'

export function PartnerDetailPage() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const [editing, setEditing] = useState(false)
  const draftId = id ?? NEW_RECORD_ID
  const discardToken = useDiscardToken(MODULE, draftId)

  const { data, isLoading, isError, dataUpdatedAt } = useQuery({
    queryKey: ['record', COLLECTION, id],
    queryFn: async () => (await api.get<Record<string, unknown>>(`/${COLLECTION}/${id}`)).data,
    enabled: Boolean(id),
  })

  const values = useMemo(() => (data ? withRecordId(MODULE, data) : undefined), [data])
  const types = Array.isArray(values?.account_type) ? (values.account_type as string[]) : []

  if (isError) {
    return (
      <PageLayout
        title={id ?? 'Partner'}
        tabs={[
          {
            key: 'missing',
            label: 'Partner',
            content: <p className="py-6 text-sm text-destructive">No account with id {id}.</p>,
          },
        ]}
      />
    )
  }

  if (values && !isPartnerAccount(values)) {
    return (
      <PageLayout
        title={displayNameOf(values)}
        subtitle={id}
        tabs={[
          {
            key: 'not-a-partner',
            label: 'Partner',
            content: (
              <div className="py-6 text-sm">
                <p>
                  {displayNameOf(values)} carries no partner Account Type, so it has no partner
                  record.
                </p>
                <p className="text-muted-foreground mt-1">
                  Add Partner / SI or OEM / Technology Partner to its Account Type on the{' '}
                  <Link className="underline underline-offset-2" to={`/accounts/${id}`}>
                    account
                  </Link>{' '}
                  and it appears here — the organisation record is the same one either way.
                </p>
              </div>
            ),
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
          {types.map((t) => (
            <Badge key={t} variant="secondary">
              {labelForValue('accounts__account_type', t)}
            </Badge>
          ))}
          <UnsavedBadge module={MODULE} recordId={draftId} />
        </>
      }
      subtitle={id}
      actions={
        <>
          <Button variant="outline" onClick={() => navigate(`/accounts/${id}`)}>
            <Building2Icon className="size-4" />
            Account record
          </Button>
          {!editing && (
            <Button variant="outline" onClick={() => setEditing(true)} disabled={isLoading}>
              <PencilIcon className="size-4" />
              Edit
            </Button>
          )}
        </>
      }
      tabs={[
        {
          key: 'profile',
          label: 'Profile',
          content: (
            <div className="space-y-3 py-3">
              <SharedRecordNote id={id} />

              {isLoading ? (
                <p className="py-6 text-sm text-muted-foreground">Loading…</p>
              ) : editing ? (
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
                <RecordForm
                  key={`view:${id}:${dataUpdatedAt}`}
                  module={MODULE}
                  mode="view"
                  values={values}
                />
              )}
            </div>
          ),
        },
        {
          key: 'registrations',
          label: 'Deal registrations',
          content: (
            <div className="space-y-3 py-3">
              <div className="flex items-center justify-between gap-3">
                <p className="text-sm text-muted-foreground">
                  Deals this partner has registered. Exclusivity runs per client and project.
                </p>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => navigate(`/partners/registrations/new?partner=${id}`)}
                >
                  <PlusIcon className="size-4" />
                  New registration
                </Button>
              </div>

              <RecordListView
                module="registrations"
                collection="registrations"
                basePath="/partners/registrations"
                filter={{ partner: id ?? '' }}
                hiddenColumns={['partner']}
                renderCell={registrationListCell}
                pageSize={10}
                emptyMessage="This partner has registered no deals yet."
              />
            </div>
          ),
        },
        {
          key: 'contacts',
          label: 'Contacts',
          content: (
            <div className="space-y-3 py-3">
              <div className="flex items-center justify-between gap-3">
                <p className="text-sm text-muted-foreground">Everybody whose Account is {id}.</p>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => navigate(`/contacts/new?account=${id}`)}
                >
                  <PlusIcon className="size-4" />
                  Add contact
                </Button>
              </div>

              <RecordListView
                module="contacts"
                collection="contacts"
                basePath="/contacts"
                filter={{ account: id ?? '' }}
                hiddenColumns={['account']}
                renderCell={contactListCell}
                pageSize={10}
                emptyMessage="No contacts at this partner yet."
              />
            </div>
          ),
        },
      ]}
    />
  )
}

/**
 * The point of the whole module, said out loud on the screen.
 *
 * An organisation can be an End Client and a Partner at the same time. Both
 * screens edit the same account, so a reviewer must not be able to believe
 * there are two of it.
 */
function SharedRecordNote({ id }: { id: string | undefined }) {
  return (
    <div className="rounded-lg border border-dashed p-3 text-sm">
      <span className="font-medium">This is the account record, seen from the partner side.</span>{' '}
      <span className="text-muted-foreground">
        There is no separate partner organisation. The same {id} appears on the Accounts screen,
        and an edit made here changes it there too — an organisation that is both an End Client and
        a Partner stays one record.
      </span>{' '}
      <Link className="underline underline-offset-2" to={`/accounts/${id}`}>
        Open in Accounts
      </Link>
    </div>
  )
}
