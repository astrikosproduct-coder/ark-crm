import { useRef } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'

import { FieldControl } from '@/components/form/FieldControl'
import { RecordFormProvider } from '@/hooks/useRecordForm'
import { api } from '@/lib/api'
import { fieldsOf } from '@/lib/spec'
import type { Values } from '@/lib/spec/conditions'

/** Synthetic section name for a field that is current state rather than
 * something a stage captures — never rendered as a collapsible form section,
 * only here. See spec/extensions.json new_fields (overall_rag and friends). */
export const HEADER_STRIP_SECTION = '__header'

const SAVE_DEBOUNCE_MS = 300

interface Props {
  module: string
  collection: string
  recordId: string
  values: Values
  readOnly: boolean
}

/**
 * The key-facts strip above the tabs: Overall RAG, Next Milestone and
 * whatever else a module declares in the __header section. Unlike every
 * other field on a pipeline record, these are edited right here, immediately
 * — no Edit button, no stage gate. They are current state, not something a
 * stage transition sets.
 *
 * Wrapped in its own RecordFormProvider purely so FieldControl has the
 * context hook it always calls — every value and every write below goes
 * through `scope`, never through the provider's own state, so nothing here
 * ever becomes a draft. The record id is namespaced ("header:...") so it can
 * never collide with the real edit form's draft for the same record.
 */
export function HeaderStrip({ module, collection, recordId, values, readOnly }: Props) {
  const fields = fieldsOf(module).filter((f) => f.section === HEADER_STRIP_SECTION)
  if (fields.length === 0 || !recordId) return null

  return (
    <RecordFormProvider module={module} mode="edit" recordId={`header:${recordId}`}>
      <HeaderStripBody
        collection={collection}
        recordId={recordId}
        fields={fields}
        values={values}
        readOnly={readOnly}
      />
    </RecordFormProvider>
  )
}

function HeaderStripBody({
  collection,
  recordId,
  fields,
  values,
  readOnly,
}: {
  collection: string
  recordId: string
  fields: ReturnType<typeof fieldsOf>
  values: Values
  readOnly: boolean
}) {
  const queryClient = useQueryClient()
  const timers = useRef<Record<string, ReturnType<typeof setTimeout>>>({})

  const save = useMutation({
    mutationFn: async (patch: Values) => (await api.put(`/${collection}/${recordId}`, patch)).data,
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['record', collection, recordId] }),
        queryClient.invalidateQueries({ queryKey: ['list', collection] }),
        queryClient.invalidateQueries({ queryKey: ['collection', collection] }),
      ])
    },
  })

  const setField = (apiName: string, value: unknown) => {
    clearTimeout(timers.current[apiName])
    timers.current[apiName] = setTimeout(() => save.mutate({ [apiName]: value }), SAVE_DEBOUNCE_MS)
  }

  return (
    <div className="mb-4 flex flex-wrap items-center gap-x-6 gap-y-2 rounded-lg border bg-muted/20 px-4 py-2.5">
      {fields.map((field) => (
        <div key={field.qref} className="flex min-w-0 items-center gap-2">
          <span className="shrink-0 text-xs font-medium text-muted-foreground">{field.label}</span>
          <div className="w-36 shrink-0">
            <FieldControl
              field={field}
              scope={{
                value: values[field.api_name],
                set: (v) => setField(field.api_name, v),
                mode: readOnly ? 'view' : 'edit',
                id: `header.${field.qref}`,
              }}
            />
          </div>
        </div>
      ))}
    </div>
  )
}
