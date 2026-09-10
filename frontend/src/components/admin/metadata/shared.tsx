import type { ReactNode } from 'react'
import { DatabaseIcon } from 'lucide-react'

import { Badge } from '@/components/ui/badge'
import { errorMessage } from '@/lib/admin'

/**
 * Pieces the six metadata screens all need.
 *
 * THE ADMIN UI IS THE ONE PLACE FIELDS ARE HARDCODED — DELIBERATELY
 * ------------------------------------------------------------------
 * CLAUDE.md rule 3 says never hardcode a field: every form renders from
 * spec/fields.json. These screens are the documented exception, and they have
 * to be, because they are the screens that EDIT spec/fields.json. Rendering the
 * field editor from the field register would mean the register describing
 * itself — and a register with a broken row would take away the very screen
 * needed to fix it.
 *
 * Same exception, same reason as src/components/admin/UserDialog.tsx, which
 * says so in its own docstring. It is scoped to this folder: no other screen in
 * the application names a field in code.
 */

export function MetadataIntro({ children }: { children: ReactNode }) {
  return <p className="text-muted-foreground mb-3 max-w-3xl text-sm">{children}</p>
}

export function LoadingRow({ what }: { what: string }) {
  return <p className="text-muted-foreground py-8 text-sm">Loading {what}…</p>
}

export function ErrorBox({ error }: { error: unknown }) {
  return (
    <div className="border-destructive/40 bg-destructive/5 rounded-md border p-4">
      <p className="text-destructive text-sm font-medium">Could not reach the API</p>
      <p className="text-muted-foreground mt-1 text-sm">{errorMessage(error)}</p>
      <p className="text-muted-foreground mt-2 text-xs">
        The metadata layer needs the FastAPI backend on port 8000 and PostgreSQL on 5433.
      </p>
    </div>
  )
}

/** The banner every metadata tab carries: this is the draft, not the live CRM. */
export function DraftNotice({ pending }: { pending: number | null }) {
  return (
    <div className="bg-muted/40 mb-4 flex items-start gap-2 rounded-md border px-3 py-2">
      <DatabaseIcon className="mt-0.5 size-3.5 shrink-0" />
      <p className="text-muted-foreground text-xs">
        You are editing the <strong className="text-foreground">draft</strong> in PostgreSQL.
        Nothing changes anywhere else in the CRM until you publish — the rest of the
        application reads the generated <code>spec/*.json</code> files, which publishing
        rewrites.
        {pending !== null && pending > 0 && (
          <>
            {' '}
            <strong className="text-foreground">
              {pending} unpublished change{pending === 1 ? '' : 's'}.
            </strong>
          </>
        )}
      </p>
    </div>
  )
}

export function StatusBadge({ active, labels }: { active: boolean; labels?: [string, string] }) {
  const [on, off] = labels ?? ['Active', 'Inactive']
  return <Badge variant={active ? 'default' : 'outline'}>{active ? on : off}</Badge>
}

export function Table({ head, children }: { head: ReactNode; children: ReactNode }) {
  return (
    <div className="overflow-x-auto rounded-md border">
      <table className="w-full text-sm">
        <thead className="bg-muted/50 text-muted-foreground text-label">
          <tr className="[&>th]:px-3 [&>th]:py-2 [&>th]:text-left [&>th]:font-medium">{head}</tr>
        </thead>
        <tbody>{children}</tbody>
      </table>
    </div>
  )
}

export function Row({ children, muted }: { children: ReactNode; muted?: boolean }) {
  return (
    <tr
      className={`border-t [&>td]:px-3 [&>td]:py-2 [&>td]:align-top ${
        muted ? 'text-muted-foreground' : ''
      }`}
    >
      {children}
    </tr>
  )
}

export function Mono({ children }: { children: ReactNode }) {
  return <span className="text-muted-foreground font-mono text-xs">{children}</span>
}
