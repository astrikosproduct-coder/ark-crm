import { useMemo, useState } from 'react'
import { BoxesIcon, ChevronRightIcon, PanelLeftCloseIcon, PanelLeftOpenIcon } from 'lucide-react'
import { NavLink } from 'react-router-dom'

import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import {
  MODULE_GROUPS,
  MODULES,
  SIDEBAR_BOTTOM,
  SIDEBAR_TOP,
  TOOLS,
  type ModuleDef,
} from '@/lib/modules'
import { useSidebarStore } from '@/store/useSidebarStore'
import { useIsDeveloper } from '@/lib/feedback'
import { cn } from '@/lib/utils'


const moduleByKey = (key: string): ModuleDef | undefined => MODULES.find((m) => m.key === key)

/**
 * One nav row. The active item is a FLOATING pill — inset from both edges of
 * the nav, rounded, the accent at 15% behind fully opaque accent text. It was a
 * full-width filled band, which read as a selected row in a table rather than a
 * place in a menu. Collapsed, the row is the icon alone and the label moves into
 * a tooltip so nothing becomes unreachable.
 */
function NavItem({
  module,
  indent,
  collapsed,
}: {
  module: ModuleDef
  indent?: boolean
  collapsed: boolean
}) {
  const link = (
    <NavLink
      to={`/${module.key}`}
      className={({ isActive }) =>
        cn(
          // Inset from both edges, so the active state reads as a pill FLOATING
          // in the nav rather than a band spanning it — mx-2 is what makes it
          // float, and without it the accent tint would run edge to edge and
          // look like a selected table row.
          'text-label group flex items-center gap-2.5 rounded-lg py-2 font-medium transition-colors',
          // The rail already has its own px-2; a second inset there would leave
          // the pill narrower than the icon it wraps.
          collapsed ? 'mx-0 justify-center px-0' : indent ? 'mx-2 pr-3 pl-6' : 'mx-2 px-3',
          isActive
            ? // BRIGHTER, NOT BLUER. This was the accent tint with accent-
              // coloured text, and a module name turning blue read as a link
              // rather than as the page you are on — the nav was the only place
              // in the app where being selected changed a word's hue. Selection
              // is now the same ink as everything else, just at full strength
              // against the muted grey of every other row, on a neutral pill.
              'bg-accent text-foreground'
            : 'text-muted-foreground hover:bg-accent hover:text-accent-foreground'
        )
      }
    >
      <module.icon className="size-4.5 shrink-0" />
      {!collapsed && <span className="truncate">{module.label}</span>}
    </NavLink>
  )

  if (!collapsed) return link

  // The trigger wraps the link rather than being it: `asChild` would hand
  // NavLink a plain className prop, and NavLink's className here is a function
  // of isActive — it would be stringified and every class silently lost.
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <span className="flex">{link}</span>
      </TooltipTrigger>
      <TooltipContent side="right">{module.label}</TooltipContent>
    </Tooltip>
  )
}

/**
 * The nav's own header: brand mark, wordmark, and the control that collapses
 * the nav to an icon rail. It sits here rather than in the top bar because the
 * reference puts it here — level with the header, inside the nav's own width,
 * with the collapse control at the nav's right edge (ARK_brand_UI.md §2.2).
 * Collapsed, the wordmark goes and the two controls stack.
 */
function SidebarBrand({ collapsed }: { collapsed: boolean }) {
  const toggleCollapsed = useSidebarStore((s) => s.toggleCollapsed)
  const Icon = collapsed ? PanelLeftOpenIcon : PanelLeftCloseIcon
  const label = collapsed ? 'Show menu' : 'Hide menu'

  return (
    <div
      className={cn(
        'bg-card sticky top-0 z-10 mb-2 flex shrink-0 items-center',
        collapsed ? 'flex-col justify-center gap-1 py-2' : 'h-14 gap-2 px-3'
      )}
    >
      <img
        src="/Astrikos%20logo.png"
        alt=""
        aria-hidden
        className="size-8 shrink-0 rounded-md object-contain"
      />
      {!collapsed && (
        <span className="text-foreground truncate text-base font-bold tracking-tight">ARK CRM</span>
      )}
      <button
        type="button"
        onClick={toggleCollapsed}
        aria-label={label}
        aria-expanded={!collapsed}
        title={label}
        className={cn(
          'text-muted-foreground hover:bg-accent hover:text-accent-foreground flex size-8 shrink-0 items-center justify-center rounded-md transition-colors',
          !collapsed && 'ml-auto'
        )}
      >
        <Icon className="size-4.5" />
      </button>
    </div>
  )
}

/**
 * A collapsible module group: header with a chevron that rotates, items
 * indented beneath. Open by default — a reviewer should see every module. On
 * the icon-only rail the headers go away and the icons run on unbroken.
 */
