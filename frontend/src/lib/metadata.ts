import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { api } from '@/lib/api'

/**
 * Administration's metadata layer — the field register itself, as data.
 *
 * Goes through the shared axios client like everything else (CLAUDE.md rule 2)
 * and reaches FastAPI at /api/admin/metadata/* — DEVELOPER-only in V1.
 *
 * WHAT THESE SCREENS ARE EDITING, AND WHAT THEY ARE NOT
 * ------------------------------------------------------
 * They edit the DRAFT in PostgreSQL. They do not change a single screen in the
 * CRM until somebody publishes: the rest of the application still reads
 * spec/fields.json, spec/picklists.json and spec/stages.json, which the backend
 * rewrites only on publish. That is the whole Phase-1 arrangement —
 *
 *     Administration -> PostgreSQL -> publish -> spec/*.json -> the frontend
 *
 * — and it is why nothing here invalidates the spec: a published change reaches
 * the running app through Vite reloading the regenerated file, not through
 * React Query.
 */

export interface MetadataModule {
  module_key: string
  label: string
  sort_order: number
  active: boolean
  field_count: number
  deleted_field_count: number
  section_count: number
}

export interface MetadataSection {
  id: number
  module_key: string
  label: string
  sort_order: number
  active: boolean
  field_count: number
  deleted_field_count: number
}

/**
 * One field AS ONE MODULE SHOWS IT — a placement, with its definition inlined.
 *
 * `id` is the PLACEMENT id: the list this appears in is a list of the fields on
 * one module, and that is what gets reordered, removed from the module and
 * restored. `definition_id` is the canonical field behind it, and is what a
 * rename or a type change acts on.
 *
 * Which properties are which is not a convention to remember — the API says so
 * on every row. Anything named definition_* changes every module; everything
 * else changes this one.
 */
export interface MetadataField {
  id: number
  placement_id: number
  definition_id: number
  module_key: string
  scope_key: string
  section_id: number
  section_label: string
  api_name: string
  label: string
  field_type: string
  requirement: string
  required: boolean
  sort_order: number | null
  max_length: number | null
  min_value: number | null
  max_value: number | null
  picklist_key: string | null
  lookup_target: string | null
  lookup_filter: string | null
  values_note: string | null
  capture_stage: number | null
  capture_any_stage: boolean
  mandatory_from: number | null
  blocks_transition: string | null
  origin: string
  source_ref: string | null
  description: string
  use_case: string
  required_on_skip: boolean | null
  visibility_condition: string | null
  condition: string | null
  computed_formula: string | null
  status: 'active' | 'deleted'
  definition_status: 'active' | 'deleted'
  deleted_at: string | null
  deleted_by: string | null
  /** Removed by a delete-everywhere, rather than from this module alone. */
  deleted_by_cascade: boolean
  has_extension: boolean
  created_at: string
  updated_at: string

  // ---- naming
  /** What THIS module calls it, when that differs from the canonical label. */
  label_override: string | null
  /** The canonical name. Renaming it renames the field on every module. */
  definition_label: string

  // ---- value behaviour on this module
  value_mode: 'own' | 'read_through' | 'carry_forward'
  value_locked: boolean
  editable: boolean
  /** The module a read-through or carried value actually comes from. */
  value_source_module: string | null
  /** 'column', 'custom_fields', or null for read_through, which stores nothing. */
  storage: 'column' | 'custom_fields' | null
  /** One value per record, or one per stage. See StageScoped in types/field.ts. */
  stage_scoped: 'none' | 'carry_forward' | 'sticky'

  // ---- where it draws, as against what kind of field it is
  /** The api_name on this module this placement renders next to, or null. */
  anchor_field: string | null
  anchor_position: 'after' | 'beside' | null
  layout_span: 'full' | 'half' | null

