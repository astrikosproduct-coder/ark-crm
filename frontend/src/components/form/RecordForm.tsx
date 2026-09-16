import { useMemo, useState } from 'react'
import { ChevronDownIcon } from 'lucide-react'

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

/**
 * One section of the register, rendered as a two-column grid of fields.
 *
 * FIELD ORDER COMES FROM THE REGISTER, AND ONLY FROM THERE (B1)
 * -------------------------------------------------------------
 * This component used to let a user drag fields around, and stored the result
 * in localStorage under `arkcrm-field-layout`, keyed `module::section`. It was
 * layered ON TOP of the register's own order, so the two disagreed by design:
 * Administration's reorder writes `field_placements.sort_order` through
 * POST /placements/reorder and is real, shared and published, and a stray drag
 * on one record screen silently outranked it — in that one browser, invisibly
 * to everyone else, including whoever had just done the reorder properly.
 *
 * Two places to arrange one form is the same defect as two places to write one
 * answer, which extensions.json already documents rejecting for Stage Skip
 * Reason. Reordering is an administrative act; it belongs on the screen whose
 * job that is, where it can be reviewed and published.
 *
 * The store is deleted rather than disabled. Its own `clearAll()` claimed to
 * keep "Reset demo data" from leaving a stale order behind and was called by
 * nothing, so a reset already left one.
 */
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

  const all = visibleFieldsOf(form, module, section, hiddenFields)
  const fields = only
    ? only.map((name) => all.find((f) => f.api_name === name)).filter((f): f is FieldSpec => Boolean(f))
    : all
  // Anchored fields draw next to the field they answer rather than at their own
  // position in this list — see lib/spec/anchors.ts. `only` stays flat: it names
  // an explicit order (a quick-create dialog's handful of fields), and an anchor
  // rearranging it would be fighting the caller.
  const nodes = only
    ? fields.map((field) => ({ field, under: [] }) as FormNode)
    : arrangeAnchored(module, fields)
  const errorCount = fields.filter((f) => form.visibleErrors[f.api_name]).length

  // A section with nothing to show is not worth a header, in either mode —
  // Accounts' PARTNER ATTRIBUTES is hidden whole when no field in it applies.
  if (nodes.length === 0) return null

  return (
    // A SURFACE, not a box. No outer border: the card's own background lifts it
    // off the canvas (and in light mode a soft shadow does the rest), which is
    // the whole elevation system — see index.css. The header separates by
    // weight and by the space around it rather than by a rule.
    <Collapsible
      open={open}
      onOpenChange={setOpen}
      className="bg-card rounded-lg shadow-sm"
    >
      <CollapsibleTrigger className="flex w-full items-center gap-2 px-6 pt-5 pb-1 text-left">
        <ChevronDownIcon
          className={cn(
            'text-muted-foreground size-4 shrink-0 transition-transform',
            !open && '-rotate-90'
          )}
        />
        <span className="text-page-title font-bold tracking-tight">{title ?? section}</span>
        {errorCount > 0 && (
          <Badge variant="destructive" className="ml-auto">
            {errorCount}
          </Badge>
        )}
      </CollapsibleTrigger>

      <CollapsibleContent>
        {/* Roomier than it was, because the rows are label-beside-value now and
            the reference gives each one about 40px of rhythm — §3.3.
            A CONTAINER, and the columns answer to its width rather than the
            window's: the same section renders full width on a record page and
            inside a 672px quick-create dialog, and only the first of those has
            room for two columns of label-plus-value. FieldRow reads the same
            container to decide whether its label sits beside the value.

            The container is a WRAPPER, not the grid. A container query only
            ever measures an ANCESTOR, so `@container` and `@3xl:grid-cols-2`
            on the same element meant the grid could never see its own width:
            the two-column rule never matched, every section rendered as one
            column, and every picklist stretched the full section. */}
        <div className="@container">
        {/* grid-cols-1 and *:min-w-0: a grid cell is otherwise never narrower
            than its content, so a child table wider than the column pushed the
            cell — and the whole page — sideways instead of scrolling inside
            its own overflow box. With no column template at all, the one
            implicit column grew to the table's width the same way. */}
        <div className="grid grid-cols-1 gap-x-10 gap-y-5 px-6 pt-4 pb-7 *:min-w-0 [--ark-form-label:9rem] @3xl:grid-cols-2">
          {nodes.map((node) => (
            <AnchorCell
              key={node.field.qref}
              node={node}
              className={cn(nodeSpansFullWidth(node, FULL_WIDTH) && '@3xl:col-span-2')}
              onCreateNew={onCreateNew}
            />
          ))}
        </div>
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

  // Whether this cell occupies the whole row. The stack below it may only lay
  // its children out in two columns when it does — inside a half-width cell
  // there is no second column to put one in, and the section-level @3xl
  // breakpoint measures the SECTION, so it cannot tell the difference.
  const wide = nodeSpansFullWidth(node, FULL_WIDTH)

  return (
    // A GRID, so the anchor keeps its own width when the CELL was widened for
    // something else. nodeSpansFullWidth is true if the anchor OR anything
    // stacked under it needs the row, and the cell was then laid out as a flex
    // column — which stretched the anchor to the full two columns as a side
    // effect of a child's requirement. Agreed Next Step is a plain picklist
    // with no layout_span at all, and it rendered as a select twice the width
    // of Interest Level directly above it, purely because the file link
    // anchored beneath it is marked `full`.
    //
    // As a two-column grid the anchor takes one column like any other field,
    // and only the things that actually asked for the row get it.
    <div className={cn('grid grid-cols-1 gap-x-10 gap-y-4 *:min-w-0', wide && '@3xl:grid-cols-2', className)}>
      <FieldRow field={node.field} onCreateNew={onCreateNew} />
      {/* Ruled and indented, so the stack reads as "these belong to the field
          above" rather than as unrelated boxes that happen to sit close.
          `--ark-form-label` is narrowed by exactly what the rule and its
          padding consume (0.75rem + 2px), which is what keeps a nested row's
          VALUE on the same x as every unnested value in the section — see the
          note in FieldRow. One level is enough: no anchored field in any module
          is itself an anchor target, so the stacks are never nested.

          A GRID, NOT A COLUMN, when the cell is wide. These children carry
          their own layout_span and it was being thrown away: Pilot Commercial
          Model and Pilot Fee are both declared `half` in the register, and a
          flex column rendered them one above the other at DOUBLE width, each
          filling a two-column cell. Two halves now sit side by side, which is
          what the admin asked for in the layout canvas. */}
      <div
        className={cn(
          'border-muted-foreground/25 gap-x-10 gap-y-4 border-l-2 pl-3 [--ark-form-label:calc(9rem_-_0.875rem)]',
          wide ? 'grid grid-cols-1 *:min-w-0 @3xl:col-span-2 @3xl:grid-cols-2' : 'flex min-w-0 flex-col'
        )}
      >
        {node.under.map((child) => (
          <AnchorCell
            key={child.field.qref}
            node={child}
            className={cn(
              wide && nodeSpansFullWidth(child, FULL_WIDTH) && '@3xl:col-span-2'
            )}
            onCreateNew={onCreateNew}
          />
        ))}
      </div>
    </div>
  )
}
