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
} from '@/hooks/useRecordForm'
import { sectionsFor } from '@/lib/spec'
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
    >
      <RecordFormBody module={module} sections={sections} onCreateNew={onCreateNew} footer={footer} />
    </RecordFormProvider>
  )
}

function RecordFormBody({
  module,
  sections,
  onCreateNew,
  footer,
}: {
  module: string
  sections?: string[]
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
  onCreateNew,
  defaultOpen = true,
  only,
  title,
}: {
  module: string
  section: string
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

  const all = visibleFieldsOf(form, module, section)
  const naturalFields = only
    ? only.map((name) => all.find((f) => f.api_name === name)).filter((f): f is FieldSpec => Boolean(f))
    : all
  // `only` names an explicit subset in an explicit order (a quick-create
  // dialog's handful of fields) — the drag preference is for a real section,
  // so it is skipped there rather than fighting that order.
  const fields = only ? naturalFields : applyFieldOrder(naturalFields, storedOrder)
  const errorCount = fields.filter((f) => form.visibleErrors[f.api_name]).length
  // Dragging reorders array positions, which needs at least two fields to
  // mean anything, and never leaves this section — the drop handler only
  // ever permutes `fields`, the same array the section already renders.
  const draggable = !only && fields.length > 1

  // A section with nothing to show in view mode is not worth a header.
  if (fields.length === 0 && form.mode === 'view') return null

  const dropOn = (index: number) => {
    if (dragIndex === null || dragIndex === index) {
      setDragIndex(null)
      setOverIndex(null)
      return
    }
    const next = [...fields]
    const [moved] = next.splice(dragIndex, 1)
    next.splice(index, 0, moved)
    setStoredOrder(module, section, next.map((f) => f.api_name))
    setDragIndex(null)
    setOverIndex(null)
  }

  return (
    <Collapsible open={open} onOpenChange={setOpen} className="rounded-lg border">
      <CollapsibleTrigger className="flex w-full items-center gap-2 px-4 py-3 text-left">
        <ChevronDownIcon
          className={cn('size-4 shrink-0 transition-transform', !open && '-rotate-90')}
        />
        <span className="text-sm font-semibold tracking-wide">{title ?? section}</span>
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
          {fields.length === 0 ? (
            <p className="text-sm text-muted-foreground md:col-span-2">
              Every field in this section is hidden by a visibility condition.
            </p>
          ) : (
            fields.map((field, index) =>
              draggable ? (
                <div
                  key={field.qref}
                  className={cn(
                    'group flex items-start gap-1 rounded-md transition-shadow',
                    FULL_WIDTH.has(field.type) && 'md:col-span-2',
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
                      e.dataTransfer.setData('text/plain', field.api_name)
                    }}
                    onDragEnd={() => {
                      setDragIndex(null)
                      setOverIndex(null)
                    }}
                    className="mt-1.5 shrink-0 cursor-grab touch-none text-muted-foreground/30 opacity-0 transition-opacity hover:text-foreground group-hover:opacity-100 active:cursor-grabbing"
                    title="Drag to reorder within this section"
                    aria-label={`Reorder ${field.label}`}
                  >
                    <GripVerticalIcon className="size-4" />
                  </button>
                  <div className="min-w-0 flex-1">
                    <FieldRow field={field} onCreateNew={onCreateNew} />
                  </div>
                </div>
              ) : (
                <FieldRow key={field.qref} field={field} onCreateNew={onCreateNew} />
              )
            )
          )}
        </div>
      </CollapsibleContent>
    </Collapsible>
  )
}
