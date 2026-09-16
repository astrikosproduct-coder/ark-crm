import fieldsData from '../../../spec/fields.json'
import picklistsData from '../../../spec/picklists.json'
import extensionsData from '../../../spec/extensions.json'
import type {
  FieldExtension,
  FieldSetSpec,
  FieldSpec,
  ListViewSpec,
  PartnerRegistrationSpec,
  PicklistMap,
  PicklistOption,
  RawFieldSpec,
  SeedNormalisationSpec,
  SpecNote,
} from '@/types/field'

/** A new_fields row: every register column, plus the two sidecar-only keys. */
type NewFieldSpec = RawFieldSpec & Pick<FieldExtension, 'computed_by' | 'structural'>

interface ExtensionsFile {
  version: number
  fields: Record<string, FieldExtension>
  new_fields: NewFieldSpec[]
  list_views: Record<string, ListViewSpec | string>
  seed_normalisation: Record<string, SeedNormalisationSpec | string>
  partner_roster: { account_types: string[] }
  partner_registration: PartnerRegistrationSpec
  quick_create: { extra_fields: Record<string, string[]> }
  kanban: { status_field: string; terminal_statuses: string[] }
  open_questions: { rows: SpecNote[] }
  precision_limits: { rows: SpecNote[] }
}

const extensionsFile = extensionsData as unknown as ExtensionsFile
const extensions = extensionsFile.fields
export const picklists = picklistsData as unknown as PicklistMap

/**
 * The origin string the 27 gap-fix rows carry. Spec Health groups on it.
 *
 * They used to live in extensions.json `new_fields` and be appended to the
 * register list here, which meant Administration could not see them at all —
 * bootstrap_metadata.py said so in as many words: "extensions.json's
 * new_fields rows are NOT imported". 27 fields rendered in the CRM and existed
 * in no database table. Round 7 absorbed them into field_definitions, so they
 * arrive in fields.json like every other field and are administrable like
 * every other field. What still distinguishes them is `origin`, which is all
 * that ever should have.
 */
export const NEW_FIELD_ORIGIN = 'gap-fix — 14-stage review'

/**
 * Every field, already placed.
 *
 * spec/fields.json is generated from field_placements: one row per module a
 * field appears on, carrying the section, order, label and value behaviour it
 * has THERE. Nothing is re-homed here — see ./moduleSplit.ts for what that
 * file used to do and why it no longer does it.
 */
const raw: RawFieldSpec[] = fieldsData as unknown as RawFieldSpec[]



/**
 * The split's own vocabulary, re-exported so a component reaches for one spec
 * entry point rather than importing half of it from a second file.
 */
export {
  PIPELINE_MODULES,
  moduleForStage,
  moduleOwnsStage,
  parentLinkOf,
  parentModuleOf,
  rangeOf,
  registerCorrections,
  stageFieldOf,
} from './moduleSplit'

/** True when this field's value lives on the parent record, not on this one. */
export function isReadThrough(field: FieldSpec): boolean {
  return field.value_mode === 'read_through'
}

/**
 * True when this field's opening value is copied from the parent at creation
 * and owned afterwards. Seeded by the API, not by the form — see
 * backend/app/carry_forward.py.
 */
export function isCarriedForward(field: FieldSpec): boolean {
  return field.value_mode === 'carry_forward'
}

// ----------------------------------------------------------- ambiguous names

/**
 * Nine api_names are defined twice inside one module, because a register sheet
 * describes several different records in one flat list of rows — partners.partner
 * is written into both DEAL REGISTRATION and QUARTERLY SCORECARD.
 *
 * The containment is to key the index on module.section.api_name, and to keep
 * module.api_name as an alias ONLY where the name is unique in that module. An
 * ambiguous alias resolves to nothing rather than to whichever definition
 * happened to be written last. Nothing here merges the duplicates or renames
 * them: the register still carries them, and the Spec Health entry stays up
 * until the register pass fixes them properly.
 */
function qrefOf(f: { module: string; section: string; api_name: string }): string {
  return `${f.module}.${f.section}.${f.api_name}`
}

