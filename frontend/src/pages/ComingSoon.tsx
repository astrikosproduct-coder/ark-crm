import { Construction } from 'lucide-react'

/**
 * A placeholder for something the register describes and this release does not
 * yet render.
 *
 * THE WORDING IS LOAD-BEARING. This said "Coming in this prototype" over
 * "{label} hasn't been built yet in this walkthrough." — true when every screen
 * was browser-only and the whole thing was shown as a walkthrough, and no
 * longer true of an application with Entra sign-in, six modules on PostgreSQL
 * and an Administration screen that publishes the register. Calling it a
 * prototype in front of a BD user now understates what they are looking at, and
 * "walkthrough" tells them a thing they are using is a demonstration.
 *
 * It says what is actually the case instead: this part is scheduled, not
 * skipped. Every other prototype disclaimer in the application is deliberate
 * and stays — see PrototypeBanner, and rules 5 and 7 in CLAUDE.md.
 */
export function ComingSoon({ label }: { label: string }) {
  return (
    <div className="border-border flex flex-col items-center gap-3 rounded-lg border border-dashed py-16 text-center">
      <Construction className="text-muted-foreground size-8" />
      <div>
        <p className="text-foreground font-medium">Coming in a later phase</p>
        <p className="text-muted-foreground mt-1 text-sm">{label} hasn't been built yet.</p>
      </div>
    </div>
  )
}
