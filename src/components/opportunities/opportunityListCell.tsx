import type { ReactNode } from 'react'
import { useQuery } from '@tanstack/react-query'

import type { ListRow } from '@/components/list/ListCell'
import { StageChip } from '@/components/leads/StageChip'
import { useResolvedRecord } from '@/hooks/useResolvedRecord'
import { api } from '@/lib/api'
import { collectionFor, displayNameOf, idOf } from '@/lib/spec'
import type { FieldSpec } from '@/types/field'

/**
 * opportunity_name and end_client are read_through fields — an Opportunity
 * record does not store them, so `row.opportunity_name` and `row.end_client`
 * are undefined on every row the list endpoint returns, exactly as they are on
 * the record itself. The record page resolves them with useResolvedRecord;
 * this cell does the same thing, once per row, which is the reason it is a
 * component and not a plain string lookup like the rest of leadListCell.
 */
export function ReadThroughText({ row, apiName }: { row: ListRow; apiName: string }) {
  const resolved = useResolvedRecord('opportunities', row)
  const value = resolved.values[apiName]
  if (typeof value !== 'string' || !value) return <span className="text-muted-foreground">—</span>
  return <span className="font-medium">{value}</span>
}

/**
 * A read-through LOOKUP field, resolved twice over: once through the parent
 * chain to find which account id the Lead holds, then — same as LookupValue in
 * FieldControl.tsx — from that id to a display name, off the same cached
 * `/accounts` collection every other lookup in the app reads.
 */
export function ReadThroughLookup({
  row,
  apiName,
  lookupTarget,
}: {
  row: ListRow
  apiName: string
  lookupTarget: string | null
}) {
  const resolved = useResolvedRecord('opportunities', row)
  const value = resolved.values[apiName]
  const collection = collectionFor(lookupTarget)

  const { data } = useQuery({
    queryKey: ['collection', collection],
    queryFn: async () => (await api.get<Record<string, unknown>[]>(`/${collection}`)).data,
    enabled: Boolean(collection) && typeof value === 'string' && Boolean(value),
    staleTime: 30_000,
  })

  if (typeof value !== 'string' || !value) return <span className="text-muted-foreground">—</span>
  const hit = data?.find((r) => idOf(r) === value)
  return <span>{hit ? displayNameOf(hit) : value}</span>
}

/**
 * The Opportunities list columns that read as something other than their raw
 * value. opportunity_name and end_client are read-through — see the two
 * components above; everything else on the list_views.opportunities columns
 * (project_stage, total_value_tcv, submission_deadline, probability_pct,
 * progression_pct) is a real field stored on the Opportunity itself, so it
 * falls through to the default ListCell renderer.
 */
export function opportunityListCell(field: FieldSpec, row: ListRow): ReactNode | undefined {
  if (field.api_name === 'opportunity_name') {
    return <ReadThroughText row={row} apiName="opportunity_name" />
  }

  if (field.api_name === 'end_client' || field.api_name === 'customer_partner_si') {
    return <ReadThroughLookup row={row} apiName={field.api_name} lookupTarget={field.lookup_target} />
  }

  if (field.api_name === 'project_stage') {
    return <StageChip value={row.project_stage} />
  }

  if (field.api_name === 'probability_pct') {
    const v = row.probability_pct
    if (v === null || v === undefined || v === '') return <span className="text-muted-foreground">—</span>
    return <span className="tabular-nums">{String(v)}%</span>
  }

  return undefined
}
