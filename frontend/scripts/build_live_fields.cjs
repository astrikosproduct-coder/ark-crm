// Writes spec/LIVE_FIELDS.md — the field reference for Partners, Accounts,
// Contacts, Leads, Opportunities and Deals: every field the prototype actually
// renders, with its type, its picklist options and, for a child list, every
// column of a row.
//
// Read-only over the spec, and it runs THE APPLICATION'S OWN LOADER rather than
// re-implementing it — see scripts/dump_spec.cjs. That matters more since the
// pipeline split: the placement rules in spec/module_split.json are subtle
// enough that a second implementation here would drift, and a field register
// that disagrees with the product is worse than none. Regenerate with:
//   npm run spec:fields

const fs = require('fs')
const path = require('path')
const { bundleSpec } = require('./dump_spec.cjs')

const ROOT = path.resolve(__dirname, '..')
const STAGES = require(path.join(ROOT, 'spec/stages.json'))

const MODULES = [
  ['partners', 'Partners'],
  ['accounts', 'Accounts'],
  ['contacts', 'Contacts'],
  ['leads', 'Leads'],
  ['opportunities', 'Opportunities'],
  ['deals', 'Deals'],
]

const TYPE = {
  autonumber: 'autonumber',
  childlist: 'child list',
  longtext: 'long text',
  richtext: 'rich text',
  multiselect: 'multi-select',
  datetime: 'date-time',
}

const REQ = {
  Mandatory: '**Mandatory**',
  System: 'System',
  Computed: 'Computed',
  Conditional: 'Conditional',
  Advisory: 'Advisory',
  Optional: 'Optional',
}

const CARRY = {
  own: '',
  moved: 'moved',
  shared: 'shared',
  own_instance: 'own instance',
  read_through: 'read-through',
  new: 'NEW',
}

main().catch((error) => {
  console.error(error)
  process.exit(1)
})

