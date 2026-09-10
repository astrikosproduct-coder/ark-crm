import { Bell, PanelLeftClose, PanelLeftOpen, Search, Settings } from 'lucide-react'
import { Link } from 'react-router-dom'

import { ThemeToggle } from '@/components/ThemeToggle'
import { UserMenu } from '@/components/layout/UserMenu'
import { useSidebarStore } from '@/store/useSidebarStore'

export function TopBar() {
  return (
    <header className="border-border bg-background flex h-14 shrink-0 items-center gap-4 border-b px-4">
      <SidebarToggle />

      <span className="flex shrink-0 items-center gap-2">
        <img
          src="/Astrikos%20logo.png"
          alt=""
          aria-hidden
          className="size-9 shrink-0 rounded-md object-contain"
        />
        <span className="text-foreground text-base font-bold tracking-tight">ARK CRM</span>
      </span>

      <div className="relative ml-auto w-[411px] max-w-[38vw] shrink">
        <Search className="text-placeholder pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2" />
        <input
          type="text"
          placeholder="Search records"
          disabled
          className="border-input bg-secondary text-input-text placeholder:text-placeholder h-[34px] w-full rounded-md border pl-9 pr-3 text-sm outline-none disabled:cursor-not-allowed"
        />
      </div>

      <div className="flex shrink-0 items-center gap-1.5">
        <ThemeToggle />
        <button
          type="button"
          aria-label="Notifications"
          className="text-muted-foreground hover:bg-accent hover:text-accent-foreground flex size-9 items-center justify-center rounded-md transition-colors"
        >
          <Bell className="size-4.5" />
        </button>
        <Link
          to="/settings"
          aria-label="Settings"
          className="text-muted-foreground hover:bg-accent hover:text-accent-foreground flex size-9 items-center justify-center rounded-md transition-colors"
        >
          <Settings className="size-4.5" />
        </Link>
        <UserMenu />
      </div>
    </header>
  )
}

/**
 * Collapses the left nav. It sits here rather than inside the nav itself: on
 * its own row up there it left an empty band above the first item, and this is
 * the strip the reference keeps it in anyway — level with the brand mark.
 */
function SidebarToggle() {
  const collapsed = useSidebarStore((state) => state.collapsed)
  const toggleCollapsed = useSidebarStore((state) => state.toggleCollapsed)
  const Icon = collapsed ? PanelLeftOpen : PanelLeftClose
  const label = collapsed ? 'Show menu' : 'Hide menu'

  return (
    <button
      type="button"
      onClick={toggleCollapsed}
      aria-label={label}
      aria-expanded={!collapsed}
      title={label}
      className="text-muted-foreground hover:bg-accent hover:text-accent-foreground flex size-8 shrink-0 items-center justify-center rounded-md transition-colors"
    >
      <Icon className="size-4.5" />
    </button>
  )
}
