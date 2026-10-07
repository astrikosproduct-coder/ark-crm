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
  return dep.map[String(parentValue)] ?? []
}

/** Does this field have anything to choose from right now? */
export function offersChoices(module: string, apiName: string, values: Record<string, unknown>): boolean {
  const allowed = allowedChoices(module, apiName, values)
  return allowed === null || allowed.length > 0
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
    if (allowed.includes(String(current))) continue
    out = clearOrphanedChoices(module, { ...out, [child]: null }, child)
  }
  return out
}
