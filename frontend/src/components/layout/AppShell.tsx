import { Suspense, useMemo, useState } from 'react'
import { Outlet, useLocation } from 'react-router-dom'

import { RegisterUpdateBanner } from '@/components/layout/RegisterUpdateBanner'
import { ScrollToTop } from '@/components/layout/ScrollToTop'
import { ShellSlotsContext } from '@/components/layout/shellSlots'
import { Sidebar } from '@/components/layout/Sidebar'
import { TopBar } from '@/components/layout/TopBar'
import { UnsavedChangesDialog } from '@/components/record/UnsavedChangesDialog'
import { useUnsavedChangesGuard } from '@/hooks/useUnsavedChangesGuard'
import { cn } from '@/lib/utils'

// Dashboards sit on a darker page than list screens in the reference —
// ARK_brand_UI.md §5a.5. Scoped to that route, as it is there.
const DASHBOARD_ROUTES = ['/dashboard']

export function AppShell() {
  const { pathname } = useLocation()
  const onDashboard = DASHBOARD_ROUTES.some((route) => pathname.startsWith(route))

  // One guard for the whole app: every navigation, and every in-page action
  // routed through requestDiscard(), is held here until it is answered.
  const guard = useUnsavedChangesGuard()

  // A list screen's title goes up into the top bar, and the screen asks to be
  // exactly one viewport tall so its records box scrolls, not the document —
  // Zoho's list (Release 1.2). See components/layout/shellSlots.ts.
  const [titleSlot, setTitleSlot] = useState<HTMLElement | null>(null)
  const [fillScreen, setFillScreen] = useState(false)
  const slots = useMemo(() => ({ titleSlot, setTitleSlot, setFillScreen }), [titleSlot])

  return (
    // No h-screen, no overflow clipping anywhere in here: the DOCUMENT scrolls,
    // exactly the length of whatever page is on screen. A short record — three
    // fields and a Save button — is a short page, full stop; a long one scrolls
    // the way a long page always has. The old shell fixed this whole tree to
    // viewport height and scrolled only `main`, which meant every screen was
    // AT LEAST a full viewport tall whether it had content for that or not —
    // short screens ended in a slab of empty background with nothing to explain
    // it. TopBar and Sidebar use `sticky` instead of a clipped flex row, so they
    // still track the viewport as the page scrolls; see their own comments.
    // The nav is a full-height column beside the header rather than under it —
    // the reference puts the brand mark inside the nav and starts the header at
    // the content's left edge, so the module title lines up with the content
    // below it. ARK_brand_UI.md §2.1–2.2.
    <ShellSlotsContext.Provider value={slots}>
    <div className="flex min-h-screen items-start">
      <UnsavedChangesDialog open={guard.open} onStay={guard.stay} onLeave={guard.leave} />
      <Sidebar />
      {/* The one exception to the document scrolling: a list screen, from md
          up, is one viewport tall and scrolls inside its records box. */}
      <div className={cn('flex min-w-0 flex-1 flex-col self-stretch', fillScreen && 'md:h-dvh md:overflow-hidden')}>
        <TopBar />
        <RegisterUpdateBanner />
        <main className={cn('min-w-0 flex-1', fillScreen && 'flex flex-col md:min-h-0', onDashboard && 'bg-dashboard-bg')}>
          {/* Each page's code is fetched the first time it is opened (App.tsx).
              The shell stays put while it arrives; only the page area waits. */}
          <Suspense fallback={<div className="text-muted-foreground p-6 text-sm">Loading…</div>}>
            <Outlet />
          </Suspense>
        </main>
      </div>
      <ScrollToTop />
    </div>
    </ShellSlotsContext.Provider>
  )
}
