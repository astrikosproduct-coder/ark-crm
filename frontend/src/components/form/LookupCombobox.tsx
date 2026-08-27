import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { CheckIcon, ChevronsUpDownIcon, PlusIcon } from 'lucide-react'

import { Button } from '@/components/ui/button'
import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
  CommandSeparator,
} from '@/components/ui/command'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { api } from '@/lib/api'
import { applyLookupFilter } from '@/lib/spec/conditions'
import { collectionFor, displayNameOf, idOf } from '@/lib/spec'
import { cn } from '@/lib/utils'
import type { FieldSpec } from '@/types/field'

type Record_ = Record<string, unknown>

interface Props {
  field: FieldSpec
  value: unknown
  onChange: (value: string | null) => void
  onCreateNew?: (field: FieldSpec) => void
  disabled?: boolean
  id?: string
}

/**
 * Searchable lookup over the target collection.
 *
 * Reads through /api/<collection> with Axios and TanStack Query like any other
 * data access — CLAUDE.md rule 2 — so this component behaves identically once
 * a real backend replaces MSW.
 */
export function LookupCombobox({ field, value, onChange, onCreateNew, disabled, id }: Props) {
  const [open, setOpen] = useState(false)
  const collection = collectionFor(field.lookup_target)

  const { data, isLoading, isError } = useQuery({
    queryKey: ['collection', collection],
    queryFn: async () => (await api.get<Record_[]>(`/${collection}`)).data,
    enabled: Boolean(collection) && open,
    staleTime: 30_000,
  })

  // The same query, kept warm so a selected value can render its name without
  // opening the popover.
  const { data: resolved } = useQuery({
    queryKey: ['collection', collection],
    queryFn: async () => (await api.get<Record_[]>(`/${collection}`)).data,
    enabled: Boolean(collection) && Boolean(value),
    staleTime: 30_000,
  })

  const rows = useMemo(() => {
    const all = Array.isArray(data) ? data : []
    return applyLookupFilter(all, field.lookup_filter_expr)
  }, [data, field.lookup_filter_expr])

  const selectedLabel = useMemo(() => {
    if (!value) return ''
    const hit = (resolved ?? []).find((r) => idOf(r) === value)
    return hit ? displayNameOf(hit) : String(value)
  }, [resolved, value])

  if (!collection) {
    return (
      <div className="flex h-9 items-center rounded-md border border-dashed px-3 text-sm text-muted-foreground">
        No lookup_target in the register
      </div>
    )
  }

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
          className={cn('h-9 w-full justify-between font-normal', !value && 'text-muted-foreground')}
        >
          <span className="truncate">{value ? selectedLabel : `Search ${field.lookup_target}…`}</span>
          <ChevronsUpDownIcon className="ml-2 size-4 shrink-0 opacity-50" />
        </Button>
      </PopoverTrigger>

      <PopoverContent className="w-(--radix-popover-trigger-width) p-0">
        <Command>
          <CommandInput placeholder={`Search ${field.lookup_target}…`} />
          <CommandList>
            {isLoading && <div className="py-6 text-center text-sm text-muted-foreground">Loading…</div>}
            {isError && (
              <div className="py-6 text-center text-sm text-destructive">
                Could not load {collection}
              </div>
            )}
            {!isLoading && !isError && (
              <CommandEmpty>
                {field.lookup_filter_expr
                  ? `No ${field.lookup_target} matches ${field.lookup_filter}`
                  : `No ${field.lookup_target} found`}
              </CommandEmpty>
            )}

            <CommandGroup>
              {rows.map((row) => {
                const rid = idOf(row)
                return (
                  <CommandItem
                    key={rid}
                    value={`${displayNameOf(row)} ${rid}`}
                    onSelect={() => {
                      onChange(rid === value ? null : rid)
                      setOpen(false)
                    }}
                  >
                    <CheckIcon className={cn('size-4', value === rid ? 'opacity-100' : 'opacity-0')} />
                    <span className="truncate">{displayNameOf(row)}</span>
                    <span className="ml-auto text-xs text-muted-foreground">{rid}</span>
                  </CommandItem>
                )
              })}
            </CommandGroup>

            {onCreateNew && (
              <>
                <CommandSeparator />
                <CommandGroup>
                  <CommandItem
                    value="__create_new__"
                    onSelect={() => {
                      setOpen(false)
                      onCreateNew(field)
                    }}
                  >
                    <PlusIcon className="size-4" />
                    Create new {field.lookup_target}
                  </CommandItem>
                </CommandGroup>
              </>
            )}
          </CommandList>
        </Command>
      </PopoverContent>
    </Popover>
  )
}
