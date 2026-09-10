import { useState } from 'react'
import { CheckIcon, ChevronsUpDownIcon, UserPlusIcon } from 'lucide-react'

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
import { cn } from '@/lib/utils'
import type { AdminUser } from '@/lib/admin'

interface Props {
  users: AdminUser[]
  loading?: boolean
  /** An existing person was picked — their details come from the database. */
  onPick: (user: AdminUser) => void
  /** Nobody matched. The typed text seeds the name on a fresh record. */
  onCreateNew: (typedName: string) => void
}

/**
 * Step one of adding a user: find out whether this person already exists.
 *
 * The search is on NAME, never on user id — nobody remembers USR-014. This is
 * a purpose-built combobox rather than the spec-driven LookupCombobox, which
 * reads a FieldSpec and resolves its collection through the register; users
 * live in PostgreSQL and are not a spec collection.
 */
export function UserLookup({ users, loading, onPick, onCreateNew }: Props) {
  const [open, setOpen] = useState(false)
  const [search, setSearch] = useState('')

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button
          type="button"
          variant="outline"
          role="combobox"
          aria-expanded={open}
          className="data-[state=open]:border-ring data-[state=open]:ring-ring/50 data-[state=open]:ring-[3px] h-9 w-full justify-between font-normal text-muted-foreground"
        >
          Search people by name…
          <ChevronsUpDownIcon className="ml-2 size-4 shrink-0 opacity-50" />
        </Button>
      </PopoverTrigger>

      <PopoverContent className="w-(--radix-popover-trigger-width) p-0">
        <Command>
          <CommandInput
            placeholder="Type a name…"
            value={search}
            onValueChange={setSearch}
          />
          <CommandList>
            {loading && (
              <div className="text-muted-foreground py-6 text-center text-sm">Loading…</div>
            )}
            {!loading && <CommandEmpty>No one by that name yet</CommandEmpty>}

            <CommandGroup heading="Existing people">
              {users.map((user) => (
                <CommandItem
                  key={user.user_id}
                  value={`${user.name} ${user.email} ${user.user_id}`}
                  onSelect={() => {
                    onPick(user)
                    setOpen(false)
                    setSearch('')
                  }}
                >
                  <CheckIcon className={cn('size-4', 'opacity-0')} />
                  <span className="truncate">{user.name}</span>
                  <span className="text-muted-foreground ml-auto text-xs">
                    {user.user_id}
                  </span>
                </CommandItem>
              ))}
            </CommandGroup>

            <CommandSeparator />
            <CommandGroup>
              {/* The value carries the search text so cmdk's filter always
                  keeps this item visible. A fixed value would be filtered out
                  by a name that matches nobody — precisely when the admin
                  needs the create option. */}
              <CommandItem
                value={`create new User ${search}`}
                onSelect={() => {
                  onCreateNew(search.trim())
                  setOpen(false)
                  setSearch('')
                }}
              >
                <UserPlusIcon className="size-4" />
                {search.trim() ? `Create "${search.trim()}"` : 'Create a new User'}
              </CommandItem>
            </CommandGroup>
          </CommandList>
        </Command>
      </PopoverContent>
    </Popover>
  )
}
