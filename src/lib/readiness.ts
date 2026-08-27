import { fieldOf } from '@/lib/spec'
import { scopeOver, type Values } from '@/lib/spec/conditions'
import { evaluateBool } from '@/lib/spec/evaluate'
import { identifiersOf, parse } from '@/lib/spec/parser'
import {
  criteriaFor,
  gateForAnchor,
  type Criterion,
  type Gate,
} from '@/lib/pipeline'
import type { FieldSpec } from '@/types/field'

export type CheckStatus = 'pass' | 'fail' | 'warn'

export interface ReadinessItem {
  key: string
  code?: string
  label: string
  status: CheckStatus
  detail?: string
  enforcement?: 'blocking' | 'advisory'
  /** Present when the item names exactly one field of the module, so the panel
   * can offer "go to field" — never guessed, only when the source expression
   * resolves to one real field unambiguously. */
  field?: FieldSpec
}

export interface ReadinessLayer {
  /** No 'mandatory': layer 1 is not shown in this panel — see computeReadiness. */
  key: 'exit' | 'entry' | 'gate'
  label: string
  description: string
  items: ReadinessItem[]
}

export interface Readiness {
  from: number
  to: number
  layers: ReadinessLayer[]
}

/**
 * A criterion's `source` is written for a human, not this parser — some rows
 * are valid expressions ("demo_agreed == true"), many are prose ("budget_estimate
 * and probable_award_date", "contact_roles has DECM or RECM"). Anything that
 * fails to parse, or whose evaluation is attestation/manual/signature, reads as
 * a manual check rather than a fabricated pass or fail — the same fail-open
 * posture the rest of the spec engine takes on a broken expression.
 */
function evaluateCriterionLike(
  module: string,
  values: Values,
  source: string | null,
  evaluation: string
): { status: CheckStatus; detail?: string; field?: FieldSpec } {
  if (evaluation === 'attestation' || evaluation === 'manual' || evaluation === 'signature') {
    return { status: 'warn', detail: 'Attested by a person — not evaluated automatically here.' }
  }

  if (!source) {
    return { status: 'warn', detail: 'No machine-checkable source recorded in the register.' }
  }

  if (source.startsWith('gate:')) {
    return {
      status: 'warn',
      detail: 'Depends on a gate — see Gate status below; the Gates module is not built in this walkthrough.',
    }
  }

  try {
    const ast = parse(source)
    const result = evaluateBool(ast, scopeOver(module, values), source)
    const ids = identifiersOf(ast)
    const field = ids.map((n) => fieldOf(module, n)).find((f): f is FieldSpec => Boolean(f))
    if (result) return { status: 'pass', field }
    return { status: evaluation === 'automatic' || evaluation === 'semi_auto' ? 'fail' : 'warn', field }
  } catch {
    return { status: 'warn', detail: 'Not written as a checkable expression — read the criterion and confirm by hand.' }
  }
}

function criteriaLayer(
  key: 'exit' | 'entry',
  module: string,
  values: Values,
  stage: number,
  label: string,
  description: string
): ReadinessLayer {
  const rows = criteriaFor(stage, key)
  const items: ReadinessItem[] = rows.map((c) => {
    const evaluated = evaluateCriterionLike(module, values, c.source, c.evaluation)
    return {
      key: c.code,
      code: c.code,
      label: c.text,
      status: evaluated.status,
      detail: evaluated.detail,
      enforcement: c.enforcement,
      field: evaluated.field,
    }
  })
  return { key, label, description, items }
}

function gateLayer(to: number): ReadinessLayer {
  const gate = gateForAnchor(to)
  const items: ReadinessItem[] = gate
    ? [
        {
          key: gate.gate_type,
          label: gate.name,
          status: 'warn',
          detail: `${gate.items.length} checklist items, ${gate.passes_on} required to pass. The Gates module isn't built in this walkthrough, so this can't be verified here. ${gate.warning}`,
          enforcement: gate.enforcement,
        },
      ]
    : [
        {
          key: 'no-gate',
          label: 'No gate anchors this stage',
          status: 'pass',
        },
      ]
  return {
    key: 'gate',
    label: 'Gate status',
    description: `Gates anchored at entry to Stage ${to}.`,
    items,
  }
}

/**
 * Layers 2 to 4 of the four-layer transition check from CLAUDE.md: exit
 * criteria of the stage being left, entry criteria of the stage being entered,
 * gate status. Advisory only in this walkthrough — nothing here blocks the
 * Advance button; see AdvanceStageDialog.
 *
 * LAYER 1, MANDATORY FIELDS, IS DELIBERATELY NOT SHOWN HERE. It was removed
 * from the panel at review because it restated on the right of the screen what
 * the form on the left already says — every demanded field carries a red
 * asterisk, an inline error and a count above the Save button, and the register
 * demands so many fields per stage that the layer buried the three criteria
 * layers underneath a list nobody read.
 *
 * The rule itself is untouched: validateForTransition in lib/spec/validation.ts
 * is still the engine for layer 1 and still reports every blocker, and the Form
 * engine page still renders it. Nothing about what the register demands has
 * changed — only where a reviewer reads it.
 */
export function computeReadiness(module: string, values: Values, from: number, to: number): Readiness {
  return {
    from,
    to,
    layers: [
      criteriaLayer('exit', module, values, from, 'Exit criteria', `Leaving Stage ${from}.`),
      criteriaLayer('entry', module, values, to, 'Entry criteria', `Entering Stage ${to}.`),
      gateLayer(to),
    ],
  }
}

export function layerCounts(layer: ReadinessLayer): { pass: number; fail: number; warn: number } {
  let pass = 0
  let fail = 0
  let warn = 0
  for (const item of layer.items) {
    if (item.status === 'pass') pass++
    else if (item.status === 'fail') fail++
    else warn++
  }
  return { pass, fail, warn }
}

export type { Criterion, Gate }
