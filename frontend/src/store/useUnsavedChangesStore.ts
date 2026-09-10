import { create } from 'zustand'

interface UnsavedChangesState {
  /** Ids of the forms currently holding unsaved edits. */
  dirtyForms: Record<string, true>
  /**
   * An action held back until the user answers the confirm dialog — a tab
   * switch, closing an editor, opening another record.
   */
  pending: (() => void) | null
  setFormDirty: (id: string, dirty: boolean) => void
  /**
   * Run an action that would discard unsaved edits. With nothing unsaved it
   * runs immediately; otherwise it waits behind the dialog.
   */
  requestDiscard: (action: () => void) => void
  /** Run the held action, discarding the edits. */
  confirmDiscard: () => void
  /** Drop the held action and stay put. */
  cancelDiscard: () => void
}

/**
 * Which forms have unsaved edits, app-wide.
 *
 * A registry rather than component state because the thing that would destroy
 * an edit is usually NOT the editor: the tab strip above it, the sidebar, the
 * browser's back button. They each need to ask "is anything unsaved?" without
 * being anywhere near the form that knows.
 *
 * Deliberately holds no values — only the fact that something is unsaved. What
 * was typed lives in the form and dies with it; nothing here can resurrect it.
 */
export const useUnsavedChangesStore = create<UnsavedChangesState>()((set, get) => ({
  dirtyForms: {},
  pending: null,

  setFormDirty: (id, dirty) =>
    set((state) => {
      const has = id in state.dirtyForms
      if (dirty === has) return state
      const dirtyForms = { ...state.dirtyForms }
      if (dirty) dirtyForms[id] = true
      else delete dirtyForms[id]
      return { dirtyForms }
    }),

  requestDiscard: (action) => {
    if (!hasUnsavedChanges()) {
      action()
      return
    }
    set({ pending: action })
  },

  confirmDiscard: () => {
    const { pending } = get()
    set({ pending: null })
    pending?.()
  },

  cancelDiscard: () => set({ pending: null }),
}))

/**
 * Non-reactive read, for callers that run outside React's render — the router's
 * blocker and the beforeunload handler both ask at the moment of the event, not
 * at the moment they were registered.
 */
export function hasUnsavedChanges(): boolean {
  return Object.keys(useUnsavedChangesStore.getState().dirtyForms).length > 0
}

/** Ask before running an action that would throw unsaved edits away. */
export function requestDiscard(action: () => void): void {
  useUnsavedChangesStore.getState().requestDiscard(action)
}

/**
 * Mark a form clean immediately, without waiting for a re-render.
 *
 * A successful save clears the flag and navigates in the same tick; going
 * through an effect would leave the blocker still seeing the pre-save state and
 * holding the app on the page it just saved.
 */
export function markFormSaved(id: string): void {
  useUnsavedChangesStore.getState().setFormDirty(id, false)
}
