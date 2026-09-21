import { useMemo, useRef, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { isAxiosError } from 'axios'

import { Checkbox } from '@/components/ui/checkbox'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { FieldControl } from '@/components/form/FieldControl'
import { RecordFormProvider } from '@/hooks/useRecordForm'
import { api } from '@/lib/api'
import { PRIORITY_FLAGS, takenRanksFor } from '@/lib/priorityFlags'
import { fieldsOf } from '@/lib/spec'
import type { Values } from '@/lib/spec/conditions'
import type { FieldSpec } from '@/types/field'

/** Synthetic section name for a field that is current state rather than
 * something a stage captures — never rendered as a collapsible form section,
 * only here. See spec/extensions.json new_fields (overall_rag and friends). */
export const HEADER_STRIP_SECTION = '__header'

const SAVE_DEBOUNCE_MS = 300

interface Props {
  module: string
  collection: string
  recordId: string
  values: Values
  readOnly: boolean
}

/**
 * A checkbox whose rank lives in a sibling field named `<name>_rank`, where
 * `<name>` is the checkbox's own api_name with its `is_` prefix stripped —
 * `is_low_hanging` -> `low_hanging_rank`. Declared in lib/priorityFlags,
 * which is also where the cap and label for each pair live.
 */
function rankFieldNameFor(field: FieldSpec): string | undefined {
  if (field.type !== 'checkbox' || !field.api_name.startsWith('is_')) return undefined
  return `${field.api_name.slice(3)}_rank`
}

/**
 * What is left of the key-facts strip: the Opportunities priority flags.
 *
 * Overall RAG, Next Milestone and Next Milestone Date used to be here too, and
 * they are ordinary HEADER fields now — drawn by RecordForm at the top of the
 * stage tab and saved by its Save button, because a debounced PUT per keystroke
 * cost a refetch and a full form remount every time somebody typed. `__header`
 * is empty on Leads and Deals as a result, and this renders nothing there.
 *
 * The flags did NOT follow them, and the reason is the rank rather than the
 * checkbox: Low Hanging and Top 10 are ranked 1..cap and a rank is unique
 * ACROSS RECORDS, so the picker has to read the whole collection to know which
 * ranks are still free. The form engine has no vocabulary for a value
 * constrained by other records, and inventing one for two fields would be the
 * larger mistake. They stay here, edited immediately, no Edit button.
 *
 * Wrapped in its own RecordFormProvider purely so FieldControl has the
 * context hook it always calls — every value and every write below goes
 * through `scope`, never through the provider's own state, so nothing here
 * ever becomes a draft. The record id is namespaced ("header:...") so it can
 * never collide with the real edit form's draft for the same record.
 */
export function HeaderStrip({ module, collection, recordId, values, readOnly }: Props) {
  const allFields = fieldsOf(module).filter((f) => f.section === HEADER_STRIP_SECTION)

  // Rank fields are real, declared fields — Spec Health and the payload both
  // see them — but they are never their own input; a companion checkbox
  // above renders a rank picker instead. Rendering both would be two boxes
  // for one fact.
  const rankFieldNames = new Set(allFields.map(rankFieldNameFor).filter(Boolean) as string[])
  const fields = allFields.filter((f) => !rankFieldNames.has(f.api_name))

  if (fields.length === 0 || !recordId) return null

  return (
    <RecordFormProvider module={module} mode="edit" recordId={`header:${recordId}`}>
      <HeaderStripBody
        collection={collection}
        recordId={recordId}
        fields={fields}
        values={values}
        readOnly={readOnly}
      />
    </RecordFormProvider>
  )
}

function HeaderStripBody({
  collection,
  recordId,
  fields,
  values,
  readOnly,
}: {
  collection: string
  recordId: string
  fields: ReturnType<typeof fieldsOf>
  values: Values
  readOnly: boolean
}) {
  const queryClient = useQueryClient()
  const timers = useRef<Record<string, ReturnType<typeof setTimeout>>>({})
  // Keyed by api_name so a second field's error never clobbers the first's,
  // and a later successful save on the SAME field clears only its own line.
  const [errors, setErrors] = useState<Record<string, string>>({})

  const save = useMutation({
    mutationFn: async (patch: Values) => (await api.put(`/${collection}/${recordId}`, patch)).data,
    onSuccess: async (_data, patch) => {
      setErrors((prev) => {
        const next = { ...prev }
        for (const apiName of Object.keys(patch)) delete next[apiName]
        return next
      })
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['record', collection, recordId] }),
        queryClient.invalidateQueries({ queryKey: ['list', collection] }),
        queryClient.invalidateQueries({ queryKey: ['collection', collection] }),
      ])
    },
    onError: (err, patch) => {
      const message = isAxiosError(err)
        ? ((err.response?.data as { message?: string } | undefined)?.message ?? err.message)
        : 'Could not save.'
      setErrors((prev) => {
        const next = { ...prev }
        for (const apiName of Object.keys(patch)) next[apiName] = message
        return next
      })
    },
  })

  const setField = (apiName: string, value: unknown) => {
    clearTimeout(timers.current[apiName])
    timers.current[apiName] = setTimeout(() => save.mutate({ [apiName]: value }), SAVE_DEBOUNCE_MS)
  }

  return (
    <div className="bg-card mb-4 rounded-lg px-4 py-3 shadow-sm">
      <div className="flex flex-wrap items-center gap-x-6 gap-y-2">
        {fields.map((field) => {
          const rankFieldName = rankFieldNameFor(field)
          const priority = PRIORITY_FLAGS.find((p) => p.flag === field.api_name)

          if (rankFieldName && priority) {
            return (
              <PriorityFlagPicker
                key={field.qref}
                collection={collection}
                recordId={recordId}
                flagField={field.api_name}
                rankField={rankFieldName}
                label={field.label}
                cap={priority.cap}
                checked={Boolean(values[field.api_name])}
                committedRank={typeof values[rankFieldName] === 'number' ? (values[rankFieldName] as number) : undefined}
                readOnly={readOnly}
                pending={save.isPending}
                error={errors[field.api_name]}
                onSave={(patch, onSettled) => {
                  save.mutate(patch, { onSettled })
                }}
              />
            )
          }

          return (
            <div key={field.qref} className="flex min-w-0 items-center gap-2">
              <span className="shrink-0 text-xs font-medium text-muted-foreground">{field.label}</span>
              <div className="w-36 shrink-0">
                <FieldControl
                  field={field}
                  scope={{
                    value: values[field.api_name],
                    set: (v) => setField(field.api_name, v),
                    mode: readOnly ? 'view' : 'edit',
                    id: `header.${field.qref}`,
                  }}
                />
              </div>
            </div>
          )
        })}
      </div>

      {Object.values(errors).length > 0 && (
        <p className="mt-2 text-xs text-destructive">{Object.values(errors)[0]}</p>
      )}
    </div>
  )
}

