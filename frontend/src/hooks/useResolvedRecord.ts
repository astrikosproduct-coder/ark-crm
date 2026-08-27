import { useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'

import { api } from '@/lib/api'
import { parentModuleOf } from '@/lib/spec'
import type { Values } from '@/lib/spec/conditions'
import {
  parentRequestFor,
  resolveRecord,
  unresolved as noParents,
  type ParentRecords,
  type ResolvedRecord,
} from '@/lib/spec/resolveRecord'

/**
 * The fetching half of the effective record. resolveRecord does the merge and
 * knows nothing about the network; this walks the chain over /api so CLAUDE.md
 * rule 2 holds — no component, and no library function under one, reads the
 * Zustand store directly.
 *
 * The chain is two links long by declaration (Deal -> Opportunity -> Lead), so
 * it is two queries rather than a loop: hooks cannot be called in one, and a
 * generic walker for a fixed depth of two would be more machinery than rule.
 * Each is enabled only once the record above it has arrived and actually names
 * a parent, so a Lead fires nothing at all.
 */
export interface UseResolvedRecord extends ResolvedRecord {
  /** True while an ancestor is still in flight. */
  isLoading: boolean
}

/** Pipeline collections are named after their module. */
function collectionOf(module: string): string {
  return module
}

function useParent(request: { module: string; id: string } | undefined) {
  const { data, isLoading } = useQuery({
    queryKey: ['record', request?.module, request?.id],
    queryFn: async () =>
      (await api.get<Values>(`/${collectionOf(request?.module ?? '')}/${request?.id}`)).data,
    enabled: Boolean(request?.module && request?.id),
  })
  return { record: data, isLoading: Boolean(request) && isLoading }
}

export function useResolvedRecord(module: string, record: Values | undefined): UseResolvedRecord {
  const parentRequest = parentRequestFor(module, record)
  const parent = useParent(parentRequest)

  const grandparentRequest = parentRequest
    ? parentRequestFor(parentRequest.module, parent.record)
    : undefined
  const grandparent = useParent(grandparentRequest)

  // Named primitives, not the request objects: those are rebuilt every render,
  // so depending on them directly would defeat the memo and re-resolve on every
  // keystroke in the form below.
  const parentModuleName = parentRequest?.module
  const grandparentModuleName = grandparentRequest?.module
  const parentRecord = parent.record
  const grandparentRecord = grandparent.record

  const parents: ParentRecords = useMemo(() => {
    const out: ParentRecords = {}
    if (parentModuleName && parentRecord) out[parentModuleName] = parentRecord
    if (grandparentModuleName && grandparentRecord) out[grandparentModuleName] = grandparentRecord
    return out
  }, [parentModuleName, parentRecord, grandparentModuleName, grandparentRecord])

  const resolved = useMemo(() => {
    if (!parentModuleOf(module)) return noParents(record)
    return resolveRecord(module, record, parents)
  }, [module, record, parents])

  // Memoised, not spread fresh each render. The result is a prop on
  // RecordFormProvider, where it feeds the inherited-values memo, which feeds
  // the computed-fields memo, which feeds validation — a new object identity
  // here would recompute the whole chain on every keystroke in the form.
  const isLoading = parent.isLoading || grandparent.isLoading
  return useMemo(() => ({ ...resolved, isLoading }), [resolved, isLoading])
}
