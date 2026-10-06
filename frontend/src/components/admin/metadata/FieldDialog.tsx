import { useEffect, useMemo, useRef, useState } from 'react'
import { ChevronDownIcon } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Notice } from '@/components/ui/notice'
import { Textarea } from '@/components/ui/textarea'
import { ChoicesEditor } from './ChoicesEditor'
import { RuleBuilder } from './RuleBuilder'
import { PIPELINE_MODULES, fields as publishedFields, parentModuleOf } from '@/lib/spec'
import { identifiersOf, parse } from '@/lib/spec/parser'
import { readableFormula } from '@/lib/spec/readableFormula'
import { stagesFor } from '@/lib/pipeline'
import { errorMessage } from '@/lib/admin'
import { cn } from '@/lib/utils'
import {
  COUNTRY_CODE_SET,
  FIELD_TYPES,
  choiceLines,
  lookupTargetLabel,
  typeLabel,
  useAddPlacement,
  useCreateField,
  useDraftStatus,
  useMetadataField,
  useMetadataFields,
  useMetadataModules,
  useMetadataPicklists,
  useMetadataSections,
  usePublishMetadata,
  useUpdateField,
  useUpdatePlacement,
  type MetadataField,
} from '@/lib/metadata'

/**
 * Add or edit one field — Zoho's properties dialog, one per type.
 *
 * Hardcoded, like everything in this folder, and for the reason given in
 * shared.tsx: this is the form that edits the register, so it cannot render
 * from it.
 *
 * NO API NAME, ANYWHERE IN IT (Setup rebuild, 4a, 1 Oct 2026)
 * ------------------------------------------------------------
 * Zoho never asks for one and neither does this form: the server makes a new
 * field's api_name from its label, once, and a later rename leaves it alone —
 * it is the key every stored record writes the value under. It is shown only
 * in Setup → Developer Space → API Names. The module is fixed too: the field
 * belongs to the module it is created on.
 *
 * WHAT IT OFFERS (4d, slimmed in 4e on 5 Oct 2026)
 * -------------------------------------------------
 * Titled by the type — "Pick List Properties" — and showing only what that
 * type has: the label; characters for text; options and a Default value for a
 * Pick List; minimum and maximum for a number; the lookup module; a formula,
 * checked as it is typed and written out in labels. Then:
 *
 *   Required        Zoho's tick. "Show only when…" says when the field is on
 *                   the form at all, and a required field is demanded exactly
 *                   while it is shown — so there is one rule, not two. The
 *                   old Conditional requirement and its second rule were the
 *                   same rule on every row the register had (setup_step4e).
 *   Required before leaving   the stage a required field must be filled by,
 *                   on Leads, Opportunities and Deals; it starts as the stage
 *                   of its section. Zoho needs a Blueprint for this.
 *   Answer kept     once per record, or once per stage — ours, not Zoho's.
 *   Tooltip         the ⓘ, the export and the import sheet's "what to enter".
 *
 * WHAT IT NO LONGER OFFERS, AND WHERE IT WENT
 *   * where it draws (under / beside another field, width) — the layout
 *     editor's tile menu, where a field is placed by hand;
 *   * "Blocks", "Editable at any stage", the written formula sentence — they
 *     changed nothing (blocks always equalled the stage; nothing read "any
 *     stage"); the columns are dropped at Step 9;
 *   * Use case, where it is stored, the sidecar note — Developer Space →
 *     API Names, for the people who need them;
 *   * "apply to every module" — since metadata v2 a field has one owner.
 * Copied at conversion and "Also show on a later module" stay under More
 * properties until Conversion Mapping (Step 5) takes them.
 *
 * Opened from the layout editor there is no Section box: there, a field is
 * placed by dragging it, and a box here would fight the editor's own Save.
 */

interface Props {
  open: boolean
  onOpenChange: (open: boolean) => void
  moduleKey: string
  /** Present for edit, absent for add. */
  field?: MetadataField
  /** Preselected section when adding. */
  sectionId?: number
  /** Preselected type when adding — the type dropped from the layout's palette. */
  fieldType?: string
  /**
   * Opened from the layout editor, which places fields by dragging: no Section
   * box, and an edit never sends a section (the editor's Save decides it).
   */
  fromLayout?: boolean
}

/**
 * Mirrors DESCRIPTION_MAX_LENGTH in backend/app/schemas_metadata.py, which is
 * itself mirrored by a CHECK constraint in migration 0033. Three places, one
 * number; the server is the one that refuses, this one only stops the typing.
 */
const DESCRIPTION_MAX_LENGTH = 255
/** Where the counter appears — late enough that an ordinary description never sees it. */
const DESCRIPTION_SOFT_WARN = 200

/** Requirements a person chooses between. Any other is the CRM's own. */
const CHOSEN = new Set(['Optional', 'Mandatory', 'Conditional'])

