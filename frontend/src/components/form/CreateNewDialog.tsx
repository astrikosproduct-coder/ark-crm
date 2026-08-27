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
import { collectionFor, quickCreateExtraFieldsFor, sectionsFor } from '@/lib/spec'
import { useDraftStore } from '@/store/useDraftStore'
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

  // Namespaced per originating field, not just "new" — otherwise creating an
  // account here while /accounts/new also has an open draft would have the
  // two stomp on the same draft-store key.
  const recordId = field ? `new@${field.qref}` : ''

  // The Cancel button and a successful create both already call onClose;
  // ESC / overlay-click reach it through Dialog's onOpenChange instead, which
  // is wired on this outer component rather than inside the RecordFormProvider
  // below. Clearing here, once, covers all three paths without threading a
  // form reference through each of them.
  const closeAndClearDraft = () => {
    if (module) useDraftStore.getState().clearDraft(module, recordId)
    onClose()
  }

  if (!field) return null

  return (
    <Dialog open onOpenChange={(open) => !open && closeAndClearDraft()}>
      <DialogContent className="max-h-[85vh] max-w-2xl overflow-y-auto">
        <DialogHeader>
          <DialogTitle>New {target.replace(/_/g, ' ')}</DialogTitle>
          <DialogDescription>
            Created from {field.label}. Only the first section is shown, plus a few fields from
            later sections that matter from day one — enough to make the record selectable.
          </DialogDescription>
        </DialogHeader>

        {module && collection ? (
          <RecordFormProvider module={module} mode="edit" recordId={recordId}>
            <CreateNewBody
              module={module}
              collection={collection}
              onClose={closeAndClearDraft}
              onCreated={onCreated}
            />
          </RecordFormProvider>
        ) : (
          <p className="text-sm text-muted-foreground">
            The register has no module describing a {target}, so one cannot be created here.
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
  const fields = [...firstSectionFields, ...extraFields]

  const create = useMutation({
    mutationFn: async () => (await api.post(`/${collection}`, form.toPayload())).data,
    onSuccess: (record: Record<string, unknown>) => {
      void queryClient.invalidateQueries({ queryKey: ['collection', collection] })
      const id = record.id ?? record.sku ?? record.code
      if (typeof id === 'string') onCreated(id)
      // onClose clears the draft (see closeAndClearDraft above) — a created
      // record must not leave one behind to resurrect on the next "+ Create
      // new" from this same field.
      onClose()
    },
  })

  const submit = () => {
    form.markSubmitted()
    if (Object.keys(form.allErrors).length > 0) return
    create.mutate()
  }

  return (
    <>
      <div className="grid gap-x-6 gap-y-4 md:grid-cols-2">
        {fields.map((f) => (
          <FieldRow key={f.qref} field={f} />
        ))}
      </div>

      {create.isError && (
        <p className="text-sm text-destructive">Could not create the record.</p>
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
