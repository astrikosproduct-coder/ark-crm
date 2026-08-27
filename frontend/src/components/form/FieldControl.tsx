import { useRef } from 'react'
import { Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { ArrowUpRightIcon, PaperclipIcon } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Input } from '@/components/ui/input'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Textarea } from '@/components/ui/textarea'
import { Badge } from '@/components/ui/badge'
import { ChildListTable } from '@/components/form/ChildListTable'
import { LookupCombobox } from '@/components/form/LookupCombobox'
import { MultiSelect } from '@/components/form/MultiSelect'
import { useRecordForm, type FormMode } from '@/hooks/useRecordForm'
import { api } from '@/lib/api'
import { logAutomation } from '@/lib/automation'
import { date as fmtDate, dateTime as fmtDateTime, money, number, percent } from '@/lib/format'
import { computedGap } from '@/lib/spec/formula'
import { collectionFor, displayNameOf, fieldOf, idOf, labelForValue, optionsFor } from '@/lib/spec'
import type { FieldSpec } from '@/types/field'

/**
 * Where a control reads and writes, when that is not the record itself.
 *
 * A child-list cell is the only caller: it holds a value inside a row rather
 * than under the record's api_name. Passing the scope in — instead of writing a
 * second set of table-sized inputs — is what keeps one control layer, so a fix
 * to the currency box or the lookup combobox lands in tables too.
 */
export interface FieldScope {
  value: unknown
  set: (value: unknown) => void
  invalid?: boolean
  /** Overrides the form's mode, for a read-only linked-record table. */
  mode?: FormMode
  /** Must be unique on the page — the row index is folded in by the caller. */
  id?: string
}

interface Props {
  field: FieldSpec
  onCreateNew?: (field: FieldSpec) => void
  scope?: FieldScope
}

/** Types the user never types into, whatever the mode. */
const DERIVED = new Set(['computed', 'autonumber'])

