import { useMemo, useState } from 'react'
import { ChevronDownIcon, GripVerticalIcon } from 'lucide-react'

import { Badge } from '@/components/ui/badge'
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from '@/components/ui/collapsible'
import { FieldRow, FULL_WIDTH } from '@/components/form/FieldRow'
import {
  RecordFormProvider,
  useRecordForm,
  visibleFieldsOf,
  type FormMode,
  type StageScope,
} from '@/hooks/useRecordForm'
import { sectionsFor } from '@/lib/spec'
import {
  arrangeAnchored,
  nodeSpansFullWidth,
  type FormNode,
} from '@/lib/spec/anchors'
import type { Values } from '@/lib/spec/conditions'
import type { Children } from '@/lib/spec/formula'
import type { ResolvedRecord } from '@/lib/spec/resolveRecord'
import { applyFieldOrder, useFieldLayoutStore, useFieldOrder } from '@/store/useFieldLayoutStore'
import { cn } from '@/lib/utils'
import type { FieldSpec } from '@/types/field'

export interface RecordFormProps {
  module: string
  mode: FormMode
  values?: Values
  children?: Children
  /** The parent chain, for a module whose identity is read through one. */
  resolved?: ResolvedRecord
  /** Render only these sections, in this order. Defaults to all of them. */
  sections?: string[]
  /**
   * api_names this screen draws somewhere else and must not draw twice — see
   * visibleFieldsOf. A pipeline record's stage strip and sticky panel use it.
   */
  hiddenFields?: ReadonlySet<string>
  /** This form shows ONE STAGE of a pipeline record — see useRecordForm. */
  stageScope?: StageScope
  onCreateNew?: (field: FieldSpec) => void
  footer?: React.ReactNode
}

/**
 * Renders a whole record from the spec. Nothing about which fields appear, in
 * what order, in which section, or how they behave is written here — it all
 * comes from spec/fields.json plus spec/extensions.json.
 */
export function RecordForm({
  module,
  mode,
  values,
  children,
  resolved,
  sections,
  hiddenFields,
  stageScope,
  onCreateNew,
  footer,
}: RecordFormProps) {
  return (
    <RecordFormProvider
      module={module}
      mode={mode}
      initialValues={values}
      initialChildren={children}
      resolved={resolved}
      stageScope={stageScope}
    >
      <RecordFormBody
        module={module}
        sections={sections}
        hiddenFields={hiddenFields}
        onCreateNew={onCreateNew}
        footer={footer}
      />
    </RecordFormProvider>
  )
}

function RecordFormBody({
  module,
  sections,
  hiddenFields,
  onCreateNew,
  footer,
}: {
  module: string
  sections?: string[]
  hiddenFields?: ReadonlySet<string>
  onCreateNew?: (field: FieldSpec) => void
  footer?: React.ReactNode
}) {
  const list = useMemo(() => sections ?? sectionsFor(module), [module, sections])

  return (
    <div className="space-y-3">
      {list.map((section) => (
        <FormSection
          key={section}
          module={module}
          section={section}
          hiddenFields={hiddenFields}
          onCreateNew={onCreateNew}
        />
      ))}
      {footer}
    </div>
  )
}

