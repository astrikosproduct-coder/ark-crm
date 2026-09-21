import { useEffect, useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { ChevronDownIcon, ChevronRightIcon, FilterIcon, SearchIcon, XIcon } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Command, CommandEmpty, CommandInput, CommandItem, CommandList } from '@/components/ui/command'
import { Input } from '@/components/ui/input'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { fetchCollection } from '@/lib/collections'
import { date as fmtDate, money } from '@/lib/format'
import {
  type Condition,
  type FilterField,
  isComplete,
  type ListFilters,
  OPERATOR_LABELS,
  OPERATORS,
  type Operator,
  valuesNeeded,
} from '@/lib/listFilters'
import { stagesFor } from '@/lib/pipeline'
import { collectionFor, displayNameOf, fieldOptions, idOf } from '@/lib/spec'
import { applyLookupFilter } from '@/lib/spec/conditions'
import { cn } from '@/lib/utils'

interface Option {
  key: string
  label: string
}

/**
 * The toolbar above a live module's list (and a pipeline module's Kanban) —
 * Zoho's layout, reference shared 17 Sep 2026:
 *
 *   [ Open leads ▾ ] [ Filter 2 ]  [ search ]   BD Owner is Sara ×   Value > 250,000 ×
 *
 * Filter opens a panel of the module's fields: find one, tick it, pick how it
 * compares, give a value, Apply Filter. The record search box stays outside the
 * panel, for speed. What is filtering reads as a line of chips, so nobody has
 * to open the panel to know.
 *
 * The SCOPE picker comes before Filter, where Zoho puts the view name, and only
 * on a module that declares one (spec/extensions.json `list_scopes`). It is the
 * answer to "why is this converted lead still in my list": it is not, by
 * default, and the picker is where it went. It sits with the filters rather
 * than beside the page title because it IS one — List and Kanban share it, and
 * it travels in the URL with everything else.
 */
export function ListFilterBar({
  filters,
  plural,
  showStage = true,
  searchPlaceholder = 'Search…',
}: {
  filters: ListFilters
  /** "Leads" — the panel reads "Filter Leads by". */
  plural: string
  /** False on Kanban, whose columns ARE the stages. */
  showStage?: boolean
  searchPlaceholder?: string
}) {
  const hidden = showStage ? undefined : filters.stageField
  const active = Object.entries(filters.conditions).filter(([key]) => key !== hidden)
  const byKey = useMemo(
    () => new Map([...filters.common, ...filters.others].map((f) => [f.key, f])),
    [filters.common, filters.others]
  )

  return (
    <div className="flex flex-wrap items-center gap-2 pt-3">
      <ScopePicker filters={filters} />
      <FilterPanel filters={filters} plural={plural} hidden={hidden} activeCount={active.length} />
      <SearchBox filters={filters} placeholder={searchPlaceholder} />
      {active.map(([key, condition]) => {
        const field = byKey.get(key)
        if (!field) return null
        return (
          <span
            key={key}
            className="border-primary/40 bg-primary/5 text-foreground inline-flex h-7 max-w-72 items-center gap-1 rounded-full border pr-1 pl-2.5 text-xs"
          >
            <span className="truncate">
              <span className="font-medium">{field.label}</span>{' '}
              <ConditionText field={field} filters={filters} condition={condition} />
            </span>
            <button
              type="button"
              aria-label={`Remove the ${field.label} filter`}
              className="hover:bg-accent rounded-full p-0.5"
              onClick={() => filters.remove(key)}
            >
              <XIcon className="size-3" />
            </button>
          </span>
        )
      })}
      {active.length > 1 && (
        <Button type="button" variant="ghost" size="sm" className="h-7 px-2 text-xs" onClick={filters.clearAll}>
          Clear all
        </Button>
      )}
    </div>
  )
}

function SearchBox({ filters, placeholder }: { filters: ListFilters; placeholder: string }) {
  const [text, setText] = useState(filters.q)

  // The URL can change without this box — a pasted link.
  useEffect(() => setText(filters.q), [filters.q])

  // Debounced so a five-letter search is one request, not five.
  useEffect(() => {
    if (text === filters.q) return
    const t = setTimeout(() => filters.setQ(text), 250)
    return () => clearTimeout(t)
  }, [text, filters])

  return (
    <div className="relative w-56">
      <SearchIcon className="text-muted-foreground pointer-events-none absolute top-1/2 left-2.5 size-3.5 -translate-y-1/2" />
      <Input
        id={`list-search-${filters.module}`}
        className="h-8 pl-8 text-sm"
        placeholder={placeholder}
        value={text}
        onChange={(e) => setText(e.target.value)}
      />
    </div>
  )
}

// ------------------------------------------------------------------ the panel

