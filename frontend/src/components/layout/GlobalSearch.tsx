import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { SearchIcon, XIcon } from 'lucide-react'

import { api } from '@/lib/api'
import { cn } from '@/lib/utils'

interface Hit {
  module: string
  id: string
  title: string
  subtitle: string | null
  meta: string | null
}

interface Group {
  module: string
  label: string
  total: number
  items: Hit[]
}

interface SearchResponse {
  q: string
  groups: Group[]
}

/** Where a hit goes. Same prefixes the sidebar and every list row already use. */
const BASE_PATH: Record<string, string> = {
  leads: '/leads',
  opportunities: '/opportunities',
  deals: '/deals',
  accounts: '/accounts',
  contacts: '/contacts',
}

/** Mirrors MIN_QUERY in backend/app/routers/search.py — change both. */
const MIN_QUERY = 2

/**
 * The header's search box: one field, every live module.
 *
 * WHAT WAS HERE BEFORE
 * --------------------
 * A `disabled` input with a magnifying glass, 411px wide, in the most valuable
 * row in the app. It had never done anything. In a demo to management a search
 * box that does not respond reads as unfinished software, and it was the first
 * thing anyone clicked.
 *
 * WHY IT IS A DROPDOWN AND NOT A RESULTS PAGE
 * -------------------------------------------
 * Because of what people use it for: reaching a record they already know
 * exists. That is a navigation act, not a research one, and it wants to end in
 * one keystroke and one click rather than a page that has to be read and then
 * left. Each group therefore shows a few hits and says how many more there are;
 * "See all N in Leads" hands the rest to the module's own list, which already
 * has the filters, the columns and the sort a real search session needs. The
 * dropdown never tries to be that screen.
 *
 * KEYBOARD FIRST
 * --------------
 * Ctrl/Cmd+K from anywhere, arrows to move, Enter to open, Escape to leave.
 * The pointer works too, but the people who use this most will never reach for
 * it — and a search box that demands a mouse is slower than the sidebar it is
 * meant to beat.
 *
 * DEBOUNCED, AND HONEST WHILE IT WAITS
 * ------------------------------------
 * 200ms after the last keystroke, so a five-letter word is one request and not
 * five. The panel keeps the previous results dimmed rather than emptying, so
 * the list does not flash between letters — the same choice the list screens
 * make with keepPreviousData.
 */
