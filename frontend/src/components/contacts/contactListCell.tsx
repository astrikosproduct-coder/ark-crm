import type { ReactNode } from 'react'

import {
  ConfidentialChip,
  ContactRoleBadge,
  isConfidentialContact,
} from '@/components/contacts/ContactRoleBadge'
import type { ListRow } from '@/components/list/ListCell'
import type { FieldSpec } from '@/types/field'

/**
 * The two contact columns that read as something other than their raw value.
 * Passed to RecordListView wherever contacts are listed — the module list and
 * the child list on an Account — so both look the same.
 */
export function contactListCell(field: FieldSpec, row: ListRow): ReactNode | undefined {
  if (field.api_name === 'contact_role') {
    return <ContactRoleBadge value={row.contact_role} />
  }

  if (field.api_name === 'full_name') {
    return (
      <span className="flex items-center gap-2">
        <span className="font-medium">{String(row.full_name ?? '—')}</span>
        {isConfidentialContact(row) && <ConfidentialChip />}
      </span>
    )
  }

  return undefined
}
