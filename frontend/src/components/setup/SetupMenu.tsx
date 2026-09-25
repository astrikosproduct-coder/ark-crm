import { useEffect, useState } from 'react'
import { Link, NavLink } from 'react-router-dom'
import { ChevronRightIcon } from 'lucide-react'

import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible'
import { cn } from '@/lib/utils'
import { SetupSearch } from './SetupHome'
import { SETUP, matchesSetup, setupPath, type SetupCategory } from './setupMap'

/**
 * The left menu on every Setup item page, as Zoho has it: "Setup" back to the
 * home, a search box, then the categories as collapsible groups. The category
 * you are in starts open; while searching, every group with a match is open
 * and the rest are gone.
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
    <aside className="w-56 shrink-0">
      <Link to="/setup" className="text-foreground mb-2 block px-2 text-sm font-semibold hover:underline">
        Setup
      </Link>
      <SetupSearch value={query} onChange={setQuery} className="mb-2" />

      <nav className="flex flex-col gap-0.5">
        {SETUP.map((category) => {
          const items = category.items.filter((item) => matchesSetup(category, item, query))
          if (items.length === 0) return null
          return (
            <Collapsible
              key={category.slug}
              open={searching || open.has(category.slug)}
              onOpenChange={(isOpen) => toggle(category.slug, isOpen)}
            >
              <CollapsibleTrigger className="text-muted-foreground hover:text-foreground flex w-full items-center gap-1.5 rounded-md px-2 py-1.5 text-sm font-semibold transition-colors">
                <ChevronRightIcon
                  className={cn(
                    'size-3.5 shrink-0 transition-transform',
                    (searching || open.has(category.slug)) && 'rotate-90'
                  )}
                />
                <span className="truncate">{category.label}</span>
              </CollapsibleTrigger>
              <CollapsibleContent className="flex flex-col gap-0.5">
                {items.map((item) => (
                  <NavLink
                    key={item.slug}
                    to={setupPath(category, item)}
                    className={({ isActive }) =>
                      cn(
                        'rounded-md py-1.5 pr-2 pl-7 text-sm transition-colors',
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
    </aside>
  )
}
