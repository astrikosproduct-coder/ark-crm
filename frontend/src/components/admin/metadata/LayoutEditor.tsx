import { createContext, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQueryClient } from '@tanstack/react-query'
import {
  AlignLeftIcon,
  ArrowLeftIcon,
  CalendarIcon,
  CheckSquareIcon,
  ChevronDownIcon,
  CircleDollarSignIcon,
  FunctionSquareIcon,
  GripVerticalIcon,
  HashIcon,
  LinkIcon,
  ListChecksIcon,
  ListIcon,
  MailIcon,
  MoreHorizontalIcon,
  PercentIcon,
  PlusIcon,
  SearchIcon,
  SettingsIcon,
  TableIcon,
  TextIcon,
  TypeIcon,
} from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { ErrorNotice, Notice } from '@/components/ui/notice'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { FieldDialog } from './FieldDialog'
import { UnusedItems } from './UnusedItems'
import { LoadingRow } from './shared'
import {
  addSection,
  DRAG,
  cellIds,
  deleteSection,
  freshLabel,
  initialDraft,
  isDirty,
  isRequired,
  kindOf,
  moveIds,
  moveSection,
  nodesOf,
  reconcile,
  renameSection,
  savePayload,
  sectionTitle,
  stagePrefixOf,
  type Draft,
  type DraftSection,
  type SectionKind,
} from './layoutDraft'
import {
  FIELD_TYPES,
  typeLabel,
  useMetadataFields,
  useMetadataSections,
  useSaveLayout,
  type MetadataField,
  type MetadataLayout,
} from '@/lib/metadata'
import { PIPELINE_MODULES } from '@/lib/spec'
import type { AnchoredNode } from '@/lib/spec/anchors'
import { stagesFor } from '@/lib/pipeline'
import { cn } from '@/lib/utils'
import { markFormSaved, useUnsavedChangesStore } from '@/store/useUnsavedChangesStore'

/**
 * The layout editor — Zoho's, full screen (Setup rebuild, 4c, 1 Oct 2026):
 * "← Leads | Standard" and Cancel · Save and Close · Save across the top; the
 * New Fields palette, NEW SECTION and Unused Items down the left; the form's
 * sections, drawn as the record draws them, in the middle.
 *
 * NOTHING IS WRITTEN UNTIL SAVE. Moving fields and sections, adding, renaming
 * and deleting sections, removing and restoring fields and Mark as required
 * are a session (layoutDraft.ts); Save sends the arrangement in one request
 * that is applied all or nothing (PUT /layouts/{id}), and Cancel discards it.
 * Save writes the DRAFT register — the Publish banner still decides when the
 * CRM sees it. Two things save at once, because they have dialogs of their
 * own with a Save button: a field's properties, and a new field from the
 * palette (it appears where it was dropped).
 *
 * TABS ARE THE RECORD PAGE'S. A pipeline record shows its sections in places:
 * above every stage (the header strip and the key facts), each stage's own
 * view, and Details. The editor shows the same places as tabs, so a section
 * added under "Stage 2" is a "STAGE 2 — …" section and lands in that stage's
 * view — the STAGE part of its name is fixed, because that is what puts it
 * there. Record header holds what every stage shows, on all three modules
 * (4d, 5 Oct 2026), so a stage tab is only that stage's own sections.
 *
 * NOT DRAWN: a stage this module does not own, and the "From the Lead"
 * sections — the Lead's own fields shown live on an Opportunity or Deal, which
 * are changed on the Lead (its field's "Also show on"), not here. They stay in
 * the draft untouched, because Save deletes a section it leaves out.
 * The Opportunities strip of Low Hanging and Top 10 is drawn as Priority Flags
 * and locked: a rank there is unique across records, so those fields save the
 * moment they change and cannot share a form with the rest.
 *
 * WHAT IT DELIBERATELY IS NOT: a live form. Tiles draw a type icon and a label,
 * the way Zoho's builder does; the record screen is what draws inputs.
 */
const FORM_ID = 'setup-layout-editor'

