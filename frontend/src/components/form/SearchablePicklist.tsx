import { useMemo, useState } from 'react'
import { CheckIcon, ChevronsUpDownIcon } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Command, CommandEmpty, CommandGroup, CommandInput, CommandItem, CommandList } from '@/components/ui/command'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import type { PicklistOption } from '@/types/field'
import { cn } from '@/lib/utils'

/** Above this many choices a picklist gets a search box (Release 1.1: 249 countries). */
export const SEARCHABLE_FROM = 15

/**
 * A picklist with a search box — the same control as a lookup
 * (LookupCombobox), over a list of choices instead of records. Used for long
 * lists: Country has 249 choices, a country's States up to a few hundred.
 *
 * Choosing the selected choice again clears it, as in a lookup.
 */
export function SearchablePicklist({
  id,
  options,
  value,
  onChange,
  invalid,
  placeholder = 'Select…',
  noun = 'choice',
}: {
  id: string
  options: PicklistOption[]
  value: string | null
  onChange: (value: string | null) => void
  invalid?: boolean
  placeholder?: string
  /** "country", "state" — for the search box and the empty message. */
  noun?: string
}) {
  const [open, setOpen] = useState(false)
  const selected = useMemo(() => options.find((o) => o.key === value)?.label ?? value ?? '', [options, value])

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button
          id={id}
          type="button"
          variant="outline"
          role="combobox"
          aria-expanded={open}
          aria-invalid={invalid}
          className={cn(
            'bg-input-bg data-[state=open]:border-ring data-[state=open]:ring-ring/50 data-[state=open]:ring-[3px] h-9 w-full justify-between font-normal',
            !value && 'text-muted-foreground'
          )}
        >
          <span className="truncate">{value ? selected : placeholder}</span>
          <ChevronsUpDownIcon className="ml-2 size-4 shrink-0 opacity-50" />
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-(--radix-popover-trigger-width) p-0">
        <Command>
          <CommandInput placeholder={`Search ${noun}…`} />
          <CommandList>
            <CommandEmpty>No {noun} found</CommandEmpty>
            <CommandGroup>
              {options.map((o) => (
                <CommandItem
                  key={o.key}
                  value={`${o.label} ${o.key}`}
                  onSelect={() => {
                    onChange(o.key === value ? null : o.key)
                    setOpen(false)
                  }}
                >
                  <CheckIcon className={cn('size-4', value === o.key ? 'opacity-100' : 'opacity-0')} />
                  <span className="truncate">{o.label}</span>
                </CommandItem>
              ))}
            </CommandGroup>
          </CommandList>
        </Command>
      </PopoverContent>
    </Popover>
  )
}
