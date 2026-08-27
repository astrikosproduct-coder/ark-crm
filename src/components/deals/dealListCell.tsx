import type { ReactNode } from 'react'

import type { ListRow } from '@/components/list/ListCell'
import { StageChip } from '@/components/leads/StageChip'
import type { FieldSpec } from '@/types/field'

/**
 * The Deals list columns that read as something other than their raw value —
 * same pattern as leadListCell.
 */
export function dealListCell(field: FieldSpec, row: ListRow): ReactNode | undefined {
  if (field.api_name === 'deal_id') {
    // autonumber field the store never actually stores under this key — see
    // withRecordId — a raw list row carries the record id as `id` instead.
    return <span className="font-medium">{String(row.id ?? '—')}</span>
  }

  if (field.api_name === 'deal_name') {
    return <span className="font-medium">{String(row.deal_name ?? '—')}</span>
  }

  if (field.api_name === 'deal_stage') {
    return <StageChip value={row.deal_stage} />
  }

  return undefined
}