const TYPE_ICON: Record<string, typeof TextIcon> = {
  text: TextIcon,
  longtext: AlignLeftIcon,
  richtext: AlignLeftIcon,
  email: MailIcon,
  url: LinkIcon,
  number: HashIcon,
  percent: PercentIcon,
  currency: CircleDollarSignIcon,
  date: CalendarIcon,
  datetime: CalendarIcon,
  checkbox: CheckSquareIcon,
  picklist: ListIcon,
  multiselect: ListChecksIcon,
  lookup: SearchIcon,
  computed: FunctionSquareIcon,
  autonumber: TypeIcon,
  childlist: TableIcon,
  file: LinkIcon,
}
const iconFor = (type: string) => TYPE_ICON[type] ?? TextIcon

type TabId = string // 'header' | 'details' | 'all' | `stage-${n}`

interface EditorActions {
  draft: Draft
  byId: Map<number, MetadataField>
  kinds: Map<string, SectionKind>
  setDraft: (next: Draft) => void
  /** A type from the palette dropped on a section, before a field (or at the end). */
  newField: (sectionKey: string, beforeId: number | null, type: string) => void
  editField: (field: MetadataField) => void
  renaming: string | null
  setRenaming: (key: string | null) => void
  dragSection: boolean
  setDragSection: (on: boolean) => void
}

const Editor = createContext<EditorActions | null>(null)
const useEditor = () => {
  const ctx = useContext(Editor)
  if (!ctx) throw new Error('outside the layout editor')
  return ctx
}

