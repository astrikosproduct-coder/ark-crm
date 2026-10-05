import { lazy, Suspense, useEffect } from 'react'
import { Outlet, useLocation } from 'react-router-dom'

import { RegisterUpdateBanner } from '@/components/layout/RegisterUpdateBanner'
import { ScrollToTop } from '@/components/layout/ScrollToTop'
import { Sidebar } from '@/components/layout/Sidebar'
import { TopBar } from '@/components/layout/TopBar'
import { UnsavedChangesDialog } from '@/components/record/UnsavedChangesDialog'
import { useUnsavedChangesGuard } from '@/hooks/useUnsavedChangesGuard'
import { isLayoutEditorPath } from '@/components/setup/modulesPaths'
import { useIsDeveloper } from '@/lib/feedback'
import { isSetupPath, rememberAppPath } from '@/lib/setupReturn'
import { cn } from '@/lib/utils'

// Setup's sidebar is Setup's code — loaded with Setup, not with the app.
const SetupSidebar = lazy(() =>
  import('@/components/setup/SetupSidebar').then((m) => ({ default: m.SetupSidebar }))
)

// Dashboards sit on a darker page than list screens in the reference —
// ARK_brand_UI.md §5a.5. Scoped to that route, as it is there.
const DASHBOARD_ROUTES = ['/dashboard']

export function AppShell() {
  const { pathname, search } = useLocation()
  const onDashboard = DASHBOARD_ROUTES.some((route) => pathname.startsWith(route))

  // Setup takes the screen over as Zoho's does (4c, 1 Oct 2026): its own
  // sidebar stands where the app's is — none at all on its home and in the
  // layout editor — and the editor drops the top bar as well. Only for a
  // developer: anyone else is sent away from /setup (App.tsx) and keeps the
  // app's sidebar while that happens.
  const isDeveloper = useIsDeveloper()
  const inSetup = isDeveloper && isSetupPath(pathname)
  const fullScreen = inSetup && isLayoutEditorPath(pathname)
  // Where Setup's back arrow returns to.
  useEffect(() => {
    if (!isSetupPath(pathname)) rememberAppPath(pathname + search)
  }, [pathname, search])

  // One guard for the whole app: every navigation, and every in-page action
  // routed through requestDiscard(), is held here until it is answered.
  const guard = useUnsavedChangesGuard()

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
    <div className="flex min-h-screen items-start">
      <UnsavedChangesDialog open={guard.open} onStay={guard.stay} onLeave={guard.leave} />
      {inSetup ? (
        <Suspense fallback={null}>
          <SetupSidebar />
        </Suspense>
      ) : (
        <Sidebar />
      )}
      <div className="flex min-w-0 flex-1 flex-col self-stretch">
        {!fullScreen && <TopBar />}
        {!fullScreen && <RegisterUpdateBanner />}
        <main className={cn('min-w-0 flex-1', onDashboard && 'bg-dashboard-bg')}>
          {/* Each page's code is fetched the first time it is opened (App.tsx).
              The shell stays put while it arrives; only the page area waits. */}
          <Suspense fallback={<div className="text-muted-foreground p-6 text-sm">Loading…</div>}>
            <Outlet />
          </Suspense>
        </main>
      </div>
      <ScrollToTop />
    </div>
  )
}
