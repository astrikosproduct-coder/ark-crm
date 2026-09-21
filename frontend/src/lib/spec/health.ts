import { childSpecFor } from './childSpec'
import { computedGap, validateSpecExpressions } from './formula'
import {
  duplicateApiNames,
  fieldByRef,
  fields,
  movedRefUsages,
  newFields,
  openQuestions,
  orphanedExtensions,
  orphanedFieldSetNames,
  orphanedListColumns,
  precisionLimits,
  registerCorrections,
} from './index'
import type { FieldSpec } from '@/types/field'

export interface HealthRow {
  ref: string
  module: string
  api_name: string
  label: string
  type: string
  detail: string
}

export interface HealthGroup {
  id: string
  title: string
  /** What a reviewer is being asked to supply. */
  ask: string
  rows: HealthRow[]
}

/**
 * What a reviewer reads on the childlist row: either "no shape at all", or the
 * proposed columns and what they were derived from, so the correction can be
 * made against something concrete rather than against a blank.
 */
function childListDetail(f: FieldSpec): string {
  const spec = childSpecFor(f)
  if (!spec) return f.unexpressed ?? 'No child_spec'

  const columns = spec.columns.map((c) => c.field.label).join(', ')
  const basis = spec.basis ?? 'No basis recorded — add one to spec/extensions.json.'
  return `PROPOSED SHAPE, ${spec.columns.length} columns: ${columns}. Basis: ${basis}`
}

/**
 * One row per REGISTER row.
 *
 * The split places every CROSS-CUTTING and SYSTEM field on all three pipeline
 * modules and adds a read-through copy of each identity field, so counting
 * `fields` directly would report `days_in_current_stage` as three missing
 * formulas rather than one. A gap in the register is ONE gap: it is listed
 * against the module the register writes it on, and the copies are skipped.
 *
 * A `moved` field is included — it exists exactly once, just not where the
 * workbook filed it.
 */
const seenDefinitions = new Set<string>()
const registerRows = fields.filter((f) => {
  // One row per FIELD DEFINITION, not per placement. A field placed on three
  // modules is one register row seen three times, and counting it three times
  // would inflate every gap total on this page.
  //
  // A read-through copy is never the definition — it stores nothing and exists
  // to make the parent's value visible. Everything else is deduped on the
  // module the definition originated on.
  if (f.value_mode === 'read_through') return false
  const key = `${f.register_module ?? f.module}.${f.api_name}`
  if (seenDefinitions.has(key)) return false
  seenDefinitions.add(key)
  return true
})

function row(f: FieldSpec, detail: string): HealthRow {
  return {
    ref: f.ref,
    module: f.module,
    api_name: f.api_name,
    label: f.label,
    type: f.type,
    detail,
  }
}

/**
 * Gaps in the field register, read live from the spec. This is the point of
 * the prototype: every row here is a question the register cannot currently
 * answer, and the answers become Phase 1 requirements.
 */
