import { fieldsOf, parentLinkOf, parentModuleOf } from './index'
import type { Values } from './conditions'

/**
 * The effective record: what a pipeline record's values ARE, as opposed to what
 * it stores.
 *
 * An Opportunity does not store its End Client and a Deal does not store its
 * Segment. Those are identity, they belong to the Lead the pursuit started as,
 * and spec/module_split.json marks them read_through. Two conversions means two
 * chances for the same value to be copied and then edited on one side only, so
 * nothing is copied: the value is READ THROUGH the parent link every time it is
 * displayed, validated or fed to a formula.
 *
 * This resolver is the one place that walk happens. Everything downstream — the
 * criteria engine, the formula engine, validateForTransition, the form — is
 * handed the merged values and does not need to know a parent exists.
 *
 * IT DOES NOT FETCH. CLAUDE.md rule 2 says every read goes through the API
 * client, so the parent records are fetched by useResolvedRecord and passed in
 * here. That also keeps this function pure and the merge rule testable without
 * a network or a store.
 */

export interface InheritedSource {
  /** The module the value actually lives on — `leads`, for a Deal's Segment. */
  module: string
  /** That record's id, for the "from LEAD-00118" affordance. */
  id: string
}

export interface ResolvedRecord {
  /** The record's own values with inherited ones merged over the top. */
  values: Values
  /** api_names whose value came from an ancestor rather than from this record. */
  inherited: Set<string>
  /** api_name -> the record the value lives on. Only for inherited names. */
  sources: Record<string, InheritedSource>
  /** The ancestors walked, nearest first. Empty for a Lead. */
  chain: InheritedSource[]
  /**
   * read_through api_names that could not be resolved, because the CHAIN is
   * broken — the parent link is empty, or the parent record was not supplied.
   *
   * Not the same as an empty value. A field that reads "—" because nobody
   * entered an End Client on the Lead is inherited and fine; a field that reads
   * "—" because this record names no Lead at all is a different problem, and the
   * screen must not show them the same way. Only the second is listed here.
   */
  unresolved: string[]
  /** Why, when `unresolved` is non-empty. */
  brokenLink?: {
    module: string
    /** The lookup field that should hold the parent's id. */
    via: string
    reason: 'no-link' | 'parent-not-loaded'
  }
}

/** Parent records the caller has already fetched, keyed by module. */
export type ParentRecords = Record<string, Values | undefined>

function idOf(record: Values | undefined): string {
  const id = record?.id
  return typeof id === 'string' ? id : ''
}

/**
 * The next record to fetch when resolving `module`, or undefined at the root of
 * the chain (a Lead) or when the link is empty.
 *
 * Exposed so useResolvedRecord can walk the chain one query at a time without
 * duplicating the rule about which field holds which link.
 */
export function parentRequestFor(
  module: string,
  record: Values | undefined
): { module: string; id: string } | undefined {
  const parent = parentModuleOf(module)
  const via = parentLinkOf(module)
  if (!parent || !via || !record) return undefined
  const id = record[via]
  return typeof id === 'string' && id ? { module: parent, id } : undefined
}

/**
 * Merge a record with everything it reads through its parents.
 *
 * Recursive, because the chain is two links long and the middle one inherits
 * too: a Deal's Segment is read through the Opportunity, which does not store it
 * either — it reads it through the Lead. Resolving the parent's EFFECTIVE record
 * first is what makes the far end of the chain reachable, and it is why `sources`
 * names the Lead rather than the Opportunity for that field.
 */
export function resolveRecord(
  module: string,
  record: Values | undefined,
  parents: ParentRecords = {}
): ResolvedRecord {
  const own: Values = { ...(record ?? {}) }
  const readThrough = fieldsOf(module).filter((f) => f.value_mode === 'read_through')

  if (!readThrough.length) {
    return { values: own, inherited: new Set(), sources: {}, chain: [], unresolved: [] }
  }

  const parentModule = parentModuleOf(module)
  const via = parentLinkOf(module) ?? ''
  const parentRecord = parentModule ? parents[parentModule] : undefined
  const linked = parentRequestFor(module, record)

  if (!parentModule || !parentRecord) {
    return {
      values: own,
      inherited: new Set(),
      sources: {},
      chain: [],
      unresolved: readThrough.map((f) => f.api_name),
      brokenLink: {
        module: parentModule ?? '',
        via,
        reason: linked ? 'parent-not-loaded' : 'no-link',
      },
    }
  }

  const parent = resolveRecord(parentModule, parentRecord, parents)
  const here: InheritedSource = { module: parentModule, id: idOf(parentRecord) || (linked?.id ?? '') }

  const values: Values = { ...own }
  const inherited = new Set<string>()
  const sources: Record<string, InheritedSource> = {}
  // Empty by construction below this point: the chain resolved, so nothing is
  // unresolved. Kept as a field so the shape is the same on both branches.
  const unresolved: string[] = []

  for (const field of readThrough) {
    const name = field.api_name

    // Inherited whether or not the ancestor HAS a value. An empty End Client on
    // the Lead is an empty End Client here — the field's home is still the Lead,
    // and it still reads read-only with a link there. Only a broken CHAIN counts
    // as unresolved; treating a blank as unresolved would tell the user their
    // record is not linked when it is, which is the more alarming of the two
    // messages and the wrong one.
    //
    // The parent wins even where this record holds a stale copy of the same
    // api_name — a Deal converted before the split stored its own end_client.
    // Preferring the stored one would be preferring the drift.
    values[name] = parent.values[name] ?? null
    inherited.add(name)

    // If the PARENT inherited it too, the value lives further up. Name the
    // record it actually lives on, so the affordance reads "from LEAD-00118"
    // rather than pointing at a middle record that is only passing it along.
    sources[name] = parent.sources[name] ?? here
  }

  return {
    values,
    inherited,
    sources,
    chain: [here, ...parent.chain],
    unresolved,
  }
}

/**
 * A record with nothing inherited. For a module the split gives no parent —
 * every non-pipeline module, and Leads, which is the root of the chain.
 */
export function unresolved(record: Values | undefined): ResolvedRecord {
  return {
    values: { ...(record ?? {}) },
    inherited: new Set(),
    sources: {},
    chain: [],
    unresolved: [],
  }
}
