import splitData from '../../../spec/module_split.json'
import type { FieldCarry, FieldSpec } from '@/types/field'

/**
 * The three-module pipeline split, applied to the merged field list.
 *
 * spec/fields.json is generated from the workbook and is not edited, so the
 * reassignment lives in spec/module_split.json and is applied HERE, after
 * spec/extensions.json has been merged on top — a sidecar entry keyed on
 * `leads.total_value_tcv` has to find its field before the field moves to
 * Opportunities.
 *
 * Nothing about which module owns which stage is written in this file. It is
 * all read off module_split.json, which is the single authority; `applies_to`
 * in spec/stages.json still says stages 4-7 are `lead` and is deliberately
 * ignored, with a register-correction row on the Spec Health page.
 */

interface OwnSpec {
  reason: string
  exclude?: string[]
  exclude_reason?: string
  relabel?: Record<string, string>
  relabel_note?: string
}

interface EquivalenceSpec {
  shared: string
  existing: string
  note: string
}

/**
 * A field relocated to a different stage than the register captures it at, as
 * a deliberate product decision — not a register error, which is why this is
 * a separate mechanism from register_corrections. mandatory_from and
 * blocks_transition are optional: a Conditional field with no stage gate has
 * nothing to move on that axis, only capture_stage and section.
 */
interface RelocationSpec {
  capture_stage: number
  section: string
  mandatory_from?: number
  blocks_transition?: string
  reason: string
}

interface SplitFile {
  version: number
  ranges: Record<string, [number, number]>
  pipeline: string[]
  stage_field: Record<string, string>
  reassign: Record<string, Record<string, string>>
  shared: {
    source_module: string
    sections: string[]
    equivalence: EquivalenceSpec[]
  }
  own: { section: string; fields: Record<string, OwnSpec> }
  read_through: {
    section: string
    parent_of: Record<string, string>
    parent_link: Record<string, string>
    source_module: string
    skip_when_declared: boolean
    fields: string[]
  }
  section_order: Record<string, number>
  register_corrections: { ref: string; detail: string }[]
  relocated_fields: Record<string, RelocationSpec>
}

/** `$`-prefixed keys in the JSON are documentation, not data. */
export const split = splitData as unknown as SplitFile

export const PIPELINE_MODULES: string[] = split.pipeline

/** Inclusive [first, last] stage of a pipeline module. Undefined for the rest. */
export function rangeOf(module: string): [number, number] | undefined {
  const r = split.ranges[module]
  return Array.isArray(r) ? [r[0], r[1]] : undefined
}

/** True when this module owns that stage number. */
export function moduleOwnsStage(module: string, stage: number): boolean {
  const r = rangeOf(module)
  return Boolean(r && stage >= r[0] && stage <= r[1])
}

/** The pipeline module that owns a stage — leads 0-3, opportunities 4-6, deals 7-9. */
export function moduleForStage(stage: number): string | undefined {
  return PIPELINE_MODULES.find((m) => moduleOwnsStage(m, stage))
}

/** The field a module stores its own stage in. Deals keeps the register's deal_stage. */
export function stageFieldOf(module: string): string | undefined {
  return split.stage_field[module]
}

/** The module a read-through field's value is resolved from. */
export function parentModuleOf(module: string): string | undefined {
  return split.read_through.parent_of[module]
}

/** The lookup field on `module` holding the parent record's id. */
export function parentLinkOf(module: string): string | undefined {
  return split.read_through.parent_link[module]
}

export const sharedEquivalence: EquivalenceSpec[] = split.shared.equivalence ?? []
export const registerCorrections = split.register_corrections ?? []

/**
 * Fields relocated to a stage the register does not capture them at, keyed on
 * their REGISTER ref ("leads.payment_milestones") — checked before the normal
 * stage-based reassign in placementsFor, so the field routes to whichever
 * module owns the override stage.
 */
/** `$`-prefixed keys in relocated_fields are documentation, not a field entry. */
export const relocatedFields: Record<string, RelocationSpec> = Object.fromEntries(
  Object.entries(split.relocated_fields ?? {}).filter(([key]) => !key.startsWith('$'))
)

// ------------------------------------------------------------------ placement

const SHARED_SECTIONS = split.shared.sections
const OWN_FIELDS = split.own.fields
const READ_THROUGH = split.read_through.fields

function isSharedSection(section: string): boolean {
  const upper = (section ?? '').toUpperCase()
  return SHARED_SECTIONS.some((s) => upper.startsWith(s))
}

