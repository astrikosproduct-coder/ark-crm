import { useMemo } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { Building2Icon, PlusIcon } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { PageLayout } from '@/components/layout/PageLayout'
import { RecordForm } from '@/components/form/RecordForm'
import { RecordListView } from '@/components/list/RecordListView'
import { contactListCell } from '@/components/contacts/contactListCell'
import { registrationListCell } from '@/components/partners/registrationListCell'
import { api } from '@/lib/api'
import { displayNameOf, isPartnerAccount, labelForValue, withRecordId } from '@/lib/spec'

// A partner IS an account. Both of these say accounts on purpose — there is no
// partners collection, because a second organisation record is exactly what
// this module must not create.
const MODULE = 'accounts'
const COLLECTION = 'accounts'

/**
 * A partner, seen from the partner side.
 *
 * The profile is READ-ONLY here. Accounts is the one place an account is
 * created, edited or deleted; this screen used to carry its own Edit, which
 * made two doors onto the same record and meant any account rule added to the
 * Accounts screen had to be remembered here as well. "Account record" is the
 * way to change it.
 */
export function PartnerDetailPage() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()

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
        back
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
        back
        title={displayNameOf(values)}
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
      back
      title={
        <>
          {values ? displayNameOf(values) : (id ?? '')}
          {types.length > 0 && (
            <>
              <span aria-hidden className="text-muted-foreground font-normal">-</span>
              <span className="text-muted-foreground text-base font-normal">
                {types.map((t) => labelForValue('accounts__account_type', t)).join(' · ')}
              </span>
            </>
          )}
        </>
      }
      actions={
        <Button variant="outline" onClick={() => navigate(`/accounts/${id}`)}>
          <Building2Icon className="size-4" />
          Account record
        </Button>
      }
      tabs={[
        {
          key: 'profile',
          label: 'Profile',
          content: (
            <div className="space-y-3 py-3">
              {isLoading ? (
                <p className="py-6 text-sm text-muted-foreground">Loading…</p>
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
              <div className="flex items-center justify-end gap-3">
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