export function GlobalSearch() {
  const navigate = useNavigate()
  const [text, setText] = useState('')
  const [debounced, setDebounced] = useState('')
  const [open, setOpen] = useState(false)
  const [active, setActive] = useState(0)
  const inputRef = useRef<HTMLInputElement>(null)
  const boxRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const id = setTimeout(() => setDebounced(text.trim()), 200)
    return () => clearTimeout(id)
  }, [text])

  const enabled = debounced.length >= MIN_QUERY
  const { data, isFetching } = useQuery({
    queryKey: ['search', debounced],
    queryFn: async () => (await api.get<SearchResponse>('/search', { params: { q: debounced } })).data,
    enabled,
    // A search result is a snapshot of a moment; holding it for a minute keeps
    // re-opening the box instant without ever being meaningfully stale.
    staleTime: 60_000,
  })

  // Flattened once, because the keyboard moves through HITS while the panel
  // draws GROUPS — two shapes of the same list, and only one of them can own
  // the index.
  const hits = (data?.groups ?? []).flatMap((group) => group.items)

  useEffect(() => setActive(0), [debounced])

  // Ctrl/Cmd+K from anywhere. Registered on the document rather than the input
  // because the whole point is to reach the box without first finding it.
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k') {
        event.preventDefault()
        inputRef.current?.focus()
        inputRef.current?.select()
        setOpen(true)
      }
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [])

  // A click anywhere else closes it. Pointerdown, not click: a click that lands
  // on a result must still reach that result's own handler first.
  useEffect(() => {
    if (!open) return
    const onDown = (event: PointerEvent) => {
      if (!boxRef.current?.contains(event.target as Node)) setOpen(false)
    }
    document.addEventListener('pointerdown', onDown)
    return () => document.removeEventListener('pointerdown', onDown)
  }, [open])

  const go = (hit: Hit) => {
    const base = BASE_PATH[hit.module]
    if (!base) return
    setOpen(false)
    setText('')
    setDebounced('')
    navigate(`${base}/${hit.id}`)
  }

  const seeAll = (group: Group) => {
    const base = BASE_PATH[group.module]
    if (!base) return
    setOpen(false)
    // Handed to the module's own list under the SAME url key its filter bar
    // reads (lib/listFilters.ts), so the search the reader typed up here is the
    // search they land inside.
    navigate(`${base}?q=${encodeURIComponent(debounced)}`)
  }

  const onKeyDown = (event: React.KeyboardEvent) => {
    if (event.key === 'Escape') {
      setOpen(false)
      inputRef.current?.blur()
      return
    }
    if (!open || hits.length === 0) return
    if (event.key === 'ArrowDown') {
      event.preventDefault()
      setActive((i) => (i + 1) % hits.length)
    } else if (event.key === 'ArrowUp') {
      event.preventDefault()
      setActive((i) => (i - 1 + hits.length) % hits.length)
    } else if (event.key === 'Enter') {
      event.preventDefault()
      const hit = hits[active]
      if (hit) go(hit)
    }
  }

  const showPanel = open && debounced.length >= MIN_QUERY

  return (
    <div ref={boxRef} className="relative ml-auto w-[411px] max-w-[38vw] shrink">
      <SearchIcon className="text-placeholder pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2" />
      <input
        ref={inputRef}
        type="text"
        role="combobox"
        aria-expanded={showPanel}
        aria-controls="global-search-results"
        aria-label="Search records"
        placeholder="Search records"
        value={text}
        onChange={(e) => {
          setText(e.target.value)
          setOpen(true)
        }}
        onFocus={() => setOpen(true)}
        onKeyDown={onKeyDown}
        className="border-input bg-secondary text-input-text placeholder:text-placeholder h-[34px] w-full rounded-md border pr-16 pl-9 text-sm outline-none focus:border-primary"
      />

      {text ? (
        <button
          type="button"
          aria-label="Clear search"
          onClick={() => {
            setText('')
            setDebounced('')
            inputRef.current?.focus()
          }}
          className="text-muted-foreground hover:text-foreground absolute top-1/2 right-2 -translate-y-1/2 rounded p-0.5"
        >
          <XIcon className="size-4" />
        </button>
      ) : (
        /* The shortcut, shown where the clear button will be. Hidden from
           screen readers: the input's own label already says what this is, and
           a literal "Ctrl K" read aloud mid-field is noise. */
        <kbd
          aria-hidden
          className="text-placeholder pointer-events-none absolute top-1/2 right-2.5 -translate-y-1/2 text-[11px]"
        >
          Ctrl K
        </kbd>
      )}

      {showPanel && (
        <div
          id="global-search-results"
          role="listbox"
          className={cn(
            'bg-card absolute top-full right-0 left-0 z-50 mt-1 max-h-[70vh] overflow-y-auto rounded-md border shadow-lg transition-opacity',
            isFetching && 'opacity-70'
          )}
        >
          {hits.length === 0 ? (
            <p className="text-muted-foreground px-3 py-4 text-sm">
              {isFetching ? 'Searching…' : `Nothing matches “${debounced}”.`}
            </p>
          ) : (
            (data?.groups ?? []).map((group) => (
              <section key={group.module}>
                <p className="text-muted-foreground bg-muted/50 px-3 py-1 text-[11px] font-medium tracking-wide uppercase">
                  {group.label}
                </p>
                {group.items.map((hit) => {
                  const index = hits.indexOf(hit)
                  return (
                    <button
                      key={`${hit.module}:${hit.id}`}
                      type="button"
                      role="option"
                      aria-selected={index === active}
                      onPointerEnter={() => setActive(index)}
                      onClick={() => go(hit)}
                      className={cn(
                        'flex w-full items-baseline gap-2 px-3 py-1.5 text-left text-sm',
                        index === active ? 'bg-accent' : 'hover:bg-accent/50'
                      )}
                    >
                      <span className="min-w-0 flex-1 truncate">{hit.title}</span>
                      {hit.subtitle && (
                        <span className="text-muted-foreground shrink-0 truncate text-xs">{hit.subtitle}</span>
                      )}
                      {hit.meta && <span className="text-muted-foreground shrink-0 text-[11px]">{hit.meta}</span>}
                    </button>
                  )
                })}
                {group.total > group.items.length && (
                  <button
                    type="button"
                    onClick={() => seeAll(group)}
                    className="text-link hover:bg-accent/50 w-full px-3 py-1.5 text-left text-xs"
                  >
                    See all {group.total} in {group.label}
                  </button>
                )}
              </section>
            ))
          )}
        </div>
      )}
    </div>
  )
}
