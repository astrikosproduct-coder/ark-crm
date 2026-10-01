import { useState } from 'react'
import { PlusIcon } from 'lucide-react'

import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { errorMessage } from '@/lib/admin'
import { useCreateSection, useUpdateSection } from '@/lib/metadata'

/**
 * Adding and renaming sections — on the layout, where Zoho has them, since the
 * Fields tab became a plain listing (Setup rebuild, 4b, 1 Oct 2026). Moved here
 * from that tab unchanged in what they do.
 *
 * Sections are per module and their labels are unique within one: the API
 * refuses a duplicate rather than creating a second section nothing could tell
 * apart. A section is renamed rather than recreated, because placements point
 * at its id — the label is not its identity.
 */

/** Zoho's full-width NEW SECTION button, under the New Fields palette. */
export function NewSectionButton({ moduleKey }: { moduleKey: string }) {
  const createSection = useCreateSection()
  const [open, setOpen] = useState(false)
  const [label, setLabel] = useState('')
  const [error, setError] = useState<string | null>(null)

  const submit = async () => {
    setError(null)
    try {
      await createSection.mutateAsync({ module_key: moduleKey, label: label.trim() })
      setLabel('')
      setOpen(false)
    } catch (err) {
      setError(errorMessage(err))
    }
  }

  return (
    <>
      <Button
        type="button"
        variant="outline"
        className="w-full justify-center text-xs font-semibold tracking-wide"
        onClick={() => setOpen(true)}
      >
        <PlusIcon className="size-4" />
        NEW SECTION
      </Button>

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Add a section</DialogTitle>
            <DialogDescription>
              Sections group the fields on the form. Each name is used once per module.
            </DialogDescription>
          </DialogHeader>

          <Input
            value={label}
            autoFocus
            placeholder="Section name"
            onChange={(e) => setLabel(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && label.trim()) void submit()
            }}
          />
          {error && <p className="text-destructive text-sm">{error}</p>}

          <DialogFooter>
            <Button variant="ghost" onClick={() => setOpen(false)}>
              Cancel
            </Button>
            <Button disabled={!label.trim() || createSection.isPending} onClick={() => void submit()}>
              {createSection.isPending ? 'Adding…' : 'Add section'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  )
}

/** A section's name, renamed in place: click it, type, Enter. */
export function SectionLabel({
  sectionId,
  label,
  className,
}: {
  sectionId: number
  label: string
  className?: string
}) {
  const updateSection = useUpdateSection()
  const [editing, setEditing] = useState(false)
  const [value, setValue] = useState(label)
  const [error, setError] = useState<string | null>(null)

  const save = async () => {
    const next = value.trim()
    if (!next || next === label) {
      setEditing(false)
      return
    }
    setError(null)
    try {
      await updateSection.mutateAsync({ sectionId, patch: { label: next } })
      setEditing(false)
    } catch (err) {
      setError(errorMessage(err))
    }
  }

  if (!editing) {
    return (
      <button
        type="button"
        className={className ?? 'hover:text-foreground text-left text-sm font-bold'}
        title="Rename this section"
        onClick={() => {
          setValue(label)
          setEditing(true)
        }}
      >
        {label}
      </button>
    )
  }

  return (
    <span className="flex items-center gap-2">
      <Input
        className="h-7 w-72"
        value={value}
        autoFocus
        disabled={updateSection.isPending}
        onChange={(e) => setValue(e.target.value)}
        onBlur={() => void save()}
        onKeyDown={(e) => {
          if (e.key === 'Enter') void save()
          if (e.key === 'Escape') setEditing(false)
        }}
      />
      {error && <span className="text-destructive text-xs">{error}</span>}
    </span>
  )
}
