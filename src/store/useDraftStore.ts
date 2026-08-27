import { create } from 'zustand'
import { persist } from 'zustand/middleware'

import type { Values } from '@/lib/spec/conditions'
import type { Children } from '@/lib/spec/formula'

const STORAGE_KEY = 'arkcrm-drafts'

export interface DraftEntry {
  values: Values
  children: Children
  savedAt: number
}

function draftKey(module: string, recordId: string): string {
  return `${module}:${recordId}`
}

interface DraftState {
  drafts: Record<string, DraftEntry>
  /**
   * Bumped only by discardDraft, never by setDraft. A page component outside
   * the form's own React tree (the "Unsaved changes" badge in a page header)
   * cannot reach into a mounted RecordFormProvider to make it revert its
   * in-memory state, so it forces a remount by folding this token into the
   * form's `key` prop instead — the same remount-on-key-change idiom already
   * used across this codebase for "start clean". Keying off draft presence
   * itself would also remount the form the moment autosave first fires,
   * yanking focus out from under whatever the user is mid-typing; keying off
   * a counter that only moves on an explicit Discard avoids that.
   */
  discardTokens: Record<string, number>
  setDraft: (module: string, recordId: string, values: Values, children: Children) => void
  /** Removes the draft only. Used after a successful save, and by an in-tree
   * caller (useRecordForm's own discardDraft) that resets its local state
   * itself and so has no need to force a remount. */
  clearDraft: (module: string, recordId: string) => void
  /** Removes the draft and bumps its discard token, for a caller outside the
   * form's tree — see discardTokens above. */
  discardDraft: (module: string, recordId: string) => void
  /** CLAUDE.md rule: "Reset demo data" must not leave ghost drafts behind. */
  clearAll: () => void
}

/**
 * Persisted drafts of in-progress edits, keyed by module + record id ("new"
 * for an unsaved record). Deliberately a SEPARATE store from useDataStore,
 * with its own localStorage key — a draft is never real data. It is written
 * and read only by useRecordForm and the small "Unsaved changes" badges next
 * to it; MSW, /api/…, lookups and list views all read useDataStore alone and
 * have no way to see a draft.
 */
export const useDraftStore = create<DraftState>()(
  persist(
    (set) => ({
      drafts: {},
      discardTokens: {},

      setDraft: (module, recordId, values, children) => {
        const key = draftKey(module, recordId)
        set((state) => ({
          drafts: { ...state.drafts, [key]: { values, children, savedAt: Date.now() } },
        }))
      },

      clearDraft: (module, recordId) => {
        const key = draftKey(module, recordId)
        set((state) => {
          if (!(key in state.drafts)) return state
          const drafts = { ...state.drafts }
          delete drafts[key]
          return { drafts }
        })
      },

      discardDraft: (module, recordId) => {
        const key = draftKey(module, recordId)
        set((state) => {
          const drafts = { ...state.drafts }
          delete drafts[key]
          return {
            drafts,
            discardTokens: { ...state.discardTokens, [key]: (state.discardTokens[key] ?? 0) + 1 },
          }
        })
      },

      clearAll: () => {
        localStorage.removeItem(STORAGE_KEY)
        set({ drafts: {}, discardTokens: {} })
      },
    }),
    { name: STORAGE_KEY }
  )
)

/** Non-reactive read, for use inside useRecordForm's lazy reducer initializer. */
export function draftFor(module: string, recordId: string): DraftEntry | undefined {
  return useDraftStore.getState().drafts[draftKey(module, recordId)]
}

/** Whether a draft currently exists for this module + record. Reactive. */
export function useHasDraft(module: string, recordId: string): boolean {
  return useDraftStore((s) => draftKey(module, recordId) in s.drafts)
}

/** See discardTokens above. Reactive; fold into a form's remount key. */
export function useDiscardToken(module: string, recordId: string): number {
  return useDraftStore((s) => s.discardTokens[draftKey(module, recordId)] ?? 0)
}
