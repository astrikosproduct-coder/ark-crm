import { useState } from 'react'
import {
  AlignLeftIcon,
  CalendarIcon,
  CheckSquareIcon,
  ChevronDownIcon,
  CircleDollarSignIcon,
  FunctionSquareIcon,
  GripVerticalIcon,
  HashIcon,
  LinkIcon,
  ListIcon,
  ListChecksIcon,
  MailIcon,
  MoreHorizontalIcon,
  PercentIcon,
  SearchIcon,
  TableIcon,
  TextIcon,
  TypeIcon,
} from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { FieldDialog } from './FieldDialog'
import { ErrorBox, LoadingRow } from './shared'
import { errorMessage } from '@/lib/admin'
import {
  FIELD_TYPES,
  useMetadataFields,
  useMetadataModules,
  useMetadataSections,
  useRemovePlacement,
  useReorderFields,
  useSetFieldRequired,
  type MetadataField,
} from '@/lib/metadata'
import { arrangeAnchoredWith, childrenByAnchor, type AnchoredNode } from '@/lib/spec/anchors'
import { cn } from '@/lib/utils'

/**
 * The form, as the form draws it, with editing chrome over the top.
 *
 * WHY THIS EXISTS ALONGSIDE THE FIELDS TAB
 * -----------------------------------------
 * The Fields tab is a table: every property of every row, dense, filterable,
 * the right tool for "what does the register say about licence_model". It is
 * the wrong tool for "what will BD actually see", and that is the question
 * this prototype is built to answer. A table cannot show that On Hold Reason
 * draws underneath Lead Status, that a field takes the full row, or that a
 * section has two visible fields and eleven conditional ones.
 *
 * IT ARRANGES WITH THE FORM'S OWN CODE
 * -------------------------------------
 * arrangeAnchoredWith() in lib/spec/anchors.ts is the same function
 * RecordForm's FormSection calls. The canvas passes DRAFT rows and the record
 * screen passes published ones; neither has a layout algorithm of its own. A
 * canvas that quietly disagreed with the form would be worse than no canvas —
 * a picture people trust and shouldn't.
 *
 * WHAT IT DELIBERATELY IS NOT
 * ----------------------------
 * A live form. The cells draw a type icon and a label, the way Zoho's builder
 * does, not working inputs. Rendering real controls would mean running the
 * whole form engine — conditions, formulas, per-stage projection — against a
 * record that does not exist, and every one of those needs values to mean
 * anything. What the canvas is FOR is position, and position it draws exactly.
 *
 * There is no Save / Cancel pair either, and its absence is not an oversight.
 * Every edit here writes to the draft immediately, exactly as the Fields tab
 * does; the staged Save the reference screens show would be a promise this
 * model does not make. The draft banner above says what is unpublished, and
 * Publish is the button that matters.
 */

/** A type icon per field type, so a cell reads at a glance the way Zoho's do. */
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

function iconFor(type: string) {
  return TYPE_ICON[type] ?? TextIcon
}

export function LayoutTab() {
  const { data: modules = [], isLoading, isError, error } = useMetadataModules()
  const [moduleKey, setModuleKey] = useState('leads')
  const [dialog, setDialog] = useState<{
    open: boolean
    field?: MetadataField
    sectionId?: number
  }>({ open: false })

  const { data: sections = [] } = useMetadataSections(moduleKey)
  const { data: fields = [] } = useMetadataFields(moduleKey, 'active')

  if (isLoading) return <LoadingRow what="modules" />
  if (isError) return <ErrorBox error={error} />

  const activeSections = sections.filter((s) => s.active)

  return (
    <>
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <select
          className="border-input bg-input-bg h-9 rounded-md border px-2 text-sm"
          value={moduleKey}
          onChange={(e) => setModuleKey(e.target.value)}
        >
          {modules.map((m) => (
            <option key={m.module_key} value={m.module_key}>
              {m.label} ({m.field_count})
            </option>
          ))}
        </select>
        <p className="text-muted-foreground text-xs">
          The form as the record screen draws it &mdash; same arrangement code, same
          anchors, same full-width rule. Drag a type from the left into a section, or drag a
          field to move it.
        </p>
      </div>

      <div className="flex gap-4">
        <NewFieldsPalette />

        <div className="min-w-0 flex-1 space-y-4">
          {activeSections.length === 0 ? (
            <p className="text-muted-foreground py-8 text-sm">
              This module has no sections yet. Add one on the Fields tab before laying
              anything out.
            </p>
          ) : (
            activeSections.map((section) => (
              <CanvasSection
                key={section.id}
                moduleKey={moduleKey}
                sectionId={section.id}
                label={section.label}
                fields={fields}
                onEdit={(field) => setDialog({ open: true, field })}
                onAdd={(sectionId) => setDialog({ open: true, sectionId })}
              />
            ))
          )}
        </div>
      </div>

      <FieldDialog
        open={dialog.open}
        onOpenChange={(open) => setDialog({ open })}
        moduleKey={moduleKey}
        field={dialog.field}
        sectionId={dialog.sectionId}
      />
    </>
  )
}

