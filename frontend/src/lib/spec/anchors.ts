import { fieldsOf } from '@/lib/spec'
import type { FieldSpec } from '@/types/field'

/**
 * WHERE A FIELD DRAWS, as against what kind of field it is.
 *
 * THE PROBLEM
 * -----------
 * A form section used to be the answer to both questions at once. `section`
 * said CROSS-CUTTING and therefore also said "bottom of the Details tab", so
 * On Hold Reason sat at order 74 while the Lead Status whose value reveals it
 * sat at order 19 in STAGE 0 — CONNECT: fifty-five fields and one tab away
 * from the question it answers.
 *
 * That is not a cosmetic complaint. A conditional field's visibility_condition
 * is evaluated against LIVE form state, so a field that is not in the same
 * RecordForm as its trigger physically cannot react before a save. Setting the
 * status did nothing; the box only appeared after saving, on a second surface,
 * with its own second save. Two saves for one answer, and nothing on screen
 * between them saying a reason was going to be wanted.
 *
 * THE MODEL
 * ---------
 * `anchor_field` names another api_name ON THE SAME MODULE. The field draws
 * next to it, wherever that field happens to be — including inside a section
 * this field does not belong to. `section` keeps its job of saying what kind
 * of field this is, which is what Spec Health and the field register read.
 * They are allowed to disagree, and on a reason field they are meant to.
 *
 *     anchor_position 'after'   a row directly beneath the anchor, inside its
 *                               grid cell. What a revealed field wants.
 *     anchor_position 'beside'  the adjacent grid cell — flat in the section's
 *                               own field list, immediately after the anchor.
 *
 * Null anchor is the ordinary case: draw in my own section, in `order`.
 *
 * NOTHING HERE MOVES A VALUE. An anchor changes which form a field is rendered
 * inside; the api_name it writes, the section the register files it under and
 * the condition that reveals it are all untouched.
 */

/** How many links of an anchor chain to follow before calling it a loop. */
const MAX_CHAIN = 32

interface ModuleAnchors {
  /** api_name -> the section the field ends up drawing in. */
  home: Map<string, string>
  /** anchor api_name -> the fields anchored to it, in register order. */
  children: Map<string, FieldSpec[]>
  /** api_names with a resolvable anchor — i.e. drawn somewhere else. */
  anchored: Set<string>
}

const cache = new Map<string, ModuleAnchors>()

/**
 * An anchor is RESOLVABLE when it names a field this module actually has.
 *
 * A dangling anchor is treated as no anchor rather than as an error. The
 * backend releases dependents when their anchor is removed from a module, so
 * this should not happen — but a field that quietly returns to its own section
 * is a worse screen, while a field that throws is no screen at all.
 */
function anchorsOf(module: string): ModuleAnchors {
  const cached = cache.get(module)
  if (cached) return cached

  const fields = fieldsOf(module)
  const byName = new Map<string, FieldSpec>()
  for (const f of fields) if (!byName.has(f.api_name)) byName.set(f.api_name, f)

  const home = new Map<string, string>()
  const children = new Map<string, FieldSpec[]>()
  const anchored = new Set<string>()

  for (const field of fields) {
    // Walk to the root of the chain. The root's section is where the whole
    // chain draws, which is what lets a CROSS-CUTTING field appear inside
    // STAGE 0 — CONNECT without either row being rewritten.
    let cursor: FieldSpec = field
    const seen = new Set<string>([field.api_name])
    for (let hop = 0; hop < MAX_CHAIN; hop++) {
      const next = cursor.anchor_field ? byName.get(cursor.anchor_field) : undefined
      // Unresolvable, or a loop the API's own check somehow let through.
      if (!next || seen.has(next.api_name)) break
      seen.add(next.api_name)
      cursor = next
    }
    home.set(field.api_name, cursor.section)

    const parent = field.anchor_field ? byName.get(field.anchor_field) : undefined
    if (!parent || parent.api_name === field.api_name) continue
    anchored.add(field.api_name)
    const list = children.get(parent.api_name)
    if (list) list.push(field)
    else children.set(parent.api_name, [field])
  }

  const resolved: ModuleAnchors = { home, children, anchored }
  cache.set(module, resolved)
  return resolved
}