/**
 * The index is built TWICE, over two different lists, because a sidecar key and
 * an expression are asking different questions.
 *
 * A key in extensions.json is written against the register — `leads.rfp_document`
 * — and has to be resolved before spec/module_split.json moves that field to
 * Opportunities. An identifier inside a computed_expr is evaluated against a
 * LIVE record and has to be resolved against the module that record belongs to
 * now. So the pre-split index below serves the sidecar merge, and the post-split
 * index further down serves everything else.
 *
 * They agree everywhere it matters: none of the nine duplicated api_names is on
 * a pipeline module, and PostgreSQL's uq_field_placements_qname constraint
 * refuses to store one.
 */
/**
 * The alias index a SIDECAR KEY is written against.
 *
 * spec/extensions.json is hand-maintained and its 58 field keys were written
 * against the register's own modules — `leads.rfp_received_date` for a field
 * that renders on Opportunities. `register_module` carries that original
 * module on every row, so the sidecar still finds its field without anyone
 * rewriting a single key. 57 of the 58 resolve this way; the one that does not
 * names a field that has been deleted, and Spec Health reports it.
 *
 * A definition-level sidecar entry lands on EVERY placement of that field,
 * which is correct: computed_expr, child_spec and type_override describe the
 * field, not the module it is being shown on.
 */
function sidecarKeysFor(f: RawFieldSpec): string[] {
  const own = `${f.module}.${f.api_name}`
  const register = f.register_module ? `${f.register_module}.${f.api_name}` : null
  return register && register !== own ? [own, register] : [own]
}

const preSplitByAlias = new Map<string, RawFieldSpec[]>()
for (const f of raw) {
  // Only a field on its OWN module counts towards ambiguity. A field copied
  // onto three modules is one definition seen three times, not three
  // definitions — the duplicated api_names the register really does carry are
  // all in non-pipeline modules, where module and register_module agree.
  if (f.register_module && f.register_module !== f.module) continue
  const alias = `${f.module}.${f.api_name}`
  preSplitByAlias.set(alias, [...(preSplitByAlias.get(alias) ?? []), f])
}

const preSplitAmbiguous = new Set(
  [...preSplitByAlias.entries()].filter(([, defs]) => defs.length > 1).map(([alias]) => alias)
)

export interface DuplicateApiName {
  module: string
  api_name: string
  /** Every section of the module that defines it, in register order. */
  sections: string[]
  /** "SECTION #order" for each definition. */
  places: string[]
}

/**
 * A sidecar key, plain or fully qualified.
 *
 * Neither a module, a section nor an api_name contains a dot anywhere in the
 * register, so a two-part key is `module.api_name` and anything longer is
 * `module.section.api_name`. The section is taken as everything between, so the
 * parse survives a section name growing a dot later.
 */
function parseRef(ref: string): { module: string; section?: string; api_name: string } | null {
  const parts = ref.split('.')
  if (parts.length < 2) return null
  if (parts.length === 2) return { module: parts[0], api_name: parts[1] }
  return {
    module: parts[0],
    section: parts.slice(1, -1).join('.'),
    api_name: parts[parts.length - 1],
  }
}

/**
 * Sidecar keys that name a duplicated api_name without saying which one.
 *
 * Collected rather than thrown from module scope, so main.tsx can render the
 * list instead of the app showing a blank page. Startup stops either way — a
 * sidecar entry that binds to an arbitrary one of two fields is worse than no
 * prototype at all.
 */
export const specRefErrors: string[] = []

function checkRef(ref: string, where: string): void {
  const parsed = parseRef(ref)
  if (!parsed || parsed.section) return
  // The PRE-split index: a sidecar key names the register's own module, and it
  // is checked before the split has moved anything.
  const alias = `${parsed.module}.${parsed.api_name}`
  if (!preSplitAmbiguous.has(alias)) return
  specRefErrors.push(
    `${where} names "${ref}", but "${parsed.api_name}" is defined in ${(
      preSplitByAlias.get(alias) ?? []
    )
      .map((f) => `"${f.section}"`)
      .join(' and ')} of module "${parsed.module}". Qualify it as ` +
      `"${parsed.module}.<SECTION>.${parsed.api_name}".`
  )
}

/** `$`-prefixed keys are the sidecar's own documentation, not field entries. */
const extensionKeys = Object.keys(extensions).filter((key) => !key.startsWith('$'))

for (const key of extensionKeys) checkRef(key, 'spec/extensions.json fields')