  /**
   * The expression the engine evaluates. NOT computed_formula, which is the
   * register's English sentence about the same rule — both are shown to the
   * user, because where they disagree that is a finding.
   */
  computed_expr: string | null

  // ---- reach
  /** How many modules this field is live on. 1 unless it is shared. */
  module_count: number
  /** Where the concept originated. Provenance only — never where it appears. */
  origin_module: string | null
  provenance: string | null
}

export interface MetadataPicklistValue {
  id: number
  picklist_key: string
  key: string
  label: string
  sort_order: number
  active: boolean
}

export interface MetadataPicklist {
  picklist_key: string
  label: string | null
  sort_order: number
  active: boolean
  field_count: number
  values: MetadataPicklistValue[]
}

export interface MetadataStage {
  stage: number
  name: string
  /** What a record takes on entering this stage — whole percents, steps of 5. */
  progression_pct: number | null
  probability_pct: number | null
  owner_role: string | null
  bid_phase: string | null
  applies_to: string | null
  sort_order: number
  active: boolean
}

export interface MetadataValidation {
  ok: boolean
  errors: string[]
  warnings: string[]
  orphaned_sidecar_refs: string[]
}

export interface MetadataVersion {
  id: number
  version_no: number
  status: string
  note: string | null
  restored_from: number | null
  created_by: string | null
  created_at: string
  published_by: string | null
  published_at: string | null
  field_count: number
  picklist_count: number
  stage_count: number
}

export interface DraftStatus {
  published_version: number | null
  published_at: string | null
  has_changes: boolean
  changes: string[]
  validation: MetadataValidation
  counts: Record<string, number>
}

export interface PublishResult {
  version: MetadataVersion
  validation: MetadataValidation
  written: string[]
}

const BASE = '/admin/metadata'

export const metadataKeys = {
  modules: ['metadata', 'modules'] as const,
  sections: (module?: string) => ['metadata', 'sections', module ?? 'all'] as const,
  fields: (module?: string, status?: string) =>
    ['metadata', 'fields', module ?? 'all', status ?? 'active'] as const,
  field: (definitionId?: number) => ['metadata', 'field', definitionId] as const,
  picklists: ['metadata', 'picklists'] as const,
  stages: ['metadata', 'stages'] as const,
  draft: ['metadata', 'draft'] as const,
  versions: ['metadata', 'versions'] as const,
}

/**
 * Everything the metadata screens show is derived from the same draft, so one
 * write invalidates all of it — a renamed section changes the fields list, a
 * deleted field changes the draft's pending-change count and the deleted tab.
 * Cheap here (a few hundred rows) and much safer than trying to work out which
 * of six lists a given mutation could have moved.
 */
function useInvalidateMetadata() {
  const queryClient = useQueryClient()
  return () => void queryClient.invalidateQueries({ queryKey: ['metadata'] })
}

// ------------------------------------------------------------------ modules

export function useMetadataModules() {
  return useQuery({
    queryKey: metadataKeys.modules,
    queryFn: async () => (await api.get<MetadataModule[]>(`${BASE}/modules`)).data,
  })
}

export function useCreateModule() {
  const invalidate = useInvalidateMetadata()
  return useMutation({
    mutationFn: async (input: { module_key: string; label: string }) =>
      (await api.post<MetadataModule>(`${BASE}/modules`, input)).data,
    onSuccess: invalidate,
  })
}

export function useUpdateModule() {
  const invalidate = useInvalidateMetadata()
  return useMutation({
    mutationFn: async ({
      moduleKey,
      patch,
    }: {
      moduleKey: string
      patch: Partial<Pick<MetadataModule, 'label' | 'sort_order' | 'active'>>
    }) => (await api.patch<MetadataModule>(`${BASE}/modules/${moduleKey}`, patch)).data,
    onSuccess: invalidate,
  })
}

// ----------------------------------------------------------------- sections

