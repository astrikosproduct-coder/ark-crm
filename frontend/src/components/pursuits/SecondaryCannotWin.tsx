import { useState } from 'react'

import { Button } from '@/components/ui/button'
import { ChangePrimaryDialog } from '@/components/pursuits/ChangePrimaryDialog'
import { Notice } from '@/components/ui/notice'
import { pursuitErrorOf } from '@/lib/pursuitGroups'

interface Props {
  /** The failed conversion's error. Renders nothing unless it is this refusal. */
  error: unknown
  /** The record being converted — a pursuit's own id. */
  recordId: string
  /** Convert again, once this pursuit is the primary. */
  retry: () => void
}

/**
 * A secondary pursuit cannot be the one that wins: Actual Revenue never comes
 * from a record that does not count (backend/app/pursuits.py::guard_win). The
 * server refuses before the Deal exists, so nothing was written; this offers
 * the one way forward — make this pursuit primary, with a reason — and then
 * converts.
 */
export function SecondaryCannotWin({ error, recordId, retry }: Props) {
  const refusal = pursuitErrorOf(error)
  const [open, setOpen] = useState(false)
  // Every other refusal of a conversion — Final Negotiated Value not matching
  // TCV, for one — is the dialog's own to show, in the server's words.
  if (!refusal || refusal.code !== 'SECONDARY_CANNOT_WIN' || !refusal.group_id) return null

  return (
    <Notice
      tone="warning"
      boxed
      lead="Not converted yet."
      bullets={[
        refusal.primary_name
          ? `${refusal.primary_name} is the pursuit that counts in ${refusal.group_name ?? 'its group'}.`
          : `Another pursuit counts in ${refusal.group_name ?? 'its group'}.`,
        'Make this one primary first. It converts right after.',
      ]}
    >
      <Button type="button" size="sm" variant="outline" className="mt-1" onClick={() => setOpen(true)}>
        Make this one primary…
      </Button>
      <ChangePrimaryDialog
        open={open}
        groupId={refusal.group_id}
        initialRecordId={recordId}
        context={{ lead: 'Only the pursuit that counts can be won.', bullets: ['It converts to a Deal right after.'] }}
        onClose={() => setOpen(false)}
        onChanged={retry}
      />
    </Notice>
  )
}