function NavGroup({
  label,
  modules,
  collapsed,
}: {
  label: string
  modules: ModuleDef[]
  collapsed: boolean
}) {
  const [open, setOpen] = useState(true)
  if (modules.length === 0) return null

  if (collapsed) {
    return (
      <div className="border-border/60 flex flex-col gap-0.5 border-t pt-1 first:border-t-0">
        {modules.map((mod) => (
          <NavItem key={mod.key} module={mod} collapsed />
        ))}
      </div>
    )
  }

  return (
    <Collapsible open={open} onOpenChange={setOpen}>
      <CollapsibleTrigger className="text-muted-foreground hover:text-foreground text-label flex w-full items-center gap-1.5 rounded-md px-3 py-2 font-semibold tracking-wide uppercase transition-colors">
        <ChevronRightIcon
          className={cn('size-3.5 shrink-0 transition-transform', open && 'rotate-90')}
        />
        <span className="truncate">{label}</span>
      </CollapsibleTrigger>
      <CollapsibleContent className="flex flex-col gap-0.5">
        {modules.map((mod) => (
          <NavItem key={mod.key} module={mod} indent collapsed={false} />
        ))}
      </CollapsibleContent>
    </Collapsible>
  )
}

/**
 * The left nav, laid out the way the reference is (ARK_brand_UI.md §5a.1 and
 * the Leads screenshot): the dashboard on its own above a divider — where the
 * reference puts Home — then a "Modules" heading and the modules themselves.
 *
 * The collapse control lives in the top bar rather than here: on its own row it
 * left an empty band above Dashboard, and the top bar is the same strip the
 * reference puts it in anyway.
 *
 * Colours and icons are ARK's existing ones throughout; only the arrangement
 * follows the reference.
 */
export function Sidebar() {
  const collapsed = useSidebarStore((s) => s.collapsed)
  const isDeveloper = useIsDeveloper()

  const top = SIDEBAR_TOP.map(moduleByKey).filter((m): m is ModuleDef => Boolean(m))
  const bottom = SIDEBAR_BOTTOM.map(moduleByKey).filter((m): m is ModuleDef => Boolean(m))

  const groups = useMemo(
    () =>
      MODULE_GROUPS.map((group) => ({
        label: group.label,
        modules: group.keys.map(moduleByKey).filter((m): m is ModuleDef => Boolean(m)),
      })),
    []
  )

  return (
    // Sticky from the very top rather than under the header: the reference runs
    // the nav the full height of the window with the brand mark inside it, and
    // starts the header beside it — see AppShell. The document still scrolls as
    // one piece, so this holds its own position against that scroll instead of
    // being handed a clipped box to scroll internally. It gets its own vertical
    // scrollbar for a nav list taller than the window; a short list just sits
    // there unscrolled.
    <nav
      className={cn(
        'bg-card sticky top-0 flex h-screen shrink-0 flex-col gap-0.5 overflow-x-hidden overflow-y-auto pb-3 transition-[width]',
        collapsed ? 'w-14 px-2' : 'w-56'
      )}
    >
      <SidebarBrand collapsed={collapsed} />

      {top.map((mod) => (
        <NavItem key={mod.key} module={mod} collapsed={collapsed} />
      ))}

      <div className={cn('mt-2 border-t pt-2', collapsed && 'mx-1')}>
        {!collapsed && (
          <p className="text-foreground mb-1 flex items-center gap-2 px-3 py-1 text-sm font-semibold">
            <BoxesIcon className="text-muted-foreground size-4.5 shrink-0" />
            Modules
          </p>
        )}

        {groups.map((group) => (
          <NavGroup
            key={group.label}
            label={group.label}
            modules={group.modules}
            collapsed={collapsed}
          />
        ))}

        {bottom.map((mod) => (
          <NavItem key={mod.key} module={mod} collapsed={collapsed} />
        ))}
      </div>

      {/*
        Instrumentation, not product surface: the form-engine harness and the
        field-register worklist. Shown only to DEVELOPER, because to everyone
        else they are a confusing pair of screens that expose the register's
        own defects rather than the business.

        This hides the NAV ENTRY, which is not the same as protecting the
        pages — both remain reachable by typing their URL. That is deliberate
        and acceptable here: they read the spec JSON the browser already has
        and expose no business data. Anything that did would need a route
        guard and, more to the point, a check on the API — which is exactly
        what Feedback has: GET /api/feedback answers 403 to anyone who is not
        a DEVELOPER (backend/app/auth.py::require_developer).
      */}
      {isDeveloper && (
        <div className={cn('mt-4 border-t pt-3', collapsed && 'mx-1')}>
          {!collapsed && (
            <p className="text-muted-foreground text-meta px-3 pb-1 font-medium">Developer tools</p>
          )}
          <div className="flex flex-col gap-0.5">
            {TOOLS.map((tool) => (
              <NavItem key={tool.key} module={tool} collapsed={collapsed} />
            ))}
          </div>
        </div>
      )}
    </nav>
  )
}
