import { useEffect, useState } from 'react'

import { PossibleConflictDialog } from '@/components/partners/PossibleConflictDialog'
import { ChangePrimaryDialog } from '@/components/pursuits/ChangePrimaryDialog'
import { DuplicatePursuitDialog } from '@/components/pursuits/DuplicatePursuitDialog'
import type { PossibleConflictMatch } from '@/lib/registrations'
import type { Values } from '@/lib/spec/conditions'
import { answerableRefusalOf } from '@/lib/pursuitGroups'

interface Props {
  /** The failed save's error — anything, only a pursuit refusal is acted on. */
  error: unknown
  pending: boolean
  /** Save again, with these values merged into the same payload. */
  retry: (extra: Values) => void
}

/**
 * Turns a save the server refused on a pursuit-group rule into the question it
 * was really asking, then saves again with the answer.
 *
 *   POSSIBLE_DUPLICATE             "Join its group, or say why not"
 *   PRIMARY_HAS_OPEN_SECONDARIES   "Choose the new primary before closing"
 *
 * Mounted by RecordEditor, which every record save goes through, so the create
 * page, a stage editor and the Details tab all get it — rather than one screen
 * knowing the rule and the next one saying "could not be saved".
 *
 * Every other refusal is not this component's: the screen that saved shows it
 * with <ErrorNotice>. The line kept here is for after the dialog is closed
 * unanswered — the save still did not happen, and the page should say why.
 */
export function PursuitSaveResolver({ error, pending, retry }: Props) {
  const refusal = answerableRefusalOf(error)
  const [open, setOpen] = useState(false)

  useEffect(() => {
    setOpen(Boolean(refusal))
  }, [error, refusal])

  if (!refusal) return null

  return (
    <>
      {!open && <p className="text-sm text-destructive">Not saved yet. {refusal.message}</p>}

      {refusal.code === 'POSSIBLE_DUPLICATE' && (
        <DuplicatePursuitDialog
          open={open}
          matches={refusal.matches ?? []}
          suggestedReason={refusal.suggested_reason ?? undefined}
          pending={pending}
          onJoin={(recordId) => retry({ join_pursuit_of: recordId })}
          onDecline={(reason) => retry({ not_duplicate_reason: reason })}
          onClose={() => setOpen(false)}
        />
      )}

      {/* A deal registration saved beside a similar project at the same End
          Client: raise a conflict, or say why it is a different project. The
          answer rides back in the same save. */}
      {refusal.code === 'POSSIBLE_CONFLICT' && (
        <PossibleConflictDialog
          open={open}
          matches={(refusal.matches ?? []) as unknown as PossibleConflictMatch[]}
          pending={pending}
          onResolve={(answer) => retry({ ...answer })}
          onClose={() => setOpen(false)}
        />
      )}

      {refusal.code === 'PRIMARY_HAS_OPEN_SECONDARIES' && refusal.group_id && (
        <ChangePrimaryDialog
          open={open}
          groupId={refusal.group_id}
          initialRecordId={refusal.open?.[0]?.record_id}
          context={{ lead: refusal.message, bullets: refusal.details }}
          onClose={() => setOpen(false)}
          onChanged={() => retry({})}
        />
      )}
    </>
  )
}