/**
 * fields.json is generated by build_spec.py and must never be hand-edited, so
 * the keys the form engine needs but the register does not carry live in
 * spec/extensions.json and are merged on top here. A regenerate of fields.json
 * leaves the sidecar untouched.
 *
 * A sidecar entry may key on either form. The qualified key wins, and the plain
 * alias is only consulted when the name is unique in the module — an ambiguous
 * alias has already been rejected above.
 */
const mergedFields: FieldSpec[] = raw.map((f) => {
  const ref = `${f.module}.${f.api_name}`
  const qref = qrefOf(f)
  const aliases = sidecarKeysFor(f)
  const ext =
    extensions[qref] ??
    aliases.map((key) => (preSplitAmbiguous.has(key) ? undefined : extensions[key])).find(Boolean)
  return {
    ...f,
    ...(ext ?? {}),
    ref,
    qref,
    // Applied explicitly, not by the spread above: RawFieldSpec.type and
    // .label are mandatory, so the sidecar carries these under different
    // names (type_override/label_override) rather than clashing with them —
    // see FieldExtension's own comment.
    ...(ext?.type_override ? { type: ext.type_override } : {}),
    ...(ext?.label_override ? { label: ext.label_override } : {}),
  }
})

export const fields: FieldSpec[] = mergedFields

/**
 * Refs written against a field's ORIGINAL module that now name it elsewhere.
 *
 * `leads.total_value_tcv` -> `opportunities.total_value_tcv`. Every sidecar
 * key, list_views column, child_spec column ref and seed_normalisation entry
 * written before the pipeline was split still resolves through this.
 *
 * Derived from the data rather than declared: a row whose register_module
 * differs from its module contributes one entry, and only when nothing on the
 * original module already answers to that name — a field that is genuinely on
 * Leads AND Opportunities needs no fall-through, because the direct lookup
 * already finds the Leads one. The debt is not hidden: Spec Health lists every
 * entry so the sidecar can be rewritten deliberately rather than silently.
 */
const liveAliases = new Set(mergedFields.map((f) => `${f.module}.${f.api_name}`))
const derivedMovedRefs = new Map<string, string>()
for (const f of mergedFields) {
  if (!f.register_module || f.register_module === f.module) continue
  const from = `${f.register_module}.${f.api_name}`
  if (liveAliases.has(from) || derivedMovedRefs.has(from)) continue
  derivedMovedRefs.set(from, `${f.module}.${f.api_name}`)
}

export const movedRefs: ReadonlyMap<string, string> = derivedMovedRefs

/**
 * The gap-fix rows, for Spec Health. Ordinary fields in every other respect.
 *
 * Taken from the MERGED list so the sidecar is already on them — `structural`
 * marks the two parent links, and it lives in spec/extensions.json `fields`
 * now rather than inline on a new_fields row.
 */
export const newFields: FieldSpec[] = mergedFields.filter(
  (f) => f.origin === NEW_FIELD_ORIGIN
)

/**
 * Placements that would put two different fields on one module under one
 * api_name. Enforced in PostgreSQL now — uq_field_placements_qname — so this
 * stays empty; it is kept because a generated file could still be stale.
 */
export const splitErrors: string[] = []

specRefErrors.push(...splitErrors)

// ------------------------------------------------------------- the index

const definitionsByAlias = new Map<string, FieldSpec[]>()
for (const f of fields) {
  definitionsByAlias.set(f.ref, [...(definitionsByAlias.get(f.ref) ?? []), f])
}

export const duplicateApiNames: DuplicateApiName[] = [...definitionsByAlias.entries()]
  .filter(([, defs]) => defs.length > 1)
  .map(([, defs]) => ({
    module: defs[0].module,
    api_name: defs[0].api_name,
    sections: defs.map((f) => f.section),
    places: defs.map((f) => `${f.section} #${f.register_order ?? f.order}`),
  }))

const ambiguousAliases = new Set(duplicateApiNames.map((d) => `${d.module}.${d.api_name}`))

/** True when `api_name` is defined in more than one section of `module`. */
export function isAmbiguous(module: string, apiName: string): boolean {
  return ambiguousAliases.has(`${module}.${apiName}`)
}

/** The sections of `module` that define `api_name`. Empty when none do. */
export function sectionsDefining(module: string, apiName: string): string[] {
  return (definitionsByAlias.get(`${module}.${apiName}`) ?? []).map((f) => f.section)
}

