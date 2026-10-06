import type { ReactNode } from 'react'

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

export function StatusBadge({ active, labels }: { active: boolean; labels?: [string, string] }) {
  const [on, off] = labels ?? ['Active', 'Inactive']
  return <Badge variant={active ? 'default' : 'outline'}>{active ? on : off}</Badge>
}

export function Table({ head, children }: { head: ReactNode; children: ReactNode }) {
  return (
    <div className="bg-card overflow-x-auto rounded-lg shadow-sm">
      <table className="w-full text-sm">
        <thead className="text-muted-foreground text-label [&>tr>th]:border-border [&>tr>th]:border-b">
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

/**
 * Zoho's Status toggle — the on/off pill at the end of a Setup row. A button
 * with role="switch"; the project has no switch primitive and one control is
 * not worth a dependency.
 */
/**
 * A change saved to the draft and not yet published (Setup 4e) — on a module,
 * a section or a field, wherever Setup lists it. The Publish banner says what
 * the changes are; this says where.
 */
export function PendingDot() {
  return (
    <span
      className="bg-primary ml-1.5 inline-block size-1.5 shrink-0 rounded-full align-middle"
      title="Not published yet"
      aria-label="Not published yet"
    />
  )
}

export function StatusSwitch({
  checked,
  onChange,
  disabled,
  label,
  title,
}: {
  checked: boolean
  onChange?: (next: boolean) => void
  disabled?: boolean
  label: string
  title?: string
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={label}
      title={title}
      disabled={disabled}
      onClick={() => onChange?.(!checked)}
      className={`relative inline-flex h-5 w-9 shrink-0 items-center rounded-full transition-colors disabled:cursor-not-allowed disabled:opacity-60 ${
        checked ? 'bg-emerald-600' : 'bg-muted-foreground/40'
      }`}
    >
      <span
        className={`inline-block size-4 rounded-full bg-white shadow transition-transform ${
          checked ? 'translate-x-4' : 'translate-x-0.5'
        }`}
      />
    </button>
  )
}
