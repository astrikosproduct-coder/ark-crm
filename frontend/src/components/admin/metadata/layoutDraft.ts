import { HEADER_STRIP_SECTION } from '@/lib/pipeline'
import { placeOfSection, type SectionPlace } from '@/lib/recordLayout'
import { arrangeAnchoredWith, childrenByAnchor, type AnchoredNode } from '@/lib/spec/anchors'
import type { LayoutSaveInput, MetadataField, MetadataSection } from '@/lib/metadata'

/**
 * The layout editor's draft — everything the editor changes before Save (Setup
 * rebuild, 4c, 1 Oct 2026). Pure functions over plain data, so the component
 * only draws and the arithmetic lives in one place.
 *
 * The draft holds EVERY active section of the module, shown or not: Save sends
 * the whole arrangement, and a section the save leaves out is deleted. A tab
 * only chooses which of them are drawn.
 *
 * WHERE A FIELD DRAWS is part of the session too (4e): "Show under…", "Show
 * beside…" and the width item change `anchors` and `spans`, and Save sends
 * them with the arrangement. An attached field lives in its anchor's section,
 * so moving a field away from the one it is under detaches it.
 */
export interface DraftSection {
  /** `s<id>` for a saved section, `new-<n>` for one made in this session. */
  key: string
  id: number | null
  label: string
}

export type AnchorPosition = 'after' | 'beside'
export type Span = 'full' | 'half' | null

export interface Draft {
  sections: DraftSection[]
  /** Placement ids per section, in order — attached fields included. */
  cells: Record<string, number[]>
  /** Placement ids waiting in Unused Items. */
  unused: number[]
  /** Mark as required toggles made in this session, by placement id. */
  toggled: Record<number, boolean>
  /** Attach / detach made in this session: the placement it draws next to, or null. */
  anchors: Record<number, { to: number | null; position: AnchorPosition }>
  /** Width changes made in this session. */
  spans: Record<number, Span>
}

export const sectionKey = (id: number) => `s${id}`

/** What a drag carries, so a drop knows what it was handed. */
export const DRAG = {
  newField: 'application/x-ark-new-field',
  cell: 'application/x-ark-cell',
  unused: 'application/x-ark-unused',
  newSection: 'application/x-ark-new-section',
  section: 'application/x-ark-section',
  choice: 'application/x-ark-choice',
} as const

const byOrder = (a: MetadataField, b: MetadataField) =>
  (a.sort_order ?? 0) - (b.sort_order ?? 0) || a.placement_id - b.placement_id

export function initialDraft(sections: MetadataSection[], fields: MetadataField[]): Draft {
  const active = fields.filter((f) => f.status === 'active').sort(byOrder)
  const used = new Set(active.map((f) => f.section_id))
  const kept = sections
    .filter((s) => s.active || used.has(s.id))
    .sort((a, b) => a.sort_order - b.sort_order || a.id - b.id)
  const cells: Record<string, number[]> = {}
  for (const s of kept) cells[sectionKey(s.id)] = []
  for (const f of active) cells[sectionKey(f.section_id)]?.push(f.placement_id)
  return {
    sections: kept.map((s) => ({ key: sectionKey(s.id), id: s.id, label: s.label })),
    cells,
    unused: fields
      .filter((f) => f.status === 'deleted')
      .sort((a, b) => a.label.localeCompare(b.label))
      .map((f) => f.placement_id),
    toggled: {},
    anchors: {},
    spans: {},
  }
}

/**
 * Bring a draft up to date with the server without losing the session — a
 * field created from the palette appears where it was dropped; one deleted
 * elsewhere disappears. Returns the same object when nothing changed.
 */
export function reconcile(
  draft: Draft,
  fields: MetadataField[],
  insert: { sectionKey: string; beforeId: number | null } | null
): Draft {
  const ids = new Set(fields.map((f) => f.placement_id))
  const known = new Set([...Object.values(draft.cells).flat(), ...draft.unused])
  let changed = [...known].some((id) => !ids.has(id))
  const cells: Record<string, number[]> = {}
  for (const [key, list] of Object.entries(draft.cells)) cells[key] = list.filter((id) => ids.has(id))
  let unused = draft.unused.filter((id) => ids.has(id))
  for (const f of fields) {
    if (known.has(f.placement_id)) continue
    if (f.status === 'deleted') {
      unused = [...unused, f.placement_id]
      changed = true
      continue
    }
    const key = insert && cells[insert.sectionKey] ? insert.sectionKey : sectionKey(f.section_id)
    if (!cells[key]) continue
    cells[key] = insertBefore(cells[key], [f.placement_id], insert?.beforeId ?? null)
    changed = true
  }
  return changed ? { ...draft, cells, unused } : draft
}

function insertBefore(list: number[], ids: number[], beforeId: number | null): number[] {
  const rest = list.filter((id) => !ids.includes(id))
  const at = beforeId === null ? -1 : rest.indexOf(beforeId)
  return at < 0 ? [...rest, ...ids] : [...rest.slice(0, at), ...ids, ...rest.slice(at)]
}

