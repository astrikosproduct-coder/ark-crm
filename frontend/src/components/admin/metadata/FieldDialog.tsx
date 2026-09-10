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
  useCreateField,
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
  description: string
  use_case: string
  capture_any_stage: boolean
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
  description: '',
  use_case: '',
  capture_any_stage: false,
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
        description: field.description ?? '',
        use_case: field.use_case ?? '',
        capture_any_stage: field.capture_any_stage,
      })
    } else {
      setForm({ ...EMPTY, section_id: sectionId ?? sections[0]?.id ?? null })
    }
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
    description: payload.description,
    use_case: payload.use_case,
  }

  const placementPatch = {
    requirement: payload.requirement,
    capture_stage: payload.capture_stage,
    capture_any_stage: payload.capture_any_stage,
    mandatory_from: payload.mandatory_from,
    blocks_transition: payload.blocks_transition,
    visibility_condition: payload.visibility_condition,
    condition: payload.condition,
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
              This field has an entry in <code>spec/extensions.json</code> — a computed
              expression, a child-list shape or a type override. That file is hand-maintained
              and is <strong>not</strong> regenerated, so changing the type here will not
              update it.
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
