import { useState } from 'react'
import { CheckIcon, ChevronsUpDownIcon } from 'lucide-react'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from '@/components/ui/command'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { cn } from '@/lib/utils'
import type { PicklistOption } from '@/types/field'

interface Props {
  id?: string
  options: PicklistOption[]
  value: string[]
  onChange: (value: string[]) => void
  disabled?: boolean
  placeholder?: string
}

export function MultiSelect({ id, options, value, onChange, disabled, placeholder }: Props) {
  const [open, setOpen] = useState(false)

  const toggle = (key: string) => {
    onChange(value.includes(key) ? value.filter((v) => v !== key) : [...value, key])
  }

  const labelOf = (key: string) => options.find((o) => o.key === key)?.label ?? key

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button
          id={id}
          type="button"
          variant="outline"
          role="combobox"
          aria-expanded={open}
          disabled={disabled}
          className="bg-input-bg data-[state=open]:border-ring data-[state=open]:ring-ring/50 data-[state=open]:ring-[3px] h-auto min-h-9 w-full justify-between font-normal"
        >
          <span className="flex flex-wrap gap-1 py-1">
            {value.length === 0 && (
              <span className="text-muted-foreground">{placeholder ?? 'Select…'}</span>
            )}
            {value.map((v) => (
              <Badge key={v} variant="secondary">
                {labelOf(v)}
              </Badge>
            ))}
          </span>
          <ChevronsUpDownIcon className="ml-2 size-4 shrink-0 opacity-50" />
        </Button>
      </PopoverTrigger>

      <PopoverContent className="w-(--radix-popover-trigger-width) p-0">
        <Command>
          <CommandInput placeholder="Search…" />
          <CommandList>
            <CommandEmpty>Nothing matches</CommandEmpty>
            <CommandGroup>
              {options.map((o) => (
                <CommandItem key={o.key} value={o.label} onSelect={() => toggle(o.key)}>
                  <CheckIcon
                    className={cn('size-4', value.includes(o.key) ? 'opacity-100' : 'opacity-0')}
                  />
                  {o.label}
                </CommandItem>
              ))}
            </CommandGroup>
          </CommandList>
        </Command>
      </PopoverContent>
    </Popover>
  )
}
