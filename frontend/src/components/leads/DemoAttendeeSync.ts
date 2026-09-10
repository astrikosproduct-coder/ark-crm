import type { QueryClient } from '@tanstack/react-query'

import { api } from '@/lib/api'
import { childFieldSyncFor } from '@/lib/spec/childSpec'
import { fieldOf } from '@/lib/spec'
import type { Values } from '@/lib/spec/conditions'

/**
 * The reverse half of demo_attendees' child_field_sync (see
 * spec/extensions.json leads.demo_attendees and ChildRowSync in
 * ChildListTable.tsx, which does the live Contact -> row direction).
 *
 * Called from RecordEditor's afterSave once a Lead's Stage 1 — Demo
 * Presentation section has saved. For every attendee row that carries a
 * value its own Contact record does not, writes the gap onto that Contact
 * and logs it — a background write to records the user is not looking at,
 * so CLAUDE.md rule 6 has it recorded rather than silent.
 *
 * Reads the mirror mapping from the same sidecar entry the live direction
 * uses, rather than restating job_title/organisation/attendee_role here —
 * the two directions can only drift out of step if someone edits the JSON.
 */
export async function backfillContactsFromDemoAttendees(
  record: Record<string, unknown>,
  queryClient: QueryClient
): Promise<void> {
  const field = fieldOf('leads', 'demo_attendees')
  const sync = field && childFieldSyncFor(field)
  if (!sync) return

  const rows = Array.isArray(record.demo_attendees) ? (record.demo_attendees as Values[]) : []
  if (rows.length === 0) return

  const touchedContacts = new Set<string>()

  for (const row of rows) {
    const contactId = typeof row[sync.trigger_column] === 'string' ? (row[sync.trigger_column] as string) : undefined
    if (!contactId) continue

    // Same rule as every other background gap-fill in this app: never fail
    // the save this ran alongside over a network hiccup on a side effect.
    try {
      const contact = (await api.get<Values>(`/${sync.target_module}/${contactId}`)).data

      const patch: Values = {}
      for (const [rowColumn, targetField] of Object.entries(sync.mirror)) {
        if (row[rowColumn] && !contact[targetField]) patch[targetField] = row[rowColumn]
      }
      if (Object.keys(patch).length === 0) continue

      await api.put(`/${sync.target_module}/${contactId}`, patch)
      touchedContacts.add(contactId)
    } catch (error) {
      console.error('[demo-attendee-sync] could not backfill contact fields', error)
    }
  }

  if (touchedContacts.size === 0) return
  await Promise.all([
    queryClient.invalidateQueries({ queryKey: ['list', sync.target_module] }),
    queryClient.invalidateQueries({ queryKey: ['collection', sync.target_module] }),
    ...[...touchedContacts].map((id) =>
      queryClient.invalidateQueries({ queryKey: ['record', sync.target_module, id] })
    ),
  ])
}
