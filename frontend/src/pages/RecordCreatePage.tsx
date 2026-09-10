import { useMemo } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'

import { PageLayout } from '@/components/layout/PageLayout'
import { RecordEditor } from '@/components/record/RecordEditor'
import { fieldOf } from '@/lib/spec'
import type { Values } from '@/lib/spec/conditions'

interface Props {
  module: string
  collection: string
  /** Where the list lives; a save navigates to `${basePath}/${newId}`. */
  basePath: string
  title: string
}

/**
 * A blank record of any module.
 *
 * Query parameters that name a field of the module prefill it, which is how
 * "Add contact" on an Account arrives here as `/contacts/new?account=ACC-001`.
 * Anything else in the query string is ignored rather than written into the
 * record.
 */
export function RecordCreatePage({ module, collection, basePath, title }: Props) {
  const navigate = useNavigate()
  const [search] = useSearchParams()

  const initialValues = useMemo(() => {
    const values: Values = {}
    for (const [key, value] of search.entries()) {
      if (fieldOf(module, key)) values[key] = value
    }
    return values
  }, [module, search])


  return (
    <PageLayout
      title={
        <>
          {title}
        </>
      }
      subtitle="Nothing is required to save — only the formats are checked."
      tabs={[
        {
          key: 'new',
          label: 'Details',
          content: (
            <RecordEditor
              module={module}
              collection={collection}
              initialValues={initialValues}
              saveLabel="Create"
              onSaved={(id) => navigate(`${basePath}/${id}`, { replace: true })}
              onCancel={() => navigate(basePath)}
            />
          ),
        },
      ]}
    />
  )
}
