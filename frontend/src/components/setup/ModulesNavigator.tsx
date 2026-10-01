import { useState } from 'react'
import { Link } from 'react-router-dom'
import { ChevronLeftIcon, SearchIcon, XIcon } from 'lucide-react'

import { Input } from '@/components/ui/input'
import { useMetadataModules, withChildrenUnderParents } from '@/lib/metadata'
import { cn } from '@/lib/utils'

/**
 * The left panel inside a module — Zoho's "‹ Modules" (Setup rebuild, 4b,
 * 1 Oct 2026). It takes the place of Setup's category menu while a module is
 * open, so switching from Leads to Deals is one click rather than a trip back
 * to the list. "‹ Modules" goes back to that list; the magnifier filters.
 *
 * Opening another module keeps the tab you are on when that module has it —
 * Fields stays Fields — and otherwise lands on Layout.
 */
export function ModulesNavigator({
  base,
  current,
  hrefFor,
}: {
  base: string
  current: string
  /** Where a module opens from here — the page decides which tabs it has. */
  hrefFor: (moduleKey: string) => string
}) {
  const { data: modules = [] } = useMetadataModules()
  const [searching, setSearching] = useState(false)
  const [query, setQuery] = useState('')

  const term = query.trim().toLowerCase()
  const shown = withChildrenUnderParents(modules).filter(
    (m) => !term || m.label.toLowerCase().includes(term)
  )

  return (
    <aside className="w-56 shrink-0">
      <div className="mb-2 flex items-center gap-1">
        <Link
          to={base}
          className="text-foreground hover:bg-accent flex flex-1 items-center gap-1 rounded-md px-1 py-1 text-sm font-semibold"
          title="Back to Modules and Fields"
        >
          <ChevronLeftIcon className="size-4" />
          Modules
        </Link>
        <button
          type="button"
          aria-label={searching ? 'Close search' : 'Search modules'}
          className="text-muted-foreground hover:text-foreground hover:bg-accent rounded-md p-1.5"
          onClick={() => {
            setSearching((v) => !v)
            setQuery('')
          }}
        >
          {searching ? <XIcon className="size-4" /> : <SearchIcon className="size-4" />}
        </button>
      </div>

      {searching && (
        <Input
          autoFocus
          className="mb-2 h-8"
          placeholder="Search modules"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
      )}

      <nav className="flex flex-col gap-0.5">
        {shown.map((m) => (
          <Link
            key={m.module_key}
            to={hrefFor(m.module_key)}
            className={cn(
              'rounded-md py-1.5 pr-2 text-sm transition-colors',
              m.setup_parent ? 'pl-6' : 'pl-3',
              m.module_key === current
                ? 'bg-accent text-foreground font-medium'
                : 'text-muted-foreground hover:bg-accent hover:text-accent-foreground',
              !m.active && 'opacity-60'
            )}
          >
            {m.label}
          </Link>
        ))}
        {shown.length === 0 && (
          <p className="text-muted-foreground px-3 py-1.5 text-xs">No module matches.</p>
        )}
      </nav>
    </aside>
  )
}
