import { Outlet, useLocation } from 'react-router-dom'

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

  return (
    <div className="flex h-screen flex-col">
      <UnsavedChangesDialog open={guard.open} onStay={guard.stay} onLeave={guard.leave} />
      <TopBar />
      <div className="flex min-h-0 flex-1">
        <Sidebar />
        <main className={cn('min-w-0 flex-1 overflow-y-auto', onDashboard && 'bg-dashboard-bg')}>
          <Outlet />
        </main>
      </div>
    </div>
  )
}