export function FieldControl({ field, onCreateNew, scope }: Props) {
  const form = useRecordForm()
  const value = scope ? scope.value : form.values[field.api_name]
  const id = scope?.id ?? `${field.module}.${field.api_name}`
  const set = scope ? scope.set : (v: unknown) => form.setValue(field.api_name, v)
  const invalid = scope ? Boolean(scope.invalid) : Boolean(form.visibleErrors[field.api_name])
  const mode = scope?.mode ?? form.mode

  if (field.type === 'childlist') return <ChildListTable field={field} />

  // Identity belongs to the record the pursuit started as. An Opportunity shows
  // its End Client and never stores it — see read_through in
  // spec/module_split.json, and toPayload, which strips these on the way out.
  //
  // Same shape as transition_owned below: read-only whatever the mode, with the
  // reason stated underneath rather than left for the user to infer from a box
  // that will not accept typing.
  if (field.carry === 'read_through' && !scope) {
    return <InheritedValue field={field} value={value} mode={mode} />
  }

  // A stage belongs to the transition that recorded it, not to whoever last
  // saved a form. Shown, never typed into — see transition_owned in
  // spec/extensions.json and the note under the value.
  if (field.transition_owned) {
    return (
      <div className="space-y-1">
        <ReadOnlyValue field={field} value={value} />
        {mode === 'edit' && (
          <p className="text-xs text-muted-foreground">
            Changed only by Advance / Change stage, which records a reason.
          </p>
        )}
      </div>
    )
  }

  if (mode === 'view' || DERIVED.has(field.type)) {
    return <ReadOnlyValue field={field} value={value} />
  }

  switch (field.type) {
    case 'picklist': {
      const options = optionsFor(field.picklist)
      // 11 picklist fields in the register name no value set. A free text box
      // is honest about that; an empty dropdown is not.
      if (!options.length) {
        return (
          <div className="space-y-1">
            <Input
              id={id}
              aria-invalid={invalid}
              value={(value as string) ?? ''}
              onChange={(e) => set(e.target.value)}
            />
            <p className="text-xs text-amber-700 dark:text-amber-400">
              No picklist named in the register — free text until one is supplied.
            </p>
          </div>
        )
      }
      return (
        <Select value={(value as string) || undefined} onValueChange={set}>
          <SelectTrigger id={id} aria-invalid={invalid} className="w-full">
            <SelectValue placeholder="Select…" />
          </SelectTrigger>
          <SelectContent>
            {options.map((o) => (
              <SelectItem key={o.key} value={o.key}>
                {o.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      )
    }

    case 'multiselect':
      return (
        <MultiSelect
          id={id}
          options={optionsFor(field.picklist)}
          value={Array.isArray(value) ? (value as string[]) : []}
          onChange={set}
        />
      )

    case 'lookup':
      return (
        <LookupCombobox
          id={id}
          field={field}
          value={value}
          onChange={set}
          onCreateNew={onCreateNew}
        />
      )

    case 'checkbox':
      return (
        <div className="flex h-9 items-center">
          <Checkbox
            id={id}
            checked={Boolean(value)}
            onCheckedChange={(checked) => set(checked === true)}
          />
        </div>
      )

    case 'currency':
      return (
        <div className="relative">
          <span className="pointer-events-none absolute inset-y-0 left-3 flex items-center text-sm text-muted-foreground">
            $
          </span>
          <Input
            id={id}
            type="number"
            className="pl-6"
            aria-invalid={invalid}
            value={(value as number | string) ?? ''}
            onChange={(e) => set(e.target.value === '' ? '' : Number(e.target.value))}
          />
        </div>
      )

    case 'percent':
      return (
        <div className="relative">
          <Input
            id={id}
            type="number"
            step="any"
            className="pr-7"
            aria-invalid={invalid}
            value={(value as number | string) ?? ''}
            onChange={(e) => set(e.target.value === '' ? '' : Number(e.target.value))}
          />
          <span className="pointer-events-none absolute inset-y-0 right-3 flex items-center text-sm text-muted-foreground">
            %
          </span>
        </div>
      )

    case 'number':
      return (
        <Input
          id={id}
          type="number"
          step="any"
          aria-invalid={invalid}
          value={(value as number | string) ?? ''}
          onChange={(e) => set(e.target.value === '' ? '' : Number(e.target.value))}
        />
      )

    case 'date':
      return (
        <Input
          id={id}
          type="date"
          aria-invalid={invalid}
          value={(value as string) ?? ''}
          onChange={(e) => set(e.target.value)}
        />
      )

    case 'datetime':
      return (
        <Input
          id={id}
          type="datetime-local"
          aria-invalid={invalid}
          value={(value as string) ?? ''}
          onChange={(e) => set(e.target.value)}
        />
      )

    case 'longtext':
      return (
        <Textarea
          id={id}
          rows={4}
          aria-invalid={invalid}
          placeholder={field.placeholder}
          value={(value as string) ?? ''}
          onChange={(e) => set(e.target.value)}
        />
      )

    case 'richtext':
      // Two fields in the whole register are richtext. A markdown textarea
      // carries the intent without an editor dependency.
      return (
        <div className="space-y-1">
          <Textarea
            id={id}
            rows={5}
            aria-invalid={invalid}
            className="font-mono text-xs"
            value={(value as string) ?? ''}
            onChange={(e) => set(e.target.value)}
          />
          <p className="text-xs text-muted-foreground">Markdown — **bold**, _italic_, - list</p>
        </div>
      )

    case 'file':
      return <FileStub field={field} value={value} onChange={set} id={id} />

    case 'email':
      return (
        <Input
          id={id}
          type="email"
          aria-invalid={invalid}
          value={(value as string) ?? ''}
          onChange={(e) => set(e.target.value)}
        />
      )

    case 'url':
      return (
        <Input
          id={id}
          type="url"
          aria-invalid={invalid}
          placeholder="https://"
          value={(value as string) ?? ''}
          onChange={(e) => set(e.target.value)}
        />
      )

    default:
      return (
        <Input
          id={id}
          type="text"
          maxLength={field.max_length ?? undefined}
          aria-invalid={invalid}
          placeholder={field.placeholder}
          value={(value as string) ?? ''}
          onChange={(e) => set(e.target.value)}
        />
      )
  }
}

/**
 * File fields store a filename and nothing else. Real upload is out of scope
 * (CLAUDE.md), so picking a file records the automation that would have run.
 */
function FileStub({
  field,
  value,
  onChange,
  id,
}: {
  field: FieldSpec
  value: unknown
  onChange: (v: unknown) => void
  id: string
}) {
  const input = useRef<HTMLInputElement>(null)

  return (
    <div className="flex items-center gap-2">
      <input
        ref={input}
        id={id}
        type="file"
        className="hidden"
        onChange={(e) => {
          const file = e.target.files?.[0]
          if (!file) return
          onChange(file.name)
          void logAutomation({
            type: 'file_upload',
            target: file.name,
            detail: `Would upload "${file.name}" and attach it to ${field.label}`,
            module: field.module,
            api_name: field.api_name,
          })
          // Let the same file be picked again after a clear.
          e.target.value = ''
        }}
      />
      <Button type="button" variant="outline" size="sm" onClick={() => input.current?.click()}>
        <PaperclipIcon className="size-4" />
        Choose file
      </Button>
      {typeof value === 'string' && value ? (
        <>
          <span className="truncate text-sm">{value}</span>
          <Button type="button" variant="ghost" size="sm" onClick={() => onChange('')}>
            Clear
          </Button>
        </>
      ) : (
        <span className="text-sm text-muted-foreground">No file</span>
      )}
    </div>
  )
}

/** How a value reads when it is not being edited. */
/**
 * A field whose value lives on an ancestor record.
 *
 * The affordance matters as much as the read-only-ness. Without it the field
 * reads as an ordinary locked box and a reviewer asks why they cannot edit the
 * End Client; with "from LEAD-00118" they can see the value has an owner, and
 * follow the link to the one place it can be changed.
 */
function InheritedValue({
  field,
  value,
  mode,
}: {
  field: FieldSpec
  value: unknown
  mode: FormMode
}) {
  const form = useRecordForm()
  const source = form.sourceOf(field.api_name)
  const broken = form.unresolvedInherited.has(field.api_name)

  // The parent link's own label — "Parent Opportunity" — rather than the module
  // name, which would render as "no opportunities to read it from".
  const via = field.read_through_via ? fieldOf(field.module, field.read_through_via) : undefined
  const linkLabel = via?.label ?? 'parent record'
  const linked = field.read_through_via ? form.values[field.read_through_via] : undefined

  return (
    <div className="space-y-1">
      {broken ? (
        <p className="rounded-md border border-dashed px-3 py-2 text-sm text-amber-700 dark:text-amber-400">
          {linked
            ? `Not resolved — ${linkLabel} is set, but that record could not be loaded.`
            : `Not resolved — no ${linkLabel} is set on this record.`}
        </p>
      ) : (
        <ReadOnlyValue field={field} value={value} />
      )}

      {source ? (
        <Link
          to={`/${source.module}/${source.id}`}
          className="inline-flex items-center gap-0.5 text-xs text-muted-foreground underline underline-offset-2 hover:text-foreground"
        >
          from {source.id}
          <ArrowUpRightIcon className="size-3" />
        </Link>
      ) : (
        mode === 'edit' &&
        !broken && (
          <p className="text-xs text-muted-foreground">
            Read through {linkLabel} — changed there, never here.
          </p>
        )
      )}
    </div>
  )
}

export function ReadOnlyValue({ field, value }: { field: FieldSpec; value: unknown }) {
  const gap = computedGap(field)

  if (gap) {
    return (
      <p className="rounded-md border border-dashed px-3 py-2 text-sm text-muted-foreground">
        {gap}
      </p>
    )
  }

  if (value === null || value === undefined || value === '') {
    return <p className="px-1 py-2 text-sm text-muted-foreground">—</p>
  }

  // A lookup stores a record id. Showing USR-001 where the form showed "Kishan
  // Pawar" a moment ago reads as a different value, not the same one — so the
  // name is resolved here, through the same cached query the combobox uses.
  if (field.type === 'lookup') {
    return <LookupValue field={field} value={value} />
  }

  if (Array.isArray(value)) {
    return (
      <div className="flex flex-wrap gap-1 py-1.5">
        {value.map((v) => (
          <Badge key={String(v)} variant="secondary">
            {labelForValue(field.picklist, v)}
          </Badge>
        ))}
      </div>
    )
  }

  return <p className="px-1 py-2 text-sm">{formatValue(field, value)}</p>
}

/**
 * The display name of a looked-up record.
 *
 * Reads through /api/<collection> with the SAME query key LookupCombobox uses,
 * so a screen that has already opened the combobox pays nothing, and CLAUDE.md
 * rule 2 holds — no component touches the store directly.
 *
 * Falls back to the raw id while loading and when the id resolves to nothing.
 * A dangling reference must stay visible as an id rather than render blank.
 */
function LookupValue({ field, value }: { field: FieldSpec; value: unknown }) {
  const collection = collectionFor(field.lookup_target)

  const { data } = useQuery({
    queryKey: ['collection', collection],
    queryFn: async () => (await api.get<Record<string, unknown>[]>(`/${collection}`)).data,
    enabled: Boolean(collection),
    staleTime: 30_000,
  })

  const hit = data?.find((r) => idOf(r) === value)
  return <p className="px-1 py-2 text-sm">{hit ? displayNameOf(hit) : String(value)}</p>
}

function formatValue(field: FieldSpec, value: unknown): string {
  switch (field.type) {
    case 'currency':
      return money(value)
    case 'percent':
      return percent(value)
    case 'number':
      return number(value)
    case 'date':
      return fmtDate(value)
    case 'datetime':
      return fmtDateTime(value)
    case 'checkbox':
      return value ? 'Yes' : 'No'
    case 'picklist':
      return labelForValue(field.picklist, value)
    case 'computed':
      return formatComputed(field, value)
    default:
      return String(value)
  }
}

/**
 * A computed field has no type of its own in the register, so its formatting
 * is inferred from what the expression produced.
 *
 * `includes` rather than `endsWith`: api_names like third_party_pct_of_tcv and
 * guarantee_—_pct_of_contract_value carry "_pct" in the middle, not the end.
 */
export function formatComputed(field: FieldSpec, value: unknown): string {
  if (typeof value === 'boolean') return value ? 'Yes' : 'No'
  if (typeof value === 'number') {
    return field.api_name.includes('_pct') ? percent(value) : money(value)
  }
  if (typeof value === 'string' && /^\d{4}-\d{2}-\d{2}/.test(value)) return fmtDate(value)
  return String(value)
}