function sectionOf(draft: Draft, id: number): string | null {
  for (const [key, list] of Object.entries(draft.cells)) if (list.includes(id)) return key
  return null
}

// ------------------------------------------------------------- where it draws

/** The placement a field draws next to in this session, and how — or null. */
export function anchorOf(
  draft: Draft,
  field: MetadataField,
  byId: Map<number, MetadataField>
): { to: number; position: AnchorPosition } | null {
  const set = draft.anchors[field.placement_id]
  if (set) return set.to === null ? null : { to: set.to, position: set.position }
  if (!field.anchor_field) return null
  for (const other of byId.values()) {
    if (other.api_name === field.anchor_field && other.status === 'active') {
      return { to: other.placement_id, position: field.anchor_position ?? 'after' }
    }
  }
  return null
}

export function spanOf(draft: Draft, field: MetadataField): Span {
  return field.placement_id in draft.spans ? draft.spans[field.placement_id] : (field.layout_span as Span)
}

/** The field as this session would draw it: its anchor and width as edited. */
function effective(draft: Draft, field: MetadataField, byId: Map<number, MetadataField>): MetadataField {
  const anchor = anchorOf(draft, field, byId)
  return {
    ...field,
    anchor_field: anchor ? (byId.get(anchor.to)?.api_name ?? null) : null,
    anchor_position: anchor ? anchor.position : null,
    layout_span: spanOf(draft, field),
  }
}

/** Show `id` under or beside `to` (same section), or on its own with null. */
export function attach(draft: Draft, id: number, to: number | null, position: AnchorPosition = 'after'): Draft {
  return { ...draft, anchors: { ...draft.anchors, [id]: { to, position } } }
}

export function setSpan(draft: Draft, id: number, span: Span): Draft {
  return { ...draft, spans: { ...draft.spans, [id]: span } }
}

/** Fields `id` may be shown under: its section's other fields, never one already under it. */
export function attachTargets(draft: Draft, id: number, byId: Map<number, MetadataField>): MetadataField[] {
  const key = sectionOf(draft, id)
  if (!key) return []
  const below = new Set(cellIds(draft, byId, id))
  return (draft.cells[key] ?? [])
    .filter((other) => !below.has(other))
    .map((other) => byId.get(other))
    .filter((f): f is MetadataField => Boolean(f) && !f!.asked_at_stage_move)
}

// ------------------------------------------------------------- moving

/** Move fields into a section (before `beforeId`, or at the end) or to Unused Items. */
export function moveIds(
  draft: Draft,
  ids: number[],
  target: string | 'unused',
  beforeId: number | null,
  byId?: Map<number, MetadataField>
): Draft {
  if (beforeId !== null && ids.includes(beforeId)) return draft
  const cells: Record<string, number[]> = {}
  for (const [key, list] of Object.entries(draft.cells)) cells[key] = list.filter((id) => !ids.includes(id))
  let unused = draft.unused.filter((id) => !ids.includes(id))
  if (target === 'unused') unused = [...unused, ...ids]
  else cells[target] = insertBefore(cells[target] ?? [], ids, beforeId)
  // A field taken away from the one it is shown under is no longer under it:
  // an attached field lives in its anchor's section.
  let anchors = draft.anchors
  if (byId) {
    for (const id of ids) {
      const field = byId.get(id)
      const anchor = field ? anchorOf(draft, field, byId) : null
      if (anchor && !ids.includes(anchor.to) && target !== sectionOf(draft, anchor.to)) {
        anchors = { ...anchors, [id]: { to: null, position: 'after' } }
      }
    }
  }
  return { ...draft, cells, unused, anchors }
}

/** A section's fields as the form draws them: cells, each with what is attached under it. */
export function nodesOf(
  draft: Draft,
  ids: number[],
  byId: Map<number, MetadataField>
): AnchoredNode<MetadataField>[] {
  const rows = ids
    .map((id) => byId.get(id))
    .filter((f): f is MetadataField => Boolean(f))
    .map((f) => effective(draft, f, byId))
  return arrangeAnchoredWith(rows, childrenByAnchor(rows))
}

export function nodeIds(node: AnchoredNode<MetadataField>): number[] {
  return [node.field.placement_id, ...node.under.flatMap(nodeIds)]
}

/** The ids that travel with a field when it is dragged: it, and what is attached under it. */
export function cellIds(draft: Draft, byId: Map<number, MetadataField>, headId: number): number[] {
  for (const list of Object.values(draft.cells)) {
    if (!list.includes(headId)) continue
    const find = (nodes: AnchoredNode<MetadataField>[]): number[] | null => {
      for (const node of nodes) {
        if (node.field.placement_id === headId) return nodeIds(node)
        const inner = find(node.under)
        if (inner) return inner
      }
      return null
    }
    return find(nodesOf(draft, list, byId)) ?? [headId]
  }
  return [headId]
}