/** Every field, keyed on module.section.api_name. Always complete. */
const byQref = new Map(fields.map((f) => [f.qref, f]))

/** Only fields whose api_name is unique in their module. The alias index. */
const byRef = new Map(fields.filter((f) => !ambiguousAliases.has(f.ref)).map((f) => [f.ref, f]))

const byModule = new Map<string, FieldSpec[]>()
for (const f of fields) {
  const list = byModule.get(f.module)
  if (list) list.push(f)
  else byModule.set(f.module, [f])
}
for (const list of byModule.values()) list.sort((a, b) => a.order - b.order)

/** Sidecar keys that name a field which no longer exists after a regenerate. */
export const orphanedExtensions = extensionKeys.filter((ref) => !refExists(ref))

export const modules = [...byModule.keys()]

/**
 * Resolve a field reference in either form.
 *
 * A qualified ref always resolves. A plain alias resolves only when the name is
 * unique in its module; for a duplicated one this returns undefined rather than
 * picking a definition, which is the whole point of the containment.
 */
export function fieldByRef(ref: string): FieldSpec | undefined {
  const hit = byQref.get(ref) ?? byRef.get(ref)
  if (hit) return hit
  // The split moved the field this ref was written against. Rather than rewrite
  // 8 sidecar keys, a list_views column and four child_spec column refs by hand
  // — and have the next person wonder why a Leads child list points at Deals —
  // the old ref keeps resolving and Spec Health lists every one of them.
  const moved = movedRefs.get(ref)
  return moved ? (byQref.get(moved) ?? byRef.get(moved)) : undefined
}

/** Whether a ref names a field at all, qualified or not, ambiguous or not. */
export function refExists(ref: string): boolean {
  if (byQref.has(ref) || byRef.has(ref) || movedRefs.has(ref)) return true
  const parsed = parseRef(ref)
  return parsed ? sectionsDefining(parsed.module, parsed.api_name).length > 0 : false
}

/** Every definition of an api_name in a module — one entry unless duplicated. */
export function fieldsNamed(module: string, apiName: string): FieldSpec[] {
  return definitionsByAlias.get(`${module}.${apiName}`) ?? []
}

/** One definition, named exactly. The only safe accessor for a duplicated name. */
export function fieldAt(module: string, section: string, apiName: string): FieldSpec | undefined {
  return byQref.get(`${module}.${section}.${apiName}`)
}

export function fieldsOf(module: string): FieldSpec[] {
  return byModule.get(module) ?? []
}

/**
 * The single field of a module with this api_name.
 *
 * Undefined for a duplicated name — callers that only need to know whether the
 * register carries the name at all should use fieldsNamed() instead, so a
 * duplicate is not mistaken for an unknown field.
 */
export function fieldOf(module: string, apiName: string): FieldSpec | undefined {
  return byRef.get(`${module}.${apiName}`)
}

/** api_names of one module — the namespace every expression resolves against. */
export function apiNamesOf(module: string): Set<string> {
  return new Set(fieldsOf(module).map((f) => f.api_name))
}

export function fieldsFor(module: string, section: string): FieldSpec[] {
  return fieldsOf(module).filter((f) => f.section === section)
}

/**
 * Sections in the register's own order. `order` is contiguous per section in
 * every module, so first-appearance order is the register's order.
 */
export function sectionsFor(module: string): string[] {
  const seen: string[] = []
  for (const f of fieldsOf(module)) {
    if (!seen.includes(f.section)) seen.push(f.section)
  }
  return seen
}

export function optionsFor(picklistKey: string | null | undefined): PicklistOption[] {
  if (!picklistKey) return []
  const options = picklists[picklistKey] ?? []
  return options.filter((o) => o.active).sort((a, b) => a.sort - b.sort)
}

/** The options THIS field offers — its picklist minus the sidecar's exclude_options. */
export function fieldOptions(field: Pick<FieldSpec, 'picklist' | 'exclude_options'>): PicklistOption[] {
  const options = optionsFor(field.picklist)
  const excluded = field.exclude_options
  return excluded?.length ? options.filter((o) => !excluded.includes(o.key)) : options
}

