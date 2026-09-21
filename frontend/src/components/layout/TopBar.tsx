import { ChevronRightIcon } from 'lucide-react'
import { Link, useLocation } from 'react-router-dom'

import { FeedbackButton } from '@/components/layout/FeedbackButton'
import { GlobalSearch } from '@/components/layout/GlobalSearch'
import { UserMenu } from '@/components/layout/UserMenu'
import { MODULES, TOOLS } from '@/lib/modules'

/**
 * The way BACK to the module, on a record screen only.
 *
 * WHICH OF THE TWO HEADINGS WON, AND WHY (18 Sep 2026)
 * ----------------------------------------------------
 * Every list screen printed its module name twice — once up here and again as
 * PageLayout's H1 a few pixels below — and the first pass at this only fixed
 * the record case, leaving "Deals / Deals" exactly as it was.
 *
 * The PAGE HEADING wins. Three reasons, and none of them is taste:
 *
 *   1. It sits with the page's own controls. The heading and the Actions
 *      button belong to each other; splitting them puts the label in the
 *      chrome and the verbs on the page.
 *   2. It is the real <h1>. A screen reader announcing a page should say what
 *      the page IS, not read a strip of app furniture.
 *   3. The sidebar already marks the module as current. With the H1 that is
 *      twice; with this bar as well it was three times, on a screen whose
 *      whole job is a list of records.
 *
 * So on a list screen this renders NOTHING. On a RECORD screen the two were
 * never duplicates — "Deals" here, "Al Waha Command Centre" below — so the
 * module stays, as a link back to its list, in small muted type. It is a
 * TRAIL, not a title: it used to be drawn at the same size and weight as the
 * H1 below it, which is what made two headings look like a mistake even when
 * they said different things.
 */
function moduleCrumbFor(pathname: string): { label: string; to: string } | null {
  const segments = pathname.split('/').filter(Boolean)
  const key = segments[0]
  if (!key) return null
  const module = [...MODULES, ...TOOLS].find((m) => m.key === key)
  if (!module) return null
  // /leads is a list and /leads/new is the create screen; both title themselves.
  // Only /leads/LEAD-00118 is a record sitting inside something.
  const isRecord = segments.length > 1 && segments[1] !== 'new'
  return isRecord ? { label: module.label, to: `/${key}` } : null
}

export function TopBar() {
  const { pathname } = useLocation()
  const crumb = moduleCrumbFor(pathname)

  return (
    // Sticky, not fixed: it takes part in normal flow (so it does not need a
    // matching spacer to avoid covering the first thing on the page) and pins
    // itself the moment the document would otherwise scroll it away. z-40 is
    // the app-shell tier — above ordinary content, below Dialog/Sheet overlays.
    // The brand mark and the collapse control are in the nav beside this now,
    // which is where the reference keeps them — see Sidebar.
    <header className="bg-card sticky top-0 z-40 flex h-14 shrink-0 items-center gap-4 px-6">
      {crumb && (
        <nav aria-label="Breadcrumb" className="flex min-w-0 items-center gap-1">
          <Link
            to={crumb.to}
            className="text-muted-foreground hover:text-foreground truncate text-sm"
          >
            {crumb.label}
          </Link>
          <ChevronRightIcon aria-hidden className="text-muted-foreground size-3.5 shrink-0" />
        </nav>
      )}

      <GlobalSearch />

      {/* WHAT IS NOT IN THIS CORNER ANY MORE (18 Sep 2026)
          - Notifications: a bell with no handler, no badge and nothing behind
            it, which read as unfinished software and was the next thing anyone
            clicked after the disabled search box.
          - Settings: a prototype-only screen whose own subtitle said nothing on
            it exists in the real product, given a permanent seat one click from
            every page. Its single working control reloaded the catalogue into a
            browser holding a stale copy — a workaround for reference data being
            persisted at all, which lib/spec/seed.ts now fixes at the source.
          - The theme toggle, which moved into the user menu where a monthly
            preference belongs.
          Feedback and the account menu are what is left, because both do
          something on every visit. */}
      <div className="flex shrink-0 items-center gap-1.5">
        <FeedbackButton />
        <UserMenu />
      </div>
    </header>
  )
}
