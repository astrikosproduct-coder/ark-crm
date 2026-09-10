import { CheckIcon } from 'lucide-react'

import { date as fmtDate, dateTime as fmtDateTime, money, number, percent } from '@/lib/format'
import { labelForValue } from '@/lib/spec'
import type { FieldSpec } from '@/types/field'

/** A list row as the mock server returns it: the record plus joined labels. */
export type ListRow = Record<string, unknown> & {
  __labels?: Record<string, string>
}

export const NUMERIC_TYPES = new Set(['number', 'currency', 'percent'])

/**
 * One cell, rendered from the field's spec type. Nothing here knows which
 * module it is showing — the same component renders an account's Segment and a
 * contact's Relationship Score.
 */
export function ListCell({ field, row }: { field: FieldSpec; row: ListRow }) {
  const value = row[field.api_name]

  if (value === null || value === undefined || value === '') {
    return <span className="text-muted-foreground">—</span>
  }

  switch (field.type) {
    case 'lookup':
      // Joined by the list endpoint rather than resolved per row, so a page of
      // 25 contacts is one request and not twenty-six.
      return <span>{row.__labels?.[field.api_name] ?? String(value)}</span>

    case 'multiselect':
      // Comma-separated text, not a row of filled chips: several values are
      // still one field, and they read as one sentence.
      return (
        <span>
          {(Array.isArray(value) ? value : [value])
            .map((v) => labelForValue(field.picklist, v))
            .join(', ')}
        </span>
      )

    case 'picklist':
      return <span>{labelForValue(field.picklist, value)}</span>

    case 'checkbox':
      return value ? (
        <CheckIcon className="size-4" aria-label="Yes" />
      ) : (
        <span className="text-muted-foreground">—</span>
      )

    case 'currency':
      return <span className="tabular-nums">{money(value)}</span>

    case 'percent':
      return <span className="tabular-nums">{percent(value)}</span>

    case 'number':
      return <span className="tabular-nums">{number(value)}</span>

    case 'date':
      return <span className="whitespace-nowrap">{fmtDate(value)}</span>

    case 'datetime':
      return <span className="whitespace-nowrap">{fmtDateTime(value)}</span>

    default:
      return <span>{String(value)}</span>
  }
}