/**
 * Which modules a field belongs to after the split, and why.
 *
 * A field the register writes on a module the split does not touch stays
 * exactly where it is — accounts, contacts, partners and everything else are
 * unaffected.
 */
function placementsFor(field: FieldSpec, isNew: boolean): { module: string; carry: FieldCarry }[] {
  const home = field.module

  // A new_fields row names the module it belongs to outright — including
  // `opportunities`, which the register has never heard of.
  if (isNew) return [{ module: home, carry: 'new' }]

  const reassign = split.reassign[home]
  if (!reassign) return [{ module: home, carry: 'own' }]

  if (isSharedSection(field.section)) {
    return PIPELINE_MODULES.map((m) => ({ module: m, carry: m === home ? 'own' : ('shared' as FieldCarry) }))
  }

  const own = OWN_FIELDS[field.api_name]
  if (own) {
    return PIPELINE_MODULES.filter((m) => !(own.exclude ?? []).includes(m)).map((m) => ({
      module: m,
      carry: m === home ? 'own' : ('own_instance' as FieldCarry),
    }))
  }

  // A relocated field routes on its OVERRIDE stage, not the register's own —
  // payment_milestones is captured at Stage 7 in the register but this build
  // moves it to Stage 6, so it must reassign to Opportunities, not Deals.
  const relocation = relocatedFields[refOf(field)]
  const stage = relocation ? relocation.capture_stage : field.capture_stage
  const target = stage === null ? undefined : reassign[String(stage)]
  if (target) return [{ module: target, carry: 'moved' }]

  return [{ module: home, carry: 'own' }]
}

// ------------------------------------------------------------- section order

/**
 * Where a section sits in a split module's running order. Register order is
 * preserved INSIDE a section; only the sequence of sections is decided here, so
 * a Stage 5 block still reads in the order the workbook wrote it.
 */
function sectionRank(field: FieldSpec): number {
  const o = split.section_order
  const section = (field.section ?? '').toUpperCase()
  if (section.startsWith('HEADER')) return o.HEADER
  if (section.startsWith('RECORD STATE')) return o['RECORD STATE']
  if (section.startsWith('READ THROUGH')) return o['READ THROUGH THE PARENT']
  if (section.startsWith('CROSS-CUTTING')) return o['CROSS-CUTTING']
  if (section.startsWith('SYSTEM')) return o.SYSTEM
  if (field.capture_stage !== null && field.capture_stage !== undefined) {
    return o.stage_offset + field.capture_stage
  }
  return o.unstaged
}

// ------------------------------------------------------------------- applying

export interface SplitResult {
  fields: FieldSpec[]
  /**
   * Every ref and qref that named a field on its register module and now names
   * one somewhere else — `leads.rfp_received_date` -> `opportunities.rfp_received_date`.
   *
   * fieldByRef falls through this map, so every sidecar key, list_views column,
   * child_spec column ref and seed_normalisation entry written before the split
   * still resolves. The debt is not hidden: Spec Health lists each one so the
   * sidecar can be rewritten deliberately rather than silently.
   */
  movedRefs: Map<string, string>
  /** Placements that would put two different fields under one api_name. */
  errors: string[]
}

function refOf(f: { module: string; api_name: string }): string {
  return `${f.module}.${f.api_name}`
}

function qrefOf(f: { module: string; section: string; api_name: string }): string {
  return `${f.module}.${f.section}.${f.api_name}`
}

/**
 * Apply the split to a merged field list.
 *
 * Input is the register plus new_fields with the sidecar merged on top, keyed
 * on the register's own modules. Output is the same fields re-homed, with the
 * shared, own-instance and read-through copies added.
 */