export function specHealth(): HealthGroup[] {
  const groups: HealthGroup[] = []

  // 1. Conditional with no rule anywhere.
  groups.push({
    id: 'conditionless',
    title: 'Conditional fields with no condition',
    ask: 'State when each of these is required. Until then the engine treats them as optional — it will not guess a rule from the field name.',
    rows: registerRows
      .filter((f) => f.requirement === 'Conditional' && !f.condition && !f.visibility_condition)
      .map((f) => row(f, 'requirement = Conditional, condition is empty')),
  })

  // 2. Computed fields with nothing executable behind them.
  //
  //    A field with a working `computed_by` is NOT a gap: days_in_current_stage
  //    is resolved by a named resolver because its value is a function of a
  //    derived date and the clock, which no expression over api_names can
  //    express. One whose computed_by names a resolver that does not exist still
  //    counts — computedGap() decides, so the page and the control agree.
  groups.push({
    id: 'computed',
    title: 'Computed fields with no executable formula',
    ask: 'Supply a formula, or confirm the field is not really computed. These render read-only and blank.',
    rows: registerRows
      .filter((f) => f.type === 'computed' && !f.computed_expr && computedGap(f) !== null)
      .map((f) =>
        row(
          f,
          f.unexpressed
            ? f.unexpressed
            : f.computed_formula
              ? `Prose only: "${f.computed_formula}"`
              : 'No computed_formula in the register'
        )
      ),
  })

  // 3. Picklists with no set behind them.
  groups.push({
    id: 'picklists',
    title: 'Picklist fields with no picklist',
    ask: 'Name the value set, or change the type. Several of these look like they want to be lookups rather than picklists.',
    rows: registerRows
      .filter((f) => (f.type === 'picklist' || f.type === 'multiselect') && !f.picklist)
      .map((f) => row(f, `type = ${f.type}, picklist is empty`)),
  })

  // 4. Childlists the register does not give a row shape.
  //
  //    Rendering a table does NOT close this. A child_spec marked inferred is a
  //    proposal the prototype made so the screen could exist at all; the
  //    register still says nothing, so it stays on this list — with its columns
  //    and its basis printed, which is what a reviewer needs in order to correct
  //    it. Only origin: "stated" drops off.
  groups.push({
    id: 'childlists',
    title: 'Child lists with no row shape in the register',
    ask: 'Define the columns of each child row in the register. Where the prototype proposes a shape it says so on the screen too, beside the field label — correct the columns there or here. Only a child_spec marked origin: "stated" leaves this list.',
    rows: registerRows
      .filter((f) => f.type === 'childlist')
      .filter((f) => !f.child_spec || f.child_spec.origin !== 'stated')
      .map((f) => row(f, childListDetail(f))),
  })

  // 5. Lookup filters that cannot bind to the data.
  groups.push({
    id: 'filters',
    title: 'Lookup filters that cannot be applied',
    ask: 'The filter text names a property the target records do not have. Add the field to the seed, or restate the filter.',
    rows: registerRows
      .filter((f) => f.lookup_filter && !f.lookup_filter_expr)
      .map((f) => row(f, f.unexpressed ?? `Prose only: "${f.lookup_filter}"`)),
  })

  // 6. Expressions that will not compile — real errors, not gaps.
  const problems = validateSpecExpressions()
  groups.push({
    id: 'broken',
    title: 'Expressions that will not compile',
    ask: 'These are errors rather than gaps. The engine ignores the rule and shows the field.',
    rows: problems.map((p) => {
      const f = fields.find((x) => x.qref === p.ref)
      return {
        ref: p.ref,
        module: f?.module ?? p.ref,
        api_name: f?.api_name ?? '',
        label: f?.label ?? '',
        type: p.kind,
        detail: p.message.replace(/\n\s*/g, ' · '),
      }
    }),
  })

  // 7. Sidecar entries pointing at fields that no longer exist.
  groups.push({
    id: 'orphans',
    title: 'Sidecar entries with no matching field',
    ask: 'A regenerate of fields.json has removed or renamed these. Update spec/extensions.json.',
    rows: orphanedExtensions.map((ref) => ({
      ref,
      module: ref.split('.')[0],
      api_name: ref.split('.').slice(1).join('.'),
      label: '',
      type: '',
      detail: 'Key in extensions.json matches no field in fields.json',
    })),
  })

  // 8. List columns naming a field that does not exist.
  groups.push({
    id: 'list-columns',
    title: 'List columns with no matching field',
    ask: 'A list_views entry in spec/extensions.json names a column the register does not carry. The column is dropped from the screen.',
    rows: orphanedListColumns.map(({ module, ref }) => ({
      ref,
      module,
      api_name: ref.split('.').slice(1).join('.'),
      label: '',
      type: 'list column',
      detail: 'Named in list_views, matches no field in fields.json',
    })),
  })

  // 8b. child_spec columns naming a field that does not exist.
  groups.push({
    id: 'child-columns',
    title: 'Child list columns with no matching field',
    ask: 'A child_spec in spec/extensions.json names a column by a ref the register does not carry. The column is dropped from the table.',
    rows: registerRows
      .filter((f) => f.type === 'childlist')
      .flatMap((f) =>
        (childSpecFor(f)?.orphanedColumns ?? []).map((ref) => ({
          ref: `${f.ref}:${ref}`,
          module: f.module,
          api_name: f.api_name,
          label: f.label,
          type: 'child column',
          detail: `child_spec names "${ref}", which matches no field in fields.json`,
        }))
      ),
  })

  // 10. One api_name written into two sections of the same sheet.
  groups.push({
    id: 'duplicates',
    title: 'api_names defined twice in one module',
    ask: 'Rename one of each pair in the register. Until then the prototype CONTAINS them rather than curing them: the field index is keyed on module.section.api_name, the short module.api_name alias resolves to nothing for these, a sidecar entry or list column naming one without its section stops the app at startup, and an expression that mentions one refuses to compile. Nothing binds to whichever definition the register happened to write last.',
    rows: duplicateApiNames.map((d) => ({
      ref: `${d.module}.${d.api_name}`,
      module: d.module,
      api_name: d.api_name,
      label: '',
      type: 'duplicate',
      detail: `Defined in ${d.places.join(' and ')}. Qualify as ${d.sections
        .map((s) => `"${d.module}.${s}.${d.api_name}"`)
        .join(' or ')}.`,
    })),
  })

  // 11. Sidecar field sets naming a field the register does not carry.
  groups.push({
    id: 'field-sets',
    title: 'Field sets naming a field that does not exist',
    ask: 'A named field set in spec/extensions.json lists an api_name the register no longer carries in that section. The field is dropped from the screen it drives.',
    rows: orphanedFieldSetNames.map((f) => ({
      ref: `${f.module}.${f.api_name}`,
      module: f.module,
      api_name: f.api_name,
      label: '',
      type: 'field set',
      detail: `Named in a field set for section ${f.section}, matches no field there`,
    })),
  })

  // 12. Gaps nobody can detect by reading fields.json — found while building a
  //     screen and written down in the sidecar so they are not lost.
  groups.push({
    id: 'open-questions',
    title: 'Questions raised while building a screen',
    ask: 'No check over fields.json can find these — each one was hit while making the register drive a real screen. They are recorded in spec/extensions.json open_questions rather than left in a commit message.',
    rows: openQuestions.map(noteRow),
  })

  // 14. The pipeline split's own debt, in three parts.
  //
  //     None of these is an error and none of them breaks anything. They are the
  //     price of splitting one register sheet into three modules without editing
  //     the generated file, written down where a reviewer sees them rather than
  //     absorbed silently into a loader.

  // 14a. What the workbook has to change now that the split exists.
  groups.push({
    id: 'register-corrections',
    title: 'Register corrections the pipeline split requires',
    ask: 'Each of these is a place the workbook and spec/module_split.json now disagree. The split is the authority and the prototype runs correctly, but the register should be regenerated so the two say the same thing. Nothing here is worked around in a sidecar — stage options are derived from the module range instead, so no picklist was quietly patched.',
    rows: registerCorrections.map((c, i) => noteRow(c, i)),
  })

  // 14b. Fields the register does not carry at all.
  const business = newFields.filter((f) => !f.structural)
  const structural = newFields.filter((f) => f.structural)
  // `structural` now arrives through the ordinary field sidecar rather than
  // inline on a new_fields row — see spec/extensions.json.
  groups.push({
    id: 'new-fields',
    title: `Fields added outside the register — ${
      new Set(business.map((f) => f.api_name)).size
    } gap-fix fields and ${structural.length} structural links`,
    ask:
      'Added outside the workbook and identified by origin. Until Round 7 these lived in spec/extensions.json new_fields and were deliberately NOT imported, so 27 fields rendered in the CRM and existed in no database table — Administration could not see or edit one of them. They are ordinary field_definitions rows now. The gap-fix fields are business fields agreed at the 14-stage review and need a register row each. The structural ones are the parent links carry-forward-by-reference runs on — plumbing, listed apart so nobody is asked to approve a lookup as though it were a new requirement.',
    rows: newFields.map((f) => ({
      ref: `${f.module}.${f.api_name}`,
      module: f.module,
      api_name: f.api_name,
      label: f.label,
      type: f.type,
      detail: `${f.structural ? 'STRUCTURAL LINK' : 'GAP FIX'} · ${f.section} · ${
        f.capture_stage === null ? 'no capture stage' : `Stage ${f.capture_stage}`
      } · ${f.requirement}. ${f.use_case}`,
    })),
  })

  // 14c. Sidecar entries still written against the register's own module.
  groups.push({
    id: 'moved-refs',
    title: 'Sidecar refs naming a module the field has left',
    ask: 'Every one of these still resolves — the loader keeps a movedRefs fall-through so the split needed no hand-editing of extensions.json. Rewrite them deliberately when the sidecar is next touched. Left as-is they are only confusing: a child list on the Deals module whose columns are written as leads.* reads like a bug.',
    rows: movedRefUsages.map((u) => ({
      ref: u.ref,
      module: u.ref.split('.')[0],
      api_name: u.ref.split('.').slice(1).join('.'),
      label: fieldByRef(u.ref)?.label ?? '',
      type: 'moved ref',
      detail: `${u.where} writes "${u.ref}"; the field is now "${u.now}".`,
    })),
  })

  // 14e / 14f. The shared-equivalence and relocated-field groups used to be
  //            built from spec/module_split.json's `shared.equivalence` and
  //            `relocated_fields` blocks. Round 7 removed both: a relocated
  //            field simply HAS the stage and section it has, so there is no
  //            override left to report, and the equivalence pair is a register
  //            inconsistency rather than a placement rule. Neither observation
  //            was lost — both are now register_corrections entries and are
  //            rendered by the group above.

  // 13. Not gaps. Things the register's types cannot carry, stated so no screen
  //     is later read as claiming precision the data does not have.
  groups.push({
    id: 'precision',
    title: 'Known precision limits',
    ask: 'Nothing to fix. Each of these is a rule the playbook states more finely than the register’s field type can carry, so the prototype applies the coarser version and says so on screen. Listed to stop somebody reading an exact claim into a rounded one — reopen only if the finer rule is meant literally.',
    rows: precisionLimits.map(noteRow),
  })

  return groups.filter((g) => g.rows.length > 0)
}

/**
 * A hand-written sidecar note as a Spec Health row.
 *
 * `ref` may name a field or a whole module, and for a duplicated api_name it
 * resolves to nothing — in every case the note still has to render, so the
 * field's details are filled in where they are available and left blank where
 * they are not.
 */
function noteRow(note: { ref: string; detail: string }, i: number): HealthRow {
  const f = fieldByRef(note.ref)
  return {
    ref: `${note.ref}#${i}`,
    module: f?.module ?? note.ref.split('.')[0],
    api_name: f?.api_name ?? note.ref.split('.').slice(1).join('.'),
    label: f?.label ?? '',
    type: f?.type ?? 'module',
    detail: note.detail,
  }
}

export function healthTotal(): number {
  return specHealth().reduce((n, g) => n + g.rows.length, 0)
}
