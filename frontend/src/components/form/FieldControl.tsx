import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { ArrowUpRightIcon, LockIcon, PaperclipIcon } from 'lucide-react'

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
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { ChildListTable } from '@/components/form/ChildListTable'
import { LookupCombobox } from '@/components/form/LookupCombobox'
import { MultiSelect } from '@/components/form/MultiSelect'
import { PhoneInput } from '@/components/form/PhoneInput'
import { NumericInput } from '@/components/ui/numeric-input'
import {
  useOptionalRecordForm,
  useRecordForm,
  type FormMode,
  type RecordForm,
} from '@/hooks/useRecordForm'
import { useResolvedRecord } from '@/hooks/useResolvedRecord'
import { fetchCollection } from '@/lib/collections'
import { date as fmtDate, dateTime as fmtDateTime, money, number, percent } from '@/lib/format'
import { compileFor } from '@/lib/spec/conditions'
import { computedGap } from '@/lib/spec/formula'
import {
  collectionFor,
  displayNameOf,
  fieldOf,
  fieldOptions,
  idOf,
  labelForValue,
  moduleForCollection,
} from '@/lib/spec'
import type { Values } from '@/lib/spec/conditions'
import type { FieldSpec } from '@/types/field'

/**
 * A field the application writes and the user does not.
 *
 * Register-driven, both halves of it — no api_name is named here, per
 * CLAUDE.md's "never hardcode a field":
 *
 * `requirement === 'System'` is the register saying this value is recorded by
 * the application. It is what Created By / Created Date / Modified By /
 * Modified Date carry, and what makes them read-only now that the server
 * stamps all four from the Entra session and its own clock.
 *
 * `editable === false` is the placement-level flag the register has carried
 * since Round 7 and which, until now, NOTHING in the form engine read — a
 * field could be marked read-only in Administration and still render as a text
 * box. Honouring it here is what makes that switch mean something.
 *
 * ONE KNOWN MISLABEL, worth stating because this makes it visible: leads'
 * `fx_rate_at_entry` is marked System in the register but nothing in the
 * application stamps it, so it becomes read-only here with no other way to set
 * it. That is a register correction (Administration -> change its requirement),
 * not a case to special-case in code.
 */
export function isSystemField(field: FieldSpec): boolean {
  // value_locked joins the other two since 16 Sep 2026: a Deal's commercial
  // terms are carried from the Opportunity and fixed once won. The server
  // already refuses a changed value (carry_forward.locked_violations); drawing
  // an editable box for it would invite an edit guaranteed to fail on Save.
  return field.requirement === 'System' || field.editable === false || field.value_locked === true
}

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

/**
 * The two conversions a `stored_as: 'fraction'` percent field needs, rounded
 * so that neither direction accumulates float dust: 0.155 shows as 15.5, and
 * 15.5 stores as 0.155 rather than 0.15500000000000003. Four decimal places on
 * the fraction is exactly what the column holds.
 */
function toWholePercent(value: unknown): number | '' {
  const n = typeof value === 'number' ? value : Number(value)
  if (value === null || value === undefined || value === '' || !Number.isFinite(n)) return ''
  return Math.round(n * 10000) / 100
}

function toFraction(wholePercent: number): number | '' {
  if (!Number.isFinite(wholePercent)) return ''
  return Math.round(wholePercent * 100) / 10000
}

