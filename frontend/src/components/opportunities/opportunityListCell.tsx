import type { ReactNode } from 'react'
import { UsersIcon } from 'lucide-react'

import type { ListRow } from '@/components/list/ListCell'
import { StageChip } from '@/components/leads/StageChip'
import { PriorityFlagSlot } from '@/components/opportunities/PriorityFlagMark'
import { RevenueAmount } from '@/components/pipeline/RevenueAmount'
import { percent } from '@/lib/format'
import type { FieldSpec } from '@/types/field'

/**
 * opportunity_name, end_client and the owners are read_through fields — an
 * Opportunity record does not store them. The LIST endpoint resolves them onto
 * each row from the root Lead (backend/app/read_through_rows.py), so a list
 * cell reads the row like any other. Until 17 Sep 2026 each cell fetched its
 * parent Lead itself, one request per row, and the server could not search,
 * sort or filter these columns at all.
 *
 * Only for LIST rows. A record read still carries none of these — the record
 * page resolves them with useResolvedRecord.
 */
export function ReadThroughText({ row, apiName }: { row: ListRow; apiName: string }) {
  const value = row[apiName]
  if (typeof value !== 'string' || !value) return <span className="text-muted-foreground">—</span>
  return <span className="font-medium">{value}</span>
}

/** A read-through LOOKUP on a list row: its display name, joined by the server. */
export function ReadThroughLookup({ row, apiName }: { row: ListRow; apiName: string; lookupTarget?: string | null }) {
  const label = row.__labels?.[apiName]
  if (!label) return <span className="text-muted-foreground">—</span>
  return <span>{label}</span>
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
    // Low Hanging / Top 10 mark in a fixed-width slot AFTER the name, so the
    // name column keeps one left edge. See PriorityFlagMark.
    return (
      <span className="inline-flex items-center gap-1.5">
        {/* Name first. The priority mark follows it — see PriorityFlagSlot. */}
        <ReadThroughText row={row} apiName="opportunity_name" />
        <PriorityFlagSlot row={row} />
        {/* Pursuit Group is not a column any more: a grouped pursuit carries
            this mark, and the group's name is one hover away. */}
        {typeof row.pursuit_group === 'string' && row.pursuit_group && (
          <span
            className="text-muted-foreground ml-1.5 inline-flex"
            title={`In ${row.__labels?.pursuit_group ?? 'a pursuit group'}${row.is_primary_pursuit ? '' : ' · secondary pursuit'}`}
          >
            <UsersIcon className="size-3.5" aria-label="In a pursuit group" />
          </span>
        )}
      </span>
    )
  }

  if (field.api_name === 'total_value_tcv') {
    return <RevenueAmount row={row} />
  }

  if (field.api_name === 'project_stage') {
    return <StageChip value={row.project_stage} />
  }

  // Both are set from the stage (app/progression.py) and are FRACTIONS (0.70
  // is 70%); percent() turns that into "70%", never "0.7%" — see lib/format.ts.
  if (field.api_name === 'probability_pct' || field.api_name === 'progression_pct') {
    const v = row[field.api_name]
    if (v === null || v === undefined || v === '') return <span className="text-muted-foreground">—</span>
    return <span className="tabular-nums">{percent(v)}</span>
  }

  return undefined
}
