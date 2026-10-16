import { specSource } from './source'

/**
 * Fields whose choices follow another field — Region -> Country -> State.
 *
 * Release 1.1 (decided 6 Oct 2026), Zoho's Map Dependency Fields. Per module,
 * a child picklist offers only the choices mapped to its parent's value:
 * Region MEA offers the MEA countries, Country UAE offers the seven emirates.
 * The maps come with the published register (GET /api/spec, or the built-in
 * spec/dependencies.json) and are edited in Setup from Phase 2.
 *
 * THE SAME RULES THE SERVER APPLIES (backend/app/field_dependencies.py):
 *   - a child with nothing to offer — parent empty, or a parent mapped to no
 *     choices — is never required (offersChoices);
 *   - a child choice its parent does not offer is refused on save.
 *
 * SEVERAL CHOICES (Products, 13 Oct 2026; Accounts in Release 1.2): a product's
 * and an Account's Segment -> Segment Category -> Subsegment are multi-choice. A
 * child then offers the choices of EVERY parent choice held, and a parent choice
 * taken away removes only the child choices that came with it.
 */

export interface FieldDependency {
  /** The api_name of the field this one follows. */
  parent: string
  /** Parent choice -> the child choices it offers. */
  map: Record<string, string[]>
}

type DependencyMap = Record<string, Record<string, FieldDependency>>

function dependencies(): DependencyMap {
  const raw = specSource.dependencies
  return raw && typeof raw === 'object' ? (raw as DependencyMap) : {}
}

/** The field `apiName` follows on `module`, or null when its choices are its own. */
export function dependencyOf(module: string, apiName: string): FieldDependency | null {
  return dependencies()[module]?.[apiName] ?? null
}

/** Fields on `module` whose choices follow `parent` — cleared when it changes. */
export function childrenOf(module: string, parent: string): string[] {
  return Object.entries(dependencies()[module] ?? {})
    .filter(([, dep]) => dep.parent === parent)
    .map(([child]) => child)
}

function blank(value: unknown): boolean {
  return value === null || value === undefined || value === '' || (Array.isArray(value) && value.length === 0)
}

/**
 * The choices a dependent field offers given the record's values: null when no
 * dependency governs it (its whole list), [] when its parent is empty.
 */
export function allowedChoices(module: string, apiName: string, values: Record<string, unknown>): string[] | null {
  const dep = dependencyOf(module, apiName)
  if (!dep) return null
  const parentValue = values[dep.parent]
  if (blank(parentValue)) return []
  if (!Array.isArray(parentValue)) return dep.map[String(parentValue)] ?? []
  const out: string[] = []
  for (const parent of parentValue) {
    for (const choice of dep.map[String(parent)] ?? []) {
      if (!out.includes(choice)) out.push(choice)
    }
  }
  return out
}

/** Does this field have anything to choose from right now? */
export function offersChoices(module: string, apiName: string, values: Record<string, unknown>): boolean {
  const allowed = allowedChoices(module, apiName, values)
  return allowed === null || allowed.length > 0
}

/**
 * Can this field be picked from ANY parent choice? (14 Oct 2026: "I could not
 * find Vietnam".) True for a field whose parent follows nothing itself —
 * Country under Region — so a person who does not know a country's region
 * still finds it; picking it fills the Region in (fillParents). A State stays
 * inside its Country: its parent follows Region, and a state name means
 * nothing without its country.
 */
export function findableAcrossParents(module: string, apiName: string): boolean {
  const dep = dependencyOf(module, apiName)
  return dep !== null && dependencyOf(module, dep.parent) === null
}

/** The parent choice that offers `value` — Vietnam's Region is APAC. */
export function parentChoiceFor(module: string, apiName: string, value: unknown): string | null {
  const dep = dependencyOf(module, apiName)
  if (!dep || blank(value)) return null
  const wanted = String(value)
  const hit = Object.entries(dep.map).find(([, choices]) => choices.includes(wanted))
  return hit ? hit[0] : null
}

/** Every choice any parent offers, for a field that is findable across parents. */
export function choicesOfEveryParent(module: string, apiName: string): Set<string> {
  const dep = dependencyOf(module, apiName)
  return new Set(dep ? Object.values(dep.map).flat() : [])
}

/**
 * After `changed` takes a value its parent does not offer, set the parent to
 * the choice that does — picking Vietnam with Region India (or none) makes the
 * Region APAC. Only for a field findable across parents; returns `values`
 * itself when nothing had to change. Run BEFORE clearOrphanedChoices, which
 * then empties whatever followed the old value (the State).
 */
export function fillParents(
  module: string | undefined,
  values: Record<string, unknown>,
  changed: string
): Record<string, unknown> {
  if (!module || !findableAcrossParents(module, changed)) return values
  const dep = dependencyOf(module, changed)
  const value = values[changed]
  // One choice only: a several-choice field has no single parent to fill in.
  if (!dep || blank(value) || Array.isArray(value)) return values
  if ((allowedChoices(module, changed, values) ?? []).includes(String(value))) return values
  const parent = parentChoiceFor(module, changed, value)
  return parent ? { ...values, [dep.parent]: parent } : values
}

/**
 * After `changed` takes a new value, empty every field that follows it and no
 * longer holds a choice it offers — and so on down the chain: a new Region
 * empties a Country outside it, and that empties the State. Zoho does the
 * same. Returns `values` itself when nothing had to change.
 */
export function clearOrphanedChoices(
  module: string | undefined,
  values: Record<string, unknown>,
  changed: string
): Record<string, unknown> {
  if (!module) return values
  let out = values
  for (const child of childrenOf(module, changed)) {
    const current = out[child]
    if (blank(current)) continue
    const allowed = allowedChoices(module, child, out) ?? []
    if (Array.isArray(current)) {
      // Several choices: keep the ones still on offer, drop the rest.
      const kept = current.filter((v) => allowed.includes(String(v)))
      if (kept.length === current.length) continue
      out = clearOrphanedChoices(module, { ...out, [child]: kept }, child)
      continue
    }
    if (allowed.includes(String(current))) continue
    out = clearOrphanedChoices(module, { ...out, [child]: null }, child)
  }
  return out
}
