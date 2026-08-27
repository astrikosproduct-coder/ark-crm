import { InfoIcon } from 'lucide-react'

import { Label } from '@/components/ui/label'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { FieldControl } from '@/components/form/FieldControl'
import { useRecordForm } from '@/hooks/useRecordForm'
import { childSpecFor } from '@/lib/spec/childSpec'
import { cn } from '@/lib/utils'
import type { FieldSpec } from '@/types/field'

interface Props {
  field: FieldSpec
  onCreateNew?: (field: FieldSpec) => void
}

/** Types that own the full width of the section grid. */
export const FULL_WIDTH = new Set(['childlist', 'richtext', 'longtext'])

export function FieldRow({ field, onCreateNew }: Props) {
  const form = useRecordForm()
  const id = `${field.module}.${field.api_name}`
  const error = form.visibleErrors[field.api_name]
  // Shown only when the value is not ALSO malformed — "Must be a date" and
  // "This is a required field." on the same field would be one message too many,
  // and the shape error is the more specific of the two.
  const missing = !error ? form.visibleRequired[field.api_name] : undefined
  const required = form.isRequired(field)
  const unruled = form.isUnruled(field)
  // A childlist whose row shape was derived rather than read out of the
  // register. The chip goes here, on the ONE label row every field owns —
  // which is also where the comment pin goes, so a reviewer who disagrees with
  // the columns leaves the note on the same target they are looking at.
  const childSpec = childSpecFor(field)
  const proposed = childSpec?.origin === 'inferred' ? childSpec : null

  return (
    <div className={cn('flex flex-col gap-1.5', FULL_WIDTH.has(field.type) && 'md:col-span-2')}>
      <div className="flex items-center gap-1.5">
        <Label htmlFor={id} className="text-foreground">
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
        {field.computed_formula && (
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
        )}

        {!field.computed_formula && field.description && <Hint>{field.description}</Hint>}

        {unruled && (
          <Tooltip>
            <TooltipTrigger type="button" className="cursor-help text-amber-600 dark:text-amber-400">
              <span className="text-xs">conditional?</span>
            </TooltipTrigger>
            <TooltipContent className="max-w-xs">
              Marked Conditional in the register, but no condition is stated. Treated as
              optional — see Spec Health.
            </TooltipContent>
          </Tooltip>
        )}

        {proposed && (
          <Tooltip>
            <TooltipTrigger
              type="button"
              className="cursor-help rounded border border-amber-500/50 bg-amber-500/10 px-1.5 py-0.5 text-[11px] leading-none text-amber-700 dark:text-amber-400"
            >
              proposed shape
            </TooltipTrigger>
            <TooltipContent className="max-w-sm">
              <p className="font-medium">These columns are a proposal, not the register.</p>
              <p className="mt-1">{proposed.basis ?? 'No basis recorded in spec/extensions.json.'}</p>
              <p className="mt-1 text-muted-foreground">
                Still listed as an open question on Spec Health. Correct the columns here.
              </p>
            </TooltipContent>
          </Tooltip>
        )}
      </div>

      <FieldControl field={field} onCreateNew={onCreateNew} />

      {error && <p className="text-xs text-destructive">{error}</p>}
      {missing && <p className="text-xs text-destructive">{missing}</p>}

      {!error && !missing && form.mode === 'edit' && field.computed_formula && field.description && (
        <p className="text-xs text-muted-foreground">{field.description}</p>
      )}
    </div>
  )
}

function Hint({ children }: { children: React.ReactNode }) {
  return (
    <Tooltip>
      <TooltipTrigger type="button" className="cursor-help text-muted-foreground">
        <InfoIcon className="size-3.5" />
      </TooltipTrigger>
      <TooltipContent className="max-w-xs">{children}</TooltipContent>
    </Tooltip>
  )
}
