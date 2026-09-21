import { useEffect, useState } from 'react'

import { Button } from '@/components/ui/button'
import { REGISTER_CHECK_EVENT, publishedVersionChanged } from '@/lib/spec/source'

/** How often an open page asks whether a newer register was published. */
const EVERY_MS = 3 * 60 * 1000

/**
 * "There's a new update" — an app-wide line, shown when someone publishes in Administration
 * while this page is open (decided 21 Sep 2026).
 *
 * A page keeps the field list it loaded, so nobody is interrupted mid-form.
 * But the server checks every save against the NEW version, so a field made
 * required since the page opened could refuse a save the screen didn't warn
 * about. This line says so, and asks for a reload once the work is saved.
 *
 * Checks every few minutes, when the tab comes back into view, and whenever a
 * save is refused for a missing field (REGISTER_CHECK_EVENT). The check is a
 * conditional request: an unchanged register costs a 304 and no body.
 */
export function RegisterUpdateBanner() {
  const [updated, setUpdated] = useState(false)

  useEffect(() => {
    let cancelled = false
    const check = () => {
      void publishedVersionChanged().then((changed) => {
        if (changed && !cancelled) setUpdated(true)
      })
    }
    const onVisible = () => document.visibilityState === 'visible' && check()
    const timer = window.setInterval(check, EVERY_MS)
    document.addEventListener('visibilitychange', onVisible)
    window.addEventListener(REGISTER_CHECK_EVENT, check)
    return () => {
      cancelled = true
      window.clearInterval(timer)
      document.removeEventListener('visibilitychange', onVisible)
      window.removeEventListener(REGISTER_CHECK_EVENT, check)
    }
  }, [])

  if (!updated) return null
  return (
    <div className="flex flex-wrap items-center justify-between gap-2 border-b border-amber-500/40 bg-amber-500/10 px-4 py-2 text-sm">
      <span>There's a new update. Save your work, then reload to see it.</span>
      <Button size="sm" variant="outline" onClick={() => window.location.reload()}>
        Reload
      </Button>
    </div>
  )
}
