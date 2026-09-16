import { useEffect, useState } from 'react'
import { BuildingIcon, CheckIcon, ChevronsUpDownIcon, UserPlusIcon } from 'lucide-react'

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
import { errorMessage, useDirectorySearch, type AdminUser, type DirectoryPerson } from '@/lib/admin'

interface Props {
  users: AdminUser[]
  loading?: boolean
  /** An existing person was picked — their details come from the database. */
  onPick: (user: AdminUser) => void
  /** Someone new was picked from the Astrikos directory. */
  onPickDirectory: (person: DirectoryPerson) => void
  /** Nobody matched. The typed text seeds the name on a fresh record. */
  onCreateNew: (typedName: string) => void
}

/** How long typing must pause before the directory is asked. */
const DEBOUNCE_MS = 300

/**
 * Step one of adding a user: find the person.
 *
 * Two sources, in this order:
 *   Existing people     already in ARK CRM — picking one edits their roles
 *   Astrikos directory  Microsoft Entra members — picking one adds them, linked
 *                       to their Microsoft account from the start
 * and a manual entry for anyone the directory cannot supply.
 *
 * A directory hit that is ALREADY in ARK CRM opens that user rather than
 * offering a duplicate.
 *
 * The search is on NAME (and email), never on user id — nobody remembers
 * USR-014. This is a purpose-built combobox rather than the spec-driven
 * LookupCombobox, which reads a FieldSpec and resolves its collection through
 * the register; users live in PostgreSQL and are not a spec collection.
 */
export function UserLookup({ users, loading, onPick, onPickDirectory, onCreateNew }: Props) {
  const [open, setOpen] = useState(false)
  const [search, setSearch] = useState('')
  const [debounced, setDebounced] = useState('')

  useEffect(() => {
    const timer = window.setTimeout(() => setDebounced(search), DEBOUNCE_MS)
    return () => window.clearTimeout(timer)
  }, [search])

  const directory = useDirectorySearch(debounced)
  const typed = search.trim()

  const close = () => {
    setOpen(false)
    setSearch('')
  }

  const pickDirectory = (person: DirectoryPerson) => {
    const already = person.user_id ? users.find((u) => u.user_id === person.user_id) : undefined
    if (already) onPick(already)
    else onPickDirectory(person)
    close()
  }

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
          Search people by name or email…
          <ChevronsUpDownIcon className="ml-2 size-4 shrink-0 opacity-50" />
        </Button>
      </PopoverTrigger>

      <PopoverContent className="w-(--radix-popover-trigger-width) p-0">
        <Command>
          <CommandInput
            placeholder="Type a name or email…"
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
                    close()
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
            {/* Items carry the typed text in their value: the server already
                matched them, and cmdk's own filter must not hide a hit
                because Microsoft matched on a word it does not weigh. */}
            <CommandGroup heading="Astrikos directory">
              <DirectoryStatus
                typed={typed}
                waiting={typed !== debounced.trim() || directory.isFetching}
                error={directory.isError ? errorMessage(directory.error) : null}
                empty={directory.isSuccess && directory.data.length === 0}
                search={search}
              />
              {typed.length >= 2 &&
                directory.data?.map((person) => (
                  <CommandItem
                    key={person.entra_object_id}
                    value={`${search} directory ${person.entra_object_id}`}
                    onSelect={() => pickDirectory(person)}
                  >
                    <BuildingIcon className="size-4" />
                    <span className="min-w-0">
                      <span className="block truncate">{person.name}</span>
                      <span className="text-muted-foreground block truncate text-xs">
                        {[person.email, person.job_title, person.department].filter(Boolean).join(' · ')}
                      </span>
                    </span>
                    <span className="text-muted-foreground ml-auto shrink-0 text-xs">
                      {person.user_id ? `In ARK CRM · ${person.user_id}` : 'Add'}
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
                  onCreateNew(typed)
                  close()
                }}
              >
                <UserPlusIcon className="size-4" />
                {typed ? `Add "${typed}" manually` : 'Add someone manually'}
              </CommandItem>
            </CommandGroup>
          </CommandList>
        </Command>
      </PopoverContent>
    </Popover>
  )
}

/**
 * The one line of state under the directory heading. A CommandItem that cannot
 * be selected, rather than a bare div, because cmdk hides a group that has no
 * items — and a missing permission must be read, not hidden.
 */
function DirectoryStatus({
  typed,
  waiting,
  error,
  empty,
  search,
}: {
  typed: string
  waiting: boolean
  error: string | null
  empty: boolean
  search: string
}) {
  const message =
    typed.length < 2
      ? 'Type at least two letters to search Microsoft.'
      : waiting
        ? 'Searching…'
        : error
          ? error
          : empty
            ? 'No Astrikos employee matches.'
            : null
  if (!message) return null
  return (
    <CommandItem
      disabled
      value={`${search} directory status`}
      className={cn('text-xs', error ? 'text-destructive' : 'text-muted-foreground')}
    >
      {message}
    </CommandItem>
  )
}
