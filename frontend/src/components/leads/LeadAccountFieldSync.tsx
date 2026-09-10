import { useEffect } from 'react'
import { useQuery, type QueryClient } from '@tanstack/react-query'

import { useRecordForm } from '@/hooks/useRecordForm'
import { api } from '@/lib/api'
import type { Values } from '@/lib/spec/conditions'

/**
 * Fields mirrored between a Lead's Connect-stage form and its End Client
 * account — every one shares the exact same picklist on both modules, so a
 * raw key copies across unchanged either direction.
 *
 * Segment is the only one left. Sub-Segment was deleted at the Country /
 * Theme / ROB-gap pass (its picklist deactivated, not removed — see
 * spec/picklists.json). Region was never in this list — accounts.region and
 * leads.region shared the India/MEA/APAC/Americas picklist but not their
 * values — and leads.region no longer exists at all: it was retired on 02 Sep
 * 2026 in favour of Destination Region and Booking Region, which say which
 * region delivers the work and which books the revenue. accounts.region is
 * untouched, and nothing on the Lead side is a candidate to mirror it now.
 * This stays at Segment alone until somebody asks otherwise
 */
const MIRRORED_FIELDS = ['segment'] as const

/**
 * Mirrors Segment between a Lead and its End Client account, in the
 * Connect-stage form only.
 *
 * Gap-fill, not overwrite: neither side ever clobbers a value someone already
 * entered. Account -> Lead happens live, here, the moment an End Client whose
 * own fields are set is chosen and the Lead's boxes are still empty —
 * mounted inside the Stage 0 form context purely for this effect; it renders
 * nothing. Lead -> Account is the reverse gap-fill and runs once, on save,
 * via backfillAccountFieldsFromLead below — writing to a DIFFERENT record is
 * not something this screen should do mid-keystroke.
 */
export function LeadAccountFieldSync() {
  const form = useRecordForm()
  const endClientId = typeof form.values.end_client === 'string' ? form.values.end_client : undefined

  const { data: account } = useQuery({
    queryKey: ['record', 'accounts', endClientId],
    queryFn: async () => (await api.get<Values>(`/accounts/${endClientId}`)).data,
    enabled: Boolean(endClientId),
  })

  const leadValues = MIRRORED_FIELDS.map((name) => form.values[name])
  const { setValue } = form

  useEffect(() => {
    if (!account) return
    for (const name of MIRRORED_FIELDS) {
      if (!form.values[name] && account[name]) setValue(name, account[name])
    }
    // form.values is read through the leadValues snapshot above, not as a
    // dependency itself — form is a fresh object identity on every keystroke,
    // which would re-run this on every field the user types into.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [account, setValue, ...leadValues])

  return null
}

/**
 * The reverse gap-fill: called from RecordEditor's afterSave once a Lead's
 * Stage 0 section has saved. For every mirrored field the Lead carries that
 * its End Client account does not, writes the gap onto the account and logs
 * it — a background write to a record the user is not looking at, so
 * CLAUDE.md rule 6 has it recorded rather than silent.
 */
export async function backfillAccountFieldsFromLead(
  record: Record<string, unknown>,
  queryClient: QueryClient
): Promise<void> {
  const endClientId = typeof record.end_client === 'string' ? record.end_client : undefined
  if (!endClientId) return

  // A gap-fill onto a linked record is a
  // nice-to-have this save must never fail over, so a network hiccup here is
  // swallowed rather than surfaced as a broken save.
  try {
    const account = (await api.get<Values>(`/accounts/${endClientId}`)).data

    const patch: Values = {}
    for (const name of MIRRORED_FIELDS) {
      if (record[name] && !account[name]) patch[name] = record[name]
    }
    if (Object.keys(patch).length === 0) return

    await api.put(`/accounts/${endClientId}`, patch)
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ['record', 'accounts', endClientId] }),
      queryClient.invalidateQueries({ queryKey: ['list', 'accounts'] }),
      queryClient.invalidateQueries({ queryKey: ['collection', 'accounts'] }),
    ])
  } catch (error) {
    console.error('[account-field-sync] could not backfill account fields', error)
  }
}
