import { XIcon } from 'lucide-react'

import { Badge } from '@/components/ui/badge'
import { useDraftStore, useHasDraft } from '@/store/useDraftStore'

interface Props {
  module: string
  recordId: string
  className?: string
}

/**
 * "Unsaved changes", with a Discard action, shown in a page header wherever a
 * draft exists for module + recordId.
 *
 * Reads useDraftStore directly rather than through useRecordForm — a page
 * header is a sibling of the RecordFormProvider that owns the field-level
 * form state, not a descendant of it, so this is a plain reactive read of the
 * same persisted store the form writes to. Discard calls the store's
 * discardDraft (which bumps a per-key token) rather than the in-form
 * discardDraft method for the same reason: there is no form instance in scope
 * here to reset directly, so the owning RecordEditor is made to remount and
 * re-hydrate instead, picking up the now-absent draft — see the discardToken
 * doc in useDraftStore.
 */
export function UnsavedBadge({ module, recordId, className }: Props) {
  const hasDraft = useHasDraft(module, recordId)
  if (!hasDraft) return null

  return (
    <span className={className}>
      <Badge variant="warning" className="gap-1">
        Unsaved changes
        <button
          type="button"
          onClick={() => useDraftStore.getState().discardDraft(module, recordId)}
          className="ml-0.5 rounded-sm hover:opacity-70"
          aria-label="Discard unsaved changes"
        >
          <XIcon className="size-3" />
        </button>
      </Badge>
    </span>
  )
}