/**
 * Resolve a stored value or an expression literal to a picklist key.
 *
 * The register writes conditions against labels (`deal_source ==
 * 'Partner-sourced'`) while the controls store keys (`PARTNER_SOURCED`), so
 * both sides of a comparison go through here and meet in the middle. An
 * unmatched value is returned unchanged rather than nulled — a picklist that
 * has gained a value in the data but not in picklists.json should still
 * compare, not silently stop matching.
 */
export function toPicklistKey(picklistKey: string | null | undefined, value: unknown): unknown {
  if (typeof value !== 'string' || !picklistKey) return value
  const options = picklists[picklistKey]
  if (!options) return value
  const hit = options.find(
    (o) => o.key === value || o.label === value || o.label.toLowerCase() === value.toLowerCase()
  )
  return hit ? hit.key : value
}

export function labelForValue(picklistKey: string | null | undefined, value: unknown): string {
  if (typeof value !== 'string') return ''
  if (!picklistKey) return value
  const hit = (picklists[picklistKey] ?? []).find((o) => o.key === value || o.label === value)
  return hit ? hit.label : value
}

/** Case-folded with -, _ and space removed. Same rule as evaluate.ts slug(). */
function slug(v: string): string {
  return v.toLowerCase().replace(/[\s\-_]+/g, '')
}

/**
 * A tolerant form of toPicklistKey, used only when loading seed data.
 *
 * The seed sheets and the register sheets disagree about how a picklist value
 * is written: accounts.account_types holds labels ("End Client") while
 * contacts.contact_role holds only the code prefix of the key ("DECM" for
 * DECM_DECISION_MAKER). Both resolve here so the controls in the form engine
 * see keys and nothing else. A value that matches nothing is returned unchanged
 * and reported by seedMismatches() — never silently blanked.
 *
 * A number is coerced to a string before matching, so leads.project_stage
 * (seeded as the bare integer 3) resolves through the same code-prefix rule as
 * "DECM" below, matching picklist key "3_PRESCRIPTION".
 */
export function resolvePicklistValue(
  picklistKey: string | null | undefined,
  value: unknown
): { key: unknown; resolved: boolean } {
  if ((typeof value !== 'string' && typeof value !== 'number') || !picklistKey) {
    return { key: value, resolved: true }
  }
  const options = picklists[picklistKey]
  if (!options) return { key: value, resolved: true }
  const str = String(value)

  const hit =
    options.find((o) => o.key === str || o.label === str) ??
    options.find((o) => slug(o.key) === slug(str) || slug(o.label) === slug(str)) ??
    // "DECM" for DECM_DECISION_MAKER, or "3" for "3_PRESCRIPTION" — the
    // register's own conventions name these by a leading code, so the seed is
    // using just that code as the whole value.
    options.find((o) => slug(o.key.split('_')[0]) === slug(str))

  return hit ? { key: hit.key, resolved: true } : { key: value, resolved: false }
}

// ------------------------------------------------------------- list views

const listViews = extensionsFile.list_views ?? {}

export interface ListView extends ListViewSpec {
  /** columns resolved against fields.json, in order. Unknown refs dropped. */
  fields: FieldSpec[]
}

/**
 * The column set for a module's list screen. Never hardcoded in a component —
 * CLAUDE.md rule 3 applies to lists exactly as it does to forms.
 */
export function listViewFor(module: string): ListView | undefined {
  const spec = listViews[module]
  if (!spec || typeof spec === 'string') return undefined
  return {
    ...spec,
    fields: spec.columns.map(fieldByRef).filter((f): f is FieldSpec => Boolean(f)),
  }
}

for (const [module, spec] of Object.entries(listViews)) {
  if (module.startsWith('$') || typeof spec === 'string') continue
  for (const ref of spec.columns) checkRef(ref, `spec/extensions.json list_views.${module}`)
}

/** Column refs in list_views that name no field in fields.json. */
export const orphanedListColumns = Object.entries(listViews).flatMap(([module, spec]) =>
  typeof spec === 'string'
    ? []
    : spec.columns.filter((ref) => !refExists(ref)).map((ref) => ({ module, ref }))
)

// ------------------------------------------------------- moved-ref debt

export interface MovedRefUsage {
  /** The ref as written — `leads.total_value_tcv`. */
  ref: string
  /** Where it resolves now — `opportunities.total_value_tcv`. */
  now: string
  /** The sidecar block that still writes it the old way. */
  where: string
}