export function useMetadataSections(module?: string) {
  return useQuery({
    queryKey: metadataKeys.sections(module),
    queryFn: async () =>
      (
        await api.get<MetadataSection[]>(`${BASE}/sections`, {
          params: module ? { module } : undefined,
        })
      ).data,
  })
}

export function useCreateSection() {
  const invalidate = useInvalidateMetadata()
  return useMutation({
    mutationFn: async (input: { module_key: string; label: string }) =>
      (await api.post<MetadataSection>(`${BASE}/sections`, input)).data,
    onSuccess: invalidate,
  })
}

export function useUpdateSection() {
  const invalidate = useInvalidateMetadata()
  return useMutation({
    mutationFn: async ({
      sectionId,
      patch,
    }: {
      sectionId: number
      patch: Partial<Pick<MetadataSection, 'label' | 'sort_order' | 'active'>>
    }) => (await api.patch<MetadataSection>(`${BASE}/sections/${sectionId}`, patch)).data,
    onSuccess: invalidate,
  })
}

export function useReorderSections() {
  const invalidate = useInvalidateMetadata()
  return useMutation({
    mutationFn: async (ids: number[]) =>
      (await api.post<MetadataSection[]>(`${BASE}/sections/reorder`, { ids })).data,
    onSuccess: invalidate,
  })
}

// ------------------------------------------------------------------- fields

export function useMetadataFields(module?: string, status: 'active' | 'deleted' | 'all' = 'active') {
  return useQuery({
    queryKey: metadataKeys.fields(module, status),
    queryFn: async () =>
      (
        await api.get<MetadataField[]>(`${BASE}/fields`, {
          params: { ...(module ? { module } : {}), status },
        })
      ).data,
  })
}

/**
 * What a create sends. A field is created as one definition plus its first
 * placement, so this carries both halves; the API decides which column each
 * one lands in.
 */
export type FieldInput = Partial<
  Omit<
    MetadataField,
    | 'id'
    | 'placement_id'
    | 'definition_id'
    | 'status'
    | 'definition_status'
    | 'deleted_at'
    | 'deleted_by'
    | 'deleted_by_cascade'
    | 'has_extension'
    | 'created_at'
    | 'updated_at'
    | 'section_label'
    | 'required'
    | 'module_count'
    | 'definition_label'
    | 'value_source_module'
    | 'provenance'
    | 'scope_key'
  >
>

/** Definition-level properties. Editing any of them changes EVERY module. */
export type DefinitionInput = Partial<{
  label: string
  field_type: string
  max_length: number | null
  min_value: number | null
  max_value: number | null
  picklist_key: string | null
  lookup_target: string | null
  lookup_filter: string | null
  computed_formula: string | null
  computed_expr: string | null
  values_note: string | null
  description: string
  use_case: string
  origin: string
  source_ref: string | null
}>

/** Placement-level properties. Editing them changes ONE module. */
export type PlacementInput = Partial<{
  section_id: number
  sort_order: number
  label_override: string | null
  capture_stage: number | null
  capture_any_stage: boolean
  mandatory_from: number | null
  blocks_transition: string | null
  requirement: string
  required_on_skip: boolean | null
  visibility_condition: string | null
  condition: string | null
  value_mode: 'own' | 'read_through' | 'carry_forward'
  value_locked: boolean
  editable: boolean
  storage: 'column' | 'custom_fields'
  stage_scoped: 'none' | 'carry_forward' | 'sticky'
  /** null clears the anchor and returns the field to its own section's list. */
  anchor_field: string | null
  anchor_position: 'after' | 'beside' | null
  layout_span: 'full' | 'half' | null
}>

/** One canonical field and every module it appears on. */
export interface MetadataFieldDetail {
  definition_id: number
  scope_key: string
  api_name: string
  definition_label: string
  field_type: string
  max_length: number | null
  min_value: number | null
  max_value: number | null
  picklist_key: string | null
  lookup_target: string | null
  lookup_filter: string | null
  computed_formula: string | null
  computed_expr: string | null
  values_note: string | null
  description: string
  use_case: string
  origin: string
  source_ref: string | null
  origin_module: string | null
  definition_status: 'active' | 'deleted'
  has_extension: boolean
  placements: MetadataField[]
}

