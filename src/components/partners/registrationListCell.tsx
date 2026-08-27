import type { ReactNode } from 'react'

import type { ListRow } from '@/components/list/ListCell'
import { RegistrationStatusChip } from '@/components/partners/RegistrationStatusChip'
import { date as fmtDate } from '@/lib/format'
import { daysRemainingText, registrationState } from '@/lib/partners'
import type { FieldSpec } from '@/types/field'

/**
 * The two registration columns that read as something other than their stored
 * value. Used by both the Registrations tab and the child list on a partner, so
 * the same registration reads the same way in both places.
 */
export function registrationListCell(field: FieldSpec, row: ListRow): ReactNode | undefined {
  if (field.api_name === 'registration_status') {
    return <RegistrationStatusChip state={registrationState(row)} />
  }

  // The register carries the expiry date; days remaining is what a reviewer
  // actually reads off the screen, so the column shows both.
  if (field.api_name === 'exclusivity_expiry_date') {
    const state = registrationState(row)
    if (!state.expiry) {
      return <span className="text-muted-foreground">not yet acknowledged</span>
    }
    return (
      <span className="whitespace-nowrap">
        {fmtDate(state.expiry)}
        <span className="text-muted-foreground"> · {daysRemainingText(state)}</span>
      </span>
    )
  }

  if (field.api_name === 'project_name') {
    return <span className="font-medium">{String(row.project_name ?? '—')}</span>
  }

  return undefined
}
