import { fieldsOf, toPicklistKey } from './index'
import { nextId } from '@/lib/idGen'
import { SEED_ACTOR_ID, moduleForStage, stageKeyOf, stageNumberOf } from '@/lib/pipeline'

type Item = Record<string, unknown>

const OPPORTUNITY_SCHEME = { prefix: 'OPP', pad: 5 }
const CONVERSION_SCHEME = { prefix: 'CONV', pad: 4 }

/** Where a frozen Lead lands — the last stage the Leads module still owns. */
const FROZEN_LEAD_STAGE = 3

/**
 * api_names an Opportunity reads through its parent rather than stores. Copying
 * one of these onto the derived row would be exactly the bug carry-forward-by-
 * reference exists to prevent — a second copy of the End Client that the real
 * one can drift away from.
 */
function readThroughApiNames(module: string): string[] {
  return fieldsOf(module)
    .filter((f) => f.value_mode === 'read_through')
    .map((f) => f.api_name)
}

/** Normalize values after a Lead row crosses into its new module. */
function normalizeOpportunityRecord(record: Item): Item {
  const out = { ...record }

  for (const field of fieldsOf('opportunities')) {
    const value = out[field.api_name]
    if (value === null || value === undefined || value === '') continue
    if (field.type === 'multiselect' && Array.isArray(value)) {
      out[field.api_name] = value.map((entry) => toPicklistKey(field.picklist, entry))
    } else if (field.type === 'picklist') {
      out[field.api_name] = toPicklistKey(field.picklist, value)
    }
  }

  return out
}

/**
 * Reassigns any Lead still sitting on the Opportunities side of the 14-stage
 * split — LEAD-00119 at Stage 4 and LEAD-00122 at Stage 6 in the shipped seed,
 * and potentially others in an older localStorage snapshot.
 *
 * There is no conversion UI yet (that is the next step), so this is not a
 * simulation of one: it is the data-layer half of the split itself, applied to
 * records that predate spec/module_split.json. A Lead the split says belongs to
 * Opportunities becomes a frozen, read-only Lead at Stage 3 plus a new
 * Opportunity record that opens at the Lead's own former stage — carrying
 * every field that is not read-through, because read-through fields have
 * nowhere to be copied TO; they are resolved from the frozen Lead by
 * useResolvedRecord instead. A `conversions` row records what happened, with
 * actor "seed" rather than SEED_ACTOR_ID, so it reads honestly as something
 * that happened at load time and not a decision a person made.
 *
 * ONE function, called from two places, deliberately:
 *   - buildSeedData() runs it on a fresh seed, so a first-ever load already has
 *     the Opportunities module populated.
 *   - useDataStore's migrate() runs it on a RETURNING browser's persisted
 *     leads, which may hold edits the static seed file does not — this
 *     transforms the actual data handed to it, not a re-derivation from
 *     spec/seed/leads.json.
 *
 * Idempotent: a Lead already CONVERTED is left alone, so running this twice —
 * or migrating data buildSeedData() already derived — changes nothing the
 * second time. Returns the SAME object, untouched, when there is nothing to
 * do, which matters to callers that use presence of a key to decide whether to
 * prefer persisted data over a fresh reseed — see the migrate() comment in
 * useDataStore.ts.
 */
export function deriveOpportunitiesFromLeads(data: Record<string, unknown>): Record<string, unknown> {
  const leads = Array.isArray(data.leads) ? [...(data.leads as Item[])] : []
  const opportunities = Array.isArray(data.opportunities) ? [...(data.opportunities as Item[])] : []
  const conversions = Array.isArray(data.conversions) ? [...(data.conversions as Item[])] : []

  const readThrough = readThroughApiNames('opportunities')
  const now = new Date().toISOString()
  let changed = false

  const nextLeads = leads.map((lead) => {
    const leadId = typeof lead.id === 'string' ? lead.id : undefined
    if (!leadId || lead.lead_status === 'CONVERTED') return lead

    const stageNum = stageNumberOf(lead.project_stage)
    if (stageNum === null || moduleForStage(stageNum) !== 'opportunities') return lead

    changed = true

    // Everything the Lead currently holds becomes the Opportunity's starting
    // point — including its own project_stage and probability_pct, which is
    // exactly right: the Opportunity opens at whatever stage this Lead had
    // already reached, not at Stage 4. Read-through fields are stripped
    // because the Opportunity does not store them at all; they resolve
    // through parent_lead from here on.
    const opp: Item = normalizeOpportunityRecord(lead)
    delete opp.id
    for (const key of readThrough) delete opp[key]
    opp.parent_lead = leadId
    opp.lead_status = 'OPEN'
    opp.id = nextId(OPPORTUNITY_SCHEME, opportunities)
    opportunities.push(opp)

    conversions.push({
      id: nextId(CONVERSION_SCHEME, conversions),
      source_module: 'leads',
      source_id: leadId,
      target_module: 'opportunities',
      target_id: opp.id,
      actor: 'seed',
      timestamp: now,
      copied_fields: Object.keys(opp).filter(
        (k) => k !== 'id' && k !== 'parent_lead' && k !== 'lead_status'
      ),
      note:
        'Synthetic — this Lead was seeded on the far side of the 14-stage-review split, ' +
        'not converted by a user. See spec/module_split.json and lib/spec/pipelineSeed.ts.',
    })

    return {
      ...lead,
      project_stage: stageKeyOf(FROZEN_LEAD_STAGE) ?? lead.project_stage,
      lead_status: 'CONVERTED',
      modified_date: now,
      modified_by: SEED_ACTOR_ID,
    }
  })

  // Nothing to do: return the SAME object rather than a same-content clone, so
  // a caller can tell "nothing changed" from "changed to the same shape" and
  // let a fresher value win where that distinction matters.
  if (!changed) return data

  return { ...data, leads: nextLeads, opportunities, conversions }
}
