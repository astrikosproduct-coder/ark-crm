import { Outlet } from 'react-router-dom'

import { PrototypeBanner } from '@/components/layout/PrototypeBanner'
import { Sidebar } from '@/components/layout/Sidebar'
import { TopBar } from '@/components/layout/TopBar'

export function AppShell() {
  return (
    <div className="flex h-screen flex-col">
      <PrototypeBanner />
      <TopBar />
      <div className="flex min-h-0 flex-1">
        <Sidebar />
        <main className="min-w-0 flex-1 overflow-y-auto">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