export function applyModuleSplit(merged: FieldSpec[], newFieldQrefs: Set<string>): SplitResult {
  const out: FieldSpec[] = []
  const movedRefs = new Map<string, string>()
  const errors: string[] = []

  for (const field of merged) {
    const relocation = relocatedFields[refOf(field)]

    for (const { module, carry } of placementsFor(field, newFieldQrefs.has(field.qref))) {
      const section =
        carry === 'own_instance'
          ? split.own.section
          : (relocation?.section ?? field.section)

      const relabel = OWN_FIELDS[field.api_name]?.relabel?.[module]

      const placed: FieldSpec = {
        ...field,
        module,
        section,
        label: relabel ?? field.label,
        carry,
        register_module: field.module,
        register_order: field.order,
        ref: `${module}.${field.api_name}`,
        qref: `${module}.${section}.${field.api_name}`,
        // capture_stage travels with the relocation so sectionRank, the
        // Stage-N tabs and readiness all see where the field ACTUALLY sits.
        // mandatory_from/blocks_transition follow only when the override
        // states them — a Conditional field with no stage gate has nothing
        // on that axis to move.
        ...(relocation
          ? {
              capture_stage: relocation.capture_stage,
              ...(relocation.mandatory_from !== undefined
                ? { mandatory_from: relocation.mandatory_from }
                : {}),
              ...(relocation.blocks_transition !== undefined
                ? { blocks_transition: relocation.blocks_transition }
                : {}),
            }
          : {}),
      }
      out.push(placed)

      // Only a field that left its register module needs a fall-through: a
      // shared or own-instance field is still on Leads under its old ref.
      if (module !== field.module && carry === 'moved') {
        movedRefs.set(refOf(field), placed.ref)
        movedRefs.set(qrefOf(field), placed.qref)
      }
    }
  }

  // -------------------------------------------------------- read-through rows
  //
  // Added last so a field the target module ALREADY declares wins: deals
  // declares end_client and customer_partner_si itself, so Deals takes 18 of
  // the 20 rather than all of them. Whether those two register rows should be
  // read-through instead is an open question in extensions.json, not something
  // this loader decides.
  const source = split.read_through.source_module
  for (const module of PIPELINE_MODULES) {
    if (module === source) continue
    const parent = parentModuleOf(module)
    const via = parentLinkOf(module)
    const declared = new Set(out.filter((f) => f.module === module).map((f) => f.api_name))

    for (const apiName of READ_THROUGH) {
      if (split.read_through.skip_when_declared && declared.has(apiName)) continue
      const src = merged.find((f) => f.module === source && f.api_name === apiName)
      if (!src) {
        errors.push(
          `spec/module_split.json read_through names "${apiName}", which module "${source}" does not declare.`
        )
        continue
      }
      const section = split.read_through.section
      out.push({
        ...src,
        module,
        section,
        carry: 'read_through',
        register_module: src.module,
        register_order: src.order,
        read_through_from: parent,
        read_through_via: via,
        ref: `${module}.${apiName}`,
        qref: `${module}.${section}.${apiName}`,
      })
    }
  }

  // ------------------------------------------------------------- renumbering
  //
  // sectionsFor() reads a module's sections off first appearance in `order`, so
  // the split has to leave `order` contiguous per section or two sections would
  // interleave and the form would render one of them twice. Only the three
  // pipeline modules are renumbered; every other module keeps the register's
  // own numbering untouched.
  for (const module of PIPELINE_MODULES) {
    const rows = out.filter((f) => f.module === module)
    const sections = new Map<string, FieldSpec[]>()
    for (const f of rows) sections.set(f.section, [...(sections.get(f.section) ?? []), f])

    const ordered = [...sections.entries()].sort((a, b) => {
      const ra = sectionRank(a[1][0])
      const rb = sectionRank(b[1][0])
      if (ra !== rb) return ra - rb
      // Two sections at the same rank — ON CONVERSION and STAGE 7 — CLOSE both
      // sit at Stage 7 on Deals. The one the register numbered lower goes first.
      const la = Math.min(...a[1].map((f) => f.register_order ?? f.order))
      const lb = Math.min(...b[1].map((f) => f.register_order ?? f.order))
      return la - lb
    })

    let n = 0
    for (const [, group] of ordered) {
      group.sort((x, y) => (x.register_order ?? x.order) - (y.register_order ?? y.order))
      for (const f of group) f.order = ++n
    }
  }

  // ------------------------------------------------------------- containment
  //
  // The split must never put two DIFFERENT fields on one module under one
  // api_name — a record keys on api_name alone, so they would overwrite each
  // other. Verified to be clean today; asserted so a later edit to
  // module_split.json cannot introduce one silently.
  const seen = new Map<string, Set<string>>()
  for (const f of out) {
    const key = `${f.module}.${f.api_name}`
    const sections = seen.get(key) ?? new Set<string>()
    sections.add(f.section)
    seen.set(key, sections)
  }
  for (const [key, sections] of seen) {
    const module = key.split('.')[0]
    if (!PIPELINE_MODULES.includes(module)) continue
    if (sections.size > 1) {
      errors.push(
        `The split places "${key}" in ${[...sections].map((s) => `"${s}"`).join(' and ')}. ` +
          'A record keys on api_name alone, so one would overwrite the other.'
      )
    }
  }

  return { fields: out, movedRefs, errors }
}