export function LayoutEditor({
  moduleKey,
  moduleLabel,
  layout,
  listHref,
}: {
  moduleKey: string
  moduleLabel: string
  layout: MetadataLayout
  listHref: string
}) {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const { data: sections } = useMetadataSections(moduleKey)
  const { data: fields } = useMetadataFields(moduleKey, 'all')
  const save = useSaveLayout()
  const setFormDirty = useUnsavedChangesStore((s) => s.setFormDirty)

  const [draft, setDraft] = useState<Draft | null>(null)
  const [baseline, setBaseline] = useState<Draft | null>(null)
  const [reloading, setReloading] = useState(false)
  const [tab, setTab] = useState<TabId | null>(null)
  const [renaming, setRenaming] = useState<string | null>(null)
  const [dragSection, setDragSection] = useState(false)
  const [notice, setNotice] = useState<string | null>(null)
  const [dialog, setDialog] = useState<{
    open: boolean
    field?: MetadataField
    sectionId?: number
    fieldType?: string
  }>({ open: false })
  // Where a field being created from the palette should appear once it exists.
  const insertAt = useRef<{ sectionKey: string; beforeId: number | null } | null>(null)
  const newCount = useRef(0)

  const byId = useMemo(() => new Map((fields ?? []).map((f) => [f.placement_id, f])), [fields])

  // The session starts from the server, once — and again after a Save.
  useEffect(() => {
    if (draft || reloading || !sections || !fields) return
    const start = initialDraft(sections, fields)
    setDraft(start)
    setBaseline(start)
  }, [draft, reloading, sections, fields])

  // A field made from the palette, or one deleted elsewhere, joins the session
  // without losing it.
  useEffect(() => {
    if (!fields) return
    const before = draft ? new Set(Object.values(draft.cells).flat()) : null
    setDraft((d) => d && reconcile(d, fields, insertAt.current))
    setBaseline((b) => b && reconcile(b, fields, insertAt.current))
    if (before && fields.some((f) => f.status === 'active' && !before.has(f.placement_id))) {
      insertAt.current = null
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [fields])

  const dirty = Boolean(draft && baseline && isDirty(draft, baseline, byId))
  useEffect(() => setFormDirty(FORM_ID, dirty), [dirty, setFormDirty])
  useEffect(() => () => setFormDirty(FORM_ID, false), [setFormDirty])

  if (!draft || !sections || !fields) {
    return (
      <div className="p-6">
        <LoadingRow what="the layout" />
      </div>
    )
  }

  const isPipeline = PIPELINE_MODULES.includes(moduleKey)
  const stages = isPipeline ? stagesFor(moduleKey) : []
  const ownStages = isPipeline ? stages.map((s) => s.stage) : null
  const rowsOf = (key: string) =>
    (draft.cells[key] ?? []).map((id) => byId.get(id)).filter((f): f is MetadataField => Boolean(f))
  const kinds = new Map(draft.sections.map((s) => [s.key, kindOf(s, rowsOf(s.key), ownStages)]))
  const has = (kind: SectionKind['kind']) => [...kinds.values()].some((k) => k.kind === kind)

  const tabs: { id: TabId; label: string }[] = isPipeline
    ? [
        ...(has('header') || has('keyfacts') ? [{ id: 'header', label: 'Record header' }] : []),
        ...stages.map((s) => ({ id: `stage-${s.stage}`, label: `Stage ${s.stage} · ${s.name}` })),
        { id: 'details', label: 'Details' },
      ]
    : [{ id: 'all', label: 'Form' }]
  const current = tabs.some((t) => t.id === tab) ? (tab as TabId) : (tabs.find((t) => t.id.startsWith('stage-')) ?? tabs[0]).id
  const stageOfTab = current.startsWith('stage-') ? Number(current.slice(6)) : null

  const shownIn = (s: DraftSection): boolean => {
    const k = kinds.get(s.key)!
    if (k.kind === 'elsewhere' || k.kind === 'related') return false
    if (current === 'all') return true
    if (current === 'header') return k.kind === 'header' || k.kind === 'keyfacts'
    if (stageOfTab !== null) return k.kind === 'stage' && k.stage === stageOfTab
    return k.kind === current
  }
  // The strip above the tabs comes first, as on the record page.
  const visible = [
    ...draft.sections.filter((s) => shownIn(s) && kinds.get(s.key)!.kind === 'header'),
    ...draft.sections.filter((s) => shownIn(s) && kinds.get(s.key)!.kind !== 'header'),
  ]
  const canAddSection = current === 'details' || current === 'all' || stageOfTab !== null

  /** Where "the end of this tab" is in the module's whole order. */
  const keyAfterTab = (): string | null => {
    const last = visible[visible.length - 1]
    if (!last) return null
    const at = draft.sections.findIndex((s) => s.key === last.key)
    return draft.sections[at + 1]?.key ?? null
  }

  const addNewSection = (beforeKey: string | null) => {
    if (!canAddSection) return
    const base = stageOfTab !== null ? `STAGE ${stageOfTab} — New Section` : 'New Section'
    const key = `new-${++newCount.current}`
    setDraft(addSection(draft, { key, id: null, label: freshLabel(draft, base) }, beforeKey))
    setRenaming(key)
  }

  const newField = (sectionKey: string, beforeId: number | null, type: string) => {
    const section = draft.sections.find((s) => s.key === sectionKey)
    if (!section) return
    if (section.id === null) {
      setNotice('Save the layout first, then add fields to this new section.')
      return
    }
    setNotice(null)
    insertAt.current = { sectionKey, beforeId }
    setDialog({ open: true, sectionId: section.id, fieldType: type })
  }

  const doSave = async (close: boolean) => {
    setNotice(null)
    try {
      await save.mutateAsync({ layoutId: layout.id, input: savePayload(draft, byId) })
    } catch {
      return // shown from save.error
    }
    setReloading(true)
    setDraft(null)
    setBaseline(null)
    markFormSaved(FORM_ID)
    if (close) {
      navigate(listHref)
      return
    }
    await queryClient.invalidateQueries({ queryKey: ['metadata'] })
    setReloading(false)
  }

  const unusedFields = draft.unused
    .map((id) => byId.get(id))
    .filter((f): f is MetadataField => Boolean(f))
    .sort((a, b) => a.label.localeCompare(b.label))

  return (
    <Editor.Provider
      value={{
        draft,
        byId,
        kinds,
        setDraft,
        newField,
        editField: (field) => setDialog({ open: true, field }),
        renaming,
        setRenaming,
        dragSection,
        setDragSection,
      }}
    >
      <div className="bg-background flex h-screen flex-col">
        {/* Zoho's editor header: where you are on the left, the three buttons on the right. */}
        <header className="bg-card flex h-14 shrink-0 items-center gap-3 border-b px-4">
          <button
            type="button"
            aria-label={`Back to ${moduleLabel} layouts`}
            title="Back to the layouts"
            onClick={() => navigate(listHref)}
            className="text-muted-foreground hover:bg-accent hover:text-foreground flex size-8 items-center justify-center rounded-md"
          >
            <ArrowLeftIcon className="size-5" />
          </button>
          <span className="text-base font-semibold">{moduleLabel}</span>
          <span className="text-muted-foreground border-l pl-3 text-base">{layout.label}</span>
          {dirty && <span className="text-muted-foreground text-xs">Unsaved changes</span>}
          <div className="ml-auto flex items-center gap-2">
            <Button variant="outline" onClick={() => navigate(listHref)}>
              Cancel
            </Button>
            <Button variant="outline" disabled={!dirty || save.isPending} onClick={() => doSave(true)}>
              Save and Close
            </Button>
            <Button disabled={!dirty || save.isPending} onClick={() => doSave(false)}>
              {save.isPending ? 'Saving…' : 'Save'}
            </Button>
          </div>
        </header>

        {(save.error || notice) && (
          <div className="border-b px-4 py-2">
            <ErrorNotice error={save.error} suffix="Nothing was saved." />
            {notice && <Notice tone="warning" lead={notice} />}
          </div>
        )}

        {tabs.length > 1 && (
          <div className="flex shrink-0 justify-center border-b">
            <Tabs value={current} onValueChange={(next) => setTab(next)}>
              <TabsList className="border-b-0">
                {tabs.map((t) => (
                  <TabsTrigger key={t.id} value={t.id}>
                    {t.label}
                  </TabsTrigger>
                ))}
              </TabsList>
            </Tabs>
          </div>
        )}

        <div className="flex min-h-0 flex-1">
          <aside className="w-60 shrink-0 space-y-3 overflow-y-auto border-r p-3">
            <NewFieldsPalette />
            <NewSectionTile disabled={!canAddSection} onAdd={() => addNewSection(keyAfterTab())} />
            <UnusedItems
              fields={unusedFields}
              onDropField={(id) => setDraft(moveIds(draft, cellIds(draft, byId, id), 'unused', null))}
            />
          </aside>

          <main className="min-w-0 flex-1 overflow-y-auto p-4">
            <div className="mx-auto max-w-5xl">
              {current === 'header' && (
                <p className="text-muted-foreground mb-1 text-xs">Shown at the top of every stage.</p>
              )}
              {visible.length === 0 && (
                <p className="text-muted-foreground py-6 text-sm">
                  {canAddSection
                    ? 'Nothing here yet. Drag NEW SECTION here to start.'
                    : 'Nothing here.'}
                </p>
              )}
              {visible.map((section) => (
                <div key={section.key}>
                  <SectionDropZone
                    onDrop={(moved) =>
                      moved === null ? addNewSection(section.key) : setDraft(moveSection(draft, moved, section.key))
                    }
                    allowNew={canAddSection}
                  />
                  <SectionCard section={section} />
                </div>
              ))}
              <SectionDropZone
                onDrop={(moved) =>
                  moved === null ? addNewSection(keyAfterTab()) : setDraft(moveSection(draft, moved, keyAfterTab()))
                }
                allowNew={canAddSection}
                last
              />
            </div>
          </main>
        </div>
      </div>

      <FieldDialog
        open={dialog.open}
        onOpenChange={(open) => {
          if (!open) setDialog({ open: false })
        }}
        moduleKey={moduleKey}
        field={dialog.field}
        sectionId={dialog.sectionId}
        fieldType={dialog.fieldType}
        fromLayout
      />
    </Editor.Provider>
  )
}

/** The palette of field types — drag one onto a section to add a field there. */
function NewFieldsPalette() {
  return (
    <div>
      <p className="text-section mb-2 text-xs font-bold tracking-wide">NEW FIELDS</p>
      <div className="grid grid-cols-2 gap-1.5">
        {FIELD_TYPES.map((type) => {
          const Icon = iconFor(type)
          return (
            <div
              key={type}
              draggable
              onDragStart={(e) => {
                e.dataTransfer.effectAllowed = 'copy'
                e.dataTransfer.setData(DRAG.newField, type)
                // Firefox drops a drag with no text/plain attached.
                e.dataTransfer.setData('text/plain', type)
              }}
              className="border-input bg-input-bg flex cursor-grab items-center gap-1.5 rounded-md border px-2 py-1.5 text-xs active:cursor-grabbing"
              title={`Drag a ${typeLabel(type)} field into a section`}
            >
              <Icon className="text-muted-foreground size-3.5 shrink-0" />
              <span className="truncate">{typeLabel(type)}</span>
            </div>
          )
        })}
      </div>
    </div>
  )
}

/** Zoho's NEW SECTION — drag it between two sections, or click to add at the end. */
function NewSectionTile({ disabled, onAdd }: { disabled: boolean; onAdd: () => void }) {
  const { setDragSection } = useEditor()
  return (
    <button
      type="button"
      draggable={!disabled}
      disabled={disabled}
      title={disabled ? 'Sections are added under a stage or Details' : 'Drag between two sections, or click to add at the end'}
      onClick={onAdd}
      onDragStart={(e) => {
        e.dataTransfer.effectAllowed = 'copy'
        e.dataTransfer.setData(DRAG.newSection, '1')
        e.dataTransfer.setData('text/plain', 'New section')
        setDragSection(true)
      }}
      onDragEnd={() => setDragSection(false)}
      className="border-input bg-input-bg hover:bg-accent flex w-full cursor-grab items-center justify-center gap-2 rounded-md border px-2 py-2 text-xs font-semibold tracking-wide active:cursor-grabbing disabled:cursor-not-allowed disabled:opacity-50"
    >
      <PlusIcon className="size-4" />
      NEW SECTION
    </button>
  )
}

/** Where a section can be dropped: before the next one, or at the end. Shown while dragging one. */
function SectionDropZone({
  onDrop,
  allowNew,
  last,
}: {
  /** null: NEW SECTION was dropped; otherwise the key of the section moved. */
  onDrop: (moved: string | null) => void
  allowNew: boolean
  last?: boolean
}) {
  const { dragSection, setDragSection } = useEditor()
  const [over, setOver] = useState(false)
  return (
    <div
      className={cn(
        'rounded-md transition-all',
        dragSection ? 'my-1 h-6 border border-dashed' : last ? 'h-4' : 'h-2',
        over && 'border-primary bg-primary/10'
      )}
      onDragOver={(e) => {
        const isNew = e.dataTransfer.types.includes(DRAG.newSection)
        if (!(isNew && allowNew) && !e.dataTransfer.types.includes(DRAG.section)) return
        e.preventDefault()
        setOver(true)
      }}
      onDragLeave={() => setOver(false)}
      onDrop={(e) => {
        setOver(false)
        setDragSection(false)
        if (e.dataTransfer.types.includes(DRAG.newSection)) {
          if (!allowNew) return
          e.preventDefault()
          onDrop(null)
          return
        }
        const key = e.dataTransfer.getData(DRAG.section)
        if (!key) return
        e.preventDefault()
        onDrop(key)
      }}
    />
  )
}

function SectionCard({ section }: { section: DraftSection }) {
  const { draft, byId, kinds, setDraft, newField, setDragSection } = useEditor()
  const [open, setOpen] = useState(true)
  const [over, setOver] = useState(false)
  const kind = kinds.get(section.key)!
  // Priority Flags: nothing dropped in, nothing dragged out — see the file's docstring.
  const locked = kind.kind === 'header'
  const ids = draft.cells[section.key] ?? []
  const nodes = nodesOf(ids, byId)

  /** Whatever was dropped: a palette type, a field from the form, or one from Unused Items. */
  const handleDrop = (e: React.DragEvent, beforeId: number | null) => {
    const types = e.dataTransfer.types
    if (types.includes(DRAG.newField)) {
      e.preventDefault()
      e.stopPropagation()
      newField(section.key, beforeId, e.dataTransfer.getData(DRAG.newField))
      return
    }
    const cell = Number(e.dataTransfer.getData(DRAG.cell))
    const unused = Number(e.dataTransfer.getData(DRAG.unused))
    const moving = cell ? cellIds(draft, byId, cell) : unused ? [unused] : []
    if (moving.length === 0) return
    e.preventDefault()
    e.stopPropagation()
    setDraft(moveIds(draft, moving, section.key, beforeId))
  }
  const accepts = (e: React.DragEvent) =>
    !locked && [DRAG.newField, DRAG.cell, DRAG.unused].some((t) => e.dataTransfer.types.includes(t))

  return (
    <div
      className={cn('bg-card rounded-lg border', over && 'ring-primary/50 ring-2')}
      onDragOver={(e) => {
        if (!accepts(e)) return
        e.preventDefault()
        setOver(true)
      }}
      onDragLeave={() => setOver(false)}
      onDrop={(e) => {
        setOver(false)
        handleDrop(e, null)
      }}
    >
      <div className="flex items-center gap-2 border-b px-3 py-2">
        {!locked && (
          <span
            draggable
            onDragStart={(e) => {
              e.dataTransfer.effectAllowed = 'move'
              e.dataTransfer.setData(DRAG.section, section.key)
              e.dataTransfer.setData('text/plain', section.label)
              setDragSection(true)
            }}
            onDragEnd={() => setDragSection(false)}
            className="text-muted-foreground hover:text-foreground cursor-grab active:cursor-grabbing"
            title="Drag to move this section"
          >
            <GripVerticalIcon className="size-4" />
          </span>
        )}
        <button
          type="button"
          onClick={() => setOpen((v) => !v)}
          className="text-muted-foreground hover:text-foreground"
          aria-label={open ? 'Collapse section' : 'Expand section'}
        >
          <ChevronDownIcon className={cn('size-4 transition-transform', !open && '-rotate-90')} />
        </button>
        {locked ? (
          <span className="text-section text-sm font-bold tracking-wide">{sectionTitle(section)}</span>
        ) : (
          <SectionName section={section} />
        )}
        <span className="text-muted-foreground text-xs">
          {locked ? 'Saved the moment they change on the record' : `${ids.length} field${ids.length === 1 ? '' : 's'}`}
        </span>
        {!locked && <SectionGear section={section} kind={kind} />}
      </div>

      {open && (
        <div className="grid gap-x-4 gap-y-2 px-3 py-3 md:grid-cols-2">
          {nodes.length === 0 ? (
            <p className="text-muted-foreground text-sm md:col-span-2">Drag fields here.</p>
          ) : (
            nodes.map((node) => (
              <div
                key={node.field.placement_id}
                className={cn(node.field.layout_span === 'full' && 'md:col-span-2')}
                onDragOver={(e) => {
                  if (accepts(e)) e.preventDefault()
                }}
                onDrop={(e) => {
                  setOver(false)
                  handleDrop(e, node.field.placement_id)
                }}
              >
                <Cell node={node} locked={locked} />
              </div>
            ))
          )}
        </div>
      )}
    </div>
  )
}

/** A section's name, renamed in place. A stage section keeps its "STAGE n — ". */
function SectionName({ section }: { section: DraftSection }) {
  const { draft, setDraft, renaming, setRenaming } = useEditor()
  const prefix = stagePrefixOf(section.label)
  const [value, setValue] = useState(section.label.slice(prefix.length))
  const [error, setError] = useState<string | null>(null)
  const editing = renaming === section.key

  useEffect(() => {
    if (editing) {
      setValue(section.label.slice(prefix.length))
      setError(null)
    }
  }, [editing, section.label, prefix.length])

  if (!editing) {
    return (
      <button
        type="button"
        className="text-section hover:text-foreground text-left text-sm font-bold tracking-wide"
        title="Rename this section"
        onClick={() => setRenaming(section.key)}
      >
        {sectionTitle(section)}
      </button>
    )
  }

  const commit = () => {
    const words = value.trim()
    if (!words) {
      setRenaming(null)
      return
    }
    const label = `${prefix}${words}`
    const clash = draft.sections.some((s) => s.key !== section.key && s.label.toLowerCase() === label.toLowerCase())
    if (clash) {
      setError('Another section has this name.')
      return
    }
    setDraft(renameSection(draft, section.key, label))
    setRenaming(null)
  }

  return (
    <span className="flex items-center gap-1">
      {prefix && <span className="text-section text-sm font-bold tracking-wide">{prefix}</span>}
      <Input
        className="h-7 w-64"
        value={value}
        autoFocus
        onChange={(e) => setValue(e.target.value)}
        onBlur={commit}
        onKeyDown={(e) => {
          if (e.key === 'Enter') commit()
          if (e.key === 'Escape') setRenaming(null)
        }}
      />
      {error && <span className="text-destructive text-xs">{error}</span>}
    </span>
  )
}

/** Zoho's section gear: rename, delete. The two sections the CRM reads by role stay. */
function SectionGear({ section, kind }: { section: DraftSection; kind: SectionKind }) {
  const { draft, setDraft, setRenaming } = useEditor()
  const [open, setOpen] = useState(false)
  const fixed = kind.kind === 'header' || kind.kind === 'keyfacts'
  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <button
          type="button"
          className="text-muted-foreground hover:text-foreground ml-auto"
          aria-label={`Options for ${section.label}`}
        >
          <SettingsIcon className="size-4" />
        </button>
      </PopoverTrigger>
      <PopoverContent align="end" className="w-60 p-1">
        <MenuItem
          onClick={() => {
            setOpen(false)
            setRenaming(section.key)
          }}
        >
          Rename section
        </MenuItem>
        <MenuItem
          className="text-destructive"
          disabled={fixed}
          title={fixed ? 'The record page reads this section — it stays' : undefined}
          onClick={() => {
            setOpen(false)
            setDraft(deleteSection(draft, section.key))
          }}
        >
          Delete section
          <span className="text-muted-foreground block text-xs">Its fields move to Unused Items.</span>
        </MenuItem>
      </PopoverContent>
    </Popover>
  )
}

/** One cell: the field, and what is anchored under it, which travels with it. */
function Cell({ node, locked }: { node: AnchoredNode<MetadataField>; locked: boolean }) {
  return (
    <div className="space-y-1.5">
      <FieldTile field={node.field} locked={locked} />
      {node.under.length > 0 && (
        <div className="border-muted-foreground/25 ml-3 space-y-1.5 border-l pl-3">
          {node.under.map((kid) => (
            <Cell key={kid.field.placement_id} node={kid} locked={locked} />
          ))}
        </div>
      )}
    </div>
  )
}

function FieldTile({ field, locked }: { field: MetadataField; locked: boolean }) {
  const { draft, byId, setDraft, editField } = useEditor()
  const [menuOpen, setMenuOpen] = useState(false)
  const Icon = iconFor(field.field_type)
  const required = isRequired(draft, field)
  const toggleable = !locked && (field.requirement === 'Mandatory' || field.requirement === 'Optional')

  return (
    <div
      draggable={!locked}
      onDragStart={(e) => {
        e.stopPropagation()
        e.dataTransfer.effectAllowed = 'move'
        e.dataTransfer.setData(DRAG.cell, String(field.placement_id))
        e.dataTransfer.setData('text/plain', field.label)
      }}
      className={cn(
        'group border-input bg-input-bg flex items-center gap-2 rounded-md border px-2 py-2',
        !locked && 'cursor-grab active:cursor-grabbing',
        // Zoho marks a required field with a red bar down its left edge.
        required && 'border-l-destructive border-l-2'
      )}
    >
      <span title={typeLabel(field.field_type)} className="shrink-0">
        <Icon className="text-muted-foreground size-4" />
      </span>
      <div className="min-w-0 flex-1">
        <div className="truncate text-sm">{field.label}</div>
        {!field.editable && <div className="text-muted-foreground text-[11px]">Read-only</div>}
      </div>
      <Popover open={menuOpen} onOpenChange={setMenuOpen}>
        <PopoverTrigger asChild>
          <button
            type="button"
            className="text-muted-foreground hover:text-foreground shrink-0 opacity-0 transition-opacity group-hover:opacity-100 focus-visible:opacity-100"
            aria-label={`Options for ${field.label}`}
          >
            <MoreHorizontalIcon className="size-4" />
          </button>
        </PopoverTrigger>
        <PopoverContent align="end" className="w-56 p-1">
          {!locked && (
            <MenuItem
              disabled={!toggleable}
              title={toggleable ? undefined : 'This field has a rule of its own — change it in Edit Properties'}
              onClick={() => {
                setMenuOpen(false)
                setDraft({ ...draft, toggled: { ...draft.toggled, [field.placement_id]: !required } })
              }}
            >
              {required ? 'Mark as not required' : 'Mark as required'}
            </MenuItem>
          )}
          <MenuItem
            onClick={() => {
              setMenuOpen(false)
              editField(field)
            }}
          >
            Edit Properties
          </MenuItem>
          {!locked && (
            <MenuItem
              className="text-destructive"
              onClick={() => {
                setMenuOpen(false)
                setDraft(moveIds(draft, cellIds(draft, byId, field.placement_id), 'unused', null))
              }}
            >
              Remove Field
            </MenuItem>
          )}
        </PopoverContent>
      </Popover>
    </div>
  )
}

/** One row of a ··· or gear menu. */
function MenuItem({
  children,
  onClick,
  className,
  disabled,
  title,
}: {
  children: ReactNode
  onClick: () => void
  className?: string
  disabled?: boolean
  title?: string
}) {
  return (
    <button
      type="button"
      disabled={disabled}
      title={title}
      onClick={onClick}
      className={cn(
        'hover:bg-accent w-full rounded-sm px-2 py-1.5 text-left text-sm disabled:cursor-not-allowed disabled:opacity-50 disabled:hover:bg-transparent',
        className
      )}
    >
      {children}
    </button>
  )
}