/**
 * The palette of field types.
 *
 * Dragging one onto a section opens the Add field dialog with that type and
 * that section already chosen. It does NOT create the field on drop: an
 * api_name is the key every record stores its value under and cannot be
 * guessed from a drag, and a field created with a generated name would be a
 * field somebody has to rename later, which the API refuses.
 */
function NewFieldsPalette() {
  return (
    <div className="w-52 shrink-0">
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
                e.dataTransfer.setData('application/x-ark-new-field', type)
                // Firefox drops a drag with no text/plain attached.
                e.dataTransfer.setData('text/plain', type)
              }}
              className="border-input bg-input-bg flex cursor-grab items-center gap-1.5 rounded-md border px-2 py-1.5 text-xs active:cursor-grabbing"
              title={`Drag a ${type} field into a section`}
            >
              <Icon className="text-muted-foreground size-3.5 shrink-0" />
              <span className="truncate">{type}</span>
            </div>
          )
        })}
      </div>
      <p className="text-muted-foreground mt-2 text-xs">
        Dropping one opens Add field with the type and section filled in. The api_name is
        yours to choose &mdash; it is the key every record stores its value under, and it
        can never be changed afterwards.
      </p>
    </div>
  )
}

function CanvasSection({
  moduleKey,
  sectionId,
  label,
  fields,
  onEdit,
  onAdd,
}: {
  moduleKey: string
  sectionId: number
  label: string
  fields: MetadataField[]
  onEdit: (field: MetadataField) => void
  onAdd: (sectionId: number) => void
}) {
  const reorder = useReorderFields()
  const [open, setOpen] = useState(true)
  const [dragIndex, setDragIndex] = useState<number | null>(null)
  const [overIndex, setOverIndex] = useState<number | null>(null)
  const [dropActive, setDropActive] = useState(false)
  const [error, setError] = useState<string | null>(null)

  /**
   * This section's own rows, in register order.
   *
   * Filed by section_id, NOT by where a field draws: an anchored field keeps
   * its own section — that disagreement is the whole design — and the walk
   * below is what puts it under its anchor. A field anchored into another
   * section therefore appears on the canvas twice over the two sections only
   * if its anchor is elsewhere, which arrangeAnchoredWith resolves by leaving
   * it in its own list.
   */
  const rows = [...fields]
    .filter((f) => f.section_id === sectionId)
    .sort((a, b) => (a.sort_order ?? 0) - (b.sort_order ?? 0))

  const nodes = arrangeAnchoredWith(rows, childrenByAnchor(rows))

  /** Reorder within the module's own ordering — the same call the table makes. */
  const moveCell = (from: number, to: number) => {
    if (from === to) return
    const cells = nodes.map((n) => n.field)
    const next = [...cells]
    const [moved] = next.splice(from, 1)
    next.splice(to, 0, moved)
    // Only the CELLS are reordered. An anchored child travels inside its
    // anchor's cell and has no position of its own to send — moving it out
    // from under its question is what the anchor exists to prevent.
    const others = fields.filter((f) => !next.some((n) => n.id === f.id))
    reorder.mutate(
      [...next, ...others]
        .sort((a, b) =>
          next.includes(a) && next.includes(b)
            ? next.indexOf(a) - next.indexOf(b)
            : (a.sort_order ?? 0) - (b.sort_order ?? 0)
        )
        .map((f) => f.id),
      { onError: (err) => setError(errorMessage(err)) }
    )
  }

  return (
    <div
      className={cn(
        'rounded-lg border',
        dropActive && 'ring-primary/50 ring-2'
      )}
      onDragOver={(e) => {
        if (!e.dataTransfer.types.includes('application/x-ark-new-field')) return
        e.preventDefault()
        e.dataTransfer.dropEffect = 'copy'
        setDropActive(true)
      }}
      onDragLeave={() => setDropActive(false)}
      onDrop={(e) => {
        const type = e.dataTransfer.getData('application/x-ark-new-field')
        setDropActive(false)
        if (!type) return
        e.preventDefault()
        onAdd(sectionId)
      }}
    >
      <div className="flex items-center gap-2 border-b px-3 py-2">
        <button
          type="button"
          onClick={() => setOpen((v) => !v)}
          className="text-muted-foreground hover:text-foreground"
          aria-label={open ? 'Collapse section' : 'Expand section'}
        >
          <ChevronDownIcon
            className={cn('size-4 transition-transform', !open && '-rotate-90')}
          />
        </button>
        <span className="text-section text-sm font-bold tracking-wide">{label}</span>
        <span className="text-muted-foreground text-xs">
          {nodes.length} {nodes.length === 1 ? 'cell' : 'cells'}
        </span>
        <Button
          size="sm"
          variant="ghost"
          className="ml-auto"
          onClick={() => onAdd(sectionId)}
        >
          Add field
        </Button>
      </div>

      {error && (
        <p className="text-destructive border-b px-3 py-2 text-xs">{error}</p>
      )}

      {open && (
        <div className="grid gap-x-4 gap-y-2 px-3 py-3 md:grid-cols-2">
          {nodes.length === 0 ? (
            <p className="text-muted-foreground text-sm md:col-span-2">
              Nothing here yet. Drag a type from the left, or use Add field.
            </p>
          ) : (
            nodes.map((node, index) => (
              <div
                key={node.field.id}
                className={cn(
                  node.field.layout_span === 'full' && 'md:col-span-2',
                  overIndex === index &&
                    dragIndex !== null &&
                    dragIndex !== index &&
                    'rounded-md shadow-[inset_0_0_0_2px] shadow-primary/50'
                )}
                onDragOver={(e) => {
                  if (dragIndex === null) return
                  e.preventDefault()
                  e.dataTransfer.dropEffect = 'move'
                  if (overIndex !== index) setOverIndex(index)
                }}
                onDragLeave={() =>
                  setOverIndex((cur) => (cur === index ? null : cur))
                }
                onDrop={(e) => {
                  if (dragIndex === null) return
                  e.preventDefault()
                  e.stopPropagation()
                  moveCell(dragIndex, index)
                  setDragIndex(null)
                  setOverIndex(null)
                }}
              >
                <CanvasCell
                  node={node}
                  moduleKey={moduleKey}
                  onEdit={onEdit}
                  onDragStart={() => setDragIndex(index)}
                  onDragEnd={() => {
                    setDragIndex(null)
                    setOverIndex(null)
                  }}
                />
              </div>
            ))
          )}
        </div>
      )}
    </div>
  )
}

