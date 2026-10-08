import { useMemo, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { NetworkIcon, PencilIcon, PlusIcon, RotateCcwIcon, Trash2Icon } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { PageLayout } from '@/components/layout/PageLayout'
import { GroupCompanies } from '@/components/accounts/GroupCompanies'
import { RecordForm } from '@/components/form/RecordForm'
import { RecordEditor } from '@/components/record/RecordEditor'
import { RecordListView } from '@/components/list/RecordListView'
import { DeleteRecordDialog } from '@/components/record/DeleteRecordDialog'
import { ACCOUNT_REFERRERS } from '@/lib/referrers'
import { useSetRecordActive } from '@/lib/recordLifecycle'
import { contactListCell } from '@/components/contacts/contactListCell'
import { api } from '@/lib/api'
import { displayNameOf, isPartnerAccount, withRecordId } from '@/lib/spec'
import { ComingSoon } from '@/pages/ComingSoon'
import { cn } from '@/lib/utils'

const MODULE = 'accounts'
const COLLECTION = 'accounts'

export function AccountDetailPage() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [editing, setEditing] = useState(false)
  const [deleting, setDeleting] = useState(false)
  // Bumped only by an explicit Discard in the header badge — folded into the
  // editor's key so Discard reverts the open form even while it's mounted,
  // without this page needing to reach into RecordFormProvider's state.

  const { data, isLoading, isError, dataUpdatedAt } = useQuery({
    queryKey: ['record', COLLECTION, id],
    queryFn: async () => (await api.get<Record<string, unknown>>(`/${COLLECTION}/${id}`)).data,
    enabled: Boolean(id),
  })

  // The register calls the key field account_id; the store calls it id.
  const values = useMemo(() => (data ? withRecordId(MODULE, data) : undefined), [data])

  const website = typeof values?.website === 'string' ? values.website.trim() : ''
  const inactive = values?.active === false
  // Release 1.1: a member of a group names its head beside the title.
  const parentId = typeof values?.parent_account === 'string' ? values.parent_account : ''
  const parentName = (values?.__labels as Record<string, string> | undefined)?.parent_account ?? parentId

  const setActive = useSetRecordActive(COLLECTION, id ?? '', {
    noun: 'account',
    recordName: values ? displayNameOf(values) : (id ?? ''),
  })

  if (isError) {
    return (
      <PageLayout
        back
        title="Account"
        tabs={[
          {
            key: 'missing',
            label: 'Overview',
            content: <p className="py-6 text-sm text-destructive">This account no longer exists. It may have been deleted.</p>,
          },
        ]}
      />
    )
  }

  return (
    <>
    <PageLayout
      back
      title={
        <>
          {/* Dimmed, not struck through: a strikethrough reads as deleted,
              and this record is retired but very much still here. */}
          <span className={cn(inactive && 'text-muted-foreground')}>
            {values ? displayNameOf(values) : (id ?? '')}
          </span>
          {/* Name, then the website when one is entered. The id and the
              account types live in the form, not the heading. */}
          {website && (
            <>
              <span className="text-muted-foreground font-normal">-</span>
              <a
                href={/^https?:\/\//i.test(website) ? website : `https://${website}`}
                target="_blank"
                rel="noopener noreferrer"
                className="text-primary text-base font-normal underline-offset-2 hover:underline"
              >
                {website}
              </a>
            </>
          )}
          {parentId && (
            <span className="text-muted-foreground text-sm font-normal">
              Group:{' '}
              <Link className="text-primary underline-offset-2 hover:underline" to={`/accounts/${parentId}`}>
                {parentName}
              </Link>
            </span>
          )}
          {inactive && <span className="text-muted-foreground text-sm font-normal">Inactive</span>}
        </>
      }
      actions={
        <>
          {/* The same record, seen from the partner side. Not a second
              organisation — the Partners screen edits this very account. */}
          {isPartnerAccount(values) && (
            <Button variant="outline" onClick={() => navigate(`/partners/${id}`)}>
              <NetworkIcon className="size-4" />
              Partner record
            </Button>
          )}
          {!editing && (
            <>
              <Button variant="outline" onClick={() => setEditing(true)} disabled={isLoading}>
                <PencilIcon className="size-4" />
                Edit
              </Button>
              {/* Reactivating is the safe, reversible action, so it sits in
                  plain sight next to Edit rather than inside a Delete dialog. */}
              {inactive && (
                <Button
                  variant="outline"
                  onClick={() => setActive.mutate(true)}
                  disabled={setActive.isPending}
                >
                  <RotateCcwIcon className="size-4" />
                  {setActive.isPending ? 'Reactivating…' : 'Reactivate'}
                </Button>
              )}
              <Button
                variant="outline"
                onClick={() => setDeleting(true)}
                disabled={isLoading || !values}
                className="text-destructive hover:text-destructive"
              >
                <Trash2Icon className="size-4" />
                Delete
              </Button>
            </>
          )}
        </>
      }
      tabs={[
        {
          key: 'overview',
          label: 'Overview',
          content: isLoading ? (
            <p className="py-6 text-sm text-muted-foreground">Loading…</p>
          ) : editing ? (
            // A RecordForm seeds its state once, so both of these are keyed on
            // the fetch that produced their values — otherwise a save would
            // leave the screen showing what was there before it.
            <RecordEditor
              key={`edit:${id}:${dataUpdatedAt}`}
              module={MODULE}
              collection={COLLECTION}
              recordId={id}
              initialValues={values}
              onSaved={() => {
                setEditing(false)
                void queryClient.invalidateQueries({ queryKey: ['account-group'] })
              }}
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
        {
          key: 'group',
          label: 'Group companies',
          content: <GroupCompanies accountId={id ?? ''} />,
        },
        {
          key: 'contacts',
          label: 'Contacts',
          content: (
            <div className="space-y-3 py-3">
              <div className="flex items-center justify-between gap-3">
                <p className="text-sm text-muted-foreground">
                  Contacts at {values ? displayNameOf(values) : 'this account'}.
                </p>
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
                emptyMessage="No contacts on this account yet."
              />
            </div>
          ),
        },
        { key: 'activity', label: 'Activity', content: <ComingSoon label="Activity" /> },
      ]}
    />

    {values && (
      <DeleteRecordDialog
        open={deleting}
        onOpenChange={setDeleting}
        collection={COLLECTION}
        recordId={id ?? ''}
        recordName={displayNameOf(values)}
        noun="account"
        active={!inactive}
        lookupTarget="account"
        referrers={ACCOUNT_REFERRERS}
        onDeleted={() => navigate('/accounts')}
      />
    )}
    </>
  )
}