export function useMetadataField(definitionId?: number) {
  return useQuery({
    queryKey: ['metadata', 'field', definitionId] as const,
    enabled: definitionId !== undefined,
    queryFn: async () =>
      (await api.get<MetadataFieldDetail>(`${BASE}/fields/${definitionId}`)).data,
  })
}

export function useCreateField() {
  const invalidate = useInvalidateMetadata()
  return useMutation({
    mutationFn: async (input: FieldInput) =>
      (await api.post<MetadataField>(`${BASE}/fields`, input)).data,
    onSuccess: invalidate,
  })
}

/**
 * Edit the CANONICAL definition. This changes every module the field is on.
 *
 * Takes a DEFINITION id, not a placement id — the distinction is the whole
 * point, and a call site that reaches for `field.id` here would silently edit
 * the wrong thing if the two were interchangeable. They are not.
 */
export function useUpdateField() {
  const invalidate = useInvalidateMetadata()
  return useMutation({
    mutationFn: async ({
      definitionId,
      patch,
    }: {
      definitionId: number
      patch: DefinitionInput
    }) =>
      (await api.patch<MetadataFieldDetail>(`${BASE}/fields/${definitionId}`, patch))
        .data,
    onSuccess: invalidate,
  })
}

/** Edit ONE module's copy. Nothing on any other module moves. */
export function useUpdatePlacement() {
  const invalidate = useInvalidateMetadata()
  return useMutation({
    mutationFn: async ({
      placementId,
      patch,
    }: {
      placementId: number
      patch: PlacementInput
    }) =>
      (await api.patch<MetadataField>(`${BASE}/placements/${placementId}`, patch)).data,
    onSuccess: invalidate,
  })
}

/**
 * Show an existing field on another module. "Also show on…".
 *
 * A second PLACEMENT, never a second definition — which is the action the
 * pre-Round-7 model refused outright ("a field cannot change module").
 */
export function useAddPlacement() {
  const invalidate = useInvalidateMetadata()
  return useMutation({
    mutationFn: async ({
      definitionId,
      input,
    }: {
      definitionId: number
      input: { module_key: string; section_id: number } & PlacementInput
    }) =>
      (
        await api.post<MetadataField>(
          `${BASE}/fields/${definitionId}/placements`,
          input
        )
      ).data,
    onSuccess: invalidate,
  })
}

/**
 * The Required / Not Required toggle, on one module.
 *
 * Application-level only. It writes requirement Mandatory or Optional and has
 * no effect whatsoever on the business table's nullability — see the endpoint's
 * own docstring in backend/app/routers/metadata.py.
 */
export function useSetFieldRequired() {
  const invalidate = useInvalidateMetadata()
  return useMutation({
    mutationFn: async ({
      placementId,
      required,
    }: {
      placementId: number
      required: boolean
    }) =>
      (
        await api.patch<MetadataField>(`${BASE}/placements/${placementId}/required`, {
          required,
        })
      ).data,
    onSuccess: invalidate,
  })
}

/**
 * Remove a field from ONE module. The canonical definition and every other
 * placement are untouched, and so is every byte of business data: no
 * DROP COLUMN, no JSONB key removed.
 */
export function useRemovePlacement() {
  const invalidate = useInvalidateMetadata()
  return useMutation({
    mutationFn: async (placementId: number) =>
      (await api.delete<MetadataField>(`${BASE}/placements/${placementId}`)).data,
    onSuccess: invalidate,
  })
}

export function useRestorePlacement() {
  const invalidate = useInvalidateMetadata()
  return useMutation({
    mutationFn: async (placementId: number) =>
      (await api.post<MetadataField>(`${BASE}/placements/${placementId}/restore`)).data,
    onSuccess: invalidate,
  })
}