export function FieldControl({ field, onCreateNew, scope }: Props) {
  // A SCOPED control stands alone. Every read below already asks `scope` first,
  // and DealPaymentMilestones renders these columns straight onto the Deal page
  // with no RecordFormProvider above them — so demanding the context here threw
  // on the only screen that uses the scope prop, and took the whole page with
  // it. Without a scope the provider is genuinely required, and that stays an
  // error rather than a control silently rendering nothing.
  const context = useOptionalRecordForm()
  if (!scope && !context) {
    throw new Error('A FieldControl without a `scope` must be used inside a RecordFormProvider')
  }
  const form = context as RecordForm
  const value = scope ? scope.value : form.values[field.api_name]
  const id = scope?.id ?? `${field.module}.${field.api_name}`
  const set = scope ? scope.set : (v: unknown) => form.setValue(field.api_name, v)
  const invalid = scope ? Boolean(scope.invalid) : Boolean(form.visibleErrors[field.api_name])
  const mode = scope?.mode ?? form.mode
  const currencyCode = !scope && typeof form.values.currency === 'string' ? form.values.currency : ''

  if (field.type === 'childlist') return <ChildListTable field={field} />

  // Round-5 lookup (products, quotes, poc, bid, gates) with no records to
  // resolve against yet — see phase1_locked in types/field.ts. Locked
  // whatever the mode; there is nothing a view screen could show either.
  if (field.phase1_locked) return <LockedField field={field} id={id} />

  // Identity belongs to the record the pursuit started as. An Opportunity shows
  // its End Client and never stores it — see read_through in
  // spec/module_split.json, and toPayload, which strips these on the way out.
  //
  // Same shape as transition_owned below: read-only whatever the mode, with the
  // reason stated underneath rather than left for the user to infer from a box
  // that will not accept typing.
  if (field.value_mode === 'read_through' && !scope) {
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

  // Created By / Created Date / Modified By / Modified Date, and anything else
  // the register marks System.
  //
  // These rendered as ordinary text boxes until Sep 2026, which meant the two
  // values a manager most needs to trust — when was this last modified, and by
  // whom — were the two anyone could type over. The server now stamps them from
  // the Entra session and its own clock and discards whatever a payload claims
  // (app/routers/leads.py, SYSTEM_STAMPED), so an editable box here would be a
  // box whose contents are thrown away: worse than useless, it would look like
  // the edit had worked.
  //
  // This is presentation, NOT the boundary. The boundary is the server, which
  // refuses the value whatever the browser does.
  if (isSystemField(field)) {
    return <ReadOnlyValue field={field} value={value} />
  }

  if (mode === 'view' || DERIVED.has(field.type)) {
    return <ReadOnlyValue field={field} value={value} />
  }

  switch (field.type) {
    case 'picklist': {
      const options = fieldOptions(field)
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
      // A list the sidecar says is not closed — see allow_custom_value in
      // types/field.ts. Declared per placement in spec/extensions.json, never
      // named here: this stays the generic picklist control.
      if (field.allow_custom_value) {
        return (
          <PicklistOrCustom
            field={field}
            id={id}
            value={value}
            set={set}
            invalid={invalid}
            options={options}
          />
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
          options={fieldOptions(field)}
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
          {/* The record's own Currency, never a typed "$" — an AED lead showed
              "$" in front of dirhams. No prefix until the record has one. */}
          {currencyCode && (
            <span className="pointer-events-none absolute inset-y-0 left-3 flex items-center text-sm text-muted-foreground">
              {currencyCode}
            </span>
          )}
          <NumericInput
            id={id}
            className={currencyCode ? 'pl-12' : undefined}
            aria-invalid={invalid}
            value={value as number | string | null}
            onValueChange={set}
          />
        </div>
      )

    case 'percent': {
      // A percent field usually stores the whole number it shows. Progression %
      // and Probability % store a fraction and say so — see FieldExtension.stored_as.
      const fraction = field.stored_as === 'fraction'
      const shown = fraction ? toWholePercent(value) : ((value as number | string) ?? '')
      return (
        <div className="relative">
          <NumericInput
            id={id}
            className="pr-7"
            aria-invalid={invalid}
            value={shown}
            onValueChange={(typed) => set(typed === '' || !fraction ? typed : toFraction(typed))}
          />
          <span className="pointer-events-none absolute inset-y-0 right-3 flex items-center text-sm text-muted-foreground">
            %
          </span>
        </div>
      )
    }

    case 'number':
      return (
        <NumericInput
          id={id}
          // The register's range as a hint, e.g. "1–10". Enforced in validation.ts.
          placeholder={
            field.min_value != null && field.max_value != null
              ? `${field.min_value}–${field.max_value}`
              : undefined
          }
          aria-invalid={invalid}
          value={value as number | string | null}
          onValueChange={set}
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
      return <FileStub value={value} onChange={set} id={id} />

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

    case 'phone':
      return (
        <PhoneInput
          id={id}
          options={fieldOptions(field)}
          value={value}
          onChange={set}
          invalid={invalid}
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
 * File fields store a filename and nothing else — there is nowhere for an
 * uploaded file to go, and picking one neither uploads nor notifies anything.
 */
function FileStub({
  value,
  onChange,
  id,
}: {
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

/**
 * A lookup into a Round-5 table (products, quotes, poc, bid, gates) that has
 * no frozen fields — and so no real records — yet. Same disabled, muted
 * treatment as the Navbar's own search box (TopBar.tsx): a real control the
 * prototype is not pretending works, rather than a combobox that would only
 * ever offer an empty list. The hover message repeats the field's own
 * description (the same text the label's info icon shows) and says why it is
 * locked, so the reason travels with the field rather than living only in
 * spec/extensions.json's phase1_locked note.
 */
function LockedField({ field, id }: { field: FieldSpec; id: string }) {
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <div className="relative">
          <LockIcon className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground" />
          <input
            id={id}
            type="text"
            disabled
            placeholder={`${field.label} — not available yet`}
            className="h-9 w-full rounded-md border border-input bg-input-bg pl-9 pr-3 text-sm text-input-text outline-none placeholder:text-placeholder disabled:cursor-not-allowed"
          />
        </div>
      </TooltipTrigger>
      <TooltipContent className="max-w-xs">
        {field.description}
        {field.description && ' '}
        This lookup will be applicable soon — it switches back on once its module is built and
        frozen in a later phase.
      </TooltipContent>
    </Tooltip>
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

/**
 * A value on a record that is being read rather than edited.
 *
 * px-3, matching Input's own horizontal padding, NOT the px-1 this used to
 * carry. The label column is the same width in both modes, so the 8px
 * difference showed up as every value on the record sliding right the moment
 * Edit was pressed and back again on Cancel — a whole column of text moving for
 * no reason the user did anything to cause. The reference does not do that: a
 * value sits exactly where the input that edits it will put it.
 */
export function ReadOnlyValue({ field, value }: { field: FieldSpec; value: unknown }) {
  const gap = computedGap(field)

  if (gap) {
    return (
      <p className="rounded-md border border-dashed px-3 py-2 text-sm text-muted-foreground">
        {gap}
      </p>
    )
  }

  // A checkbox reads as a checkbox, ticked or not, rather than the word "Yes".
  // A read-only one — Is Primary Pursuit, set by the Pursuit Group — was the
  // one box on the form that looked like text. Before the blank check: an
  // unset checkbox is unticked, not missing.
  if (field.type === 'checkbox') {
    return (
      <div className="flex h-9 items-center px-3">
        <Checkbox
          checked={Boolean(value)}
          disabled
          aria-readonly
          aria-label={field.label}
          className="disabled:cursor-default disabled:opacity-100"
        />
      </div>
    )
  }

  if (value === null || value === undefined || value === '') {
    return <p className="px-3 py-2 text-sm text-muted-foreground">—</p>
  }

  // A computed field whose expression only ever yields a record id —
  // Contracting Party is the partner or the end client — reads as that
  // record's name, exactly as the lookups it was computed from do.
  if (field.type === 'computed' && typeof value === 'string') {
    const source = lookupSourceOf(field)
    if (source) return <LookupValue field={source} value={value} />
  }

  // A lookup stores a record id. Showing USR-001 where the form showed "Kishan
  // Pawar" a moment ago reads as a different value, not the same one — so the
  // name is resolved here, through the same cached query the combobox uses.
  if (field.type === 'lookup') {
    return <LookupValue field={field} value={value} />
  }

  // Comma-separated text rather than a row of filled chips — a multiselect is
  // one field with several values, and it reads as one line.
  if (Array.isArray(value)) {
    return (
      <p className="px-3 py-2 text-sm">
        {value.map((v) => labelForValue(field.picklist, v)).join(', ')}
      </p>
    )
  }

  return <p className="px-3 py-2 text-sm">{formatValue(field, value)}</p>
}

/**
 * The display name of a looked-up record.
 *
 * Reads through lib/collections.ts with the SAME query key LookupCombobox uses,
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
    queryFn: () => fetchCollection(collection!),
    enabled: Boolean(collection),
    staleTime: 30_000,
  })

  const hit = data?.find((r) => idOf(r) === value)
  if (!hit || !collection) return <p className="px-3 py-2 text-sm">{String(value)}</p>
  return (
    <p className="px-3 py-2 text-sm">
      <RecordName module={moduleForCollection(collection) ?? collection} record={hit} />
    </p>
  )
}

/**
 * A looked-up record's name, read through its parents when it stores none of
 * its own. An Opportunity holds no opportunity_name — the name is its Lead's —
 * so Parent Opportunity on a Deal read OPP-00003 while Parent Lead beside it
 * read a name. A module with no parent resolves to the record as it is.
 */
function RecordName({ module, record }: { module: string; record: Values }) {
  const { values } = useResolvedRecord(module, record)
  return <>{displayNameOf(values) || displayNameOf(record)}</>
}

/**
 * The lookup a computed field's value is read from, when its expression only
 * ever yields a record id — `deal_source == 'Partner-sourced' ?
 * customer_partner_si : end_client`. Found from the expression, never named:
 * every lookup it reads must point at the same kind of record, or there is no
 * one name to show and the raw value stays.
 */
function lookupSourceOf(field: FieldSpec): FieldSpec | undefined {
  if (!field.computed_expr) return undefined
  let deps: string[]
  try {
    deps = compileFor(field.module, field.computed_expr).deps
  } catch {
    return undefined
  }
  const lookups = deps
    .map((name) => fieldOf(field.module, name))
    .filter((f): f is FieldSpec => f?.type === 'lookup' && Boolean(f.lookup_target))
  return new Set(lookups.map((f) => f.lookup_target)).size === 1 ? lookups[0] : undefined
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

/**
 * The sentinel the extra option carries. Never stored: choosing it swaps the
 * control for a text box, and what is stored is whatever is typed there. The
 * register writes picklist keys in SCREAMING_SNAKE, so this cannot collide
 * with one.
 */
const CUSTOM_OPTION = '__other__'

/**
 * A picklist the sidecar marks as not closed — allow_custom_value in
 * spec/extensions.json, declared per placement and never named in here.
 *
 * Two states over ONE value. The dropdown offers the register's options plus
 * "+ Other"; choosing that clears the value and shows a text box. A value the
 * list does not contain opens in the text box as well — a custom value saved
 * earlier, or one restored with a row — because showing it as an empty
 * dropdown would read as "nothing chosen" for a field that has an answer.
 *
 * Going back to the list CLEARS what was typed. The two states share one
 * value, and text left behind a dropdown that cannot show it is how a record
 * saves something nobody can see.
 */
function PicklistOrCustom({
  field,
  id,
  value,
  set,
  invalid,
  options,
}: {
  field: FieldSpec
  id: string
  value: unknown
  set: (next: unknown) => void
  invalid: boolean
  options: ReturnType<typeof fieldOptions>
}) {
  const current = typeof value === 'string' ? value : ''
  const listed = options.some((option) => option.key === current)
  const [typing, setTyping] = useState(current !== '' && !listed)
  // Focus only when the PERSON asked for the box. The same state is reached by
  // an unlisted value arriving on its own, and taking focus on load moves the
  // page away from whatever someone was reading.
  const asked = useRef(false)

  useEffect(() => {
    if (current !== '' && !listed) setTyping(true)
  }, [current, listed])

  useEffect(() => {
    if (!typing || !asked.current) return
    asked.current = false
    const box = document.getElementById(id)
    if (box instanceof HTMLInputElement) box.focus()
  }, [typing, id])

  if (typing) {
    return (
      <div className="space-y-1">
        <Input
          id={id}
          aria-invalid={invalid}
          maxLength={field.max_length ?? undefined}
          value={current}
          placeholder={`${field.label} — not in the list`}
          onChange={(event) => set(event.target.value)}
        />
        <button
          type="button"
          className="text-muted-foreground hover:text-foreground text-xs underline underline-offset-2"
          onClick={() => {
            setTyping(false)
            set('')
          }}
        >
          Choose from the list instead
        </button>
      </div>
    )
  }

  return (
    <Select
      value={current || undefined}
      onValueChange={(next) => {
        if (next !== CUSTOM_OPTION) {
          set(next)
          return
        }
        asked.current = true
        setTyping(true)
        set('')
      }}
    >
      <SelectTrigger id={id} aria-invalid={invalid} className="w-full">
        <SelectValue placeholder="Select…" />
      </SelectTrigger>
      <SelectContent>
        {options.map((option) => (
          <SelectItem key={option.key} value={option.key}>
            {option.label}
          </SelectItem>
        ))}
        <SelectItem value={CUSTOM_OPTION}>+ Other…</SelectItem>
      </SelectContent>
    </Select>
  )
}