interface FormState {
  section_id: number | null
  label: string
  field_type: string
  requirement: string
  picklist_key: string
  lookup_target: string
  max_length: string
  min_value: string
  max_value: string
  mandatory_from: string
  visibility_condition: string
  computed_expr: string
  description: string
  /** Needed from a new record's first save — pipeline modules only. */
  required_on_create: boolean
  /** A Pick List's default: a choice's key, or its label for choices not saved yet. */
  default_value: string
  // ---- how its value behaves
  value_mode: 'own' | 'read_through' | 'carry_forward'
  value_locked: boolean
  stage_scoped: 'none' | 'carry_forward' | 'sticky'
}

const EMPTY: FormState = {
  section_id: null,
  label: '',
  field_type: 'text',
  requirement: 'Optional',
  picklist_key: '',
  lookup_target: '',
  max_length: '',
  min_value: '',
  max_value: '',
  mandatory_from: '',
  visibility_condition: '',
  computed_expr: '',
  description: '',
  required_on_create: false,
  default_value: '',
  value_mode: 'own',
  value_locked: false,
  stage_scoped: 'none',
}

/**
 * What a lookup can point at: every target a published field already looks up,
 * plus the one this field has. Chosen by name, never typed (4a).
 */
function lookupTargets(current: string): string[] {
  const targets = new Set(
    publishedFields.map((f) => f.lookup_target).filter((t): t is string => Boolean(t))
  )
  if (current) targets.add(current)
  return [...targets].sort((a, b) => lookupTargetLabel(a).localeCompare(lookupTargetLabel(b)))
}

/** '' means "not set" on the wire, which is null rather than an empty string. */
const orNull = (value: string) => (value.trim() === '' ? null : value.trim())
const numberOrNull = (value: string) => (value.trim() === '' ? null : Number(value))

const selectClass = 'border-input bg-input-bg h-9 rounded-md border px-2 text-sm'

