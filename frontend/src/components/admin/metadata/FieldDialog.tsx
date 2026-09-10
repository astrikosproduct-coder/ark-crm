import { useEffect, useState } from 'react'

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
import { Textarea } from '@/components/ui/textarea'
import { errorMessage } from '@/lib/admin'
import {
  FIELD_TYPES,
  REQUIREMENTS,
  useAddPlacement,
  useCreateField,
  useMetadataField,
  useMetadataFields,
  useMetadataModules,
  useMetadataPicklists,
  useMetadataSections,
  useUpdateField,
  useUpdatePlacement,
  type MetadataField,
} from '@/lib/metadata'

/**
 * Add or edit one row of the field register.
 *
 * Hardcoded, like everything in this folder, and for the reason given in
 * shared.tsx: this is the form that edits the register, so it cannot render
 * from it.
 *
 * TWO THINGS THIS FORM WILL NOT LET YOU CHANGE
 * ---------------------------------------------
 * api_name and module, on an existing field. Both are disabled rather than
 * hidden, so the reason is visible where somebody would look for the control:
 * an api_name is the key every stored record writes this field's value under,
 * and changing it would orphan all of that data while appearing to work. The
 * API refuses them too — FieldUpdate does not carry either — so this is not the
 * only thing standing between a rename and the data.
 *
 * WHAT B3 ADDED, AND WHY IT MATTERS MORE THAN IT LOOKS
 * ----------------------------------------------------
 * Six properties the placement model has carried since Round 7 and this form
 * never offered: the anchor trio, value_mode/value_locked, and stage_scoped —
 * plus computed_expr on the definition. Every one of them was set by a script
 * instead (anchor_reasons.py, anchor_stage1.py, absorb_sidecar.py), which is
 * the difference between a CRM you configure and a CRM somebody configures for
 * you. Those three scripts should be deleted now.
 *
 * `storage` is shown and NOT editable, on purpose. A register field keeps its
 * typed column; a field created here lives in custom_fields JSONB and is never
 * getting a column, because that would be an ALTER TABLE issued from an admin
 * screen. It is a fact about the field, not a choice — so it reads as one.
 */

interface Props {
  open: boolean
  onOpenChange: (open: boolean) => void
  moduleKey: string
  /** Present for edit, absent for add. */
  field?: MetadataField
  /** Preselected section when adding. */
  sectionId?: number
}

interface FormState {
  section_id: number | null
  api_name: string
  label: string
  field_type: string
  requirement: string
  picklist_key: string
  lookup_target: string
  max_length: string
  capture_stage: string
  mandatory_from: string
  blocks_transition: string
  visibility_condition: string
  condition: string
  computed_formula: string
  computed_expr: string
  description: string
  use_case: string
  capture_any_stage: boolean
  // ---- where it draws
  anchor_field: string
  anchor_position: 'after' | 'beside'
  layout_span: '' | 'full' | 'half'
  // ---- how its value behaves
  value_mode: 'own' | 'read_through' | 'carry_forward'
  value_locked: boolean
  stage_scoped: 'none' | 'carry_forward' | 'sticky'
}

const EMPTY: FormState = {
  section_id: null,
  api_name: '',
  label: '',
  field_type: 'text',
  requirement: 'Optional',
  picklist_key: '',
  lookup_target: '',
  max_length: '',
  capture_stage: '',
  mandatory_from: '',
  blocks_transition: '',
  visibility_condition: '',
  condition: '',
  computed_formula: '',
  computed_expr: '',
  description: '',
  use_case: '',
  capture_any_stage: false,
  anchor_field: '',
  anchor_position: 'after',
  layout_span: '',
  value_mode: 'own',
  value_locked: false,
  stage_scoped: 'none',
}

/** '' means "not set" on the wire, which is null rather than an empty string. */
const orNull = (value: string) => (value.trim() === '' ? null : value.trim())
const numberOrNull = (value: string) => (value.trim() === '' ? null : Number(value))