async function main() {
  const spec = await bundleSpec()
  const { picklists, fieldsOf, childSpecFor, isChildColumnOnly, split } = spec

  if (spec.specRefErrors.length) {
    console.error('The spec did not load cleanly:\n  ' + spec.specRefErrors.join('\n  '))
    process.exit(1)
  }

  const usedPicklists = new Set()

  const opts = (k) => (picklists[k] ?? []).filter((o) => o.active).sort((a, b) => a.sort - b.sort)
  const esc = (s) =>
    String(s ?? '')
      .replace(/\|/g, '\\|')
      .replace(/\s*\n+\s*/g, ' ')
      .trim()
  const ty = (f) => TYPE[f.type] ?? f.type
  const stageOf = (f) =>
    f.capture_any_stage ? 'any' : f.capture_stage === null || f.capture_stage === undefined ? '—' : String(f.capture_stage)

  /**
   * The stages a module owns, read off its range in module_split.json. This is
   * what the app does too — stage options are never taken from a picklist, so
   * neither are the ones printed here.
   */
  function derivedStages(module) {
    const range = split.ranges[module]
    if (!Array.isArray(range)) return null
    return STAGES.filter((s) => s.stage >= range[0] && s.stage <= range[1]).sort(
      (a, b) => a.stage - b.stage
    )
  }

  function detail(f) {
    const bits = []

    // A module's own stage field is the one place the register's picklist is
    // deliberately NOT the source. Printing the picklist here would show a Lead
    // offering Stage 7 and a Deal offering no Stage 7 at all — which is exactly
    // the register defect the derivation exists to stop propagating.
    const stages = split.stage_field[f.module] === f.api_name ? derivedStages(f.module) : null
    if (stages) {
      bits.push(
        '**Derived from the module range, not from `' +
          f.picklist +
          '`** — ' +
          stages.map((s) => s.stage + ' ' + esc(s.name)).join(' · ')
      )
      if (f.max_length) bits.push('max ' + f.max_length)
      if (f.values_note) bits.push(esc(f.values_note))
      return bits.join('<br>')
    }

    if (f.type === 'picklist' || f.type === 'multiselect') {
      if (f.picklist) usedPicklists.add(f.picklist)
      const o = opts(f.picklist)
      if (!f.picklist) bits.push('**No value set named in the register** — see Spec Health')
      else if (!o.length) bits.push('picklist `' + f.picklist + '` — **not found in picklists.json**')
      else bits.push('`' + f.picklist + '` — ' + o.map((x) => esc(x.label)).join(' · '))
    }
    if (f.type === 'lookup') {
      bits.push('→ `' + f.lookup_target + '`' + (f.lookup_filter ? ', filtered: _' + esc(f.lookup_filter) + '_' : ''))
    }
    if (f.type === 'childlist') bits.push('row shape in the child-list table below')
    if (f.type === 'computed') {
      if (f.computed_expr) bits.push('`' + esc(f.computed_expr) + '`')
      else if (f.computed_by) bits.push('resolved by `' + f.computed_by + '` — see lib/spec/resolvers.ts')
      else if (f.computed_formula) bits.push('prose only: _' + esc(f.computed_formula) + '_')
      else bits.push('**no formula in the register**')
    }
    if (f.max_length) bits.push('max ' + f.max_length)
    if (f.values_note) bits.push(esc(f.values_note))
    if (f.condition) bits.push('required when `' + esc(f.condition) + '`')
    if (f.visibility_condition) bits.push('shown when `' + esc(f.visibility_condition) + '`')
    return bits.join('<br>') || '—'
  }

  function carryCell(f) {
    const label = CARRY[f.carry] ?? ''
    if (!label) return '—'
    if (f.carry === 'read_through') return `read-through from \`${f.read_through_from}\` via \`${f.read_through_via}\``
    if (f.carry === 'moved') return `moved from \`${f.register_module}\``
    if (f.carry === 'shared') return `shared from \`${f.register_module}\``
    if (f.carry === 'own_instance') return 'own instance'
    return label
  }

  const isPipeline = (m) => split.pipeline.includes(m)

  function fieldTable(rows, module) {
    const pipeline = isPipeline(module)
    const head = pipeline
      ? '| Label | api_name | Type | Requirement | Stage | Options / target / formula | Carry |'
      : '| Label | api_name | Type | Requirement | Stage | Options / target / formula |'
    const rule = pipeline ? '|---|---|---|---|---|---|---|' : '|---|---|---|---|---|---|'
    const t = [head, rule]
    for (const f of rows) {
      const cells = [
        esc(f.label),
        '`' + f.api_name + '`',
        ty(f),
        REQ[f.requirement] ?? f.requirement,
        stageOf(f),
        detail(f),
      ]
      if (pipeline) cells.push(carryCell(f))
      t.push('| ' + cells.join(' | ') + ' |')
    }
    return t.join('\n')
  }

  function childTable(parent) {
    const resolved = childSpecFor(parent)
    const t = []
    t.push('#### `' + parent.api_name + '` — ' + parent.label)
    t.push('')
    if (!resolved) {
      t.push('The register defines no row shape for this list, so nothing renders. See Spec Health.')
      return t.join('\n')
    }

    const flags = ['Row shape: _' + resolved.origin + '_']
    if (resolved.child_module) flags.push('rows are records of `' + resolved.child_module + '`')
    if (resolved.readonly) flags.push('read-only')
    t.push(flags.join(' · ') + '.')
    t.push('')
    t.push('| Column | api_name | Type | Row requirement | Options / target / formula | Where the column comes from |')
    t.push('|---|---|---|---|---|---|')
    for (const c of resolved.columns) {
      const f = c.field
      const from =
        f.origin === 'Sidecar'
          ? 'declared in extensions.json'
          : 'register field `' + f.module + '.' + f.api_name + '`'
      t.push(
        '| ' +
          [
            esc(f.label),
            '`' + f.api_name + '`',
            ty(f),
            c.required ? '**required**' : 'optional',
            detail(f),
            from,
          ].join(' | ') +
          ' |'
      )
    }
    if (resolved.orphanedColumns.length) {
      t.push('\n> Unresolved column refs: ' + resolved.orphanedColumns.map((o) => '`' + o + '`').join(', '))
    }
    if (resolved.origin !== 'stated' && resolved.basis) {
      t.push('')
      t.push(
        '<details><summary><b>Why these columns</b> — the register states no row shape, so this one was derived. Correct it here or in the register.</summary>'
      )
      t.push('')
      t.push(esc(resolved.basis))
      t.push('')
      t.push('</details>')
    }
    return t.join('\n')
  }

  // ------------------------------------------------------------------ document
  const out = []
  const today = new Date().toISOString().slice(0, 10)
  // fieldsOf(), not a filter over `fields`: the loader's index is sorted by the
  // register order the split renumbered, and section sequence is read off it.
  // Filtering the flat array gives whatever order the split happened to emit,
  // which put HEADER last and interleaved ON CONVERSION with STAGE 7 - CLOSE.
  const allOf = (module) => fieldsOf(module)
  const liveOf = (module) => allOf(module).filter((f) => !isChildColumnOnly(f))

  out.push('# ARK CRM — live field reference')
  out.push('')
  out.push('> **PROTOTYPE — data is stored in this browser only. Not a live system.**')
  out.push('')
  out.push(
    'Partners · Accounts · Contacts · Leads · Opportunities · Deals — every field the prototype renders today, with its type, its picklist options and, for a child list, every column of one row.'
  )
  out.push('')
  out.push(
    "Generated on " + today + " by running the application's own spec loader, not a copy of it — `npm run spec:fields`. " +
      'The workbook remains the source; `spec/fields.json` is never hand-edited.'
  )
  out.push('')
  out.push('**What "live" means here.** A field is listed if the form engine puts it on a screen. Four rules shape the list:')
  out.push('')
  out.push(
    '- The pipeline is **three modules**, not two. `spec/module_split.json` is the authority on which module owns which stage, and every field follows the stage that captures it. The **Carry** column on each pipeline table says how the field got there — see the key below.'
  )
  out.push(
    '- Fields the register writes flat but which really describe **one row of a child list** — the four `milestone_—_*` dates, the seven `guarantee_—_*` fields — are listed **only** under their child list. The form engine drops them as record fields, because rendering them both ways gave two places to type the same value and only one of them was kept.'
  )
  out.push(
    '- Picklist options are the **active** ones, in the register’s own sort order, shown as labels. Full key → label sets are in Appendix A.'
  )
  out.push(
    '- **Requirement** and **Stage** are the register’s own `requirement` and `capture_stage` columns. `any` means the field applies at every stage; `—` means the register records no stage.'
  )
  out.push('')
  out.push('**Carry** — how a field came to be on the module it is on:')
  out.push('')
  out.push('| Carry | Meaning |')
  out.push('|---|---|')
  out.push('| — | The register writes it on this module and it stayed. |')
  out.push('| moved | Reassigned by capture stage. A Stage 5 field is an Opportunity field wherever the workbook filed it. |')
  out.push('| shared | A CROSS-CUTTING or SYSTEM field, placed on all three pipeline modules. A skip reason is as true of an Opportunity as of a Lead. |')
  out.push('| own instance | Per-record state. An Opportunity at Stage 5 and the Lead it came from at Stage 3 are two different stages, not a copy. |')
  out.push('| read-through | **Resolved from the parent record and never stored here.** Identity is carried by reference, so the same End Client cannot exist in three places and drift. |')
  out.push('| NEW | Declared in `extensions.json` `new_fields` — the register does not carry it. Listed on Spec Health as a gap-fix or a structural link. |')
  out.push('')

  out.push('## Modules at a glance')
  out.push('')
  out.push('| Module | Stages | Live record fields | Child lists | Child-list columns | Sections |')
  out.push('|---|---|---|---|---|---|')
  for (const [key, name] of MODULES) {
    const all = allOf(key)
    const cls = all.filter((f) => f.type === 'childlist')
    const childCols = cls.reduce((n, f) => n + (childSpecFor(f)?.columns.length ?? 0), 0)
    const sections = new Set(all.map((f) => f.section))
    const range = split.ranges[key]
    const stages = Array.isArray(range) ? `${range[0]}–${range[1]}` : '—'
    out.push(
      `| **${name}** | ${stages} | ${liveOf(key).length} | ${cls.length} | ${childCols} | ${sections.size} |`
    )
  }
  out.push('')
  out.push(
    'Row counts match the target placement in `ARK_CRM_Field_Register_Split_v1.xlsx`: Leads ' +
      allOf('leads').length +
      ', Opportunities ' +
      allOf('opportunities').length +
      ', Deals ' +
      allOf('deals').length +
      ' — counting every row on the sheet, including the child-column rows the form engine folds into their table.'
  )
  out.push('')

  for (const [key, name] of MODULES) {
    const all = allOf(key)
    const sections = []
    for (const f of all) if (!sections.includes(f.section)) sections.push(f.section)
    out.push('---')
    out.push('')
    out.push('## ' + name)
    out.push('')
    if (isPipeline(key)) {
      const range = split.ranges[key]
      const owned = Array.isArray(range) ? `Stages ${range[0]}–${range[1]}.` : ''
      const parent = split.read_through.parent_of[key]
      out.push(
        owned +
          (parent
            ? ` Holds \`${split.read_through.parent_link[key]}\`; identity is read through the parent \`${parent}\` and rendered read-only.`
            : '')
      )
      out.push('')
    }
    for (const s of sections) {
      const rows = all.filter((f) => f.section === s).sort((a, b) => a.order - b.order)
      const live = rows.filter((f) => !isChildColumnOnly(f))
      const hidden = rows.filter((f) => isChildColumnOnly(f))
      out.push('### ' + s)
      out.push('')
      if (live.length) out.push(fieldTable(live, key))
      else out.push('_Every field in this section defines a child-list row — see the child lists below._')
      if (hidden.length) {
        const parents = [
          ...new Set(
            all
              .filter(
                (f) =>
                  f.type === 'childlist' &&
                  (childSpecFor(f)?.columns ?? []).some((c) => hidden.some((h) => h.qref === c.field.qref))
              )
              .map((f) => f.label)
          ),
        ]
        out.push('')
        out.push(
          '> ' +
            hidden.length +
            ' further field' +
            (hidden.length === 1 ? '' : 's') +
            ' in this section — ' +
            hidden.map((h) => '`' + h.api_name + '`').join(', ') +
            ' — define row columns of **' +
            (parents.join(', ') || 'a child list') +
            '** and are listed there, not as record fields.'
        )
      }
      out.push('')
    }
    const childlists = all.filter((f) => f.type === 'childlist')
    if (childlists.length) {
      out.push('### ' + name + ' — child lists')
      out.push('')
      out.push('Each table below is **one row** of that child list.')
      out.push('')
      for (const c of childlists) {
        out.push(childTable(c))
        out.push('')
      }
    }
  }

  out.push('---')
  out.push('')
  out.push('## Appendix A — every picklist these modules use')
  out.push('')
  out.push(
    'The **key** is what the store holds and what a condition compares against; the **label** is what the screen shows. Inactive options are omitted.'
  )
  out.push('')
  for (const k of [...usedPicklists].sort()) {
    const o = opts(k)
    out.push('**`' + k + '`** — ' + o.length + ' option' + (o.length === 1 ? '' : 's'))
    out.push('')
    out.push('| key | label |')
    out.push('|---|---|')
    for (const x of o) out.push('| `' + x.key + '` | ' + esc(x.label) + ' |')
    out.push('')
  }

  // ------------------------------------------------------- Appendix B
  out.push('---')
  out.push('')
  out.push('## Appendix B — what the split did, and what it did not')
  out.push('')
  out.push(
    'The three-module pipeline agreed at the 14-stage review is applied to the **spec layer**. The screens still show the old two-module shape — Lead detail rails 0–7 and Deal detail rails 8–9 — until they are rebuilt around the split. Conversions, the readiness panel and the store are later steps.'
  )
  out.push('')

  out.push('### Fields the register does not carry')
  out.push('')
  const business = spec.newFields.filter((f) => !f.structural)
  const structural = spec.newFields.filter((f) => f.structural)
  out.push(
    'Declared in `spec/extensions.json` `new_fields`, so `spec/fields.json` stays generated. ' +
      new Set(business.map((f) => f.api_name)).size +
      ' gap-fix fields and ' +
      structural.length +
      ' structural links — the parent lookups carry-forward-by-reference runs on, counted apart because plumbing is not an invented requirement.'
  )
  out.push('')
  out.push('| Field | api_name | Type | Module | Stage | Kind |')
  out.push('|---|---|---|---|---|---|')
  for (const f of spec.newFields) {
    out.push(
      '| ' +
        [
          esc(f.label),
          '`' + f.api_name + '`',
          ty(f),
          '`' + f.module + '`',
          f.capture_stage === null ? 'header' : f.capture_stage,
          f.structural ? 'structural link' : 'gap fix',
        ].join(' | ') +
        ' |'
    )
  }
  out.push('')

  out.push('### Identity is carried by reference')
  out.push('')
  // The list used to be `split.read_through.fields`, a hand-kept array in
  // module_split.json. Round 6/7 moved placement into PostgreSQL and the
  // regenerated module_split.json carries only the structural half of the
  // block — $note, parent_of, parent_link — so that array is gone and this
  // script had been throwing on it ever since. Derived from the register
  // instead, which is the same answer from the source that now owns it: a
  // read-through placement is one whose value_mode says so.
  const readThrough = [
    ...new Set(
      split.pipeline
        .flatMap((m) => fieldsOf(m))
        .filter((f) => f.value_mode === 'read_through')
        .map((f) => f.api_name)
    ),
  ].sort()
  out.push(
    'An Opportunity holds `parent_lead`; a Deal holds `parent_opportunity`. The ' +
      readThrough.length +
      ' identity fields below are **read through that link and rendered read-only** — never copied, so the same value cannot drift in two places. They appear in `fieldsOf(module)` because a criterion or a formula naming a parent field would otherwise stop compiling; carrying them made one previously-broken expression compile again (`deals.incremental_value`, whose visibility rule reads `opportunity_type`).'
  )
  out.push('')
  out.push(readThrough.map((f) => '`' + f + '`').join(' · '))
  out.push('')
  out.push(
    'Deals takes 18 of the 20: the Deals sheet declares `end_client` and `customer_partner_si` itself. Whether those two register rows should be read-through instead is an open question on Spec Health, not something the loader decided.'
  )
  out.push('')

  out.push('### Register corrections this raises')
  out.push('')
  out.push(
    'Stage options are derived from the module range plus `spec/stages.json`, never from a picklist. No picklist was patched in a sidecar to make the split work, so each of these stays visible until the workbook is regenerated.'
  )
  out.push('')
  for (const c of split.register_corrections) out.push('- **`' + c.ref + '`** — ' + c.detail)
  out.push('')

  out.push('### Refs still written the old way')
  out.push('')
  out.push(
    spec.movedRefUsages.length +
      ' sidecar refs name a module their field has left. Every one still resolves — the loader keeps a `movedRefs` fall-through, so the split needed no hand-editing of `extensions.json` — and every one is listed on Spec Health rather than silently rewritten.'
  )
  out.push('')
  out.push('| Written as | Now lives at | Where |')
  out.push('|---|---|---|')
  for (const u of spec.movedRefUsages) {
    out.push('| `' + u.ref + '` | `' + u.now + '` | ' + u.where + ' |')
  }
  out.push('')

  out.push('### Not settled')
  out.push('')
  out.push(
    '- **Nomination Bid and Incumbent Only adjust probability, but `spec/stages.json` carries no uplift for either.** Every stage row holds only `prob_min`, `prob_max`, `owner_role`, `bid_phase` and `applies_to`. The boxes record the fact and probability is untouched; no number is invented. Incumbent advantage is written in the playbook as a *range*, which a single uplift field cannot hold.'
  )
  out.push(
    '- **Progression % is linear by stage position** — position in the ordered 0–9 list ÷ (count − 1), read from `stages.json` and never hardcoded to 9. The register states no progression curve. It is shown BESIDE Probability, never instead of it: at Stage 7 they read 78% and 90–100%, and that difference is the point.'
  )
  out.push('')

  fs.writeFileSync(path.join(ROOT, 'spec/LIVE_FIELDS.md'), out.join('\n') + '\n')
  console.log('written to spec/LIVE_FIELDS.md —', out.length, 'lines')
  console.log(
    'modules:',
    MODULES.map(([k]) => `${k} ${allOf(k).length}`).join(' · ')
  )
  console.log('picklists documented:', usedPicklists.size)
}
