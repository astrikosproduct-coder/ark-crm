import { Bell, Search, Settings } from 'lucide-react'
import { Link } from 'react-router-dom'

import { ThemeToggle } from '@/components/ThemeToggle'

export function TopBar() {
  return (
    <header className="border-border bg-background flex h-14 shrink-0 items-center gap-4 border-b px-4">
      <span className="text-foreground shrink-0 text-base font-semibold tracking-tight">Astrikos</span>

      <div className="relative max-w-md flex-1">
        <Search className="text-muted-foreground pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2" />
        <input
          type="text"
          placeholder="Search…"
          disabled
          className="border-input bg-muted/40 text-muted-foreground placeholder:text-muted-foreground h-9 w-full rounded-md border pl-9 pr-3 text-sm outline-none disabled:cursor-not-allowed"
        />
      </div>

      <div className="ml-auto flex shrink-0 items-center gap-3">
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
        <div className="bg-secondary text-secondary-foreground flex h-9 items-center gap-2 rounded-full px-3 text-sm font-medium">
          <span className="bg-primary text-primary-foreground flex size-6 items-center justify-center rounded-full text-xs">
            C
          </span>
          CEO
        </div>
      </div>
    </header>
  )
}