/**
 * One cell: the field, plus whatever is anchored beneath it in the same cell.
 *
 * The stacked children are drawn indented under a rule, which is how the real
 * form draws them — a reason box belongs to the question above it, and the
 * indent is what says so.
 */
function CanvasCell({
  node,
  moduleKey,
  onEdit,
  onDragStart,
  onDragEnd,
}: {
  node: AnchoredNode<MetadataField>
  moduleKey: string
  onEdit: (field: MetadataField) => void
  onDragStart?: () => void
  onDragEnd?: () => void
}) {
  return (
    <div className="space-y-1.5">
      <FieldChip
        field={node.field}
        moduleKey={moduleKey}
        onEdit={onEdit}
        onDragStart={onDragStart}
        onDragEnd={onDragEnd}
      />
      {node.under.length > 0 && (
        <div className="border-muted-foreground/25 ml-3 space-y-1.5 border-l pl-3">
          {node.under.map((kid) => (
            <CanvasCell
              key={kid.field.id}
              node={kid}
              moduleKey={moduleKey}
              onEdit={onEdit}
            />
          ))}
        </div>
      )}
    </div>
  )
}

function FieldChip({
  field,
  moduleKey,
  onEdit,
  onDragStart,
  onDragEnd,
}: {
  field: MetadataField
  moduleKey: string
  onEdit: (field: MetadataField) => void
  onDragStart?: () => void
  onDragEnd?: () => void
}) {
  const setRequired = useSetFieldRequired()
  const removePlacement = useRemovePlacement()
  const [menuOpen, setMenuOpen] = useState(false)
  const Icon = iconFor(field.field_type)
  const draggable = Boolean(onDragStart)

  return (
    <div
      className={cn(
        'group border-input bg-input-bg flex items-center gap-2 rounded-md border px-2 py-2',
        // Zoho marks a mandatory field with a red bar down its left edge, and
        // it is the fastest thing to read on the whole screen.
        field.required && 'border-l-destructive border-l-2'
      )}
    >
      {draggable && (
        <button
          type="button"
          draggable
          onDragStart={(e) => {
            e.dataTransfer.effectAllowed = 'move'
            e.dataTransfer.setData('text/plain', field.api_name)
            onDragStart?.()
          }}
          onDragEnd={onDragEnd}
          className="text-muted-foreground/30 hover:text-foreground cursor-grab opacity-0 transition-opacity group-hover:opacity-100 active:cursor-grabbing"
          aria-label={`Reorder ${field.label}`}
          title="Drag to reorder within this section"
        >
          <GripVerticalIcon className="size-4" />
        </button>
      )}

      <span title={field.field_type} className="shrink-0">
        <Icon className="text-muted-foreground size-4" />
      </span>

      <div className="min-w-0 flex-1">
        <div className="truncate text-sm">{field.label}</div>
        <div className="text-muted-foreground truncate font-mono text-[11px]">
          {field.api_name}
          {field.anchor_field && ` · ${field.anchor_position} ${field.anchor_field}`}
          {field.stage_scoped !== 'none' && ` · per stage (${field.stage_scoped})`}
          {!field.editable && ' · read-only'}
        </div>
      </div>

      {/* Built on Popover rather than a dropdown-menu primitive: the project
          has no @radix-ui/react-dropdown-menu and one menu is not worth a new
          dependency. Three buttons in a popover behave the same way. */}
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
          <MenuItem
            onClick={() => {
              setMenuOpen(false)
              onEdit(field)
            }}
          >
            Edit properties&hellip;
          </MenuItem>
          <MenuItem
            onClick={() => {
              setMenuOpen(false)
              setRequired.mutate({
                placementId: field.placement_id,
                required: !field.required,
              })
            }}
          >
            {field.required ? 'Mark not required' : 'Mark required'}
          </MenuItem>
          <div className="bg-border my-1 h-px" />
          <MenuItem
            className="text-destructive"
            onClick={() => {
              setMenuOpen(false)
              removePlacement.mutate(field.placement_id)
            }}
          >
            Remove from {moduleKey}
            <span className="text-muted-foreground block text-xs">
              Off this module only. The column and every value in it survive.
            </span>
          </MenuItem>
        </PopoverContent>
      </Popover>
    </div>
  )
}

/** One row of the ··· menu. A button, styled the way a menu item reads. */
function MenuItem({
  children,
  onClick,
  className,
}: {
  children: React.ReactNode
  onClick: () => void
  className?: string
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        'hover:bg-accent w-full rounded-sm px-2 py-1.5 text-left text-sm',
        className
      )}
    >
      {children}
    </button>
  )
}