export function FieldDialog({ open, onOpenChange, moduleKey, field, sectionId }: Props) {
  const isEdit = Boolean(field)
  const { data: sections = [] } = useMetadataSections(moduleKey)
  const { data: picklists = [] } = useMetadataPicklists()

  const createField = useCreateField()
  const updateField = useUpdateField()
  const updatePlacement = useUpdatePlacement()

  const [form, setForm] = useState<FormState>(EMPTY)
  const [error, setError] = useState<string | null>(null)
  const [applyToAll, setApplyToAll] = useState(false)

  /**
   * Every placement of this field, so "apply to all" has something to apply to.
   *
   * Only fetched while editing a field that is on more than one module — the
   * common case is one placement and one request would be waste.
   */
  const shared = Boolean(field && field.module_count > 1)
  const { data: detail } = useMetadataField(
    shared ? field?.definition_id : undefined
  )

  /**
   * Candidate anchors: the other active fields on THIS module.
   *
   * Cross-module anchors are refused by the API — a field cannot draw beside
   * something that is not on the same form — so offering one would be offering
   * an error.
   */
  const { data: moduleFields = [] } = useMetadataFields(moduleKey)
  const anchorCandidates = moduleFields.filter(
    (f) => f.api_name !== field?.api_name && f.status === 'active'
  )

  /**
   * "Also show on…" — a second PLACEMENT of the same field on another module.
   *
   * Never a second definition. One-Time Revenue is ONE field that appears on
   * Opportunities and Deals; creating a second definition with the same
   * api_name would give it two labels, two types and two rows to keep in step,
   * which is the confusion the placement model exists to remove. The endpoint
   * has existed since Round 7 and useAddPlacement was written for it; until B3
   * nothing called either, so the only way to put a field on a second module
   * was to write it there by hand.
   */
  const { data: modules = [] } = useMetadataModules()
  const addPlacement = useAddPlacement()
  const [alsoModule, setAlsoModule] = useState('')
  const { data: alsoSections = [] } = useMetadataSections(alsoModule || undefined)
  const [alsoSectionId, setAlsoSectionId] = useState<number | null>(null)

  const placedOn = new Set(
    (detail?.placements ?? []).filter((p) => p.status === 'active').map((p) => p.module_key)
  )
  const alsoCandidates = modules.filter(
    (m) => m.active && m.module_key !== moduleKey && !placedOn.has(m.module_key)
  )

  const addAlso = async () => {
    if (!field || !alsoModule || alsoSectionId === null) return
    setError(null)
    try {
      await addPlacement.mutateAsync({
        definitionId: field.definition_id,
        input: { module_key: alsoModule, section_id: alsoSectionId },
      })
      setAlsoModule('')
      setAlsoSectionId(null)
    } catch (err) {
      setError(errorMessage(err))
    }
  }

  useEffect(() => {
    if (!open) return
    setError(null)
    if (field) {
      setForm({
        section_id: field.section_id,
        api_name: field.api_name,
        label: field.label,
        field_type: field.field_type,
        requirement: field.requirement,
        picklist_key: field.picklist_key ?? '',
        lookup_target: field.lookup_target ?? '',
        max_length: field.max_length?.toString() ?? '',
        capture_stage: field.capture_stage?.toString() ?? '',
        mandatory_from: field.mandatory_from?.toString() ?? '',
        blocks_transition: field.blocks_transition ?? '',
        visibility_condition: field.visibility_condition ?? '',
        condition: field.condition ?? '',
        computed_formula: field.computed_formula ?? '',
        computed_expr: field.computed_expr ?? '',
        description: field.description ?? '',
        use_case: field.use_case ?? '',
        capture_any_stage: field.capture_any_stage,
        anchor_field: field.anchor_field ?? '',
        anchor_position: field.anchor_position ?? 'after',
        layout_span: field.layout_span ?? '',
        value_mode: field.value_mode,
        value_locked: field.value_locked,
        stage_scoped: field.stage_scoped,
      })
      setApplyToAll(false)
    } else {
      setForm({ ...EMPTY, section_id: sectionId ?? sections[0]?.id ?? null })
      setApplyToAll(false)
    }
    setAlsoModule('')
    setAlsoSectionId(null)
  }, [open, field, sectionId, sections])

  const set = <K extends keyof FormState>(key: K, value: FormState[K]) =>
    setForm((f) => ({ ...f, [key]: value }))

  const needsPicklist = form.field_type === 'picklist' || form.field_type === 'multiselect'
  const needsLookup = form.field_type === 'lookup'

  /**
   * The stage the chosen section implies — 4 for "STAGE 4 — RFP / RFI".
   *
   * The backend fills this in when the box is left blank (a field in a stage
   * section without a capture stage renders on no screen at all), so the form
   * shows what is about to happen rather than letting it be a surprise. Only
   * numbered sections count: "STAGE DEFINITION  (configuration)" on
   * Administration is a heading, not a pipeline stage.
   */
  const derivedStage = (() => {
    const label = sections.find((s) => s.id === form.section_id)?.label ?? ''
    const match = /^STAGE (\d+)/.exec(label)
    return match ? Number(match[1]) : null
  })()

  const payload = {
    section_id: form.section_id ?? undefined,
    label: form.label.trim(),
    field_type: form.field_type,
    requirement: form.requirement,
    picklist_key: needsPicklist ? orNull(form.picklist_key) : null,
    lookup_target: needsLookup ? orNull(form.lookup_target) : null,
    max_length: numberOrNull(form.max_length),
    capture_stage: numberOrNull(form.capture_stage),
    capture_any_stage: form.capture_any_stage,
    mandatory_from: numberOrNull(form.mandatory_from),
    blocks_transition: orNull(form.blocks_transition),
    visibility_condition: orNull(form.visibility_condition),
    condition: orNull(form.condition),
    computed_formula: orNull(form.computed_formula),
    computed_expr: orNull(form.computed_expr),
    description: form.description,
    use_case: form.use_case,
  }

  /**
   * The payload, split the way the model is.
   *
   * A definition property changes the field on EVERY module it appears on; a
   * placement property changes this module alone. The API refuses a placement
   * key sent to the definition endpoint rather than applying it everywhere, so
   * the split has to happen here — and doing it explicitly is what lets the
   * dialog warn, above, which other modules an edit will reach.
   */
  const definitionPatch = {
    label: payload.label,
    field_type: payload.field_type,
    picklist_key: payload.picklist_key,
    lookup_target: payload.lookup_target,
    max_length: payload.max_length,
    computed_formula: payload.computed_formula,
    computed_expr: payload.computed_expr,
    description: payload.description,
    use_case: payload.use_case,
  }

  /**
   * Placement properties that mean the same thing on every module.
   *
   * "Apply to all placements" sends exactly this set to each of them. The
   * anchor is in here deliberately and is the reason the toggle exists: a
   * CROSS-CUTTING field is replicated across Leads, Opportunities and Deals, so
   * anchoring On Hold Reason under Lead Status was six edits, not two — and
   * without this an admin fixes Leads, publishes, and finds Deals still wrong.
   * The API validates the anchor per module and refuses one that names a field
   * that module does not carry, so a bad apply fails loudly rather than
   * half-landing.
   */
  const sharedPlacementPatch = {
    requirement: payload.requirement,
    capture_stage: payload.capture_stage,
    capture_any_stage: payload.capture_any_stage,
    mandatory_from: payload.mandatory_from,
    blocks_transition: payload.blocks_transition,
    visibility_condition: payload.visibility_condition,
    condition: payload.condition,
    anchor_field: orNull(form.anchor_field),
    // Sent only alongside an anchor: a bare position with nothing to be a
    // position against is refused, which is the API being right.
    ...(orNull(form.anchor_field) ? { anchor_position: form.anchor_position } : {}),
    layout_span: form.layout_span === '' ? null : form.layout_span,
    value_mode: form.value_mode,
    ...(form.value_mode === 'carry_forward' ? { value_locked: form.value_locked } : {}),
    stage_scoped: form.stage_scoped,
  }

  /**
   * That set plus what belongs to THIS module alone.
   *
   * section_id is the whole list: a section id names a row of one module's
   * section table, so sending it to another module's placement would move the
   * field into a section that is not theirs. It was in neither patch until B3,
   * which meant the Section dropdown on this dialog silently did nothing when
   * editing an existing field.
   */
  const placementPatch = {
    ...sharedPlacementPatch,
    section_id: payload.section_id,
  }

  const submit = async () => {
    setError(null)
    try {
      if (isEdit && field) {
        // Definition first: if it fails, this module's placement is left
        // exactly as it was rather than half-updated against a field that
        // never changed.
        await updateField.mutateAsync({
          definitionId: field.definition_id,
          patch: definitionPatch,
        })
        await updatePlacement.mutateAsync({
          placementId: field.placement_id,
          patch: placementPatch,
        })
        if (applyToAll) {
          // This module's placement is already done, and section_id is left
          // out of the others on purpose — see sharedPlacementPatch.
          const others = (detail?.placements ?? []).filter(
            (p) => p.placement_id !== field.placement_id && p.status === 'active'
          )
          for (const other of others) {
            await updatePlacement.mutateAsync({
              placementId: other.placement_id,
              patch: sharedPlacementPatch,
            })
          }
        }
      } else {
        await createField.mutateAsync({
          ...payload,
          module_key: moduleKey,
          api_name: form.api_name.trim(),
          // A new field is the register's own only in the workbook; one added
          // here says where it came from, so a reviewer can tell the two apart
          // on the Spec Health page.
          origin: 'Administration',
        })
      }
      onOpenChange(false)
    } catch (err) {
      setError(errorMessage(err))
    }
  }

  const busy =
    createField.isPending || updateField.isPending || updatePlacement.isPending
  const canSubmit =
    form.label.trim() !== '' &&
    form.section_id !== null &&
    (isEdit || /^[a-z][a-z0-9_]*$/.test(form.api_name.trim()))

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[85vh] overflow-y-auto sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>{isEdit ? 'Edit field' : 'Add field'}</DialogTitle>
          <DialogDescription>
            {isEdit
              ? 'Changes go to the draft. Publish to put them in front of anyone.'
              : `A new field on ${moduleKey}. It reaches the CRM at the next publish.`}
          </DialogDescription>
        </DialogHeader>

        <div className="grid gap-4 py-2">
          <div className="grid grid-cols-2 gap-3">
            <div className="grid gap-1.5">
              <Label htmlFor="api_name">API name</Label>
              <Input
                id="api_name"
                value={form.api_name}
                disabled={isEdit}
                placeholder="licence_model"
                onChange={(e) => set('api_name', e.target.value)}
              />
              <p className="text-muted-foreground text-xs">
                {isEdit
                  ? 'Not editable — every stored record keys its value on this name.'
                  : 'Lower case, digits and underscores. This is the key records store.'}
              </p>
            </div>

            <div className="grid gap-1.5">
              <Label htmlFor="label">Label</Label>
              <Input
                id="label"
                value={form.label}
                placeholder="Licence Model"
                onChange={(e) => set('label', e.target.value)}
              />
              <p className="text-muted-foreground text-xs">What a user sees on the form.</p>
            </div>
          </div>

          <div className="grid grid-cols-3 gap-3">
            <div className="grid gap-1.5">
              <Label htmlFor="section">Section</Label>
              <select
                id="section"
                className="border-input bg-input-bg h-9 rounded-md border px-2 text-sm"
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

            <div className="grid gap-1.5">
              <Label htmlFor="type">Type</Label>
              <select
                id="type"
                className="border-input bg-input-bg h-9 rounded-md border px-2 text-sm"
                value={form.field_type}
                onChange={(e) => set('field_type', e.target.value)}
              >
                {FIELD_TYPES.map((t) => (
                  <option key={t} value={t}>
                    {t}
                  </option>
                ))}
              </select>
            </div>

            <div className="grid gap-1.5">
              <Label htmlFor="requirement">Requirement</Label>
              <select
                id="requirement"
                className="border-input bg-input-bg h-9 rounded-md border px-2 text-sm"
                value={form.requirement}
                onChange={(e) => set('requirement', e.target.value)}
              >
                {REQUIREMENTS.map((r) => (
                  <option key={r} value={r}>
                    {r}
                  </option>
                ))}
              </select>
              <p className="text-muted-foreground text-xs">
                Form validation only. Never the column's nullability.
              </p>
            </div>
          </div>

          {needsPicklist && (
            <div className="grid gap-1.5">
              <Label htmlFor="picklist">Picklist</Label>
              <select
                id="picklist"
                className="border-input bg-input-bg h-9 rounded-md border px-2 text-sm"
                value={form.picklist_key}
                onChange={(e) => set('picklist_key', e.target.value)}
              >
                <option value="">— none (renders as free text) —</option>
                {picklists.map((p) => (
                  <option key={p.picklist_key} value={p.picklist_key}>
                    {p.picklist_key}
                    {p.active ? '' : ' (inactive)'}
                  </option>
                ))}
              </select>
            </div>
          )}

          {needsLookup && (
            <div className="grid gap-1.5">
              <Label htmlFor="lookup_target">Lookup target</Label>
              <Input
                id="lookup_target"
                value={form.lookup_target}
                placeholder="account, user, contact, lead…"
                onChange={(e) => set('lookup_target', e.target.value)}
              />
            </div>
          )}

          <div className="grid grid-cols-4 gap-3">
            <div className="grid gap-1.5">
              <Label htmlFor="max_length">Max length</Label>
              <Input
                id="max_length"
                value={form.max_length}
                onChange={(e) => set('max_length', e.target.value)}
              />
            </div>
            <div className="grid gap-1.5">
              <Label htmlFor="capture_stage">Capture stage</Label>
              <Input
                id="capture_stage"
                value={form.capture_stage}
                placeholder={derivedStage !== null ? String(derivedStage) : undefined}
                onChange={(e) => set('capture_stage', e.target.value)}
              />
              {derivedStage !== null && form.capture_stage.trim() === '' && (
                <p className="text-muted-foreground text-xs">
                  Will be set to {derivedStage}, from the section. A field in a stage
                  section without one renders on no screen.
                </p>
              )}
            </div>
            <div className="grid gap-1.5">
              <Label htmlFor="mandatory_from">Mandatory from</Label>
              <Input
                id="mandatory_from"
                value={form.mandatory_from}
                onChange={(e) => set('mandatory_from', e.target.value)}
              />
            </div>
            <div className="grid gap-1.5">
              <Label htmlFor="blocks_transition">Blocks</Label>
              <Input
                id="blocks_transition"
                value={form.blocks_transition}
                placeholder="4 → 5"
                onChange={(e) => set('blocks_transition', e.target.value)}
              />
            </div>
          </div>

          <label className="flex items-center gap-2 text-sm">
            <Checkbox
              checked={form.capture_any_stage}
              onCheckedChange={(v) => set('capture_any_stage', v === true)}
            />
            Editable at any stage
          </label>

          <div className="grid gap-1.5">
            <Label htmlFor="visibility_condition">Visibility condition</Label>
            <Input
              id="visibility_condition"
              value={form.visibility_condition}
              placeholder="deal_source == 'Partner-sourced'"
              onChange={(e) => set('visibility_condition', e.target.value)}
            />
          </div>

          <div className="grid gap-1.5">
            <Label htmlFor="condition">Condition (when Conditional)</Label>
            <Input
              id="condition"
              value={form.condition}
              onChange={(e) => set('condition', e.target.value)}
            />
          </div>


          {form.field_type === 'computed' && (
            <div className="grid gap-1.5">
              <Label htmlFor="computed_expr">Expression</Label>
              <Input
                id="computed_expr"
                value={form.computed_expr}
                placeholder="one_time_cost + annual_recurring * 3"
                onChange={(e) => set('computed_expr', e.target.value)}
              />
              <p className="text-muted-foreground text-xs">
                What the engine evaluates. The <strong>Formula</strong> box above is the
                register&rsquo;s sentence about the same rule, shown to the user as help
                text &mdash; both appear on the field, and where they disagree the reviewer
                sees it. A computed field with no expression renders a blank row forever.
              </p>
            </div>
          )}

          {/* ---- WHERE IT DRAWS ------------------------------------------ */}
          <div className="grid gap-3 rounded-md border p-3">
            <p className="text-section text-xs font-bold tracking-wide">WHERE IT DRAWS</p>
            <div className="grid grid-cols-3 gap-3">
              <div className="grid gap-1.5">
                <Label htmlFor="anchor_field">Anchor to</Label>
                <select
                  id="anchor_field"
                  className="border-input bg-input-bg h-9 rounded-md border px-2 text-sm"
                  value={form.anchor_field}
                  onChange={(e) => set('anchor_field', e.target.value)}
                >
                  <option value="">&mdash; its own section, in order &mdash;</option>
                  {anchorCandidates.map((f) => (
                    <option key={f.placement_id} value={f.api_name}>
                      {f.label} ({f.api_name})
                    </option>
                  ))}
                </select>
              </div>
              <div className="grid gap-1.5">
                <Label htmlFor="anchor_position">Position</Label>
                <select
                  id="anchor_position"
                  className="border-input bg-input-bg h-9 rounded-md border px-2 text-sm"
                  disabled={form.anchor_field === ''}
                  value={form.anchor_position}
                  onChange={(e) =>
                    set('anchor_position', e.target.value as FormState['anchor_position'])
                  }
                >
                  <option value="after">after &mdash; directly beneath it</option>
                  <option value="beside">beside &mdash; the next grid cell</option>
                </select>
              </div>
              <div className="grid gap-1.5">
                <Label htmlFor="layout_span">Width</Label>
                <select
                  id="layout_span"
                  className="border-input bg-input-bg h-9 rounded-md border px-2 text-sm"
                  value={form.layout_span}
                  onChange={(e) => set('layout_span', e.target.value as FormState['layout_span'])}
                >
                  <option value="">auto &mdash; whatever the type takes</option>
                  <option value="half">half row</option>
                  <option value="full">full row</option>
                </select>
              </div>
            </div>
            <p className="text-muted-foreground text-xs">
              Section says what <em>kind</em> of field this is. An anchor says where it goes
              &mdash; beside the question it answers, wherever that question happens to be,
              even in another section. A conditional field has to be in the same form as its
              trigger, or the box cannot appear until after a save.
            </p>
          </div>

          {/* ---- HOW ITS VALUE BEHAVES ----------------------------------- */}
          <div className="grid gap-3 rounded-md border p-3">
            <p className="text-section text-xs font-bold tracking-wide">
              HOW ITS VALUE BEHAVES
            </p>
            <div className="grid grid-cols-2 gap-3">
              <div className="grid gap-1.5">
                <Label htmlFor="value_mode">Opening value</Label>
                <select
                  id="value_mode"
                  className="border-input bg-input-bg h-9 rounded-md border px-2 text-sm"
                  value={form.value_mode}
                  onChange={(e) => set('value_mode', e.target.value as FormState['value_mode'])}
                >
                  <option value="own">own &mdash; starts empty</option>
                  <option value="carry_forward">
                    carry forward &mdash; seeded from the parent
                  </option>
                  <option value="read_through">read through &mdash; never stored here</option>
                </select>
              </div>
              <div className="grid gap-1.5">
                <Label htmlFor="stage_scoped">Recorded</Label>
                <select
                  id="stage_scoped"
                  className="border-input bg-input-bg h-9 rounded-md border px-2 text-sm"
                  value={form.stage_scoped}
                  onChange={(e) =>
                    set('stage_scoped', e.target.value as FormState['stage_scoped'])
                  }
                >
                  <option value="none">once per record</option>
                  <option value="carry_forward">per stage, inheriting the last answer</option>
                  <option value="sticky">per stage, never carried</option>
                </select>
              </div>
            </div>

            {form.value_mode === 'carry_forward' && (
              <label className="flex items-center gap-2 text-sm">
                <Checkbox
                  checked={form.value_locked}
                  onCheckedChange={(v) => set('value_locked', v === true)}
                />
                Locked &mdash; the carried value may not be changed afterwards
              </label>
            )}

            {form.stage_scoped !== 'none' && (
              <p className="text-muted-foreground text-xs">
                Per-stage values are stored as{' '}
                <code>{(form.api_name || 'api_name') + '__s3'}</code>, one key per stage.{' '}
                {form.stage_scoped === 'sticky'
                  ? 'Never carried: a lead put on hold at Stage 1 and again at Stage 3 gives two different reasons, and the Stage 3 box opens empty.'
                  : 'A stage with no answer of its own shows the nearest earlier one, and the plain name keeps holding the current answer for list columns.'}{' '}
                Only pipeline modules have stages &mdash; the API refuses this elsewhere.
              </p>
            )}

            {isEdit && (
              <p className="text-muted-foreground text-xs">
                <strong>Stored in:</strong>{' '}
                {field?.storage === 'column'
                  ? 'its own typed column — a register field keeps the column it has'
                  : field?.storage === 'custom_fields'
                    ? 'the custom_fields JSONB store — a field added here never gets a column, because that would be an ALTER TABLE issued from an admin screen'
                    : 'nothing — a read-through field stores no value of its own'}
                . Not a choice; a fact about the field.
              </p>
            )}
          </div>

          {isEdit && shared && (
            <label className="flex items-start gap-2 rounded-md border border-amber-500/40 bg-amber-500/5 p-2 text-sm">
              <Checkbox
                className="mt-0.5"
                checked={applyToAll}
                onCheckedChange={(v) => setApplyToAll(v === true)}
              />
              <span>
                Apply these to all {field?.module_count} placements of this field
                <span className="text-muted-foreground block text-xs">
                  {(detail?.placements ?? [])
                    .filter((p) => p.status === 'active')
                    .map((p) => p.module_key)
                    .join(', ') || 'loading…'}
                  . Everything above except <strong>Section</strong>, which names a row of
                  one module&rsquo;s own section list.
                </span>
              </span>
            </label>
          )}


          {isEdit && (
            <div className="grid gap-2 rounded-md border p-3">
              <p className="text-section text-xs font-bold tracking-wide">
                ALSO SHOW ON
              </p>
              {alsoCandidates.length === 0 ? (
                <p className="text-muted-foreground text-xs">
                  Already placed on every module that could carry it.
                </p>
              ) : (
                <div className="flex flex-wrap items-end gap-2">
                  <div className="grid gap-1.5">
                    <Label htmlFor="also_module">Module</Label>
                    <select
                      id="also_module"
                      className="border-input bg-input-bg h-9 rounded-md border px-2 text-sm"
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
                      className="border-input bg-input-bg h-9 rounded-md border px-2 text-sm"
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
                    disabled={
                      alsoModule === '' || alsoSectionId === null || addPlacement.isPending
                    }
                    onClick={addAlso}
                  >
                    {addPlacement.isPending ? 'Adding…' : 'Add placement'}
                  </Button>
                </div>
              )}
              <p className="text-muted-foreground text-xs">
                The same field on another module &mdash; one definition, a second placement.
                Its label, type and picklist stay shared; section, stage, conditions and
                value behaviour are that module&rsquo;s own. Added immediately, not on Save.
              </p>
            </div>
          )}

          <div className="grid gap-1.5">
            <Label htmlFor="description">Description</Label>
            <Textarea
              id="description"
              rows={2}
              value={form.description}
              onChange={(e) => set('description', e.target.value)}
            />
          </div>

          <div className="grid gap-1.5">
            <Label htmlFor="use_case">Use case</Label>
            <Textarea
              id="use_case"
              rows={2}
              value={form.use_case}
              onChange={(e) => set('use_case', e.target.value)}
            />
          </div>

          {field?.has_extension && (
            <p className="text-muted-foreground rounded-md border border-amber-500/40 bg-amber-500/5 p-2 text-xs">
              This field has an entry in <code>spec/extensions.json</code> &mdash; a
              child-list shape, a lookup filter, or a recorded departure from the register
              such as a type override. That file is hand-maintained and is{' '}
              <strong>not</strong> regenerated, so changing the type here will not update it.
              (Computed expressions moved out of that file and into the register in B2 &mdash;
              the <strong>Expression</strong> box above is the one that counts.)
            </p>
          )}

          {error && <p className="text-destructive text-sm">{error}</p>}
        </div>

        <DialogFooter>
          <Button variant="ghost" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button disabled={!canSubmit || busy} onClick={submit}>
            {busy ? 'Saving…' : isEdit ? 'Save changes' : 'Add field'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
