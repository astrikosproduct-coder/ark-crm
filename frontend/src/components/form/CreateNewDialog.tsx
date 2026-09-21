import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'

import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { FieldRow } from '@/components/form/FieldRow'
import { RecordFormProvider, useRecordForm, visibleFieldsOf } from '@/hooks/useRecordForm'
import { api } from '@/lib/api'
import { ErrorNotice } from '@/components/ui/notice'
import { collectionFor, fieldOf, fieldsOf, quickCreateExtraFieldsFor, sectionsFor } from '@/lib/spec'
import { isUserEditable } from '@/lib/spec/validation'
import type { FieldSpec } from '@/types/field'

/**
 * The target module of a lookup. lookup_target names an entity; the form
 * engine needs the module whose fields describe it.
 */
const MODULE_OF: Record<string, string> = {
  account: 'accounts',
  contact: 'contacts',
  user: 'administration',
  lead: 'leads',
  deal: 'deals',
  quote: 'quotes',
  product: 'products',
  deal_registration: 'partners',
  poc: 'bids_pocs',
  bid: 'bids_pocs',
  gate: 'bids_pocs',
}

interface Props {
  /** The lookup field whose "+ Create new" was clicked. */
  field: FieldSpec | null
  onClose: () => void
  onCreated: (id: string) => void
}

export function CreateNewDialog({ field, onClose, onCreated }: Props) {
  const target = field?.lookup_target ?? ''
  const module = MODULE_OF[target]
  const collection = collectionFor(target)

  // Namespaced per originating field, not just "new" — two forms for the same
  // module can be open at once (this dialog over /accounts/new), and they are
  // different records.
  const recordId = field ? `new@${field.qref}` : ''

  if (!field) return null

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-h-[85vh] max-w-2xl overflow-y-auto">
        <DialogHeader>
          <DialogTitle>New {target.replace(/_/g, ' ')}</DialogTitle>
          <DialogDescription>
            Just the basics for now. Fill in the rest on the record later.
          </DialogDescription>
        </DialogHeader>

        {module && collection ? (
          <RecordFormProvider module={module} mode="edit" recordId={recordId}>
            <CreateNewBody
              module={module}
              collection={collection}
              onClose={onClose}
              onCreated={onCreated}
            />
          </RecordFormProvider>
        ) : (
          <p className="text-sm text-muted-foreground">
            A {target.replace(/_/g, ' ')} can&apos;t be created from here.
          </p>
        )}
      </DialogContent>
    </Dialog>
  )
}

function CreateNewBody({
  module,
  collection,
  onClose,
  onCreated,
}: {
  module: string
  collection: string
  onClose: () => void
  onCreated: (id: string) => void
}) {
  const form = useRecordForm()
  const queryClient = useQueryClient()
  const [section] = useState(() => sectionsFor(module)[0])

  const firstSectionFields = visibleFieldsOf(form, module, section)
  // A few fields outside the first section matter enough to ask for here too
  // — see quick_create in spec/extensions.json. Already-listed api_names are
  // skipped rather than shown twice.
  const extraFields = quickCreateExtraFieldsFor(module).filter(
    (f) => f.section !== section && form.isVisible(f)
  )
  // And every required field, wherever it sits: a save with one empty is
  // refused (decided 21 Sep 2026), so a shortcut that hid one could never
  // succeed. Classification on an Account, Engagement Owner on a Contact.
  const shown = new Set([...firstSectionFields, ...extraFields].map((f) => f.api_name))
  const requiredFields = fieldsOf(module).filter(
    (f) => !shown.has(f.api_name) && isUserEditable(f) && form.isVisible(f) && form.isRequired(f)
  )
  const fields = [...firstSectionFields, ...extraFields, ...requiredFields]

  const create = useMutation({
    mutationFn: async () => (await api.post(`/${collection}`, form.toPayload())).data,
    onSuccess: (record: Record<string, unknown>) => {
      void queryClient.invalidateQueries({ queryKey: ['collection', collection] })
      const id = record.id ?? record.sku ?? record.code
      if (typeof id === 'string') onCreated(id)
      // onClose clears the draft (see onClose above) — a created
      // record must not leave one behind to resurrect on the next "+ Create
      // new" from this same field.
      onClose()
    },
  })

  const submit = () => {
    form.markSubmitted()
    if (Object.keys(form.allErrors).length > 0 || Object.keys(form.dueRequired).length > 0) return
    create.mutate()
  }

  return (
    <>
      {/* A container, like FormSection's grid, so the rows inside can decide
          whether their labels sit beside the values — see FieldRow. The
          container wraps the grid because a container query cannot measure
          the element that declares it. */}
      <div className="@container">
        <div className="grid gap-x-10 gap-y-5 @3xl:grid-cols-2">
          {fields.map((f) => (
            <FieldRow key={f.qref} field={f} />
          ))}
        </div>
      </div>

      {create.isError && (
        <ErrorNotice error={create.error} fieldLabel={(name) => fieldOf(module, name)?.label} />
      )}

      <DialogFooter>
        <Button type="button" variant="outline" onClick={onClose}>
          Cancel
        </Button>
        <Button type="button" onClick={submit} disabled={create.isPending}>
          {create.isPending ? 'Creating…' : 'Create'}
        </Button>
      </DialogFooter>
    </>
  )
}