/**
 * Delete a field EVERYWHERE — the definition and all of its placements.
 *
 * Logical, like every delete here: the rows stay, the typed columns stay, and
 * every value in them stays. Restore brings back only the placements this
 * delete took down.
 */
export function useDeleteField() {
  const invalidate = useInvalidateMetadata()
  return useMutation({
    mutationFn: async (definitionId: number) =>
      (await api.delete<MetadataFieldDetail>(`${BASE}/fields/${definitionId}`)).data,
    onSuccess: invalidate,
  })
}

export function useRestoreField() {
  const invalidate = useInvalidateMetadata()
  return useMutation({
    mutationFn: async (definitionId: number) =>
      (await api.post<MetadataFieldDetail>(`${BASE}/fields/${definitionId}/restore`))
        .data,
    onSuccess: invalidate,
  })
}

export function useReorderFields() {
  const invalidate = useInvalidateMetadata()
  return useMutation({
    mutationFn: async (ids: number[]) =>
      (await api.post<MetadataField[]>(`${BASE}/placements/reorder`, { ids })).data,
    onSuccess: invalidate,
  })
}

/**
 * How this module's copy of a field behaves, in words an administrator can act
 * on. Section 22 of the Round-7 brief asks for exactly this on every row.
 */
export function valueBehaviourOf(field: MetadataField): {
  label: string
  detail: string
  tone: 'owned' | 'inherited' | 'carried'
} {
  if (field.value_mode === 'read_through') {
    return {
      tone: 'inherited',
      label: `Read-through from ${field.value_source_module ?? 'the parent'}`,
      detail:
        `This module does not store a value. It is resolved from the ` +
        `${field.value_source_module ?? 'parent'} record every time it is read, ` +
        `so the same value cannot exist in two places and drift. Read-only here; ` +
        `edit it on ${field.value_source_module ?? 'the parent module'}.`,
    }
  }
  if (field.value_mode === 'carry_forward') {
    return {
      tone: 'carried',
      label: `Carried from ${field.value_source_module ?? 'the parent'}`,
      detail:
        `The opening value is copied from the ${field.value_source_module ?? 'parent'} ` +
        `record when this record is created, and this module owns it afterwards` +
        (field.value_locked
          ? '. Locked: it may not be changed once carried.'
          : ' — it may be changed here without affecting the source.'),
    }
  }
  return {
    tone: 'owned',
    label: 'Owned here',
    detail: 'This module stores its own value. Nothing is inherited.',
  }
}

// ---------------------------------------------------------------- picklists

export function useMetadataPicklists() {
  return useQuery({
    queryKey: metadataKeys.picklists,
    queryFn: async () => (await api.get<MetadataPicklist[]>(`${BASE}/picklists`)).data,
  })
}

export function useCreatePicklist() {
  const invalidate = useInvalidateMetadata()
  return useMutation({
    mutationFn: async (input: { picklist_key: string; label?: string }) =>
      (await api.post<MetadataPicklist>(`${BASE}/picklists`, input)).data,
    onSuccess: invalidate,
  })
}

export function useUpdatePicklist() {
  const invalidate = useInvalidateMetadata()
  return useMutation({
    mutationFn: async ({
      picklistKey,
      patch,
    }: {
      picklistKey: string
      patch: { label?: string | null; active?: boolean }
    }) => (await api.patch<MetadataPicklist>(`${BASE}/picklists/${picklistKey}`, patch)).data,
    onSuccess: invalidate,
  })
}

export function useCreatePicklistValue() {
  const invalidate = useInvalidateMetadata()
  return useMutation({
    mutationFn: async (input: { picklist_key: string; key: string; label: string }) =>
      (await api.post<MetadataPicklistValue>(`${BASE}/picklist-values`, input)).data,
    onSuccess: invalidate,
  })
}