/**
 * Places the sidecar still names a field by the module the register filed it
 * under, which the split has since moved.
 *
 * Each of these resolves — fieldByRef falls through movedRefs — so nothing is
 * broken. They are listed anyway. A silent rewrite would leave the next person
 * reading `leads.milestone_—_planned_date` inside a child list that now lives on
 * Deals, with nothing on any screen to explain it.
 */
export const movedRefUsages: MovedRefUsage[] = (() => {
  const out: MovedRefUsage[] = []
  const seen = new Set<string>()
  const add = (ref: string, where: string) => {
    const now = movedRefs.get(ref)
    if (!now) return
    const key = `${ref}::${where}`
    if (seen.has(key)) return
    seen.add(key)
    out.push({ ref, now, where })
  }

  for (const key of extensionKeys) add(key, 'extensions.json fields')

  for (const [module, spec] of Object.entries(listViews)) {
    if (module.startsWith('$') || typeof spec === 'string') continue
    for (const ref of spec.columns) add(ref, `extensions.json list_views.${module}`)
  }

  for (const f of fields) {
    for (const column of f.child_spec?.columns ?? []) {
      if (typeof column === 'string') add(column, `child_spec of ${f.ref}`)
    }
  }

  return out
})()

// ------------------------------------------------------------------ partners

/**
 * Which account types put an organisation on the Partners list.
 *
 * A partner is not a separate kind of organisation — it is an account whose
 * account_type includes one of these. e& Enterprise is one account record that
 * appears on both the Accounts screen and the Partners screen; there is no
 * second org row anywhere. The register never states the set, so it is declared
 * in the sidecar and the question is on the Spec Health page.
 */
export const partnerAccountTypes: string[] = extensionsFile.partner_roster?.account_types ?? []

export function isPartnerAccount(account: Record<string, unknown> | undefined): boolean {
  const types = account?.account_type
  if (!Array.isArray(types)) return false
  return types.some((t) => partnerAccountTypes.includes(String(t)))
}

/** Playbook §6.2 numbers — exclusivity window, acknowledgement SLA, field sets. */
export const partnerRegistration = extensionsFile.partner_registration

/**
 * Which status ends a pursuit, for the Kanban board's terminal columns. Keys,
 * not labels, and declared rather than written into the board — see the note
 * on the block itself for why POC/Pilot Deal and On Hold are not in it.
 */
export const kanbanBoard = extensionsFile.kanban

/**
 * The fields of a declared field set, resolved and ordered as the sidecar names
 * them. A name the register no longer carries is dropped and reported, exactly
 * as an unresolvable list_views column is.
 */
export function fieldsInSet(set: FieldSetSpec): FieldSpec[] {
  return set.fields
    .map((name) => fieldsOf(set.module).find((f) => f.section === set.section && f.api_name === name))
    .filter((f): f is FieldSpec => Boolean(f))
}

/** Field-set entries naming a field the register does not carry in that section. */
export const orphanedFieldSetNames = [
  partnerRegistration?.capture_fields,
  partnerRegistration?.adjudication_criteria,
  partnerRegistration?.adjudication_outcome,
]
  .filter((set): set is FieldSetSpec => Boolean(set))
  .flatMap((set) =>
    set.fields
      .filter((name) => !fieldsOf(set.module).some((f) => f.section === set.section && f.api_name === name))
      .map((name) => ({ module: set.module, section: set.section, api_name: name }))
  )

/**
 * Fields CreateNewDialog shows beyond a module's first section — see
 * quick_create in spec/extensions.json. A '+ Create new' shortcut otherwise
 * shows only enough to make the record selectable; these are the few fields
 * outside that first section important enough to ask for on day one.
 */
export function quickCreateExtraFieldsFor(module: string): FieldSpec[] {
  const names = extensionsFile.quick_create?.extra_fields?.[module] ?? []
  return names.map((name) => fieldOf(module, name)).filter((f): f is FieldSpec => Boolean(f))
}

/** Gaps recorded by hand in the sidecar, shown beside the generated ones. */
export const openQuestions: SpecNote[] = extensionsFile.open_questions?.rows ?? []

/** Things the register's chosen types cannot express. Stated, not to be fixed. */
export const precisionLimits: SpecNote[] = extensionsFile.precision_limits?.rows ?? []

