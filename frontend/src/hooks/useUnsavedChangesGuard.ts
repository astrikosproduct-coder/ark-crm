import { useCallback, useEffect } from 'react'
import { useBlocker } from 'react-router-dom'

import { hasUnsavedChanges, useUnsavedChangesStore } from '@/store/useUnsavedChangesStore'

export interface UnsavedChangesGuard {
  /** Whether the confirm dialog should be on screen. */
  open: boolean
  /** Go ahead, discarding the unsaved edits. */
  leave: () => void
  /** Cancel whatever was attempted and stay put. */
  stay: () => void
}

/**
 * The app-wide "you have not saved your changes" guard. Mounted once, in the
 * app shell.
 *
 * Covers every way unsaved work can be lost:
 *  - in-app navigation, held by the router's blocker (which is why the app is
 *    built with createBrowserRouter — see App.tsx; a plain BrowserRouter cannot
 *    interrupt a navigation at all);
 *  - in-page actions that discard — a tab switch, closing an editor — routed
 *    through requestDiscard();
 *  - a reload or a closed tab, via beforeunload, where the browser shows its
 *    own dialog and no page may style or replace it.
 *
 * Every check reads the store at the moment of the event rather than closing
 * over a render's value, so a form that goes dirty after this mounted is still
 * guarded.
 */
export function useUnsavedChangesGuard(): UnsavedChangesGuard {
  const pending = useUnsavedChangesStore((s) => s.pending)
  const confirmDiscard = useUnsavedChangesStore((s) => s.confirmDiscard)
  const cancelDiscard = useUnsavedChangesStore((s) => s.cancelDiscard)

  const blocker = useBlocker(
    useCallback(
      ({ currentLocation, nextLocation }) =>
        hasUnsavedChanges() && currentLocation.pathname !== nextLocation.pathname,
      []
    )
  )

  useEffect(() => {
    const onBeforeUnload = (event: BeforeUnloadEvent) => {
      if (!hasUnsavedChanges()) return
      event.preventDefault()
      // Still set for the browsers that read it; modern ones show their own
      // wording and ignore anything a page provides.
      event.returnValue = ''
    }
    window.addEventListener('beforeunload', onBeforeUnload)
    return () => window.removeEventListener('beforeunload', onBeforeUnload)
  }, [])

  const stay = useCallback(() => {
    cancelDiscard()
    if (blocker.state === 'blocked') blocker.reset()
  }, [blocker, cancelDiscard])

  const leave = useCallback(() => {
    if (pending) {
      confirmDiscard()
      return
    }
    if (blocker.state === 'blocked') blocker.proceed()
  }, [blocker, pending, confirmDiscard])

  return {
    open: blocker.state === 'blocked' || pending !== null,
    leave,
    stay,
  }
}
