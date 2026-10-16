import { useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'

import { MultiSelect } from '@/components/form/MultiSelect'
import { fetchCollection } from '@/lib/collections'
import { applyLookupFilter } from '@/lib/spec/conditions'
import { collectionFor, displayNameOf, idOf } from '@/lib/spec'
import type { FieldSpec, PicklistOption } from '@/types/field'

type Record_ = Record<string, unknown>

interface Props {
  field: FieldSpec
  value: string[]
  onChange: (value: string[]) => void
  disabled?: boolean
  id?: string
}

/**
 * The rows a several-pick field offers, as the options MultiSelect draws.
 *
 * A multiselect that names a `lookup_target` picks RECORDS, not choices —
 * Secondary S!aP Suites picks products. The offer is the single lookup's:
 * the field's own filter, and nothing deactivated.
 *
 * A value already on the record always stays among the options, whatever it
 * is. That covers a product since retired, and what was typed into the field
 * before the catalogue existed — it shows as the text it is, so it can be
 * seen and removed rather than silently dropped.
 */
function useLookupOptions(field: FieldSpec, value: string[]) {
  const collection = collectionFor(field.lookup_target)
  const { data, isLoading } = useQuery({
    queryKey: ['collection', collection],
    queryFn: () => fetchCollection<Record_>(collection!),
    enabled: Boolean(collection),
    staleTime: 30_000,
  })

  return useMemo(() => {
    const all = Array.isArray(data) ? data : []
    const offered = applyLookupFilter(all, field.lookup_filter_expr).filter((row) => row.active !== false)
    const options: PicklistOption[] = offered.map((row, index) => ({
      key: idOf(row),
      label: displayNameOf(row),
      sort: index,
      active: true,
    }))
    for (const held of value) {
      if (options.some((o) => o.key === held)) continue
      const row = all.find((r) => idOf(r) === held)
      options.push({ key: held, label: row ? displayNameOf(row) : held, sort: options.length, active: true })
    }
    return { options, loading: isLoading }
  }, [data, field.lookup_filter_expr, value, isLoading])
}

/** Several records picked from one collection — the multiselect twin of LookupCombobox. */
export function LookupMultiSelect({ field, value, onChange, disabled, id }: Props) {
  const { options, loading } = useLookupOptions(field, value)
  return (
    <MultiSelect
      id={id}
      options={options}
      value={value}
      onChange={onChange}
      disabled={disabled}
      placeholder={loading ? 'Loading…' : `Search ${field.lookup_target}…`}
    />
  )
}

/** The names of the records picked, on a record being read — one line, as any multiselect. */
export function LookupValues({ field, value }: { field: FieldSpec; value: string[] }) {
  const { options } = useLookupOptions(field, value)
  return (
    <p className="px-3 py-2 text-sm">
      {value.map((v) => options.find((o) => o.key === v)?.label ?? v).join(', ')}
    </p>
  )
}
