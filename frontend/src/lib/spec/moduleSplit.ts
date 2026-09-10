import splitData from '../../../spec/module_split.json'

/**
 * The pipeline's STRUCTURE: which module owns which stage, and which module is
 * whose parent.
 *
 * THIS FILE NO LONGER DECIDES WHERE A FIELD GOES.
 *
 * It used to. Until Round 7 it held `applyModuleSplit`, 377 lines that re-homed
 * a Stage 5 Leads field onto Opportunities, added the shared, own-instance and
 * read-through copies, relabelled them and renumbered every section — a
 * projection running in the browser, reading a hand-authored JSON that nothing
 * verified. Administration read `field_metadata.module_key` instead and
 * therefore listed ZERO fields for Opportunities while this file put 105 there.
 *
 * Placement is a row now. `spec/fields.json` is generated from
 * `field_placements`, one row per module a field appears on, already carrying
 * its section, order, label and value_mode. There is nothing left to apply.
 *
 * What remains here are facts about MODULES AND STAGES, not about fields:
 *
 *     which modules are pipeline modules, in stage order
 *     which stages each one owns
 *     which field each one stores its stage in
 *     which module is whose parent, through which lookup
 *
 * Those blocks of spec/module_split.json are generated from `modules` and
 * `stages` in PostgreSQL — see app/module_split.py::split_config. The blocks
 * that used to describe field placement (`own`, `shared`, `read_through.fields`,
 * `relocated_fields`, `section_order`) are gone from the file entirely, so it
 * cannot be mistaken for a second authority.
 */

interface SplitFile {
  version: number
  ranges: Record<string, [number, number]>
  pipeline: string[]
  stage_field: Record<string, string>
  read_through: {
    parent_of: Record<string, string>
    parent_link: Record<string, string>
  }
  register_corrections: { ref: string; detail: string }[]
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
  return split.read_through?.parent_of?.[module]
}

/** The lookup field on `module` holding the parent record's id. */
export function parentLinkOf(module: string): string | undefined {
  return split.read_through?.parent_link?.[module]
}

export const registerCorrections = split.register_corrections ?? []