/**
 * Checkbox + rank, as one control.
 *
 * Ticking the box never assigns a rank by itself — it opens a "Pick a rank"
 * select scoped to whichever ranks 1..cap are still open, and nothing is
 * saved until the user actually picks one. Unticking an already-marked box
 * clears both fields immediately; no picker needed to remove something.
 */
function PriorityFlagPicker({
  collection,
  recordId,
  flagField,
  rankField,
  label,
  cap,
  checked,
  committedRank,
  readOnly,
  pending,
  error,
  onSave,
}: {
  collection: string
  recordId: string
  flagField: string
  rankField: string
  label: string
  cap: number
  checked: boolean
  committedRank: number | undefined
  readOnly: boolean
  pending: boolean
  error: string | undefined
  onSave: (patch: Values, onSettled: () => void) => void
}) {
  // undefined defers to `checked`/`committedRank` from the record itself; set
  // only while the box is ticked but no rank has been picked yet — a real
  // save is never sent for that in-between moment.
  const [awaitingRank, setAwaitingRank] = useState(false)
  const [saving, setSaving] = useState(false)

  const { data } = useQuery({
    queryKey: ['collection', collection],
    queryFn: async () => (await api.get<Record<string, unknown>[]>(`/${collection}`)).data,
  })

  const openRanks = useMemo(() => {
    const taken = data ? takenRanksFor(data, recordId, flagField, rankField) : new Set<number>()
    return Array.from({ length: cap }, (_, i) => i + 1).filter((r) => !taken.has(r) || r === committedRank)
  }, [data, recordId, flagField, rankField, cap, committedRank])

  const isFull = openRanks.length === 0 && !checked
  const showPicker = checked || awaitingRank
  const disabled = readOnly || pending || saving

  const commit = (rank: number) => {
    setSaving(true)
    onSave({ [flagField]: true, [rankField]: rank }, () => {
      setSaving(false)
      setAwaitingRank(false)
    })
  }

  const clear = () => {
    setSaving(true)
    onSave({ [flagField]: false, [rankField]: null }, () => setSaving(false))
  }

  return (
    <div className="flex min-w-0 items-center gap-2">
      <Checkbox
        id={`header.priority.${flagField}`}
        checked={showPicker}
        disabled={disabled || (isFull && !showPicker)}
        onCheckedChange={(next) => {
          if (next === true) {
            if (isFull) return
            setAwaitingRank(true)
          } else {
            setAwaitingRank(false)
            if (checked) clear()
          }
        }}
      />
      <label htmlFor={`header.priority.${flagField}`} className="shrink-0 text-xs font-medium text-muted-foreground">
        {label}
      </label>

      {showPicker ? (
        <Select
          value={checked && !awaitingRank ? String(committedRank) : undefined}
          onValueChange={(v) => commit(Number(v))}
          disabled={disabled}
        >
          <SelectTrigger className="h-8 w-28">
            <SelectValue placeholder="Pick a rank" />
          </SelectTrigger>
          <SelectContent>
            {openRanks.map((r) => (
              <SelectItem key={r} value={String(r)}>
                Rank {r}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      ) : (
        isFull && <span className="text-xs text-muted-foreground">Full ({cap}/{cap})</span>
      )}

      {error && <span className="text-xs text-destructive">{error}</span>}
    </div>
  )
}