export function FieldDialog({
  open,
  onOpenChange,
  moduleKey,
  field,
  sectionId,
  fieldType,
  fromLayout = false,
}: Props) {
  const isEdit = Boolean(field)
  const { data: sections = [] } = useMetadataSections(moduleKey)
  const { data: picklists = [] } = useMetadataPicklists()

  const createField = useCreateField()
  const updateField = useUpdateField()
  const updatePlacement = useUpdatePlacement()

  const [form, setForm] = useState<FormState>(EMPTY)
  const [error, setError] = useState<string | null>(null)
  /**
   * Where a dropdown's choices come from — Zoho's arrangement since the Setup
   * rebuild (25 Sep 2026): the field's OWN list, edited right here, or a
   * GLOBAL SET shared with other fields. null until the person picks: it then
   * follows the list the field already has, so the picklists refetching after
   * a choice is added never resets the dialog.
   */
  const [choiceSource, setChoiceSource] = useState<'own' | 'global' | null>(null)
  // A field with no list of its own yet: its choices, one per line.
  const [newChoices, setNewChoices] = useState('')
  // "More properties" — closed each time the dialog opens.
  const [moreOpen, setMoreOpen] = useState(false)
  // The formula box, so Insert field can put a name where the cursor is.
  const exprRef = useRef<HTMLInputElement>(null)

  /** The other active fields on THIS module: what a rule or a formula can read. */
  const { data: moduleFields = [] } = useMetadataFields(moduleKey)
  const otherFields = moduleFields.filter(
    (f) => f.api_name !== field?.api_name && f.status === 'active'
  )

  /**
   * "Also show on a later module" — a later module of the pipeline shows this
   * field, read-only and live, the way an Opportunity shows the Lead's End
   * Client. Metadata v2: a field is owned by ONE module; the only other place
   * it may appear is a module further down the pipeline, storing nothing. The
   * server refuses anything else (FIELD_OWNED_ELSEWHERE). Moves to Conversion
   * Mapping in Step 5.
   */
  const shown = Boolean(field && field.module_count > 1)
  const { data: detail } = useMetadataField(shown ? field?.definition_id : undefined)
  const { data: modules = [] } = useMetadataModules()
  const addPlacement = useAddPlacement()
  const [alsoModule, setAlsoModule] = useState('')
  const { data: alsoSections = [] } = useMetadataSections(alsoModule || undefined)
  const [alsoSectionId, setAlsoSectionId] = useState<number | null>(null)

  const placedOn = new Set(
    (detail?.placements ?? []).filter((p) => p.status === 'active').map((p) => p.module_key)
  )
  /** True when `module` sits below this field's module in the pipeline. */
  const isLaterModule = (module: string) => {
    for (let up = parentModuleOf(module); up; up = parentModuleOf(up)) {
      if (up === moduleKey) return true
    }
    return false
  }
  const ownedHere = field?.value_mode !== 'read_through'
  const alsoCandidates = ownedHere
    ? modules.filter((m) => m.active && isLaterModule(m.module_key) && !placedOn.has(m.module_key))
    : []

  const addAlso = async () => {
    if (!field || !alsoModule || alsoSectionId === null) return
    setError(null)
    try {
      await addPlacement.mutateAsync({
        definitionId: field.definition_id,
        input: { module_key: alsoModule, section_id: alsoSectionId, value_mode: 'read_through' },
      })
      setAlsoModule('')
      setAlsoSectionId(null)
    } catch (err) {
      setError(errorMessage(err))
    }
  }

  /**
   * Save and publish (Setup rebuild, D1, 25 Sep 2026): save this field, then
   * publish the WHOLE draft — a publish cannot take one change and leave the
   * rest. So when anything else is waiting the dialog says so before the click.
   */
  const { data: draft } = useDraftStatus()
  const publish = usePublishMetadata()
  const othersPending = draft?.has_changes ? draft.changes.length : 0
  // Saved, and the publish after it refused — the reason, until the dialog closes.
  const [notPublished, setNotPublished] = useState<string | null>(null)
  // Which button was pressed, so only that one says it is working.
  const [publishing, setPublishing] = useState(false)

  useEffect(() => {
    if (!open) return
    setError(null)
    setNotPublished(null)
    setChoiceSource(null)
    setNewChoices('')
    setMoreOpen(false)
    if (field) {
      setForm({
        section_id: field.section_id,
        label: field.label,
        field_type: field.field_type,
        requirement: field.requirement,
        picklist_key: field.picklist_key ?? '',
        lookup_target: field.lookup_target ?? '',
        max_length: field.max_length?.toString() ?? '',
        min_value: field.min_value?.toString() ?? '',
        max_value: field.max_value?.toString() ?? '',
        mandatory_from: field.mandatory_from?.toString() ?? '',
        visibility_condition: field.visibility_condition ?? '',
        computed_expr: field.computed_expr ?? '',
        description: field.description ?? '',
        required_on_create: field.required_on_create ?? false,
        default_value: field.default_value ?? '',
        value_mode: field.value_mode,
        value_locked: field.value_locked,
        stage_scoped: field.stage_scoped,
      })
    } else {
      setForm({
        ...EMPTY,
        section_id: sectionId ?? sections[0]?.id ?? null,
        field_type: fieldType ?? EMPTY.field_type,
      })
    }
    setAlsoModule('')
    setAlsoSectionId(null)
  }, [open, field, sectionId, sections, fieldType])

  const set = <K extends keyof FormState>(key: K, value: FormState[K]) =>
    setForm((f) => ({ ...f, [key]: value }))

  const needsPicklist = form.field_type === 'picklist' || form.field_type === 'multiselect'

  // The list the field had when the dialog opened, and whether it is its own.
  const startingList = field?.picklist_key
    ? picklists.find((p) => p.picklist_key === field.picklist_key)
    : undefined
  const ownList = startingList && !startingList.is_global ? startingList : undefined
  const source = choiceSource ?? (startingList?.is_global ? 'global' : 'own')
  const globalSets = picklists.filter(
    (p) => p.is_global && (p.active || p.picklist_key === form.picklist_key)
  )
  const chosenSet = globalSets.find((p) => p.picklist_key === form.picklist_key)
  const typedChoices = choiceLines(newChoices)
  // A new list of its own is made on save — by the server, with the field.
  const makesOwnList = needsPicklist && source === 'own' && !ownList && typedChoices.length > 0
  const picklistKey = !needsPicklist
    ? null
    : source === 'global'
      ? orNull(form.picklist_key)
      : (ownList?.picklist_key ?? null)
  // A new dropdown needs its choices; an existing one saved without them keeps what it had.
  const choicesReady =
    !needsPicklist ||
    (source === 'global'
      ? Boolean(chosenSet)
      : Boolean(ownList) || typedChoices.length > 0 || isEdit)
  const needsLookup = form.field_type === 'lookup'
  const isPickList = form.field_type === 'picklist'
  /**
   * What the default can be: the list's active choices, by key — or, for
   * choices typed here and not saved yet, by label (the server turns a label
   * into its choice's key). Changing the list clears a default it no longer has.
   */
  const defaultChoices: { value: string; label: string }[] = !isPickList
    ? []
    : source === 'global'
      ? (chosenSet?.values ?? []).filter((v) => v.active).map((v) => ({ value: v.key, label: v.label }))
      : ownList
        ? ownList.values.filter((v) => v.active).map((v) => ({ value: v.key, label: v.label }))
        : typedChoices.map((label) => ({ value: label, label }))
  const defaultValue = defaultChoices.some((c) => c.value === form.default_value) ? form.default_value : ''
  const textual = ['text', 'longtext', 'richtext', 'email', 'url'].includes(form.field_type)
  const moduleLabel = modules.find((m) => m.module_key === moduleKey)?.label ?? moduleKey
  const isNumeric = ['number', 'currency', 'percent'].includes(form.field_type)
  const hasFormula = form.field_type === 'computed' || form.computed_expr.trim() !== ''

  const isPipeline = PIPELINE_MODULES.includes(moduleKey)
  const stages = isPipeline ? stagesFor(moduleKey) : []
  const sectionLabel = sections.find((s) => s.id === form.section_id)?.label ?? ''
  /** The stage its section puts it in — 4 for "STAGE 4 — RFP / RFI". */
  const sectionStage = (() => {
    const match = /^STAGE (\d+)/.exec(sectionLabel)
    return match ? Number(match[1]) : null
  })()
  // Captured at: its section's stage; for a field outside a stage section, the
  // stage the register already gives it (Record State's, on Deals).
  const capturedAt = sectionStage ?? field?.capture_stage ?? null

  // ---- Required: a tick, and the CRM's own requirements as a fact.
  const requirementChosen = CHOSEN.has(form.requirement)
  const required = form.requirement === 'Mandatory' || form.requirement === 'Conditional'
  const dueAt = form.mandatory_from.trim() !== '' ? Number(form.mandatory_from) : capturedAt

  // ---- Formula: checked as it is typed, and written out in labels.
  const formulaCheck = useMemo(() => {
    const expr = form.computed_expr.trim()
    if (!expr) return null
    try {
      const names = new Set(moduleFields.map((f) => f.api_name))
      const unknown = identifiersOf(parse(expr)).filter((n) => !names.has(n))
      if (unknown.length > 0) {
        return { ok: false, text: `${moduleLabel} has no field called ${unknown[0]}. Pick it from Insert field.` }
      }
      return { ok: true, text: readableFormula(expr, (name) => moduleFields.find((f) => f.api_name === name)?.label) ?? '' }
    } catch {
      return { ok: false, text: "This formula can't be read. Check its brackets and signs." }
    }
  }, [form.computed_expr, moduleFields, moduleLabel])

  /** Put a field's name into the formula where the cursor is. */
  const insertIntoFormula = (apiName: string) => {
    const box = exprRef.current
    const text = form.computed_expr
    const start = box?.selectionStart ?? text.length
    const end = box?.selectionEnd ?? text.length
    set('computed_expr', `${text.slice(0, start)}${apiName}${text.slice(end)}`)
    requestAnimationFrame(() => {
      box?.focus()
      box?.setSelectionRange(start + apiName.length, start + apiName.length)
    })
  }

  const visibility = orNull(form.visibility_condition)
  const requirement = requirementChosen ? (required ? 'Mandatory' : 'Optional') : form.requirement

  /**
   * The definition: the shape of the value and its documentation. The API
   * refuses a placement key sent here rather than applying it everywhere.
   */
  const definitionPatch = {
    label: form.label.trim(),
    field_type: form.field_type,
    // The server refuses both at once: a new own list, or a list to point at.
    ...(makesOwnList
      ? { new_picklist: typedChoices }
      : // An existing field with no choices typed keeps its list as it was.
        needsPicklist && source === 'own' && !ownList && isEdit
        ? {}
        : { picklist_key: picklistKey }),
    lookup_target: needsLookup ? orNull(form.lookup_target) : null,
    max_length: textual ? numberOrNull(form.max_length) : null,
    min_value: isNumeric ? numberOrNull(form.min_value) : null,
    max_value: isNumeric ? numberOrNull(form.max_value) : null,
    computed_expr: hasFormula ? orNull(form.computed_expr) : null,
    description: form.description,
  }

  /** This module's placement: how the field is asked for here. */
  const sectionChanged = !fromLayout && isEdit && form.section_id !== field?.section_id
  const placementPatch = {
    requirement,
    // A required field is demanded exactly while it is shown (setup 4e); the
    // server keeps `condition` equal to the show-when rule for a required one.
    visibility_condition: visibility,
    condition: required ? visibility : null,
    mandatory_from: isPipeline && required ? numberOrNull(form.mandatory_from) : null,
    required_on_create: isPipeline && required && form.required_on_create,
    default_value: isPickList ? orNull(defaultValue) : null,
    value_mode: form.value_mode,
    ...(form.value_mode === 'carry_forward' ? { value_locked: form.value_locked } : {}),
    stage_scoped: isPipeline ? form.stage_scoped : 'none',
    // From the layout editor the section is the editor's to decide. Moved
    // here, it takes its new section's stage (capture_stage null = derive).
    ...(fromLayout ? {} : { section_id: form.section_id ?? undefined }),
    ...(sectionChanged ? { capture_stage: null } : {}),
  }

  const submit = async (andPublish = false) => {
    setError(null)
    setPublishing(andPublish)
    try {
      if (isEdit && field) {
        // Definition first: if it fails, this module's placement is left
        // exactly as it was rather than half-updated against a field that
        // never changed.
        await updateField.mutateAsync({ definitionId: field.definition_id, patch: definitionPatch })
        await updatePlacement.mutateAsync({ placementId: field.placement_id, patch: placementPatch })
      } else {
        const created = await createField.mutateAsync({
          ...definitionPatch,
          ...placementPatch,
          ...(makesOwnList ? { new_picklist: typedChoices } : {}),
          section_id: form.section_id ?? undefined,
          module_key: moduleKey,
          // A new field is the register's own only in the workbook; one added
          // here says where it came from.
          origin: 'Administration',
        })
        // Create takes the field and how it is asked for; how its answer is
        // kept is set on the placement it made.
        if (placementPatch.stage_scoped !== 'none') {
          await updatePlacement.mutateAsync({
            placementId: created.placement_id,
            patch: { stage_scoped: placementPatch.stage_scoped },
          })
        }
      }
    } catch (err) {
      setError(errorMessage(err))
      return
    }

    if (andPublish) {
      try {
        await publish.mutateAsync(
          `${moduleLabel} · ${form.label.trim()}: saved and published from the field dialog`
        )
      } catch (err) {
        // The save stands; only the publish was refused. Say so and stay open,
        // with the save buttons gone — a second Add would add the field twice.
        setNotPublished(errorMessage(err))
        return
      }
    }
    onOpenChange(false)
  }

  const busy =
    createField.isPending || updateField.isPending || updatePlacement.isPending || publish.isPending
  const canSubmit =
    form.label.trim() !== '' &&
    form.section_id !== null &&
    choicesReady &&
    !(formulaCheck && !formulaCheck.ok)

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[85vh] overflow-y-auto sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>
            {isEdit ? `${typeLabel(form.field_type)} Properties` : `New ${typeLabel(form.field_type)} Field`}
          </DialogTitle>
          <DialogDescription>
            {isEdit
              ? 'Changes go to the draft. Publish to put them in front of anyone.'
              : `A new field on ${moduleLabel}. It reaches the CRM at the next publish.`}
          </DialogDescription>
        </DialogHeader>

        <div className="grid gap-4 py-2">
          <div className={cn('grid gap-3', fromLayout ? 'grid-cols-1' : 'grid-cols-3')}>
            <div className={cn('grid gap-1.5', !fromLayout && 'col-span-2')}>
              <Label htmlFor="label">Field Label</Label>
              <Input
                id="label"
                value={form.label}
                placeholder="Licence Model"
                onChange={(e) => set('label', e.target.value)}
              />
            </div>
            {!fromLayout && (
              <div className="grid gap-1.5">
                <Label htmlFor="section">Section</Label>
                <select
                  id="section"
                  className={selectClass}
                  value={form.section_id ?? ''}
                  onChange={(e) => set('section_id', Number(e.target.value))}
                >
                  {sections.map((s) => (
                    <option key={s.id} value={s.id}>
                      {s.label}
                    </option>
                  ))}
                </select>
              </div>
            )}
          </div>

          {/* ---- WHAT THIS TYPE HAS ------------------------------------- */}
          {textual && (
            <div className="grid w-1/3 gap-1.5">
              <Label htmlFor="max_length">Number of characters allowed</Label>
              <Input
                id="max_length"
                inputMode="numeric"
                value={form.max_length}
                placeholder="No limit"
                onChange={(e) => set('max_length', e.target.value)}
              />
            </div>
          )}

          {form.field_type === 'phone' && (
            <p className="text-muted-foreground text-xs">
              The country code in front of the number comes from{' '}
              <strong>{picklists.find((p) => p.picklist_key === COUNTRY_CODE_SET)?.label ?? 'the country codes'}</strong>{' '}
              under Global Sets. Every phone field uses the same list; the first code is the one a new
              number starts with.
            </p>
          )}

          {needsPicklist && (
            <div className="grid gap-1.5">
              <div className="flex items-center gap-2">
                <Label>{isPickList ? 'Pick List Options' : 'Options'}</Label>
                <div className="ml-auto flex gap-1">
                  {(['own', 'global'] as const).map((option) => (
                    <Button
                      key={option}
                      type="button"
                      size="sm"
                      className="h-7"
                      variant={source === option ? 'default' : 'outline'}
                      onClick={() => {
                        setChoiceSource(option)
                        if (option === 'global' && !globalSets.some((p) => p.picklist_key === form.picklist_key)) {
                          set('picklist_key', '')
                        }
                      }}
                    >
                      {option === 'own' ? 'Its own choices' : 'A global set'}
                    </Button>
                  ))}
                </div>
              </div>

              {source === 'global' ? (
                <>
                  <select
                    id="picklist"
                    aria-label="Global set"
                    className={selectClass}
                    value={form.picklist_key}
                    onChange={(e) => set('picklist_key', e.target.value)}
                  >
                    <option value="">Choose a global set…</option>
                    {globalSets.map((p) => (
                      <option key={p.picklist_key} value={p.picklist_key}>
                        {p.label ?? p.picklist_key}
                        {p.active ? '' : ' (inactive)'}
                      </option>
                    ))}
                  </select>
                  {chosenSet && (
                    <p className="text-muted-foreground text-xs">
                      {chosenSet.values
                        .filter((v) => v.active)
                        .map((v) => v.label)
                        .join(', ')}
                      <br />
                      Shared with {chosenSet.field_count} field
                      {chosenSet.field_count === 1 ? '' : 's'}. Edit its choices under Global Sets.
                    </p>
                  )}
                </>
              ) : ownList ? (
                <>
                  <ChoicesEditor picklist={ownList} />
                  <p className="text-muted-foreground text-xs">
                    Choices are saved to the draft as you change them. Drag a choice to reorder.
                  </p>
                </>
              ) : (
                <>
                  <Textarea
                    id="new_choices"
                    rows={4}
                    placeholder="One choice per line"
                    value={newChoices}
                    onChange={(e) => setNewChoices(e.target.value)}
                  />
                  {isEdit && field?.picklist_key && (
                    <p className="text-muted-foreground text-xs">
                      Leave empty to keep the global set it uses now.
                    </p>
                  )}
                </>
              )}

              {/* Zoho's "Select default value" — Pick List only (1 Oct 2026). */}
              {isPickList && (
                <div className="mt-1 grid w-1/2 gap-1.5">
                  <Label htmlFor="default_value">Default value</Label>
                  <select
                    id="default_value"
                    className={selectClass}
                    value={defaultValue}
                    onChange={(e) => set('default_value', e.target.value)}
                  >
                    <option value="">None</option>
                    {defaultChoices.map((c) => (
                      <option key={c.value} value={c.value}>
                        {c.label}
                      </option>
                    ))}
                  </select>
                  <p className="text-muted-foreground text-xs">
                    A new record starts with this choice. It can be changed before saving.
                  </p>
                </div>
              )}
            </div>
          )}

          {needsLookup && (
            <div className="grid w-1/2 gap-1.5">
              <Label htmlFor="lookup_target">Lookup Module</Label>
              <select
                id="lookup_target"
                className={selectClass}
                value={form.lookup_target}
                onChange={(e) => set('lookup_target', e.target.value)}
              >
                <option value="">Choose what it looks up…</option>
                {lookupTargets(form.lookup_target).map((target) => (
                  <option key={target} value={target}>
                    {lookupTargetLabel(target)}
                  </option>
                ))}
              </select>
            </div>
          )}

          {/* Both inclusive: 1 and 10 allow 1 and 10. Checked on screen and
              refused by the API on save. */}
          {isNumeric && (
            <div className="grid grid-cols-3 gap-3">
              <div className="grid gap-1.5">
                <Label htmlFor="min_value">Minimum value</Label>
                <Input
                  id="min_value"
                  inputMode="decimal"
                  value={form.min_value}
                  placeholder="No minimum"
                  onChange={(e) => set('min_value', e.target.value)}
                />
              </div>
              <div className="grid gap-1.5">
                <Label htmlFor="max_value">Maximum value</Label>
                <Input
                  id="max_value"
                  inputMode="decimal"
                  value={form.max_value}
                  placeholder="No maximum"
                  onChange={(e) => set('max_value', e.target.value)}
                />
              </div>
            </div>
          )}

          {hasFormula && (
            <div className="grid gap-1.5">
              <div className="flex items-end gap-2">
                <Label htmlFor="computed_expr">Formula</Label>
                <select
                  aria-label="Insert field"
                  className="border-input bg-input-bg ml-auto h-8 w-56 rounded-md border px-2 text-xs"
                  value=""
                  onChange={(e) => e.target.value && insertIntoFormula(e.target.value)}
                >
                  <option value="">Insert field…</option>
                  {otherFields
                    .filter((f) => f.value_mode !== 'read_through')
                    .sort((a, b) => a.label.localeCompare(b.label))
                    .map((f) => (
                      <option key={f.placement_id} value={f.api_name}>
                        {f.label}
                      </option>
                    ))}
                </select>
              </div>
              <Input
                id="computed_expr"
                ref={exprRef}
                className="font-mono text-xs"
                value={form.computed_expr}
                placeholder="Pick fields from Insert field, joined with + − * /"
                aria-invalid={formulaCheck ? !formulaCheck.ok : undefined}
                onChange={(e) => set('computed_expr', e.target.value)}
              />
              {formulaCheck ? (
                <p className={cn('text-xs', formulaCheck.ok ? 'text-muted-foreground' : 'text-destructive')}>
                  {formulaCheck.ok ? (
                    <>
                      <span className="font-medium">Reads as:</span> {formulaCheck.text}
                    </>
                  ) : (
                    formulaCheck.text
                  )}
                </p>
              ) : (
                <p className="text-muted-foreground text-xs">
                  What the CRM works out. The ⓘ on the record shows it written out like this.
                </p>
              )}
            </div>
          )}

          {/* ---- REQUIRED ----------------------------------------------- */}
          {requirementChosen ? (
            <div className="grid gap-2">
              <div className="flex flex-wrap items-center gap-x-6 gap-y-2">
                <label className="flex items-center gap-2 text-sm font-medium">
                  <Checkbox
                    checked={required}
                    onCheckedChange={(v) => set('requirement', v === true ? 'Mandatory' : 'Optional')}
                  />
                  Required
                </label>
                {/* On Leads, Opportunities and Deals a required field is asked
                    for when a record LEAVES its stage. Ticked, it is needed from
                    the very first save as well — a Lead's name, its End Client. */}
                {isPipeline && required && (
                  <label className="flex items-center gap-2 text-sm">
                    <Checkbox
                      checked={form.required_on_create}
                      onCheckedChange={(v) => set('required_on_create', v === true)}
                    />
                    Required when creating
                  </label>
                )}
                {isPipeline && required && (
                  <label className="flex items-center gap-2 text-sm">
                    Required before leaving
                    <select
                      aria-label="Required before leaving"
                      className="border-input bg-input-bg h-8 rounded-md border px-2 text-sm"
                      value={form.mandatory_from}
                      onChange={(e) => set('mandatory_from', e.target.value)}
                    >
                      <option value="">
                        {capturedAt !== null ? `Stage ${capturedAt} (its own)` : 'Choose a stage…'}
                      </option>
                      {stages
                        .filter((s) => s.stage !== capturedAt)
                        .map((s) => (
                          <option key={s.stage} value={String(s.stage)}>
                            Stage {s.stage} · {s.name}
                          </option>
                        ))}
                    </select>
                  </label>
                )}
              </div>
              {isPipeline && capturedAt !== null && (
                <p className="text-muted-foreground text-xs">
                  Captured at Stage {capturedAt}
                  {sectionStage !== null ? ', from its section.' : '.'}
                </p>
              )}
              {isPipeline && required && dueAt === null && (
                <p className="text-xs text-amber-700 dark:text-amber-400">
                  Choose a stage, or this field is asked for at every stage move.
                </p>
              )}
            </div>
          ) : (
            <p className="text-muted-foreground text-sm">
              {form.requirement === 'Advisory'
                ? 'Shown as advice, never required.'
                : 'Filled by the CRM — never asked of a person.'}
            </p>
          )}

          {/* ---- SHOW ONLY WHEN — Zoho's Layout Rules, and for a required
              field also when it is demanded. One rule, not two. */}
          <div className="grid gap-2 rounded-md border p-3">
            <RuleBuilder
              label="Show this field only when…"
              hint={
                required
                  ? 'Leave empty to always show it. While it is shown, it is required.'
                  : 'Leave empty to always show it.'
              }
              value={form.visibility_condition}
              onChange={(expr) => set('visibility_condition', expr)}
              fields={otherFields}
              picklists={picklists}
            />
          </div>

          {/* ---- ANSWER KEPT — ours, not Zoho's ------------------------- */}
          {isPipeline && form.value_mode !== 'read_through' && (
            <div className="grid w-2/3 gap-1.5">
              <Label htmlFor="stage_scoped">Answer kept</Label>
              <select
                id="stage_scoped"
                className={selectClass}
                value={form.stage_scoped}
                onChange={(e) => set('stage_scoped', e.target.value as FormState['stage_scoped'])}
              >
                <option value="none">Once per record</option>
                <option value="carry_forward">Once per stage, starting from the last stage's answer</option>
                <option value="sticky">Once per stage, never carried — listed in Reasons &amp; Justifications</option>
              </select>
            </div>
          )}

          {/* ---- TOOLTIP ------------------------------------------------- */}
          <div className="grid gap-1.5">
            <div className="flex items-baseline justify-between gap-2">
              <Label htmlFor="description">Tooltip</Label>
              {/* Counted down, not up, and only once it starts to matter. The
                  cap is a layout promise to the field tooltip and the import
                  template — see DESCRIPTION_MAX_LENGTH. */}
              {form.description.length > DESCRIPTION_SOFT_WARN && (
                <span
                  className={cn(
                    'text-xs tabular-nums',
                    form.description.length >= DESCRIPTION_MAX_LENGTH ? 'text-destructive' : 'text-muted-foreground'
                  )}
                >
                  {DESCRIPTION_MAX_LENGTH - form.description.length} left
                </span>
              )}
            </div>
            <Textarea
              id="description"
              rows={2}
              maxLength={DESCRIPTION_MAX_LENGTH}
              value={form.description}
              onChange={(e) => set('description', e.target.value)}
            />
            <p className="text-muted-foreground text-xs">
              What the field is and when to fill it — the ⓘ beside it, the export and the import
              template. About three sentences.
            </p>
          </div>

          {/* ---- MORE PROPERTIES — closed: rarely touched ----------------- */}
          {isEdit && (
            <div className="rounded-md border">
              <button
                type="button"
                className="flex w-full items-center gap-1.5 px-3 py-2 text-sm font-semibold"
                onClick={() => setMoreOpen((v) => !v)}
              >
                <ChevronDownIcon className={cn('size-4 transition-transform', !moreOpen && '-rotate-90')} />
                More properties
              </button>

              {moreOpen && (
                <div className="grid gap-4 border-t p-3">
                  <div className="grid w-1/2 gap-1.5">
                    <Label htmlFor="type">Field type</Label>
                    <select
                      id="type"
                      className={selectClass}
                      value={form.field_type}
                      onChange={(e) => set('field_type', e.target.value)}
                    >
                      {FIELD_TYPES.map((t) => (
                        <option key={t} value={t}>
                          {typeLabel(t)}
                        </option>
                      ))}
                    </select>
                    <p className="text-muted-foreground text-xs">
                      A field that came with the CRM can only move between text types. Values already
                      saved stay as they are.
                    </p>
                  </div>

                  {form.value_mode === 'carry_forward' && (
                    <div className="grid gap-1.5">
                      <Label>Copied at conversion</Label>
                      <label className="flex items-center gap-2 text-sm">
                        <Checkbox
                          checked={form.value_locked}
                          onCheckedChange={(v) => set('value_locked', v === true)}
                        />
                        Locked — the copied value may not be changed afterwards
                      </label>
                    </div>
                  )}

                  <div className="grid gap-2">
                    <p className="text-section text-xs font-bold tracking-wide">ALSO SHOW ON A LATER MODULE</p>
                    {alsoCandidates.length === 0 ? (
                      <p className="text-muted-foreground text-xs">
                        {ownedHere
                          ? 'No later module of the pipeline is left to show it.'
                          : 'This field belongs to an earlier module. Change it there.'}
                      </p>
                    ) : (
                      <div className="flex flex-wrap items-end gap-2">
                        <div className="grid gap-1.5">
                          <Label htmlFor="also_module">Module</Label>
                          <select
                            id="also_module"
                            className={selectClass}
                            value={alsoModule}
                            onChange={(e) => {
                              setAlsoModule(e.target.value)
                              setAlsoSectionId(null)
                            }}
                          >
                            <option value="">&mdash; pick one &mdash;</option>
                            {alsoCandidates.map((m) => (
                              <option key={m.module_key} value={m.module_key}>
                                {m.label}
                              </option>
                            ))}
                          </select>
                        </div>
                        <div className="grid gap-1.5">
                          <Label htmlFor="also_section">Section</Label>
                          <select
                            id="also_section"
                            className={selectClass}
                            disabled={alsoModule === ''}
                            value={alsoSectionId ?? ''}
                            onChange={(e) => setAlsoSectionId(Number(e.target.value))}
                          >
                            <option value="">&mdash; pick one &mdash;</option>
                            {alsoSections.map((sec) => (
                              <option key={sec.id} value={sec.id}>
                                {sec.label}
                              </option>
                            ))}
                          </select>
                        </div>
                        <Button
                          variant="outline"
                          disabled={alsoModule === '' || alsoSectionId === null || addPlacement.isPending}
                          onClick={addAlso}
                        >
                          {addPlacement.isPending ? 'Adding…' : 'Show it there'}
                        </Button>
                      </div>
                    )}
                    <p className="text-muted-foreground text-xs">
                      The later module shows it read-only, live from here, under From the Lead. Added
                      at once, not on Save.
                    </p>
                  </div>
                </div>
              )}
            </div>
          )}

          {error && <p className="text-destructive text-sm">{error}</p>}

          {notPublished && (
            <Notice
              boxed
              tone="warning"
              lead="The field is saved, but nothing was published."
              bullets={[
                notPublished,
                'Open Versions under Developer Space to see what blocks it, then publish from the banner.',
              ]}
            />
          )}
        </div>

        {notPublished ? (
          <DialogFooter>
            <Button onClick={() => onOpenChange(false)}>Close</Button>
          </DialogFooter>
        ) : (
          <>
            {othersPending > 0 && (
              <p className="text-muted-foreground text-right text-xs">
                Save and publish also publishes {othersPending} other change
                {othersPending === 1 ? '' : 's'}.
              </p>
            )}
            <DialogFooter>
              <Button variant="ghost" onClick={() => onOpenChange(false)}>
                Cancel
              </Button>
              <Button variant="outline" disabled={!canSubmit || busy} onClick={() => submit(true)}>
                {busy && publishing ? (publish.isPending ? 'Publishing…' : 'Saving…') : 'Save and publish'}
              </Button>
              <Button disabled={!canSubmit || busy} onClick={() => submit()}>
                {busy && !publishing ? 'Saving…' : isEdit ? 'Save changes' : 'Add field'}
              </Button>
            </DialogFooter>
          </>
        )}
      </DialogContent>
    </Dialog>
  )
}
