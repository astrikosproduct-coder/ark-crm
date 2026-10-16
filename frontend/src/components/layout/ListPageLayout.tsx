import { useEffect, useLayoutEffect, useState, type ReactNode } from 'react'
import { createPortal } from 'react-dom'
import { StarIcon } from 'lucide-react'

import { ListToolbarSlot, useShellSlots } from '@/components/layout/shellSlots'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { cn } from '@/lib/utils'
import { useViewPreference, type PageSettings } from '@/lib/viewPreferences'

export interface ListPageView {
  key: string
  label: string
  /** Given, the view is an icon button with its label as a tooltip — List, Kanban. */
  icon?: ReactNode
  /** The view's filter bar, drawn at the start of the toolbar line. */
  toolbar?: ReactNode
  content: ReactNode
}

/**
 * A module's list screen, laid out as Zoho's (Release 1.2, 15 Oct 2026):
 *
 *   top bar   Leads [Open leads ▾]                       search · feedback · you
 *   toolbar   [Filter] [search] chips… | [≡][▦]          [⚙] [+ New lead | ▾]
 *   box       the records — the only thing that scrolls
 *
 * The title and the scope go up into the top bar, the views become icons on
 * the toolbar line, and the page is exactly one screen tall from md up, so the
 * records box takes everything left. Below md the page scrolls as before.
 * Nothing is added; it is the same title, scope, filter, views and actions.
 */
export function ListPageLayout({
  title,
  scope,
  actions,
  views,
  pageKey,
}: {
  title: string
  /** Which records — the list's scope picker, beside the title as Zoho's "All Leads ▾". */
  scope?: ReactNode
  actions?: ReactNode
  views: ListPageView[]
  /**
   * The module, to keep the view this person opens it on (user_view_preferences,
   * `page:<module>`). Given, a ☆ beside the views makes the one on screen theirs.
   */
  pageKey?: string
}) {
  const { titleSlot, setFillScreen } = useShellSlots()
  const [active, setActive] = useState(views[0]?.key)
  const page = useViewPreference<PageSettings>(pageKey && views.length > 1 ? `page:${pageKey}` : undefined)
  const defaultView = views.some((v) => v.key === page.settings?.default_view) ? page.settings?.default_view : undefined
  // Open on this person's default view once it has arrived — unless they have
  // already picked one, which is never taken back from them.
  const [picked, setPicked] = useState(false)
  useEffect(() => {
    if (!picked && defaultView) setActive(defaultView)
  }, [defaultView, picked])
  const choose = (key: string) => {
    setPicked(true)
    setActive(key)
  }
  const [toolSlot, setToolSlot] = useState<HTMLElement | null>(null)
  const current = views.find((v) => v.key === active) ?? views[0]

  useLayoutEffect(() => {
    setFillScreen(true)
    return () => setFillScreen(false)
  }, [setFillScreen])

  const heading = (
    <>
      <h1 className="text-page-title truncate font-bold">{title}</h1>
      {scope}
    </>
  )

  return (
    <ListToolbarSlot.Provider value={toolSlot}>
      <Tabs
        value={current?.key}
        onValueChange={choose}
        className="flex min-h-0 flex-1 flex-col gap-3 px-4 pt-3 pb-4 sm:px-6"
      >
        {titleSlot ? createPortal(heading, titleSlot) : <div className="flex items-center gap-3">{heading}</div>}

        <div className="flex flex-wrap items-center gap-2">
          {current?.toolbar}
          {views.length > 1 && (
            <>
              <span aria-hidden className="bg-border mx-1 h-6 w-px" />
              <TabsList aria-label="Views" className="gap-1 border-b-0">
                {views.map((view) =>
                  view.icon ? (
                    <Tooltip key={view.key}>
                      <TooltipTrigger asChild>
                        <TabsTrigger
                          value={view.key}
                          aria-label={view.label}
                          className="hover:bg-accent data-[state=active]:bg-primary/15 data-[state=active]:text-primary mb-0 grid size-8 place-items-center rounded-md border-b-0 p-0"
                        >
                          {view.icon}
                        </TabsTrigger>
                      </TooltipTrigger>
                      <TooltipContent>{view.label}</TooltipContent>
                    </Tooltip>
                  ) : (
                    <TabsTrigger
                      key={view.key}
                      value={view.key}
                      className="hover:bg-accent data-[state=active]:bg-primary/15 data-[state=active]:text-primary mb-0 h-8 rounded-md border-b-0 px-3 py-0"
                    >
                      {view.label}
                    </TabsTrigger>
                  )
                )}
              </TabsList>
              {pageKey && current && (
                <DefaultViewStar
                  isDefault={(defaultView ?? views[0]?.key) === current.key}
                  label={current.label}
                  onSet={() => page.save({ default_view: current.key })}
                  onClear={() => page.reset()}
                  explicit={defaultView === current.key}
                />
              )}
            </>
          )}
          <div className="flex-1" />
          <div ref={setToolSlot} className="flex items-center gap-2 empty:hidden" />
          {actions && <div className="flex shrink-0 items-start gap-2">{actions}</div>}
        </div>

        {/* Until this person's default view is known, nothing flashes a view they did not ask for. */}
        {(page.ready || !pageKey) && views.map((view) => (
          <TabsContent key={view.key} value={view.key} className={cn('flex min-h-0 flex-1 flex-col overflow-y-auto pt-0')}>
            {view.content}
          </TabsContent>
        ))}
      </Tabs>
    </ListToolbarSlot.Provider>
  )
}

/**
 * ☆ beside the views: make the one on screen the view this module opens on,
 * for this person only. Filled when it already is; clicking a filled star that
 * was chosen goes back to the module's own first view.
 */
function DefaultViewStar({
  isDefault,
  explicit,
  label,
  onSet,
  onClear,
}: {
  isDefault: boolean
  /** Chosen by the person, rather than the module's first view by default. */
  explicit: boolean
  label: string
  onSet: () => void
  onClear: () => void
}) {
  const tip = isDefault
    ? explicit
      ? `${label} is your default view. Click to go back to the usual one.`
      : `${label} is your default view.`
    : `Open on ${label} every time`
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <button
          type="button"
          aria-label={tip}
          aria-pressed={isDefault}
          onClick={() => (isDefault ? explicit && onClear() : onSet())}
          className={cn(
            'grid size-8 place-items-center rounded-md transition-colors',
            isDefault ? 'text-amber-500' : 'text-muted-foreground hover:bg-accent hover:text-foreground',
            isDefault && !explicit && 'cursor-default'
          )}
        >
          <StarIcon className={cn('size-4', isDefault && 'fill-current')} />
        </button>
      </TooltipTrigger>
      <TooltipContent>{tip}</TooltipContent>
    </Tooltip>
  )
}
