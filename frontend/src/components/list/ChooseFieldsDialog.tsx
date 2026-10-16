import { useEffect, useMemo, useState } from 'react'
import { GripVerticalIcon, SearchIcon } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Input } from '@/components/ui/input'
import { Sheet, SheetContent, SheetHeader, SheetTitle } from '@/components/ui/sheet'
import { cn } from '@/lib/utils'
import type { FieldSpec } from '@/types/field'

/**
 * Pick fields and put them in order — Zoho's Manage Columns (Release 1.2, 14 Oct 2026).
 *
 * The chosen fields come first, in their order, and are dragged by the grip to
 * reorder; every other field follows alphabetically. `locked` fields are always
 * on and stay first — a list's record name, which is the link into the record.
 * What may be offered is the caller's to decide; it never names a field itself.
 * A drawer that drops from the top of the screen, at its right — where View
 * Settings is — and lists fields by label alone.
 */
export function ChooseFieldsDialog({
  open,
  title,
  fields,
  selected,
  locked = [],
  max,
  saveLabel = 'Save',
  onSave,
  onClose,
}: {
  open: boolean
  title: string
  fields: FieldSpec[]
  selected: string[]
  locked?: string[]
  /** At most this many chosen (locked ones included). */
  max?: number
  saveLabel?: string
  onSave: (selected: string[]) => void
  onClose: () => void
}) {
  const [order, setOrder] = useState<string[]>(selected)
  const [search, setSearch] = useState('')
  const [dragging, setDragging] = useState<number | null>(null)

  useEffect(() => {
    if (open) {
      setOrder([...locked, ...selected.filter((name) => !locked.includes(name))])
      setSearch('')
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open])

  const byName = useMemo(() => new Map(fields.map((f) => [f.api_name, f])), [fields])
  const matches = (f: FieldSpec) => !search || f.label.toLowerCase().includes(search.trim().toLowerCase())
  const chosen = order.map((name) => byName.get(name)).filter((f): f is FieldSpec => Boolean(f))
  const rest = fields
    .filter((f) => !order.includes(f.api_name))
    .sort((a, b) => a.label.localeCompare(b.label))
  const full = max !== undefined && order.length >= max

  const toggle = (name: string) =>
    setOrder((current) => (current.includes(name) ? current.filter((n) => n !== name) : [...current, name]))

  const drop = (to: number) => {
    if (dragging === null || dragging === to) return
    setOrder((current) => {
      const next = [...current]
      const [moved] = next.splice(dragging, 1)
      next.splice(Math.max(to, locked.length), 0, moved)
      return next
    })
    setDragging(null)
  }

  const row = (f: FieldSpec, index: number | null) => {
    const isLocked = locked.includes(f.api_name)
    const on = index !== null
    return (
      <li
        key={f.qref}
        draggable={on && !isLocked}
        onDragStart={() => setDragging(index)}
        onDragOver={(e) => on && e.preventDefault()}
        onDrop={() => index !== null && drop(index)}
        className={cn(
          'flex items-center gap-2 rounded-md px-2 py-1.5 text-sm',
          on && !isLocked && 'hover:bg-accent cursor-grab',
          dragging === index && 'opacity-50'
        )}
      >
        <GripVerticalIcon className={cn('text-muted-foreground size-4 shrink-0', (!on || isLocked) && 'invisible')} />
        <Checkbox
          id={`choose-${f.qref}`}
          checked={on}
          disabled={isLocked || (!on && full)}
          onCheckedChange={() => toggle(f.api_name)}
        />
        <label htmlFor={`choose-${f.qref}`} className="min-w-0 flex-1 truncate">
          {f.label}
          {isLocked && <span className="text-destructive">*</span>}
        </label>
      </li>
    )
  }

  return (
    <Sheet open={open} onOpenChange={(next) => !next && onClose()}>
      <SheetContent side="top" aria-describedby={undefined} className="right-4 w-[calc(100%-2rem)] max-w-md gap-4 p-5 sm:right-8">
        <SheetHeader>
          <SheetTitle>{title}</SheetTitle>
        </SheetHeader>
        <div className="relative">
          <SearchIcon className="text-muted-foreground pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2" />
          <Input className="pl-9" placeholder="Search" value={search} onChange={(e) => setSearch(e.target.value)} />
        </div>
        <ul className="-mx-2 min-h-0 flex-1 overflow-y-auto">
          {chosen.map((f, i) => (matches(f) ? row(f, i) : null))}
          {chosen.length > 0 && rest.some(matches) && <li aria-hidden className="border-border my-1 border-t" />}
          {rest.filter(matches).map((f) => row(f, null))}
        </ul>
        {max !== undefined && (
          <p className="text-muted-foreground text-xs">
            {order.length} of {max} chosen.
          </p>
        )}
        <div className="flex justify-end gap-2">
          <Button variant="outline" onClick={onClose}>
            Cancel
          </Button>
          <Button onClick={() => onSave(order)}>{saveLabel}</Button>
        </div>
      </SheetContent>
    </Sheet>
  )
}