// ------------------------------------------------------- seed normalisation

const seedNormalisation = extensionsFile.seed_normalisation ?? {}

export function seedNormalisationFor(collection: string): SeedNormalisationSpec | undefined {
  const spec = seedNormalisation[collection]
  return typeof spec === 'string' ? undefined : spec
}

export const normalisedCollections = Object.keys(seedNormalisation).filter((k) => !k.startsWith('$'))

/**
 * The module whose fields describe the records in a store collection.
 *
 * Distinct from collectionFor, which goes the other way from a lookup_target.
 * The two cannot be derived from each other: a lookup_target of `user` reaches
 * the `users` collection, but users are described by the `administration`
 * module, and both `bids` and `pocs` are described by `bids_pocs`.
 */
const MODULE_OF_COLLECTION: Record<string, string> = {
  accounts: 'accounts',
  contacts: 'contacts',
  leads: 'leads',
  // The collection does not exist yet — the store, the seed and the screens are
  // a later step. The mapping is here because the MODULE does exist as of the
  // split, and a spec lookup should not have a hole in it.
  opportunities: 'opportunities',
  deals: 'deals',
  quotes: 'quotes',
  products: 'products',
  users: 'administration',
  registrations: 'partners',
  // Both live on the Partners sheet, in different sections of it — a
  // registration is DEAL REGISTRATION, an adjudication is CONFLICT ADJUDICATION.
  conflicts: 'partners',
  bids: 'bids_pocs',
  pocs: 'bids_pocs',
}

export function moduleForCollection(collection: string): string | undefined {
  return MODULE_OF_COLLECTION[collection]
}

/**
 * A record with its autonumber field filled in from the record id.
 *
 * The register gives accounts an `account_id` autonumber and contacts a
 * `contact_id`, but the store keys every collection on `id`. Rather than teach
 * each screen the name of its own key field, the autonumber is filled from
 * whatever the register happens to call it.
 */
export function withRecordId(module: string, record: Record<string, unknown>): Record<string, unknown> {
  const id = idOf(record)
  if (!id) return record
  const out = { ...record }
  for (const f of fieldsOf(module)) {
    if (f.type === 'autonumber' && !out[f.api_name]) out[f.api_name] = id
  }
  return out
}

/**
 * lookup_target names an entity in the singular; the store keys collections in
 * the plural. Everything else about a lookup is spec-driven, but this mapping
 * has to exist somewhere because the register and the seed files disagree.
 */
const COLLECTION_OF: Record<string, string> = {
  account: 'accounts',
  user: 'users',
  contact: 'contacts',
  product: 'products',
  lead: 'leads',
  // Not the naive +s pluralisation the fallback below would produce
  // ("opportunitys") — deals.parent_opportunity names this target and needs it
  // to resolve correctly the moment that field is rendered.
  opportunity: 'opportunities',
  deal: 'deals',
  quote: 'quotes',
  gate: 'gates',
  bid: 'bids',
  poc: 'pocs',
  deal_registration: 'registrations',
  // Hyphenated because it is the API path: /api/pursuit-groups.
  pursuit_group: 'pursuit-groups',
  region: 'regions',
  support_tier: 'supportTiers',
  approval: 'approvals',
  document: 'documents',
  stage_criteria: 'stageCriteria',
  competitor: 'competitors',
}

export function collectionFor(lookupTarget: string | null | undefined): string | undefined {
  if (!lookupTarget) return undefined
  return COLLECTION_OF[lookupTarget] ?? `${lookupTarget}s`
}

/**
 * The field used as the human-readable label of a looked-up record. Seed
 * records do not agree on a name field, so this walks the likely ones.
 */
export function displayNameOf(record: Record<string, unknown>): string {
  for (const key of ['account_name', 'name', 'full_name', 'opportunity_name', 'project_name', 'item_name', 'code', 'tier', 'level']) {
    const v = record[key]
    if (typeof v === 'string' && v) return v
  }
  const id = record.id ?? record.sku ?? record.code
  return typeof id === 'string' ? id : ''
}

export function idOf(record: Record<string, unknown>): string {
  const key = record.id ?? record.sku ?? record.code ?? record.level ?? record.tier
  return typeof key === 'string' ? key : ''
}