function defaultCondition(field: FilterField): Condition {
  if (field.kind === 'checkbox') return { op: 'is', values: ['true'] }
  return { op: OPERATORS[field.kind][0], values: [] }
}

/**
 * "Open leads" / "Converted leads" / "All leads".
 *
 * Disabled — not hidden — while a hand-written status condition is on. Hiding
 * it would leave the earlier choice on screen with nothing acting on it; this
 * says plainly that the filter has taken over, and removing the chip gives the
 * scope back.
 */
function ScopePicker({ filters }: { filters: ListFilters }) {
  const scope = filters.scope
  if (!scope) return null
  return (
    <Select value={scope.active.key} onValueChange={scope.set} disabled={scope.overridden}>
      <SelectTrigger
        className="h-8 w-auto gap-1 text-xs"
        aria-label="Which records to show"
        title={scope.overridden ? 'Your status filter decides this. Remove it to choose again.' : undefined}
      >
        <SelectValue />
      </SelectTrigger>
      <SelectContent>
        {scope.options.map((option) => (
          <SelectItem key={option.key} value={option.key}>
            {option.label}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  )
}

function FilterPanel({
  filters,
  plural,
  hidden,
  activeCount,
}: {
  filters: ListFilters
  plural: string
  hidden?: string
  activeCount: number
}) {
  const [open, setOpen] = useState(false)
  const [draft, setDraft] = useState<Record<string, Condition>>({})
  const [tried, setTried] = useState(false)
  const [find, setFind] = useState('')
  const [commonOpen, setCommonOpen] = useState(true)
  const [othersOpen, setOthersOpen] = useState(true)

  const needle = find.trim().toLowerCase()
  const shown = (list: FilterField[]) =>
    list.filter((f) => f.key !== hidden && (!needle || f.label.toLowerCase().includes(needle)))
  const incomplete = Object.entries(draft)
    .filter(([, c]) => !isComplete(c))
    .map(([key]) => key)

  const onOpenChange = (next: boolean) => {
    if (next) {
      setDraft({ ...filters.conditions })
      setTried(false)
      setFind('')
    }
    setOpen(next)
  }

  const applyDraft = () => {
    if (incomplete.length) {
      setTried(true)
      return
    }
    // A stage condition set on the List tab is kept while filtering on Kanban.
    const kept = hidden && filters.conditions[hidden] ? { [hidden]: filters.conditions[hidden] } : {}
    filters.apply({ ...draft, ...kept })
    setOpen(false)
  }

  const common = shown(filters.common)
  const others = shown(filters.others)

  const renderGroup = (title: string, list: FilterField[], expanded: boolean, toggle: () => void, withSection: boolean) =>
    list.length > 0 && (
      <div>
        <button
          type="button"
          onClick={toggle}
          className="text-foreground hover:bg-accent flex w-full items-center gap-1 rounded-sm px-1 py-1 text-sm font-semibold"
        >
          {/* Searching opens both groups: a match hidden in a collapsed group is no match. */}
          {expanded || needle ? <ChevronDownIcon className="size-3.5" /> : <ChevronRightIcon className="size-3.5" />}
          {title}
        </button>
        {(expanded || needle) && (
          <div className="space-y-0.5">
            {list.map((field) => (
              <FieldRow
                key={field.key}
                field={field}
                filters={filters}
                withSection={withSection}
                condition={draft[field.key]}
                flagged={tried && incomplete.includes(field.key)}
                onChange={(condition) =>
                  setDraft((d) => {
                    const next = { ...d }
                    if (condition) next[field.key] = condition
                    else delete next[field.key]
                    return next
                  })
                }
              />
            ))}
          </div>
        )}
      </div>
    )

  return (
    <Popover open={open} onOpenChange={onOpenChange}>
      <PopoverTrigger asChild>
        <Button
          type="button"
          variant="outline"
          size="sm"
          className={cn('font-normal', activeCount > 0 && 'border-primary text-primary bg-primary/5')}
        >
          <FilterIcon className="size-3.5" />
          Filter
          {activeCount > 0 && (
            <span className="bg-primary text-primary-foreground rounded-full px-1.5 text-xs tabular-nums">{activeCount}</span>
          )}
        </Button>
      </PopoverTrigger>
      <PopoverContent align="start" className="flex max-h-[75vh] w-[22rem] flex-col p-0">
        <div className="space-y-2 border-b px-3 py-2">
          <p className="text-sm font-semibold">Filter {plural} by</p>
          <div className="relative">
            <SearchIcon className="text-muted-foreground pointer-events-none absolute top-1/2 left-2.5 size-3.5 -translate-y-1/2" />
            <Input
              id={`filter-find-${filters.module}`}
              aria-label="Find a field"
              className="h-8 pl-8 text-sm"
              placeholder="Find a field"
              value={find}
              onChange={(e) => setFind(e.target.value)}
            />
          </div>
        </div>
        <div className="min-h-0 flex-1 space-y-2 overflow-y-auto px-2 py-2">
          {renderGroup('Common filters', common, commonOpen, () => setCommonOpen((v) => !v), false)}
          {renderGroup('Filter by fields', others, othersOpen, () => setOthersOpen((v) => !v), true)}
          {needle && common.length + others.length === 0 && (
            <p className="text-muted-foreground px-2 py-3 text-sm">No field is called “{find.trim()}”.</p>
          )}
        </div>
        <div className="flex items-center gap-2 border-t px-3 py-2">
          <Button type="button" size="sm" onClick={applyDraft}>
            Apply Filter
          </Button>
          <Button
            type="button"
            size="sm"
            variant="outline"
            onClick={() => {
              setDraft({})
              filters.clearAll()
              setOpen(false)
            }}
          >
            Clear
          </Button>
          {tried && incomplete.length > 0 && <span className="text-destructive text-xs">Give each ticked field a value.</span>}
        </div>
      </PopoverContent>
    </Popover>
  )
}

function FieldRow({
  field,
  filters,
  withSection,
  condition,
  flagged,
  onChange,
}: {
  field: FilterField
  filters: ListFilters
  withSection: boolean
  condition?: Condition
  flagged: boolean
  onChange: (condition: Condition | undefined) => void
}) {
  const id = `filter-${filters.module}-${field.key.replace(/\W/g, '-')}`
  const operators = OPERATORS[field.kind]
  return (
    <div className="rounded-sm px-1 py-0.5">
      <label htmlFor={id} className="hover:bg-accent flex cursor-pointer items-center gap-2 rounded-sm px-1 py-1 text-sm">
        <Checkbox
          id={id}
          checked={Boolean(condition)}
          onCheckedChange={(checked) => onChange(checked ? defaultCondition(field) : undefined)}
        />
        <span className="min-w-0 truncate">{field.label}</span>
        {withSection && (
          <span className="text-muted-foreground ml-auto shrink-0 truncate pl-2 text-[11px]" title={`On the record under ${field.section}`}>
            {field.section}
          </span>
        )}
      </label>
      {condition && (
        <div className="space-y-1.5 pt-0.5 pb-1.5 pl-7">
          {operators.length > 1 && (
            <Select
              value={condition.op}
              onValueChange={(op) =>
                onChange({
                  op: op as Operator,
                  values: valuesNeeded(op as Operator) === valuesNeeded(condition.op) ? condition.values : [],
                })
              }
            >
              <SelectTrigger className="h-7 w-auto min-w-24 text-xs" aria-label={`How ${field.label} compares`}>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {operators.map((op) => (
                  <SelectItem key={op} value={op} className="text-xs">
                    {OPERATOR_LABELS[op]}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          )}
          <ValueEditor field={field} filters={filters} condition={condition} onChange={onChange} id={id} />
          {flagged && <p className="text-destructive text-xs">Give it a value, or untick it.</p>}
        </div>
      )}
    </div>
  )
}

function ValueEditor({
  field,
  filters,
  condition,
  onChange,
  id,
}: {
  field: FilterField
  filters: ListFilters
  condition: Condition
  onChange: (condition: Condition) => void
  id: string
}) {
  const needed = valuesNeeded(condition.op)
  if (needed === 0) return null
  const set = (index: number, value: string) => {
    const values = [...condition.values]
    values[index] = value
    onChange({ ...condition, values })
  }

  if (field.kind === 'checkbox') {
    return (
      <Select value={condition.values[0] ?? 'true'} onValueChange={(v) => onChange({ op: 'is', values: [v] })}>
        <SelectTrigger className="h-7 w-24 text-xs" aria-label={field.label}>
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="true" className="text-xs">
            Yes
          </SelectItem>
          <SelectItem value="false" className="text-xs">
            No
          </SelectItem>
        </SelectContent>
      </Select>
    )
  }

  if (field.kind === 'choice') {
    return <ChoicePicker field={field} filters={filters} selected={condition.values} onChange={(values) => onChange({ ...condition, values })} />
  }

  const type = field.kind === 'date' ? 'date' : field.kind === 'month' ? 'month' : field.kind === 'number' ? 'number' : 'text'
  const input = (index: number, label: string) => (
    <Input
      id={index === 0 ? `${id}-value` : `${id}-to`}
      aria-label={label}
      type={type}
      className="h-7 text-xs"
      value={condition.values[index] ?? ''}
      onChange={(e) => set(index, e.target.value)}
    />
  )
  if (needed === 2) {
    return (
      <div className="grid grid-cols-[1fr_auto_1fr] items-center gap-1.5">
        {input(0, `${field.label} from`)}
        <span className="text-muted-foreground text-xs">and</span>
        {input(1, `${field.label} to`)}
      </div>
    )
  }
  return input(0, field.label)
}

/** The choices of a picklist, lookup or stage field, labelled as the form labels them. */
function useChoiceOptions(field: FilterField, filters: ListFilters): { options: Option[]; loading: boolean } {
  const spec = field.field
  const collection = field.kind === 'choice' && spec.type === 'lookup' ? collectionFor(spec.lookup_target) : undefined
  const { data: rows, isLoading } = useQuery({
    queryKey: ['collection', collection],
    queryFn: () => fetchCollection(collection!),
    enabled: Boolean(collection),
    staleTime: 30_000,
  })
  const limit = filters.choiceLimits?.[field.key]
  const options = useMemo<Option[]>(() => {
    if (field.kind !== 'choice') return []
    let out: Option[]
    if (spec.type !== 'lookup') {
      out = fieldOptions(spec).map((o) => ({ key: o.key, label: o.label }))
      if (spec.api_name === filters.stageField) {
        // A stage field offers only the stages this module carries.
        const inRange = new Set(stagesFor(filters.module).map((s) => s.stage))
        out = out.filter((o) => inRange.has(Number(/^(\d+)/.exec(o.key)?.[1])))
      }
    } else {
      out = applyLookupFilter(rows ?? [], spec.lookup_filter_expr)
        .map((row) => ({ key: idOf(row), label: displayNameOf(row) }))
        .filter((o) => o.key)
        .sort((a, b) => a.label.localeCompare(b.label))
    }
    return limit ? out.filter((o) => limit.includes(o.key)) : out
  }, [field.kind, spec, rows, limit, filters.stageField, filters.module])
  return { options, loading: isLoading && Boolean(collection) }
}

function ChoicePicker({
  field,
  filters,
  selected,
  onChange,
}: {
  field: FilterField
  filters: ListFilters
  selected: string[]
  onChange: (values: string[]) => void
}) {
  const { options, loading } = useChoiceOptions(field, filters)
  const chosen = new Set(selected)
  const toggle = (key: string) => onChange(chosen.has(key) ? selected.filter((k) => k !== key) : [...selected, key])
  const summary =
    selected.length === 0
      ? 'Choose…'
      : selected.length === 1
        ? (options.find((o) => o.key === selected[0])?.label ?? selected[0])
        : `${selected.length} chosen`

  return (
    <Popover>
      <PopoverTrigger asChild>
        <Button type="button" variant="outline" size="sm" className="h-7 w-full justify-between px-2 text-xs font-normal">
          <span className={cn('truncate', selected.length === 0 && 'text-muted-foreground')}>{summary}</span>
          <ChevronDownIcon className="size-3.5 opacity-60" />
        </Button>
      </PopoverTrigger>
      <PopoverContent align="start" className="w-64 p-0">
        <Command>
          {options.length > 8 && <CommandInput placeholder="Find…" />}
          <CommandList>
            <CommandEmpty>{loading ? 'Loading…' : 'Nothing to pick.'}</CommandEmpty>
            <div className="p-1">
              {options.map((option) => (
                <CommandItem key={option.key} value={`${option.label} ${option.key}`} onSelect={() => toggle(option.key)}>
                  <Checkbox checked={chosen.has(option.key)} tabIndex={-1} className="pointer-events-none" />
                  <span className="truncate">{option.label}</span>
                </CommandItem>
              ))}
            </div>
          </CommandList>
        </Command>
      </PopoverContent>
    </Popover>
  )
}

/** "is Sara, Omar" · "between 01 Oct 2026 and 31 Dec 2026" · "> 250,000" — a chip's words. */
function ConditionText({ field, filters, condition }: { field: FilterField; filters: ListFilters; condition: Condition }) {
  const { options } = useChoiceOptions(field, filters)
  const word = OPERATOR_LABELS[condition.op]
  if (valuesNeeded(condition.op) === 0) return <>{word}</>
  const show = (value: string) => {
    if (field.kind === 'choice') return options.find((o) => o.key === value)?.label ?? value
    if (field.kind === 'checkbox') return value === 'false' ? 'No' : 'Yes'
    if (field.kind === 'date') return fmtDate(value)
    if (field.kind === 'month') return fmtDate(`${value}-01`).replace(/^\d+\s/, '')
    if (field.kind === 'number') return money(Number(value))
    return `“${value}”`
  }
  if (condition.op === 'between') {
    return (
      <>
        between {show(condition.values[0] ?? '')} and {show(condition.values[1] ?? '')}
      </>
    )
  }
  const shown = condition.values.map(show)
  return (
    <>
      {word} {shown.length > 2 ? `${shown.slice(0, 2).join(', ')} +${shown.length - 2}` : shown.join(', ')}
    </>
  )
}
