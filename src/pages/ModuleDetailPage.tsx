import { useState } from 'react'
import { useParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'

import { PageLayout } from '@/components/layout/PageLayout'
import { CreateNewDialog } from '@/components/form/CreateNewDialog'
import { FormSection } from '@/components/form/RecordForm'
import { RecordFormProvider, useRecordForm } from '@/hooks/useRecordForm'
import { api } from '@/lib/api'
import { humanize } from '@/lib/format'
import { moduleFor } from '@/lib/modules'
import { collectionFor, sectionsFor } from '@/lib/spec'
import { ComingSoon } from '@/pages/ComingSoon'
import type { FieldSpec } from '@/types/field'

/**
 * The generic record screen. It has no knowledge of any particular module —
 * the form engine renders whatever the spec holds for the :module in the URL.
 */
export function ModuleDetailPage() {
  const { module, id } = useParams<{ module: string; id: string }>()
  const key = module ?? ''
  const label = moduleFor(key)?.label ?? humanize(key)
  const collection = collectionFor(key.replace(/s$/, '')) ?? key

  const { data, isLoading } = useQuery({
    queryKey: ['record', collection, id],
    queryFn: async () => (await api.get(`/${collection}/${id}`)).data,
    enabled: Boolean(id),
  })

  return (
    <PageLayout
      title={id ?? ''}
      subtitle={label}
      tabs={[
        {
          key: 'overview',
          label: 'Overview',
          content: isLoading ? (
            <p className="py-6 text-sm text-muted-foreground">Loading…</p>
          ) : (
            <RecordFormProvider
              key={`${key}:${id}`}
              module={key}
              mode="view"
              initialValues={(data as Record<string, unknown>) ?? {}}
            >
              <RecordBody module={key} />
            </RecordFormProvider>
          ),
        },
        { key: 'activity', label: 'Activity', content: <ComingSoon label="Activity" /> },
      ]}
    />
  )
}

function RecordBody({ module }: { module: string }) {
  const form = useRecordForm()
  const [creatingFor, setCreatingFor] = useState<FieldSpec | null>(null)

  return (
    <div className="space-y-3 py-3">
      {sectionsFor(module).map((section) => (
        <FormSection key={section} module={module} section={section} onCreateNew={setCreatingFor} />
      ))}

      <CreateNewDialog
        field={creatingFor}
        onClose={() => setCreatingFor(null)}
        onCreated={(recordId) => {
          if (creatingFor) form.setValue(creatingFor.api_name, recordId)
        }}
      />
    </div>
  )
}
