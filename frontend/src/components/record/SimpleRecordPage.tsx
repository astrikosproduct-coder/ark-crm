import { useMemo, useState, type ReactNode } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { PencilIcon, RotateCcwIcon, Trash2Icon } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { PageLayout, type PageTab } from '@/components/layout/PageLayout'
import { RecordForm } from '@/components/form/RecordForm'
import { DeleteRecordDialog } from '@/components/record/DeleteRecordDialog'
import { RecordEditor } from '@/components/record/RecordEditor'
import { api } from '@/lib/api'
import { useSetRecordActive } from '@/lib/recordLifecycle'
import { displayNameOf, withRecordId } from '@/lib/spec'
import { cn } from '@/lib/utils'

type Values = Record<string, unknown>

export interface SimpleRecordPageProps {
  /** The register module whose form this is. */
  module: string
  /** The API collection the record is read from and saved to. */
  collection: string
  /** Where the list lives — where Delete goes back to. */
  listPath: string
  /** Singular, for the copy: "price book", "size". */
  noun: string
  /** Draw Edit, Reactivate and Delete. Presentation only — the server decides. */
  canEdit: boolean
  /** Under the title. */
  subtitle?: (values: Values) => ReactNode
  /** Beside the name in the title — a "Standard" mark, a status. */
  badge?: (values: Values) => ReactNode
  /** Buttons before Edit — "Make current". */
  actions?: (values: Values) => ReactNode
  /** Tabs after Overview — a price book's Prices. */
  tabs?: (values: Values) => PageTab[]
  /**
   * Offer Delete (with Deactivate beside it) for this record. Left out, every
   * record is offered it. A page that deletes by its own rules — an edition —
   * returns false and puts its own button in `actions`.
   */
  deletable?: (values: Values) => boolean
  /** In the delete dialog: the sentence under the title, and the bullets below it. */
  deleteDescription?: string
  deleteGuidance?: ReactNode
}

/**
 * One record of a small module — a price book, a size, an edition — with
 * nothing of its own but the register's form: Overview to read it, Edit to
 * change it, and Delete with Deactivate beside it, as an Account has.
 *
 * Everything on it is the register's. A page that needs more passes a badge,
 * a button or a tab; none of them names a field here.
 */
export function SimpleRecordPage({
  module,
  collection,
  listPath,
  noun,
  canEdit,
  subtitle,
  badge,
  actions,
  tabs,
  deletable,
  deleteDescription,
  deleteGuidance,
}: SimpleRecordPageProps) {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const [editing, setEditing] = useState(false)
  const [deleting, setDeleting] = useState(false)

  const { data, isLoading, isError, dataUpdatedAt } = useQuery({
    queryKey: ['record', collection, id],
    queryFn: async () => (await api.get<Values>(`/${collection}/${id}`)).data,
    enabled: Boolean(id),
  })
  const values = useMemo(() => (data ? withRecordId(module, data) : undefined), [data, module])
  const name = values ? displayNameOf(values) : ''
  const setActive = useSetRecordActive(collection, id ?? '', { noun, recordName: name })

  if (isError) {
    const label = noun.charAt(0).toUpperCase() + noun.slice(1)
    return (
      <PageLayout
        back
        title={label}
        tabs={[
          {
            key: 'missing',
            label: 'Overview',
            content: <p className="py-6 text-sm text-destructive">This {noun} no longer exists. It may have been deleted.</p>,
          },
        ]}
      />
    )
  }

  // `active` is absent on a record with no such flag (an edition): never inactive.
  const inactive = values?.active === false
  const mayDelete = Boolean(values) && (deletable ? deletable(values!) : true)

  return (
    <>
      <PageLayout
        back
        title={
          <>
            <span className={cn(inactive && 'text-muted-foreground')}>{name}</span>
            {values && badge?.(values)}
            {inactive && <span className="text-muted-foreground text-sm font-normal">Inactive</span>}
          </>
        }
        subtitle={values ? subtitle?.(values) : undefined}
        actions={
          canEdit &&
          !editing &&
          values && (
            <>
              {actions?.(values)}
              <Button variant="outline" onClick={() => setEditing(true)} disabled={isLoading}>
                <PencilIcon className="size-4" />
                Edit
              </Button>
              {inactive && (
                <Button variant="outline" onClick={() => setActive.mutate(true)} disabled={setActive.isPending}>
                  <RotateCcwIcon className="size-4" />
                  {setActive.isPending ? 'Reactivating…' : 'Reactivate'}
                </Button>
              )}
              {mayDelete && (
                <Button variant="outline" onClick={() => setDeleting(true)} className="text-destructive hover:text-destructive">
                  <Trash2Icon className="size-4" />
                  Delete
                </Button>
              )}
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
              // A RecordForm seeds its state once, so both of these are keyed
              // on the fetch that produced their values.
              <RecordEditor
                key={`edit:${id}:${dataUpdatedAt}`}
                module={module}
                collection={collection}
                recordId={id}
                initialValues={values}
                onSaved={() => setEditing(false)}
                onCancel={() => setEditing(false)}
              />
            ) : (
              <div className="py-3">
                <RecordForm key={`view:${id}:${dataUpdatedAt}`} module={module} mode="view" values={values} />
              </div>
            ),
          },
          ...(values && tabs ? tabs(values) : []),
        ]}
      />

      {values && canEdit && mayDelete && (
        <DeleteRecordDialog
          open={deleting}
          onOpenChange={setDeleting}
          collection={collection}
          recordId={id ?? ''}
          recordName={name}
          noun={noun}
          active={!inactive}
          // Nothing points at one of these by a lookup the browser can scan;
          // what uses it is the server's to say, and its refusal is shown.
          lookupTarget={module}
          referrers={[]}
          onDeleted={() => navigate(listPath)}
          guidance={deleteGuidance}
          freeDescription={deleteDescription}
        />
      )}
    </>
  )
}
