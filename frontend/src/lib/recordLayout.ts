import { HEADER_STRIP_SECTION, KEY_FACTS_ANCHOR } from '@/lib/pipeline'

/**
 * WHERE A SECTION SHOWS ON A RECORD — one set of rules for every screen that
 * draws or describes a record's layout (Setup rebuild, 4e, 5 Oct 2026).
 *
 * The record page (PipelineRecordPage) and Setup's layout editor each used to
 * carry their own copy of these rules, and they had already drifted: an empty
 * section was "Related" to one and "Details" to the other. A layout an admin
 * arranges in Setup has to be the layout a user sees, so both read this.
 *
 *   header     the strip above the tabs (`__header` — Opportunities' Priority
 *              Flags, saved the moment they change)
 *   keyfacts   the section holding the key facts (Overall RAG …): drawn at the
 *              top of every stage, and on the create page
 *   stage      "STAGE n — …": that stage's own view. The STAGE part of the name
 *              is what puts it there, so it is fixed when the section is renamed
 *   related    every field shown live from the parent ("From the Lead"): on the
 *              Related tab, under the record it belongs to — not a form section
 *   details    everything else: the Details tab
 *
 * Rows are the section's fields as the caller has them (published FieldSpec on
 * a record, the draft in Setup); only `api_name` and `value_mode` are read.
 */
export type SectionPlace =
  | { kind: 'header' }
  | { kind: 'keyfacts' }
  | { kind: 'stage'; stage: number }
  | { kind: 'related' }
  | { kind: 'details' }

export interface PlaceRow {
  api_name: string
  value_mode?: string | null
}

const STAGE_SECTION = /^STAGE (\d+)/

export function placeOfSection(label: string, rows: readonly PlaceRow[]): SectionPlace {
  if (label === HEADER_STRIP_SECTION) return { kind: 'header' }
  if (rows.some((r) => r.api_name === KEY_FACTS_ANCHOR)) return { kind: 'keyfacts' }
  const match = STAGE_SECTION.exec(label)
  if (match) return { kind: 'stage', stage: Number(match[1]) }
  if (rows.length > 0 && rows.every((r) => r.value_mode === 'read_through')) return { kind: 'related' }
  return { kind: 'details' }
}

/**
 * Fields a form never draws because another surface asks for them — the
 * Update Stage dialog (`asked_at_stage_move`, migration 0043). The record keeps
 * them, Reasons & Justifications lists them, and Setup shows them on the
 * layout editor's Stage move tab.
 */
export function isAskedAtStageMove(field: { asked_at_stage_move?: boolean | null }): boolean {
  return field.asked_at_stage_move === true
}

/**
 * What the read-only Reasons & Justifications panel lists: every reason kept
 * one per stage and never carried forward, and every field the Update Stage
 * dialog asks for. Read from the register, so a field made "kept per stage,
 * never carried" in Setup joins the panel without a code change.
 */
export function isReasonField(field: {
  stage_scoped?: string | null
  asked_at_stage_move?: boolean | null
}): boolean {
  return field.stage_scoped === 'sticky' || isAskedAtStageMove(field)
}