/** Label, order and active only — a value's KEY is what records already store. */
export function useUpdatePicklistValue() {
  const invalidate = useInvalidateMetadata()
  return useMutation({
    mutationFn: async ({
      valueId,
      patch,
    }: {
      valueId: number
      patch: { label?: string; sort_order?: number; active?: boolean }
    }) =>
      (await api.patch<MetadataPicklistValue>(`${BASE}/picklist-values/${valueId}`, patch)).data,
    onSuccess: invalidate,
  })
}

export function useReorderPicklistValues() {
  const invalidate = useInvalidateMetadata()
  return useMutation({
    mutationFn: async (ids: number[]) =>
      (await api.post<MetadataPicklistValue[]>(`${BASE}/picklist-values/reorder`, { ids })).data,
    onSuccess: invalidate,
  })
}

// ------------------------------------------------------------------- stages

export function useMetadataStages() {
  return useQuery({
    queryKey: metadataKeys.stages,
    queryFn: async () => (await api.get<MetadataStage[]>(`${BASE}/stages`)).data,
  })
}

export function useUpdateStage() {
  const invalidate = useInvalidateMetadata()
  return useMutation({
    mutationFn: async ({
      stage,
      patch,
    }: {
      stage: number
      patch: Partial<Omit<MetadataStage, 'stage'>>
    }) => (await api.patch<MetadataStage>(`${BASE}/stages/${stage}`, patch)).data,
    onSuccess: invalidate,
  })
}

export function useCreateStage() {
  const invalidate = useInvalidateMetadata()
  return useMutation({
    mutationFn: async (input: Partial<MetadataStage> & { stage: number; name: string }) =>
      (await api.post<MetadataStage>(`${BASE}/stages`, input)).data,
    onSuccess: invalidate,
  })
}

// -------------------------------------------------------- draft and versions

export function useDraftStatus() {
  return useQuery({
    queryKey: metadataKeys.draft,
    queryFn: async () => (await api.get<DraftStatus>(`${BASE}/draft`)).data,
  })
}

export function useMetadataVersions() {
  return useQuery({
    queryKey: metadataKeys.versions,
    queryFn: async () => (await api.get<MetadataVersion[]>(`${BASE}/versions`)).data,
  })
}

export function usePublishMetadata() {
  const invalidate = useInvalidateMetadata()
  return useMutation({
    mutationFn: async (note: string) =>
      (await api.post<PublishResult>(`${BASE}/publish`, { note: note || null })).data,
    onSuccess: invalidate,
  })
}

export function useRollbackMetadata() {
  const invalidate = useInvalidateMetadata()
  return useMutation({
    mutationFn: async ({ versionNo, note }: { versionNo: number; note?: string }) =>
      (
        await api.post<PublishResult>(`${BASE}/versions/${versionNo}/rollback`, {
          note: note || null,
        })
      ).data,
    onSuccess: invalidate,
  })
}

// ------------------------------------------------------------------ helpers
//
// effectiveModuleOf() used to live here — resolving where a field ACTUALLY
// lands, because field.module_key was the register sheet, not the screen.
// Round 7 removed the gap it was patching: module_key on a MetadataField IS
// the screen now, straight off field_placements. There is nothing left to
// resolve.

/** The FieldType union, for the type dropdown. Mirrors FIELD_TYPES on the API. */
export const FIELD_TYPES = [
  'text',
  'longtext',
  'richtext',
  'number',
  'currency',
  'percent',
  'date',
  'datetime',
  'checkbox',
  'picklist',
  'multiselect',
  'lookup',
  'childlist',
  'computed',
  'autonumber',
  'file',
  'url',
  'email',
  'phone',
] as const

export const REQUIREMENTS = [
  'Mandatory',
  'Conditional',
  'Optional',
  'Advisory',
  'System',
  'Computed',
] as const
