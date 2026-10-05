import { useLocation } from 'react-router-dom'

import { isLayoutEditorPath } from './modulesPaths'
import { SetupMenu } from './SetupMenu'
import { findSetupItem } from './setupMap'

/**
 * What stands in the app sidebar's place while you are in Setup — Zoho's
 * arrangement (Setup rebuild, 4c, 1 Oct 2026), drawn by AppShell:
 *
 *   /setup                      nothing: Setup's home takes the whole screen
 *   /setup/<category>/<item>    Setup's own sidebar (SetupMenu)
 *   inside a module             the item's own panel — "‹ Modules"
 *   the layout editor           nothing: the editor is full screen
 *
 * Leaving Setup brings the app sidebar back. Sticky and full height, as the
 * app sidebar is, so the top bar starts beside it.
 */
export function SetupSidebar() {
  const { pathname } = useLocation()
  const found = findSetupItem(pathname.replace(/^\/setup\/?/, ''))
  if (!found || isLayoutEditorPath(pathname)) return null
  return (
    <nav className="bg-card sticky top-0 flex h-screen w-64 shrink-0 flex-col overflow-y-auto px-3 py-3">
      {found.item.menu?.(found.at) ?? <SetupMenu current={found.category} />}
    </nav>
  )
}
