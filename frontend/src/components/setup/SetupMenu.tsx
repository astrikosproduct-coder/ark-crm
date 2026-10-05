import { useEffect, useState } from 'react'
import { Link, NavLink } from 'react-router-dom'
import { ArrowLeftIcon, ChevronDownIcon } from 'lucide-react'

import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible'
import { cn } from '@/lib/utils'
import { SetupSearch } from './SetupHome'
import { SETUP, matchesSetup, setupPath, type SetupCategory } from './setupMap'

/**
 * Setup's sidebar on an item page — Zoho's: "← Setup Home", a search box, and
 * the categories as collapsible groups (Setup rebuild, 4c, 1 Oct 2026). It
 * takes the app sidebar's place while you are in Setup (SetupSidebar); leaving
 * Setup brings the app sidebar back.
 *
 * The category you are in starts open; while searching, every group with a
 * match is open and the rest are gone.
 */
export function SetupMenu({ current }: { current: SetupCategory }) {
  const [query, setQuery] = useState('')
  const [open, setOpen] = useState<Set<string>>(() => new Set([current.slug]))

  // Following a link into another category opens it too.
  useEffect(() => {
    setOpen((prev) => (prev.has(current.slug) ? prev : new Set(prev).add(current.slug)))
  }, [current.slug])

  const toggle = (slug: string, isOpen: boolean) =>
    setOpen((prev) => {
      const next = new Set(prev)
      if (isOpen) next.add(slug)
      else next.delete(slug)
      return next
    })

  const searching = query.trim() !== ''

  return (
    <div className="flex flex-col gap-2">
      <Link
        to="/setup"
        className="text-link hover:bg-accent flex items-center gap-2 rounded-md px-2 py-1.5 text-base font-semibold"
      >
        <ArrowLeftIcon className="size-4.5" />
        Setup Home
      </Link>
      <SetupSearch value={query} onChange={setQuery} placeholder="Search" />

      <nav className="flex flex-col gap-0.5">
        {SETUP.map((category) => {
          const items = category.items.filter((item) => matchesSetup(category, item, query))
          if (items.length === 0) return null
          const isOpen = searching || open.has(category.slug)
          return (
            <Collapsible
              key={category.slug}
              open={isOpen}
              onOpenChange={(next) => toggle(category.slug, next)}
            >
              <CollapsibleTrigger className="text-foreground hover:bg-accent flex w-full items-center gap-2 rounded-md px-2 py-2 text-sm font-medium">
                <category.icon className="text-muted-foreground size-4.5 shrink-0" />
                <span className="flex-1 truncate text-left">{category.label}</span>
                <ChevronDownIcon
                  className={cn('text-muted-foreground size-4 shrink-0 transition-transform', isOpen && 'rotate-180')}
                />
              </CollapsibleTrigger>
              <CollapsibleContent className="flex flex-col gap-0.5">
                {items.map((item) => (
                  <NavLink
                    key={item.slug}
                    to={setupPath(category, item)}
                    className={({ isActive }) =>
                      cn(
                        'rounded-md py-1.5 pr-2 pl-9 text-sm transition-colors',
                        isActive
                          ? 'bg-accent text-foreground font-medium'
                          : 'text-muted-foreground hover:bg-accent hover:text-accent-foreground'
                      )
                    }
                  >
                    {item.label}
                  </NavLink>
                ))}
              </CollapsibleContent>
            </Collapsible>
          )
        })}
        {searching && SETUP.every((c) => c.items.every((i) => !matchesSetup(c, i, query))) && (
          <p className="text-muted-foreground px-2 py-1.5 text-xs">Nothing matches.</p>
        )}
      </nav>
    </div>
  )
}
