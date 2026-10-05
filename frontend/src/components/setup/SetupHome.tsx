import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { ArrowLeftIcon, SearchIcon } from 'lucide-react'

import { Input } from '@/components/ui/input'
import { appReturnPath } from '@/lib/setupReturn'
import { cn } from '@/lib/utils'
import { SETUP, matchesSetup, setupPath } from './setupMap'

/** The search box Setup's home and its left menu share. Client-side, over SETUP. */
export function SetupSearch({
  value,
  onChange,
  className,
  autoFocus,
  placeholder = 'Search Setup',
}: {
  value: string
  onChange: (value: string) => void
  className?: string
  autoFocus?: boolean
  placeholder?: string
}) {
  return (
    <div className={cn('relative', className)}>
      <SearchIcon className="text-muted-foreground pointer-events-none absolute top-1/2 left-2.5 size-4 -translate-y-1/2" />
      <Input
        type="search"
        placeholder={placeholder}
        aria-label={placeholder}
        autoFocus={autoFocus}
        className="pl-8"
        value={value}
        onChange={(e) => onChange(e.target.value)}
      />
    </div>
  )
}

/**
 * /setup — Zoho's Setup home: full screen (the app sidebar steps aside — see
 * AppShell), "← Setup" with the search box beside it, and one card per
 * category, each a plain list of its links. Typing replaces the cards with the
 * items that match. The arrow goes back to the page you came from.
 */
export function SetupHome() {
  const [query, setQuery] = useState('')
  const navigate = useNavigate()

  const results = query.trim()
    ? SETUP.flatMap((category) =>
        category.items
          .filter((item) => matchesSetup(category, item, query))
          .map((item) => ({ category, item }))
      )
    : null

  return (
    <>
      <div className="mb-5 flex flex-wrap items-center gap-3">
        <button
          type="button"
          aria-label="Leave Setup"
          title="Back to where you were"
          onClick={() => navigate(appReturnPath())}
          className="text-muted-foreground hover:bg-accent hover:text-foreground flex size-8 items-center justify-center rounded-md"
        >
          <ArrowLeftIcon className="size-5" />
        </button>
        <h1 className="text-page-title font-bold">Setup</h1>
        <SetupSearch value={query} onChange={setQuery} className="w-96" autoFocus />
      </div>

      {results ? (
        results.length === 0 ? (
          <p className="text-muted-foreground py-6 text-sm">
            Nothing in Setup matches “{query.trim()}”. Try a shorter word.
          </p>
        ) : (
          <div className="bg-card divide-y rounded-lg shadow-sm">
            {results.map(({ category, item }) => (
              <Link
                key={setupPath(category, item)}
                to={setupPath(category, item)}
                className="hover:bg-accent flex items-baseline gap-2 px-3 py-2 text-sm"
              >
                <span className="text-link font-medium">{item.label}</span>
                <span className="text-muted-foreground text-xs">{category.label}</span>
              </Link>
            ))}
          </div>
        )
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5">
          {SETUP.map((category) => (
            <section key={category.slug} className="bg-card rounded-lg p-4 shadow-sm">
              <h2 className="mb-2 flex items-center gap-2 text-sm font-semibold">
                <category.icon className="text-muted-foreground size-4 shrink-0" />
                {category.label}
              </h2>
              <ul className="space-y-0.5">
                {category.items.map((item) => (
                  <li key={item.slug}>
                    <Link to={setupPath(category, item)} className="text-link text-sm hover:underline">
                      {item.label}
                    </Link>
                  </li>
                ))}
              </ul>
            </section>
          ))}
        </div>
      )}
    </>
  )
}