/** Move a section to just before another (or to the end). */
export function moveSection(draft: Draft, key: string, beforeKey: string | null): Draft {
  const moving = draft.sections.find((s) => s.key === key)
  if (!moving || key === beforeKey) return draft
  const rest = draft.sections.filter((s) => s.key !== key)
  const at = beforeKey === null ? -1 : rest.findIndex((s) => s.key === beforeKey)
  const sections = at < 0 ? [...rest, moving] : [...rest.slice(0, at), moving, ...rest.slice(at)]
  return { ...draft, sections }
}

export function addSection(draft: Draft, section: DraftSection, beforeKey: string | null): Draft {
  return moveSection(
    { ...draft, sections: [...draft.sections, section], cells: { ...draft.cells, [section.key]: [] } },
    section.key,
    beforeKey
  )
}

/** Delete a section: its fields go to Unused Items. */
export function deleteSection(draft: Draft, key: string): Draft {
  const ids = draft.cells[key] ?? []
  const cells = { ...draft.cells }
  delete cells[key]
  return {
    ...draft,
    sections: draft.sections.filter((s) => s.key !== key),
    cells,
    unused: [...draft.unused, ...ids],
  }
}

export function renameSection(draft: Draft, key: string, label: string): Draft {
  return { ...draft, sections: draft.sections.map((s) => (s.key === key ? { ...s, label } : s)) }
}

export function isRequired(draft: Draft, field: MetadataField): boolean {
  return draft.toggled[field.placement_id] ?? field.required
}

/** What PUT /layouts/{id} takes — see LayoutSave on the server. */
export function savePayload(draft: Draft, byId: Map<number, MetadataField>): LayoutSaveInput {
  const required: Record<number, boolean> = {}
  for (const [id, value] of Object.entries(draft.toggled)) {
    const field = byId.get(Number(id))
    if (field && field.required !== value) required[Number(id)] = value
  }
  return {
    sections: draft.sections.map((s) => ({ id: s.id, key: s.key, label: s.label })),
    placements: draft.sections.flatMap((s) =>
      (draft.cells[s.key] ?? []).map((id) => {
        const entry: LayoutSaveInput['placements'][number] = { placement_id: id, section: s.key }
        const field = byId.get(id)
        // Only what this session changed is sent; the server keeps the rest.
        if (field && id in draft.anchors) {
          const anchor = anchorOf(draft, field, byId)
          entry.anchor = anchor ? anchor.to : null
          entry.anchor_position = anchor ? anchor.position : null
        }
        if (id in draft.spans) entry.span = draft.spans[id]
        return entry
      })
    ),
    required,
  }
}

/** Has the session changed anything Save would send? */
export function isDirty(draft: Draft, baseline: Draft, byId: Map<number, MetadataField>): boolean {
  const shape = (d: Draft) =>
    JSON.stringify({
      sections: d.sections,
      cells: d.sections.map((s) => d.cells[s.key] ?? []),
      unused: [...d.unused].sort((a, b) => a - b),
    })
  const drawn = (d: Draft) =>
    JSON.stringify(
      [...byId.values()].map((f) => [f.placement_id, anchorOf(d, f, byId), spanOf(d, f)])
    )
  return (
    shape(draft) !== shape(baseline) ||
    drawn(draft) !== drawn(baseline) ||
    Object.keys(savePayload(draft, byId).required).length > 0
  )
}

// ------------------------------------------------------------- tabs

/**
 * Where a section shows on the record page — the editor's tab for it. The
 * record page's own rules (lib/recordLayout.ts placeOfSection), plus one the
 * editor needs: a stage this module does not own is `elsewhere`, never drawn.
 * `related` (the Lead's own fields shown live) is not drawn either.
 */
export type SectionKind = SectionPlace | { kind: 'elsewhere' }

const STAGE_PREFIX = /^STAGE \d+\s*[—–-]\s*/

export function kindOf(
  section: DraftSection,
  rows: MetadataField[],
  ownStages: number[] | null
): SectionKind {
  const place = placeOfSection(section.label, rows)
  if (place.kind === 'stage' && ownStages && !ownStages.includes(place.stage)) return { kind: 'elsewhere' }
  return place
}

/**
 * A section's name as Setup shows it. The record-header strip is stored as
 * `__header`, the name the record page finds it by; what it holds is the
 * Opportunities priority flags, so that is what it is called here.
 */
export function sectionTitle(section: Pick<DraftSection, 'label'>): string {
  return section.label === HEADER_STRIP_SECTION ? 'Priority Flags' : section.label
}

/** "STAGE 2 — " of "STAGE 2 — POC / PILOT": the part a rename keeps. */
export function stagePrefixOf(label: string): string {
  return STAGE_PREFIX.exec(label)?.[0] ?? ''
}

/** A name for a new section no other section has. */
export function freshLabel(draft: Draft, base: string): string {
  const taken = new Set(draft.sections.map((s) => s.label.toLowerCase()))
  let label = base
  for (let n = 2; taken.has(label.toLowerCase()); n++) label = `${base} ${n}`
  return label
}
