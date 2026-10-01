import { Navigate, useParams } from 'react-router-dom'

import { ComingSoon } from '@/pages/ComingSoon'
import { PublishBanner } from '@/components/setup/PublishBanner'
import { SetupHome } from '@/components/setup/SetupHome'
import { SetupMenu } from '@/components/setup/SetupMenu'
import { findSetupItem } from '@/components/setup/setupMap'

/**
 * Setup — what was Administration until Item 3 of Phase 2 (25 Sep 2026),
 * rebuilt on Zoho's Setup: a home of category cards with a search box, and
 * every item at its own address with the category menu down the left.
 *
 * Nothing here is stored in the browser. Users and roles, and the field
 * register the Customization items edit, are PostgreSQL behind FastAPI. The
 * register is edited as a DRAFT and reaches the CRM only when published —
 * the banner across the top of every Setup page says what is waiting.
 *
 * DEVELOPER-only in V1. The boundary is the server — every /api/admin route is
 * mounted with require_administration (app/main.py) — and App.tsx only keeps
 * this screen from mounting for anyone else.
 *
 * The map of what Setup holds is components/setup/setupMap.tsx; this page only
 * finds the address in it.
 */
export function SetupPage() {
  const rest = useParams()['*'] ?? ''
  const found = findSetupItem(rest)

  // An address Setup does not have goes home rather than to a blank pane.
  if (rest.replace(/\/+$/, '') !== '' && !found) return <Navigate to="/setup" replace />

  return (
    <div className="mx-auto max-w-[96rem] px-6 py-6">
      <PublishBanner />

      {found ? (
        <div className="flex items-start gap-6">
          {found.item.menu?.(found.at) ?? <SetupMenu current={found.category} />}
          {/* Keyed by address, so moving between items starts each screen
              fresh rather than carrying one item's state into the next. */}
          <section key={found.at.path} className="min-w-0 flex-1">
            {!found.item.ownHeading && (
              <h1 className="text-page-title mb-4 font-bold">{found.item.label}</h1>
            )}
            {found.item.render ? (
              found.item.render(found.at)
            ) : (
              <ComingSoon label={found.item.label} />
            )}
          </section>
        </div>
      ) : (
        <SetupHome />
      )}
    </div>
  )
}
