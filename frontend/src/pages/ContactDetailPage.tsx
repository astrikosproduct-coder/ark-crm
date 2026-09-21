import { useMemo, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { PencilIcon, RotateCcwIcon, Trash2Icon } from 'lucide-react'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { PageLayout } from '@/components/layout/PageLayout'
import { RecordForm } from '@/components/form/RecordForm'
import { RecordEditor } from '@/components/record/RecordEditor'
import { DeleteRecordDialog } from '@/components/record/DeleteRecordDialog'
import { CONTACT_REFERRERS } from '@/lib/referrers'
import { useSetRecordActive } from '@/lib/recordLifecycle'
import { api } from '@/lib/api'
import { displayNameOf, fieldOf, labelForValue, withRecordId } from '@/lib/spec'
import { cn } from '@/lib/utils'
import { ComingSoon } from '@/pages/ComingSoon'

const MODULE = 'contacts'
const COLLECTION = 'contacts'

export function ContactDetailPage() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const [editing, setEditing] = useState(false)
  const [deleting, setDeleting] = useState(false)

  const { data, isLoading, isError, dataUpdatedAt } = useQuery({
    queryKey: ['record', COLLECTION, id],
    queryFn: async () => (await api.get<Record<string, unknown>>(`/${COLLECTION}/${id}`)).data,
    enabled: Boolean(id),
  })

  const values = useMemo(() => (data ? withRecordId(MODULE, data) : undefined), [data])
  const inactive = values?.active === false
  const roleField = fieldOf(MODULE, 'contact_role')
  const roleLabel =
    roleField && values?.contact_role
      ? labelForValue(roleField.picklist, values.contact_role)
      : ''

  const setActive = useSetRecordActive(COLLECTION, id ?? '', {
    noun: 'contact',
    recordName: values ? displayNameOf(values) : (id ?? ''),
  })

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
        back
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
          {/* <Full Name> - <Account>, then the Contact Role beneath. */}
          {account && (
            <>
              <span className="text-muted-foreground font-normal">-</span>
              <Link
                className="font-normal underline-offset-2 hover:underline"
                to={`/accounts/${values?.account}`}
              >
                {displayNameOf(account)}
              </Link>
            </>
          )}
          {inactive && (
            <Badge variant="outline" className="text-muted-foreground">
              Inactive
            </Badge>
          )}
        </>
      }
      subtitle={roleLabel || undefined}
      actions={
        !editing && (
          <>
            <Button variant="outline" onClick={() => setEditing(true)} disabled={isLoading}>
              <PencilIcon className="size-4" />
              Edit
            </Button>
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
              key={`edit:${id}:${dataUpdatedAt}`}
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

    {values && (
      <DeleteRecordDialog
        open={deleting}
        onOpenChange={setDeleting}
        collection={COLLECTION}
        recordId={id ?? ''}
        recordName={displayNameOf(values)}
        noun="contact"
        active={!inactive}
        lookupTarget="contact"
        referrers={CONTACT_REFERRERS}
        onDeleted={() => navigate('/contacts')}
        guidance={
          <ul className="text-muted-foreground list-disc space-y-0.5 pl-4">
            <li>
              <strong className="text-foreground">Deactivate</strong> keeps them on every record that names them, but
              hides them from new picks.
            </li>
            <li>
              <strong className="text-foreground">Delete permanently</strong> removes them for good. Use it only if
              they were added by mistake.
            </li>
          </ul>
        }
      />
    )}
    </>
  )
}
