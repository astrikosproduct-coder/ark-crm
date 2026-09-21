import { Notice } from '@/components/ui/notice'
import { fieldsOf } from '@/lib/spec'
import type { Values } from '@/lib/spec/conditions'
import { missingDue } from '@/lib/spec/validation'
import type { FieldSpec } from '@/types/field'

/**
 * The required fields a forward move is waiting on — layer 1 of the four-layer
 * check, enforced since 21 Sep 2026.
 *
 * Leaving a stage needs its own required fields, and every earlier stage's,
 * filled in. The stage being entered asks for its fields once the record is
 * there. The server refuses the same move (backend/app/requirements.py); this
 * says so first, and each name jumps to the field.
 */
export function requiredBeforeMove(
  module: string,
  values: Values,
  from: number,
  to: number,
  skipped: readonly number[] = []
): FieldSpec[] {
  if (to <= from) return []
  const missing = missingDue(module, values, { atStage: from, skipped })
  return fieldsOf(module).filter((f) => f.api_name in missing)
}

export function RequiredBeforeMove({
  fields,
  from,
  onJumpToField,
}: {
  fields: FieldSpec[]
  from: number
  onJumpToField?: (field: FieldSpec) => void
}) {
  if (fields.length === 0) return null
  return (
    <Notice
      tone="error"
      boxed
      lead={`Fill in ${fields.length === 1 ? 'this required field' : `these ${fields.length} required fields`} before leaving Stage ${from}:`}
      bullets={fields.map((field) =>
        onJumpToField ? (
          <button
            key={field.api_name}
            type="button"
            className="text-left underline underline-offset-2"
            onClick={() => onJumpToField(field)}
          >
            {field.label}
          </button>
        ) : (
          field.label
        )
      )}
    />
  )
}
