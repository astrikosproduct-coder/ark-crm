import { InfoIcon } from 'lucide-react'

import { Label } from '@/components/ui/label'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { FieldControl } from '@/components/form/FieldControl'
import { useRecordForm } from '@/hooks/useRecordForm'
import { spansFullWidth } from '@/lib/spec/anchors'
import { cn } from '@/lib/utils'
import type { FieldSpec } from '@/types/field'

interface Props {
  field: FieldSpec
  onCreateNew?: (field: FieldSpec) => void
  /**
   * Grid placement supplied by the caller, when the caller knows better than
   * the field's type does. FormSection passes the cell's span; an anchored
   * field stacked inside another field's cell passes nothing, because it has
   * that cell's width already. See lib/spec/anchors.ts.
   */
  className?: string
}

/**
 * Types that own the full width of the section grid. Only a table: every other
 * value, a paragraph box included, stays inside its own column so a section
 * reads as two even halves.
 */
export const FULL_WIDTH = new Set(['childlist'])

export function FieldRow({ field, onCreateNew, className }: Props) {
  const form = useRecordForm()
  const id = `${field.module}.${field.api_name}`
  const error = form.visibleErrors[field.api_name]
  // Shown only when the value is not ALSO malformed — "Must be a date" and
  // "This is a required field." on the same field would be one message too many,
  // and the shape error is the more specific of the two.
  const missing = !error ? form.visibleRequired[field.api_name] : undefined
  const required = form.isRequired(field)

  return (
    <div
      // The anchor the readiness drawer scrolls to — see lib/revealField.ts.
      // Every field carries it, so anything that can name a field can send the
      // user to it without that field's screen knowing anything about it.
      data-field={field.api_name}
      className={cn(
        // Label beside the value, not above it — the reference's record and
        // edit screens both read as a column of right-aligned labels against a
        // column of values (ARK_brand_UI.md §3.3). The breakpoint is the
        // SECTION's width, not the window's (see FormSection): a 9rem label
        // column plus a usable input needs room, and a field in a quick-create
        // dialog has less of it than the same field on a record page.
        //
        // THE LABEL COLUMN IS A VARIABLE, NOT A LITERAL, and that is what keeps
        // every value in a section on ONE x. A row nested inside the ruled
        // indent of an anchor stack starts 0.875rem to the right of an ordinary
        // row, so with a fixed 9rem label column its value landed 0.875rem off
        // every value above it — visible on any Stage 1 lead as Pilot
        // Commercial Model sitting proud of Agreed Next Step. The indent
        // narrows this variable by exactly what it consumed, so the ruled
        // group keeps its meaning and the column keeps its line. Default here
        // rather than only on FormSection, because a quick-create dialog
        // renders FieldRow without one.
        'grid gap-x-4 gap-y-1.5 @lg:grid-cols-[minmax(0,var(--ark-form-label,9rem))_minmax(0,1fr)] @lg:items-start',
        // Only a table takes the whole row — see spansFullWidth,
        // which reads the TYPE and not the placement's layout_span.
        spansFullWidth(field, FULL_WIDTH) && '@3xl:col-span-2',
        // A child table needs air. It is the one control that is not a box on a
        // line — it has a header row, its own rows, an Add button and a delete
        // per row — and at the section's ordinary 20px rhythm it butted against
        // the single-line fields either side of it, so the eye read the field
        // above as part of the table's heading. The margin is on the ROW, so it
        // applies in view mode and edit mode alike: a table is just as much a
        // block of its own when it is read as when it is filled in.
        field.type === 'childlist' && 'my-4',
        className
      )}
    >
      {/*
        ONE INLINE FLOW: label, then the asterisk, then the hint icon.

        This was a `flex flex-wrap` row with the Label, the icon and two status
        chips as siblings, and it broke in two ways a reader could see:

          * THE ICON WRAPPED ONTO ITS OWN LINE. Any label too long for the
            column pushed the icon to the next row, so "Suite Demonstrated"
            carried its hint underneath while "Demo Date" carried it beside —
            the same control, two different shapes, decided by label length.

          * THE ASTERISK MOVED. `Label` is itself `flex items-center`, so on a
            two-line label the text became one flex item and the asterisk
            another, and the asterisk centred itself vertically beside the
            block — floating at the end of line one of "Pilot Commercial
            Model" rather than following the word "Model".

        Inline, with no whitespace between them in the source, the three are one
        unbreakable unit: the asterisk is always the character after the last
        letter of the label and the icon is always the glyph after that,
        wherever the text happens to wrap. The Hint stays OUTSIDE the Label —
        it is a button, and a button inside a <label> would focus the field on
        click instead of opening the tooltip.

        The "conditional?" and "proposed shape" chips that used to sit here are
        gone from the FORM. Neither was addressed to the BD user reading the
        record — one flagged a register row marked Conditional with no condition
        stated, the other a childlist whose columns were inferred rather than
        read — and both are still reported, in full and with their basis, on
        Spec Health, which is the screen for exactly that audience. Nothing
        about the underlying data changed: requirementOf still returns
        `unruled`, and childSpecFor still carries `origin: 'inferred'`.
      */}
      <div className="text-label leading-snug @lg:pt-2 @lg:text-right">
        {/* `inline` beats Label's own `flex` through tailwind-merge, which is
            what stops the asterisk becoming a flex sibling that centres itself
            against a two-line label. `leading-snug` beats its `leading-none`,
            so a label that does wrap has lines that are readable rather than
            touching. */}
        <Label htmlFor={id} className="inline leading-snug text-muted-foreground">
          {field.label}
          {required && (
            <span className="text-destructive" aria-hidden>
              *
            </span>
          )}
        </Label>
        {/* The prose formula from the register, never the executable one — a
            reviewer should see the business statement they wrote.

            Where the sidecar carries a `note`, it follows underneath. That is
            how partners.exclusivity_expiry_date shows the register's own
            "Start date plus 90 days" next to the reason the engine computes 89:
            a reviewer needs to see both, not be quietly shown the corrected
            one. */}
        {field.computed_formula ? (
          <Hint>
            <span className="font-medium">Formula</span>
            <br />
            {field.computed_formula}
            {field.note && (
              <>
                <br />
                <br />
                <span className="font-medium">Prototype note</span>
                <br />
                {field.note}
              </>
            )}
          </Hint>
        ) : (
          field.description && <Hint>{field.description}</Hint>
        )}
      </div>

      {/* One cell, so the control and everything it has to say about itself
          stay in the value column rather than each becoming a grid row. */}
      <div className="min-w-0 space-y-1.5">
        <FieldControl field={field} onCreateNew={onCreateNew} />

        {error && <p className="text-xs text-destructive">{error}</p>}
        {missing && <p className="text-xs text-destructive">{missing}</p>}

        {!error && !missing && form.mode === 'edit' && field.computed_formula && field.description && (
          <p className="text-xs text-muted-foreground">{field.description}</p>
        )}
      </div>
    </div>
  )
}

/**
 * The hint glyph, beside the label and never under it.
 *
 * `inline` with `align-middle` and a leading hair of margin rather than a gap:
 * a flex gap would need a flex parent, and a flex parent is what used to let
 * the icon wrap onto a line of its own. ml-1 is margin, not a space character,
 * so the icon cannot be pushed to the next line away from the asterisk.
 */
function Hint({ children }: { children: React.ReactNode }) {
  return (
    <Tooltip>
      <TooltipTrigger
        type="button"
        className="ml-1 inline cursor-help align-middle text-muted-foreground"
      >
        <InfoIcon className="inline size-3.5 align-middle" />
      </TooltipTrigger>
      <TooltipContent className="max-w-xs">{children}</TooltipContent>
    </Tooltip>
  )
}