export function FormSection({
  module,
  section,
  hiddenFields,
  onCreateNew,
  defaultOpen = true,
  only,
  title,
}: {
  module: string
  section: string
  /** api_names the screen renders elsewhere — see visibleFieldsOf. */
  hiddenFields?: ReadonlySet<string>
  onCreateNew?: (field: FieldSpec) => void
  defaultOpen?: boolean
  /**
   * Render only these api_names, in this order. A section of the register can
   * describe more than one screen — DEAL REGISTRATION holds both the seven
   * fields a partner submits and the five ARK stamps on acknowledgement — and
   * the subset is named in spec/extensions.json, never here.
   */
  only?: string[]
  /** Overrides the register's section name in the header. */
  title?: string
}) {
  const form = useRecordForm()
  const [open, setOpen] = useState(defaultOpen)
  const storedOrder = useFieldOrder(module, section)
  const setStoredOrder = useFieldLayoutStore((s) => s.setOrder)
  const [dragIndex, setDragIndex] = useState<number | null>(null)
  const [overIndex, setOverIndex] = useState<number | null>(null)

  const all = visibleFieldsOf(form, module, section, hiddenFields)
  const naturalFields = only
    ? only.map((name) => all.find((f) => f.api_name === name)).filter((f): f is FieldSpec => Boolean(f))
    : all
  // `only` names an explicit subset in an explicit order (a quick-create
  // dialog's handful of fields) — the drag preference is for a real section,
  // so it is skipped there rather than fighting that order.
  const fields = only ? naturalFields : applyFieldOrder(naturalFields, storedOrder)
  // Anchored fields draw next to the field they answer rather than at their own
  // position in this list — see lib/spec/anchors.ts. `only` stays flat: it names
  // an explicit order, and an anchor rearranging it would be fighting the
  // caller. Roots keep the position `fields` gave them, drag order included.
  const nodes = only
    ? naturalFields.map((field) => ({ field, under: [] }) as FormNode)
    : arrangeAnchored(module, fields)
  const errorCount = fields.filter((f) => form.visibleErrors[f.api_name]).length
  // Dragging reorders CELLS, which needs at least two to mean anything, and
  // never leaves this section — the drop handler only ever permutes `nodes`,
  // the same array the section already renders. An anchored field is not a
  // cell of its own; it travels with the field it is anchored to, which is
  // what an anchor means.
  const draggable = !only && nodes.length > 1

  // A section with nothing to show in view mode is not worth a header.
  if (nodes.length === 0 && form.mode === 'view') return null

  const dropOn = (index: number) => {
    if (dragIndex === null || dragIndex === index) {
      setDragIndex(null)
      setOverIndex(null)
      return
    }
    const next = [...nodes]
    const [moved] = next.splice(dragIndex, 1)
    next.splice(index, 0, moved)
    // Only the cells' own fields are stored. Anchored children are left for
    // applyFieldOrder to append and for arrangeAnchored to put back under
    // their anchor, so a drag can never separate a reason from its question.
    setStoredOrder(module, section, next.map((n) => n.field.api_name))
    setDragIndex(null)
    setOverIndex(null)
  }

  return (
    <Collapsible open={open} onOpenChange={setOpen} className="rounded-lg border">
      <CollapsibleTrigger className="flex w-full items-center gap-2 px-4 py-3 text-left">
        <ChevronDownIcon
          className={cn('size-4 shrink-0 transition-transform', !open && '-rotate-90')}
        />
        <span className="text-section font-bold tracking-wide">{title ?? section}</span>
        <span className="text-xs text-muted-foreground">
          {fields.length} {fields.length === 1 ? 'field' : 'fields'}
        </span>
        {errorCount > 0 && (
          <Badge variant="destructive" className="ml-auto">
            {errorCount}
          </Badge>
        )}
      </CollapsibleTrigger>

      <CollapsibleContent>
        <div className="grid gap-x-6 gap-y-4 border-t px-4 py-4 md:grid-cols-2">
          {nodes.length === 0 ? (
            <p className="text-sm text-muted-foreground md:col-span-2">
              {/* Two different reasons a section can come up empty, and since
                  anchors the second one is common: CROSS-CUTTING on a pipeline
                  record now has all five of its fields drawn somewhere else —
                  two beside the status field, three on their own surfaces. */}
              Nothing to fill in here. Every field in this section is either hidden by a
              visibility condition or shown elsewhere on this screen.
            </p>
          ) : (
            nodes.map((node, index) =>
              draggable ? (
                <div
                  key={node.field.qref}
                  className={cn(
                    'group flex items-start gap-1 rounded-md transition-shadow',
                    nodeSpansFullWidth(node, FULL_WIDTH) && 'md:col-span-2',
                    overIndex === index && dragIndex !== null && dragIndex !== index &&
                      'shadow-[inset_0_0_0_2px] shadow-primary/50'
                  )}
                  onDragOver={(e) => {
                    e.preventDefault()
                    e.dataTransfer.dropEffect = 'move'
                    if (overIndex !== index) setOverIndex(index)
                  }}
                  onDragLeave={() => setOverIndex((cur) => (cur === index ? null : cur))}
                  onDrop={(e) => {
                    e.preventDefault()
                    dropOn(index)
                  }}
                >
                  <button
                    type="button"
                    draggable
                    onDragStart={(e) => {
                      setDragIndex(index)
                      e.dataTransfer.effectAllowed = 'move'
                      // Firefox drops a drag with no data attached.
                      e.dataTransfer.setData('text/plain', node.field.api_name)
                    }}
                    onDragEnd={() => {
                      setDragIndex(null)
                      setOverIndex(null)
                    }}
                    className="mt-1.5 shrink-0 cursor-grab touch-none text-muted-foreground/30 opacity-0 transition-opacity hover:text-foreground group-hover:opacity-100 active:cursor-grabbing"
                    title="Drag to reorder within this section"
                    aria-label={`Reorder ${node.field.label}`}
                  >
                    <GripVerticalIcon className="size-4" />
                  </button>
                  <div className="min-w-0 flex-1">
                    <AnchorCell node={node} onCreateNew={onCreateNew} />
                  </div>
                </div>
              ) : (
                <AnchorCell
                  key={node.field.qref}
                  node={node}
                  className={cn(nodeSpansFullWidth(node, FULL_WIDTH) && 'md:col-span-2')}
                  onCreateNew={onCreateNew}
                />
              )
            )
          )}
        </div>
      </CollapsibleContent>
    </Collapsible>
  )
}

/**
 * One grid cell: a field, and whatever is anchored 'after' it stacked beneath.
 *
 * The stack is what makes a conditional field usable. The reason box opens
 * directly under the status that revealed it, INSIDE THE SAME FORM, reading the
 * same live values — so it appears the instant the picklist changes, and one
 * Save writes both. See lib/spec/anchors.ts.
 *
 * `under` is empty for all but a handful of fields, and an empty stack renders
 * exactly the bare FieldRow it always did.
 */
function AnchorCell({
  node,
  className,
  onCreateNew,
}: {
  node: FormNode
  className?: string
  onCreateNew?: (field: FieldSpec) => void
}) {
  if (node.under.length === 0) {
    return <FieldRow field={node.field} onCreateNew={onCreateNew} className={className} />
  }

  return (
    <div className={cn('flex flex-col gap-4', className)}>
      <FieldRow field={node.field} onCreateNew={onCreateNew} />
      {/* Ruled and indented, so the stack reads as "these belong to the field
          above" rather than as unrelated boxes that happen to sit close. */}
      <div className="border-muted-foreground/25 flex flex-col gap-4 border-l-2 pl-3">
        {node.under.map((child) => (
          <AnchorCell key={child.field.qref} node={child} onCreateNew={onCreateNew} />
        ))}
      </div>
    </div>
  )
}