/**
 * The section a field DRAWS in — its anchor chain's root section, or its own.
 *
 * This is what the form's section filter asks instead of `f.section === s`, so
 * every existing filter downstream (visibility, hiddenFields, view-mode
 * emptiness) applies to an anchored field exactly as it always did.
 */
export function homeSectionOf(module: string, field: FieldSpec): string {
  return anchorsOf(module).home.get(field.api_name) ?? field.section
}

/** True when this field draws next to another one rather than in its own list. */
export function isAnchored(module: string, field: FieldSpec): boolean {
  return anchorsOf(module).anchored.has(field.api_name)
}

/** Every field anchored to this api_name, in register order. Empty when none. */
export function anchoredTo(module: string, apiName: string): FieldSpec[] {
  return anchorsOf(module).children.get(apiName) ?? []
}

/**
 * One field as the form grid draws it: a cell, plus whatever is stacked inside
 * that cell beneath it.
 */
export interface FormNode {
  field: FieldSpec
  /** Fields anchored 'after' this one — same grid cell, stacked below. */
  under: FormNode[]
}

/**
 * Arrange one section's visible fields into grid cells, honouring anchors.
 *
 * `fields` is the section's list AFTER every existing filter and after any
 * stored drag order — so a root's position is still whatever the caller
 * decided, and this only decides where the anchored ones land relative to it.
 *
 *   'beside' children become their own cell, immediately after the anchor's.
 *   'after'  children go inside the anchor's cell, stacked beneath it.
 *
 * A field whose anchor is not in `fields` — hidden by its own condition, or
 * drawn on another screen — is emitted as an ordinary cell in its original
 * position rather than dropped. Losing a field because its neighbour is hidden
 * would be the one outcome worse than the layout being slightly wrong.
 */
export function arrangeAnchored(module: string, fields: FieldSpec[]): FormNode[] {
  const present = new Set(fields.map((f) => f.api_name))
  const { children } = anchorsOf(module)

  const placed = new Set<string>()
  const out: FormNode[] = []

  const attach = (field: FieldSpec): FormNode => {
    const node: FormNode = { field, under: [] }
    for (const kid of children.get(field.api_name) ?? []) {
      if (kid.anchor_position !== 'after') continue
      if (!present.has(kid.api_name) || placed.has(kid.api_name)) continue
      placed.add(kid.api_name)
      node.under.push(attach(kid))
    }
    return node
  }

  const emit = (field: FieldSpec) => {
    if (placed.has(field.api_name)) return
    placed.add(field.api_name)
    out.push(attach(field))
    // 'beside' children follow as their own cells, and may carry cells of
    // their own — a chain of three renders as three adjacent cells.
    for (const kid of children.get(field.api_name) ?? []) {
      if (kid.anchor_position === 'beside' && present.has(kid.api_name)) emit(kid)
    }
  }

  for (const field of fields) {
    // An anchored field is emitted by its anchor. One whose anchor is not on
    // screen falls through to the sweep below and draws on its own.
    if (field.anchor_field && present.has(field.anchor_field)) continue
    emit(field)
  }
  // Anything an unresolvable anchor or a cycle left behind, rather than lost.
  for (const field of fields) emit(field)

  return out
}

/**
 * How much of the two-column grid this field takes.
 *
 * `layout_span` when the placement states one; otherwise the field type's own
 * width, which is what every field had before anchors existed.
 */
export function spansFullWidth(field: FieldSpec, fullWidthTypes: ReadonlySet<string>): boolean {
  if (field.layout_span === 'full') return true
  if (field.layout_span === 'half') return false
  return fullWidthTypes.has(field.type)
}

/**
 * The width of a whole cell — the anchor plus everything stacked inside it.
 *
 * A cell is as wide as its widest member: a full-width reason stacked under a
 * half-width status field needs the row, or the textarea renders into half a
 * column while the label above it spans two.
 */
export function nodeSpansFullWidth(node: FormNode, fullWidthTypes: ReadonlySet<string>): boolean {
  if (spansFullWidth(node.field, fullWidthTypes)) return true
  return node.under.some((child) => nodeSpansFullWidth(child, fullWidthTypes))
}

/** Test seam: the index is built once per module from immutable spec data. */
export function __resetAnchorCache(): void {
  cache.clear()
}
